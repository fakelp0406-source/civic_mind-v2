"""Stage 2F: evaluate the router *through the HTTP API* (``POST /api/v1/query``).

Usage: ``python eval/api_metrics.py`` -> ``eval/reports/api.v1.results.{json,md}``.
The stage 2E (``rag.v1.*``) and stage 2D (``route.v1.*``) reports are read, never written.

Three separate measurements (fixed before results were seen; nothing is tuned):

1. **Deterministic regression** (software compatibility). Every question of
   ``coverage.v1``, ``pipeline.v1`` and the ``rag.v1`` analytics items is sent to two apps on the
   same data: documents enabled (default) and ``documents=False`` (the deterministic API). A
   response without ``route`` must equal the deterministic one exactly (request id aside); a
   response with ``route`` must be a refusal whose remaining fields equal the deterministic
   refusal. HTTP statuses must match.
2. **Frozen rag.v1 labels through the API** (answer quality on this small set). Same SHA-256
   check, split and scoring as ``eval/route_metrics.py`` (BM25 gate, calibrated thresholds):
   supported items are correct only with a citation on a gold page; abstain items only if
   refused; analytics items only if unrouted and identical to the deterministic API. The API's
   outcome per item is also compared with the frozen stage 2D ``bm25@calibrated`` row (route,
   status, code, cited pages): any difference is an integration defect.
3. **Leakage and latency.** Every citation is checked against the approved corpus (document,
   allowed edition, page indexed and neither excluded nor textless). Cold start is the time of
   ``create_app`` (full index verification); warm latency is per request, by route kind.
   Latency is machine-dependent and reported apart from the metrics above.

The label set is small (65 items) and single-labeller; rates describe this set only.

Reproducibility (``reproducibility`` in the JSON; deterministic, no timestamps):

* ``source_fingerprint``: SHA-256 over a ``sha256sum``-style listing (``<sha256>  <path>``,
  sorted by path) of every file in ``FINGERPRINT_GLOBS``: all package modules
  (``src/civicmind/**/*.py``) and the three evaluation scripts. Each file is hashed with CRLF
  normalised to LF, the form Git stores (``* text=auto eol=lf``), so the value does not depend
  on a checkout's line endings. It identifies the evaluated code without a commit hash (the
  report is generated before its commit). Generated reports are never inputs (no circularity).
* ``inputs``: raw-byte SHA-256 of the question sets and the frozen stage 2D/2E reports read.
* ``retrieval``, ``index``: the live router configuration and the verified index manifest.
* ``documents``, ``datasets``: every document manifest (status, edition, hashes, exclusions)
  and every promoted dataset (data SHA-256 from its manifest), each with its manifest's hash.
* ``runtime``: installed versions read from the interpreter and package metadata.

``performance`` (machine-dependent) carries the generation timestamp and machine description.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import sqlite3
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "eval/reports"
FROZEN_SHA = "3abd425762429179869390ef744f08a65eee4f8783c9234f6e87e93271d3e85f"
REGRESSION_SETS = ("eval/questions/coverage.v1.yaml", "eval/questions/pipeline.v1.yaml")
QUERY = "/api/v1/query"
#: Files whose bytes define the evaluated behaviour (see the module docstring).
FINGERPRINT_GLOBS = (
    "src/civicmind/**/*.py",
    "eval/api_metrics.py",
    "eval/rag_metrics.py",
    "eval/route_metrics.py",
)
#: Inputs read by this evaluation, hashed as raw bytes (the frozen label hash uses raw bytes).
INPUT_FILES = (
    "eval/questions/rag.v1.yaml",
    *REGRESSION_SETS,
    "eval/reports/route.v1.results.json",
    "eval/reports/rag.v1.results.json",
    "docs/acquisition/docs-01/DOCUMENT_REVIEW_DECISIONS.yaml",
)
#: Distributions whose installed version is recorded (``unavailable`` if not installed).
RUNTIME_DISTRIBUTIONS = (
    "fastapi", "starlette", "pydantic", "PyYAML", "numpy", "pandas", "httpx", "pypdf",
    "onnxruntime", "tokenizers",
)  # fmt: skip


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"eval/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


def _strip(body: dict) -> dict:
    """The body without its per-request id (top level, or inside an error envelope)."""
    out = {k: v for k, v in body.items() if k != "request_id"}
    if isinstance(out.get("error"), dict):
        out["error"] = {k: v for k, v in out["error"].items() if k != "request_id"}
    return out


def kind_of(body: dict) -> str:
    if "error" in body:  # request rejected before the pipeline (e.g. 422 for a blank question)
        return "request_error"
    if body.get("route"):
        return body["route"]["kind"]
    return "analytics" if body["status"] == "answered" else "refused"


def code_of(body: dict) -> str | None:
    if "error" in body:
        return body["error"]["code"]
    if body.get("route"):
        return body["route"]["code"]
    return (body.get("refusal") or {}).get("code")


def status_of(body: dict) -> str:
    return "request_error" if "error" in body else body["status"]


def compare(routed, plain) -> str:
    """identical | routed_refusal_compatible | mismatch."""
    a, b = routed.json(), plain.json()
    if routed.status_code != plain.status_code:
        return "mismatch"
    if "route" not in a:
        return "identical" if _strip(a) == _strip(b) else "mismatch"
    rest = {k: v for k, v in _strip(a).items() if k not in ("route", "citations")}
    ok = a["status"] == "refused" and rest == _strip(b)
    return "routed_refusal_compatible" if ok else "mismatch"


def leakage(body: dict, corpus) -> list[str]:
    """Citations that the approved corpus does not allow (must be empty)."""
    docs = {d.document_id: d for d in corpus.documents}
    allowed = set((body.get("route") or {}).get("editions") or [])
    cits = list(body.get("citations") or [])
    for part in (body.get("route") or {}).get("parts") or []:
        cits += part.get("citations") or []
    problems = []
    for c in cits:
        d = docs.get(c["document_id"])
        where = f"{c['document_id']}:p{c['page']}"
        if d is None:
            problems.append(f"{where} not an approved corpus document")
        elif c["page"] not in d.pages_indexed:
            problems.append(f"{where} page not indexed")
        elif c["page"] in d.excluded_pages or c["page"] in d.no_text_pages:
            problems.append(f"{where} excluded or textless page")
        elif allowed and d.edition not in allowed and not body["route"]["parts"]:
            problems.append(f"{where} edition {d.edition} outside {sorted(allowed)}")
    return problems


def text_sha256(path: Path) -> str:
    """SHA-256 of a text file as Git stores it (CRLF normalised to LF)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fingerprint(root: Path) -> dict:
    """Combined and per-file SHA-256 of ``FINGERPRINT_GLOBS`` (reports are never included)."""
    files = sorted(
        {
            p.relative_to(root).as_posix()
            for pattern in FINGERPRINT_GLOBS
            for p in root.glob(pattern)
            if p.is_file() and "__pycache__" not in p.parts
        }
    )
    per_file = {f: text_sha256(root / f) for f in files}
    listing = "".join(f"{digest}  {name}\n" for name, digest in per_file.items())
    return {
        "sha256": hashlib.sha256(listing.encode("utf-8")).hexdigest(),
        "files": len(files),
        "scope": list(FINGERPRINT_GLOBS),
        "method": "sha256 of '<sha256>  <path>' lines sorted by path; each file hashed with "
        "CRLF normalised to LF (the form Git stores)",
        "file_sha256": per_file,
    }


