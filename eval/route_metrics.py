"""Evaluate the stage 2D router on the frozen rag.v1 labels (routing and edition guards).

Usage: ``python eval/route_metrics.py`` -> ``eval/reports/route.v1.results.{json,md}``.
The stage 2E outputs (``rag.v1.*``) are not touched.

Method (fixed before results were seen):

* Same frozen labels (SHA-256 checked) and the same calibration/test split as stage 2E.
* Thresholds are **not** re-tuned: the router uses the stage 2E calibrated thresholds; the stage
  2C provisional thresholds are reported only as a comparison row.
* Two gates (``bm25``, ``dense``) are run; the gate is **chosen on the calibration split** by
  balanced accuracy (evidence-supported document answers on supported items, refusals on items
  that expect abstention), ties broken by fewer unsupported answers, then BM25.
* Scoring per item: *supported* items are correct only if answered with a citation on a gold page;
  an answer without one is an unsupported answer. Items expecting abstention are correct if
  refused. Analytics items are correct only if routed to analytics and identical to the
  deterministic pipeline's answer. Composite items are reported, not scored (their labels predate
  the router and carry no gold pages).
"""

from __future__ import annotations

import functools
import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "eval/reports"
FROZEN_SHA = "3abd425762429179869390ef744f08a65eee4f8783c9234f6e87e93271d3e85f"
PROVISIONAL = {"bm25": 4.0, "dense": 0.45}

_spec = importlib.util.spec_from_file_location("rag_metrics", ROOT / "eval/rag_metrics.py")
rm = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("rag_metrics", rm)
_spec.loader.exec_module(rm)


def score(item: dict, routed, deterministic: dict | None) -> str:
    """One of: correct, unsupported_answer, abstained, wrong_route, unscored."""
    expect = item["expect"]
    if expect == "answer":
        if routed.status != "answered":
            return "abstained"
        gold = rm.gold_set(item)
        on_gold = any((c["document_id"], c["page"]) in gold for c in routed.citations)
        return "correct" if on_gold else "unsupported_answer"
    if expect == "abstain":
        return "correct" if routed.status == "refused" else "unsupported_answer"
    if expect == "deterministic":
        same = routed.route == "analytics" and routed.analytics == deterministic
        return "correct" if same else "wrong_route"
    return "unscored"


def summarise(rows: dict[str, dict], items: list[dict]) -> dict:
    sup = [i for i in items if i["expect"] == "answer"]
    abst = [i for i in items if i["expect"] == "abstain"]
    ana = [i for i in items if i["expect"] == "deterministic"]

    def count(group, outcome):
        return sum(rows[i["id"]]["outcome"] == outcome for i in group)

    supported_rate = rm._rate(count(sup, "correct"), len(sup))
    abstain_rate = rm._rate(count(abst, "correct"), len(abst))
    unsupported = count(sup, "unsupported_answer") + count(abst, "unsupported_answer")
    return {
        "supported_items": len(sup),
        "evidence_supported_rate": supported_rate,
        "supported_answered": sum(rows[i["id"]]["status"] == "answered" for i in sup),
        "abstain_items": len(abst),
        "abstain_rate": abstain_rate,
        "analytics_items": len(ana),
        "analytics_identical_rate": rm._rate(count(ana, "correct"), len(ana)),
        "unsupported_answers": unsupported,
        "balanced_accuracy": round(((supported_rate or 0) + (abstain_rate or 0)) / 2, 4),
    }