def runtime_versions() -> dict:
    out = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "sqlite": sqlite3.sqlite_version,
    }
    for dist in RUNTIME_DISTRIBUTIONS:
        try:
            out[dist] = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            out[dist] = "unavailable: not installed"
    try:
        from civicmind import __version__

        out["civicmind"] = __version__
    except ImportError:  # pragma: no cover - the package is always importable here
        out["civicmind"] = "unavailable"
    return out


def reproducibility(root: Path, retrieval) -> dict:
    """Deterministic description of what was evaluated (no timestamps, no timings)."""
    from civicmind.catalog.documents import read_document_manifests
    from civicmind.catalog.manifest import read_manifest

    router = retrieval.router
    index = router.index
    cfg = router.config
    manifest = index.manifest
    embedding = manifest.get("embedding") or {}
    eligible = {d.document_id for d in index.corpus.documents}
    documents = []
    for m in read_document_manifests(root):
        documents.append(
            {
                "document_id": m.document_id,
                "status": m.status,
                "edition": m.edition,
                "eligible": m.document_id in eligible,
                "sha256": m.integrity.sha256 if m.integrity else None,
                "extraction_sha256": m.extraction.output_sha256 if m.extraction else None,
                "excluded_pages": list(m.review.excluded_pages) if m.review else [],
                "manifest_sha256": text_sha256(root / f"data/doc_manifests/{m.document_id}.yaml"),
            }
        )
    paths = sorted((root / "data/manifests").glob("*.yaml"))
    promoted = []
    for path in paths:
        m = read_manifest(path)
        if m.status == "promoted":
            promoted.append(
                {
                    "dataset_id": m.dataset_id,
                    "sha256": m.integrity.sha256,
                    "manifest_sha256": text_sha256(path),
                }
            )
    listing = "".join(f"{text_sha256(p)}  {p.relative_to(root).as_posix()}\n" for p in paths)
    return {
        "source_fingerprint": source_fingerprint(root),
        "inputs": {rel: raw_sha256(root / rel) for rel in INPUT_FILES},
        "retrieval": {
            "gate": cfg.gate,
            "threshold": cfg.retrieval.threshold(cfg.gate),
            "k": cfg.retrieval.k,
            "candidate_pool": cfg.retrieval.candidate_pool,
            "bm25_min_score": cfg.retrieval.bm25_min_score,
            "dense_min_score": cfg.retrieval.dense_min_score,
            "dense_used": False,  # the API serves the BM25 gate only; no encoder is loaded
        },
        "index": {
            "index_id": index.index_id,
            "index_version": manifest.get("index_version"),
            "corpus_digest": manifest.get("corpus_digest"),
            "chunks": manifest.get("chunks"),
            "chunker": manifest.get("chunker"),
            "screen": manifest.get("screen"),
            "bm25": manifest.get("bm25"),
            "embedding": {
                k: embedding.get(k) for k in ("model_id", "revision", "files", "dim", "runtime")
            },
            "files_sha256": manifest.get("files"),
        },
        "documents": documents,
        "datasets": {
            "manifests": len(paths),
            "manifests_digest": hashlib.sha256(listing.encode("utf-8")).hexdigest(),
            "promoted": promoted,
        },
        "runtime": runtime_versions(),
    }


def _timed(client, question):
    started = time.perf_counter()
    r = client.post(QUERY, json={"question": question})
    return r, (time.perf_counter() - started) * 1000


def evaluate() -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from fastapi.testclient import TestClient

    from civicmind.api.app import create_app

    rm, route_m = _load("rag_metrics"), _load("route_metrics")
    items, sha = rm.load_labels()
    if sha != FROZEN_SHA:
        raise SystemExit(f"labels changed: {sha} != frozen {FROZEN_SHA}")
    parts = rm.split(items)
    frozen_d = json.loads((REPORTS / "route.v1.results.json").read_text(encoding="utf-8"))
    frozen_rows = frozen_d["routers"]["bm25@calibrated"]["per_item"]

    started = time.perf_counter()
    app = create_app(ROOT)
    cold_start_s = time.perf_counter() - started
    state = app.state.retrieval.status()
    if state.status != "ready":
        raise SystemExit(f"document retrieval is not ready: {state.code}")
    corpus = app.state.retrieval.router.index.corpus
    meta = reproducibility(ROOT, app.state.retrieval)
    api = TestClient(app, raise_server_exceptions=False)
    plain = TestClient(create_app(ROOT, documents=False), raise_server_exceptions=False)
    latency: dict[str, list[float]] = {}

    # 1. deterministic regression
    regression = {}
    questions = []
    for rel in REGRESSION_SETS:
        data = yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))
        questions += [(f"{Path(rel).stem}:{i['id']}", i["question"]) for i in data["items"]]
    questions += [
        (f"rag.v1:{i['id']}", i["question"]) for i in items if i["expect"] == "deterministic"
    ]
    for key, q in questions:
        r, ms = _timed(api, q)
        body = r.json()
        latency.setdefault(kind_of(body), []).append(ms)
        regression[key] = {
            "outcome": compare(r, plain.post(QUERY, json={"question": q})),
            "http": r.status_code,
            "status": status_of(body),
            "refusal_code": (body.get("refusal") or {}).get("code"),
            "route_code": (body.get("route") or {}).get("code"),
        }

    # 2. frozen labels through the API
    rows, agreement, leaks = {}, {}, {}
    for item in items:
        r, ms = _timed(api, item["question"])
        body = r.json()
        latency.setdefault(kind_of(body), []).append(ms)
        cited = [f"{c['document_id']}:p{c['page']}" for c in body.get("citations") or []]
        outcome = score_body(rm, item, body, plain)
        rows[item["id"]] = {
            "route": kind_of(body),
            "status": status_of(body),
            "code": code_of(body),
            "http": r.status_code,
            "citations": cited,
            "outcome": outcome,
        }
        f = frozen_rows[item["id"]]
        same = (f["route"], f["status"], f["code"], f["citations"]) == (
            kind_of(body), status_of(body), code_of(body), cited
        )  # fmt: skip
        agreement[item["id"]] = same
        if problems := leakage(body, corpus):
            leaks[item["id"]] = problems

    cal = [i for i in items if parts[i["id"]] == "calibration"]
    test = [i for i in items if parts[i["id"]] == "test"]
    reg_counts = Counter(r["outcome"] for r in regression.values())

    def pct(values, q):
        values = sorted(values)
        return round(values[min(len(values) - 1, int(q * len(values)))], 1)

    return {
        "labels": {
            "path": "eval/questions/rag.v1.yaml",
            "sha256": sha,
            "items": len(items),
            "split": {"calibration": len(cal), "test": len(test)},
        },
        "retrieval": state.model_dump(),
        "reproducibility": meta,
        "deterministic_regression": {
            "questions": len(regression),
            "outcomes": dict(sorted(reg_counts.items())),
            "mismatches": sorted(k for k, r in regression.items() if r["outcome"] == "mismatch"),
            "routed_refusals": {
                k: {"refusal_code": r["refusal_code"], "route_code": r["route_code"]}
                for k, r in regression.items()
                if r["outcome"] == "routed_refusal_compatible"
            },
            "answered_identical": sum(
                r["status"] == "answered" and r["outcome"] == "identical"
                for r in regression.values()
            ),
            "answered": sum(r["status"] == "answered" for r in regression.values()),
        },
        "frozen_labels": {
            "calibration": route_m.summarise(rows, cal),
            "test": route_m.summarise(rows, test),
            "all": route_m.summarise(rows, items),
            "by_category": route_m.by_category(rows, items),
            "agreement_with_stage_2d": {
                "items": len(agreement),
                "same": sum(agreement.values()),
                "different": sorted(k for k, v in agreement.items() if not v),
            },
            "per_item": rows,
        },
        "leakage": {
            "items_with_ineligible_citations": leaks,
            "citations_checked": sum(len(r["citations"]) for r in rows.values()),
        },
        "performance": {  # machine-dependent; the only non-deterministic part of the report
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "machine": {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "cpu_count": os.cpu_count(),
            },
            "cold_start_s": round(cold_start_s, 2),
            "warm_ms_by_route": {
                k: {"n": len(v), "p50": round(statistics.median(v), 1), "p95": pct(v, 0.95)}
                for k, v in sorted(latency.items())
            },
        },
    }