def by_category(rows: dict[str, dict], items: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for item in items:
        row = rows[item["id"]]
        cat = out.setdefault(
            item["category"],
            {"items": 0, "outcomes": Counter(), "routes": Counter(), "codes": Counter()},
        )
        cat["items"] += 1
        cat["outcomes"][row["outcome"]] += 1
        cat["routes"][row["route"]] += 1
        if row["code"]:
            cat["codes"][row["code"]] += 1
    return {
        c: {k: dict(v) if isinstance(v, Counter) else v for k, v in x.items()}
        for c, x in sorted(out.items())
    }


def run_router(router, items, deterministic) -> dict[str, dict]:
    rows = {}
    for item in items:
        started = time.perf_counter()
        r = router.route(item["question"])
        rows[item["id"]] = {
            "route": r.route,
            "status": r.status,
            "code": r.code,
            "editions": list(r.editions),
            "citations": [f"{c['document_id']}:p{c['page']}" for c in r.citations],
            "parts": [{"route": p.route, "status": p.status, "code": p.code} for p in r.parts],
            "outcome": score(item, r, deterministic.get(item["id"])),
            "seconds": round(time.perf_counter() - started, 4),
        }
    return rows


def evaluate() -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from civicmind.orchestrator.pipeline import answer_question
    from civicmind.orchestrator.router import Router, RouterConfig
    from civicmind.rag.embed import MiniLMEncoder
    from civicmind.rag.retrieve import DEFAULT_RETRIEVAL, RetrievalConfig

    items, sha = rm.load_labels()
    if sha != FROZEN_SHA:
        raise SystemExit(f"labels changed: {sha} != frozen {FROZEN_SHA}")
    parts = rm.split(items)
    cal = [i for i in items if parts[i["id"]] == "calibration"]
    test = [i for i in items if parts[i["id"]] == "test"]
    cached = functools.lru_cache(maxsize=None)(lambda q: answer_question(q, ROOT))
    answer_fn = lambda q, root: cached(q)  # noqa: E731 - deterministic, safe to memoise
    deterministic = {
        i["id"]: cached(i["question"]).to_dict() for i in items if i["expect"] == "deterministic"
    }
    encoder = MiniLMEncoder(ROOT)
    configs = {
        "calibrated": DEFAULT_RETRIEVAL,
        "provisional": RetrievalConfig(
            bm25_min_score=PROVISIONAL["bm25"], dense_min_score=PROVISIONAL["dense"]
        ),
    }
    runs, timing = {}, {}
    for label, retrieval in configs.items():
        for gate in ("bm25", "dense"):
            started = time.perf_counter()
            router = Router(
                ROOT,
                RouterConfig(gate=gate, retrieval=retrieval),
                encoder=encoder,
                answer_fn=answer_fn,
            )
            init = time.perf_counter() - started
            rows = run_router(router, items, deterministic)
            runs[f"{gate}@{label}"] = rows
            timing[f"{gate}@{label}"] = {
                "router_init_s": round(init, 2),
                # Deterministic answers are memoised after the first router run, so only the
                # first run's per-question time includes the deterministic pipeline.
                "deterministic_memoised": bool(timing),
            }

    def key(gate):
        s = summarise(runs[f"{gate}@calibrated"], cal)
        return (s["balanced_accuracy"], -s["unsupported_answers"], gate == "bm25")

    chosen = max(("bm25", "dense"), key=key)
    results = {}
    for name, rows in runs.items():
        results[name] = {
            "calibration": summarise(rows, cal),
            "test": summarise(rows, test),
            "all": summarise(rows, items),
            "by_category": by_category(rows, items),
            "per_item": {
                k: {x: v for x, v in row.items() if x != "seconds"} for k, row in rows.items()
            },
        }
    stage_e = json.loads((REPORTS / "rag.v1.results.json").read_text(encoding="utf-8"))
    return {
        "labels": {
            "path": "eval/questions/rag.v1.yaml",
            "sha256": sha,
            "items": len(items),
            "split": {"calibration": len(cal), "test": len(test)},
        },
        "thresholds": {
            "calibrated": {
                "bm25": DEFAULT_RETRIEVAL.bm25_min_score,
                "dense": DEFAULT_RETRIEVAL.dense_min_score,
            },
            "provisional": PROVISIONAL,
        },
        "chosen_gate_on_calibration": chosen,
        "routers": results,
        "stage_e_raw_retrieval_test": {  # for comparison; copied from rag.v1.results.json
            m: stage_e["methods"][m]["at_calibrated"]["test"] for m in ("bm25", "dense")
        },
        "index": stage_e["index"],
        "performance": {  # machine-dependent
            name: {
                **timing[name],
                "p50_route_ms": round(
                    1000 * sorted(r["seconds"] for r in rows.values())[len(rows) // 2], 1
                ),
            }
            for name, rows in runs.items()
        },
    }


def to_markdown(r: dict) -> str:
    lines = [
        "# Router evaluation, route.v1 (generated by eval/route_metrics.py)",
        "",
        f"Frozen labels `{r['labels']['path']}` (SHA-256 `{r['labels']['sha256'][:16]}...`), "
        f"{r['labels']['items']} items, split {r['labels']['split']}. Index "
        f"`{r['index']['index_id']}`. Thresholds: calibrated {r['thresholds']['calibrated']}, "
        f"provisional (comparison only) {r['thresholds']['provisional']}. Gate chosen on the "
        f"calibration split: **{r['chosen_gate_on_calibration']}**.",
        "",
        "A small, single-labeller set: results describe this set only.",
        "",
        "## Summary",
        "",
        "| Router | Split | Evidence-supported (supported) | Supported answered | Abstain rate "
        "| Analytics identical | Unsupported answers | Balanced acc. |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, x in r["routers"].items():
        for part in ("calibration", "test"):
            s = x[part]
            lines.append(
                f"| {name} | {part} | {s['evidence_supported_rate']} | "
                f"{s['supported_answered']}/{s['supported_items']} | {s['abstain_rate']} | "
                f"{s['analytics_identical_rate']} | {s['unsupported_answers']} | "
                f"{s['balanced_accuracy']} |"
            )
    lines += [
        "",
        "## Raw retrieval at the same thresholds (stage 2E, test split)",
        "",
        "| Method | Evidence-supported | Abstain rate | Unsupported answers rate |",
        "|---|---|---|---|",
    ]
    for m, s in r["stage_e_raw_retrieval_test"].items():
        lines.append(
            f"| {m} | {s['evidence_supported_rate']} | {s['abstain_rate']} | "
            f"{s['unsupported_answer_rate']} |"
        )
    for name in (f"{r['chosen_gate_on_calibration']}@calibrated",):
        lines += [
            "",
            f"## Per-category outcomes ({name}, all items)",
            "",
            "| Category | Items | Outcomes | Routes | Codes |",
            "|---|---|---|---|---|",
        ]
        for cat, x in r["routers"][name]["by_category"].items():
            lines.append(
                f"| {cat} | {x['items']} | {x['outcomes']} | {x['routes']} | {x['codes']} |"
            )
        lines += ["", "Composite items (not scored):", ""]
        for item_id, row in r["routers"][name]["per_item"].items():
            if item_id.startswith("C"):
                lines.append(f"- {item_id}: {row['route']} / {row['code']}; parts {row['parts']}")
    lines += [
        "",
        "## Performance (this machine)",
        "",
        "Rows marked `deterministic_memoised` reuse the deterministic answers of the first "
        "run, so their per-question time covers routing and retrieval only.",
        "",
        f"{r['performance']}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    report = evaluate()
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "route.v1.results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (REPORTS / "route.v1.results.md").write_text(
        to_markdown(report), encoding="utf-8", newline="\n"
    )
    print(to_markdown(report))


if __name__ == "__main__":
    main()