def score_body(rm, item: dict, body: dict, plain) -> str:
    """route_metrics.score, applied to an HTTP response body."""
    expect = item["expect"]
    if expect == "answer":
        if status_of(body) != "answered":
            return "abstained"
        gold = rm.gold_set(item)
        cited = {(c["document_id"], c["page"]) for c in body.get("citations") or []}
        return "correct" if cited & gold else "unsupported_answer"
    if expect == "abstain":
        refused = status_of(body) in ("refused", "request_error")
        return "correct" if refused else "unsupported_answer"
    if expect == "deterministic":
        same = "route" not in body and _strip(body) == _strip(
            plain.post(QUERY, json={"question": item["question"]}).json()
        )
        return "correct" if same else "wrong_route"
    return "unscored"


def setup_markdown(meta: dict) -> list[str]:
    """The deterministic evaluation setup (everything in ``reproducibility``)."""
    fp, ret, idx = meta["source_fingerprint"], meta["retrieval"], meta["index"]
    ds, emb = meta["datasets"], meta["index"]["embedding"]
    lines = [
        "## Evaluation setup (deterministic)",
        "",
        f"- **Source fingerprint** `{fp['sha256']}`: {fp['files']} files "
        f"({', '.join(f'`{g}`' for g in fp['scope'])}); {fp['method']}. It identifies the "
        "evaluated code without a commit hash; generated reports are never included. "
        "Per-file hashes are in the JSON.",
        f"- **Retrieval**: gate `{ret['gate']}`, threshold {ret['threshold']} "
        f"(BM25, stage 2E calibrated), k {ret['k']}, candidate pool {ret['candidate_pool']}; "
        "dense retrieval not used.",
        f"- **Index** `{idx['index_id']}` ({idx['index_version']}), corpus digest "
        f"`{idx['corpus_digest']}`, {idx['chunks']} chunks; chunker {idx['chunker']}; "
        f"screen `{idx['screen']}`; vectors built with `{emb['model_id']}@{emb['revision']}`, "
        f"runtime {emb['runtime']} (not loaded by the API).",
        f"- **Datasets**: {len(ds['promoted'])} promoted of {ds['manifests']} manifests; "
        f"manifests digest `{ds['manifests_digest']}`.",
        "",
        "| Document | Status | Edition | Eligible | Source SHA-256 | Excluded pages |",
        "|---|---|---|---|---|---|",
    ]
    for d in meta["documents"]:
        sha = f"`{d['sha256'][:16]}...`" if d["sha256"] else "n/a"
        lines.append(
            f"| {d['document_id']} | {d['status']} | {d['edition'] or 'n/a'} | "
            f"{'yes' if d['eligible'] else 'no'} | {sha} | {d['excluded_pages'] or 'none'} |"
        )
    lines += ["", "Inputs (raw-byte SHA-256):", ""]
    lines += [f"- `{path}`: `{digest}`" for path, digest in meta["inputs"].items()]
    lines += ["", "Runtime: " + ", ".join(f"{k} {v}" for k, v in meta["runtime"].items()), ""]
    return lines


def to_markdown(r: dict) -> str:
    reg, fl, perf = r["deterministic_regression"], r["frozen_labels"], r["performance"]
    lines = [
        "# API integration evaluation, api.v1 (generated by eval/api_metrics.py)",
        "",
        f"Index `{r['retrieval']['index_id']}` ({r['retrieval']['chunks']} chunks; documents "
        f"{', '.join(r['retrieval']['documents'])}), BM25 gate, stage 2E calibrated thresholds "
        f"(unchanged). Frozen labels `{r['labels']['path']}` (SHA-256 "
        f"`{r['labels']['sha256'][:16]}...`), {r['labels']['items']} items, split "
        f"{r['labels']['split']}.",
        "",
        "A small, single-labeller set: results describe this set only. Software tests, "
        "retrieval metrics (stage 2E) and these answer-level measurements are separate.",
        "",
        *setup_markdown(r["reproducibility"]),
        "## 1. Deterministic regression (documents on vs. deterministic-only API)",
        "",
        f"- Questions: {reg['questions']} (coverage.v1, pipeline.v1, rag.v1 analytics items)",
        f"- Outcomes: {reg['outcomes']}",
        f"- Answered and byte-identical: {reg['answered_identical']}/{reg['answered']}",
        f"- Mismatches: {reg['mismatches'] or 'none'}",
        "",
        "Refusals where the router also tried documents (refusal code kept; router code added):",
        "",
        "| Item | refusal.code (deterministic) | route.code |",
        "|---|---|---|",
    ]
    for k, v in reg["routed_refusals"].items():
        lines.append(f"| {k} | `{v['refusal_code']}` | `{v['route_code']}` |")
    lines += [
        "",
        "## 2. Frozen rag.v1 labels through the API",
        "",
        "| Split | Evidence-supported (supported) | Supported answered | Abstain rate "
        "| Analytics identical | Unsupported answers |",
        "|---|---|---|---|---|---|",
    ]
    for split in ("calibration", "test", "all"):
        s = fl[split]
        lines.append(
            f"| {split} | {s['evidence_supported_rate']} | "
            f"{s['supported_answered']}/{s['supported_items']} | {s['abstain_rate']} "
            f"({s['abstain_items']} items) | {s['analytics_identical_rate']} "
            f"({s['analytics_items']} items) | {s['unsupported_answers']} |"
        )
    ag = fl["agreement_with_stage_2d"]
    lines += [
        "",
        f"Agreement with the frozen stage 2D router (`bm25@calibrated`: route, status, code, "
        f"cited pages): {ag['same']}/{ag['items']}; different: {ag['different'] or 'none'}.",
        "",
        "| Category | Items | Outcomes | Routes | Codes |",
        "|---|---|---|---|---|",
    ]
    for cat, x in fl["by_category"].items():
        lines.append(f"| {cat} | {x['items']} | {x['outcomes']} | {x['routes']} | {x['codes']} |")
    leak = r["leakage"]
    lines += [
        "",
        "## 3. Leakage",
        "",
        f"Citations checked: {leak['citations_checked']}. Ineligible citations (unapproved "
        f"document, excluded/textless page, edition outside the restriction): "
        f"{leak['items_with_ineligible_citations'] or 'none'}.",
        "",
        "## Performance (this machine; not a metric of answer quality)",
        "",
        f"Generated {perf['generated_at_utc']} on {perf['machine']['platform']} "
        f"({perf['machine']['machine']}, {perf['machine']['cpu_count']} logical CPUs). Timings "
        "vary from run to run and across machines; they are not covered by the source "
        "fingerprint, and the requests run sequentially through an in-process test client "
        "(no network, no concurrency).",
        "",
        f"- Cold start (`create_app`, full index verification): {perf['cold_start_s']} s",
        "- Warm request latency by route (ms; includes the deterministic pipeline, which "
        "re-verifies dataset hashes on every query):",
        "",
        "| Route | n | p50 | p95 |",
        "|---|---|---|---|",
    ]
    for k, v in perf["warm_ms_by_route"].items():
        lines.append(f"| {k} | {v['n']} | {v['p50']} | {v['p95']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    report = evaluate()
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "api.v1.results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (REPORTS / "api.v1.results.md").write_text(to_markdown(report), encoding="utf-8", newline="\n")
    print(to_markdown(report))


if __name__ == "__main__":
    main()
