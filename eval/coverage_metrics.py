"""Run eval/questions/coverage.v1.yaml through the pipeline and compute research metrics.

Usage (from the repository root):
    .venv-py313/Scripts/python.exe eval/coverage_metrics.py

Metrics (each computed over the items it names; counts are reported with every rate):

* correct_answer_rate     - expected answers that were answered with the expected operation,
                            datasets, value basis and checked values.
* correct_refusal_rate    - expected refusals that were refused with the expected code.
* unsupported_answer_rate - expected refusals that were answered instead (must be 0).
* evidence_completeness   - data answers whose every evidence item is trusted, hash-pinned
                            and used rows (catalogue answers excluded: they cite no data).
* provenance_correctness  - answers whose cited datasets equal the expected ones, in order.
* comparability_violations - answers citing more than one road edition, a non-Annexure-47
                            road table, or a non-trusted dataset (count; must be 0).
* freshness_coverage      - water/road items whose response carries the coverage block with a
                            latest trusted period.

The set is small and fixed; the rates describe this set only, never general accuracy.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / "eval/questions/coverage.v1.yaml"
SHA256 = re.compile(r"[0-9a-f]{64}")


def _get(obj: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        elif isinstance(obj, dict):
            obj = obj[part]
        else:
            raise KeyError(path)
    return obj


def _close(a: Any, b: Any) -> bool:
    if isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(b)))
    return a == b


def check_item(item: dict, answer: Any) -> list[str]:
    """Problems with one answer against its expectation (empty list = correct)."""
    e = item["expect"]
    problems = []
    if answer.status != e["status"]:
        return [f"status {answer.status!r} != {e['status']!r} ({answer.code})"]
    if e["status"] == "refused":
        if answer.code != e["code"]:
            problems.append(f"code {answer.code!r} != {e['code']!r}")
        if answer.value is not None:
            problems.append("a refusal carried a value")
    else:
        if answer.operation != e["operation"]:
            problems.append(f"operation {answer.operation!r} != {e['operation']!r}")
        cited = [ev["dataset_id"] for ev in answer.evidence]
        if cited != e["datasets"]:
            problems.append(f"datasets {cited} != {e['datasets']}")
        if e.get("value_basis") and answer.value_basis != e["value_basis"]:
            problems.append(f"value_basis {answer.value_basis!r} != {e['value_basis']!r}")
        for path, expected in (e.get("checks") or {}).items():
            try:
                actual = _get({"value": answer.value}, path)
            except (KeyError, IndexError, ValueError):
                problems.append(f"{path} missing")
                continue
            if not _close(actual, expected):
                problems.append(f"{path} = {actual!r}, expected {expected!r}")
    for text in e.get("caveat_contains") or ():
        if not any(text in c for c in answer.caveats):
            problems.append(f"no caveat contains {text!r}")
    if item.get("coverage"):
        cov = answer.coverage
        if not cov or not cov.get("latest_trusted_period"):
            problems.append("coverage block missing")
    elif answer.coverage is not None:
        problems.append("unexpected coverage block")
    return problems


def _violates_comparability(answer: Any, statuses: dict[str, str]) -> bool:
    ids = [ev["dataset_id"] for ev in answer.evidence]
    roads = [i for i in ids if i.startswith("ROAD-")]
    editions = {i[7:11] for i in roads}
    return (
        len(editions) > 1
        or any(not i.endswith("-A47") for i in roads)
        or any(statuses.get(i) != "promoted" for i in ids)
        or any(ev["mode"] != "trusted" for ev in answer.evidence)
    )


def _complete(answer: Any) -> bool:
    return bool(answer.evidence) and all(
        SHA256.fullmatch(ev["sha256"]) and ev["mode"] == "trusted" and ev["rows_used"] > 0
        and ev["schema_version"] and ev["columns"]
        for ev in answer.evidence
    )  # fmt: skip


def _rate(num: int, den: int) -> dict:
    return {"rate": round(num / den, 4) if den else None, "count": num, "of": den}


def evaluate(root: Path = ROOT) -> dict:
    sys.path.insert(0, str(root / "src"))
    from civicmind.catalog.manifest import read_manifest
    from civicmind.orchestrator.pipeline import answer_question

    items = yaml.safe_load(SET.read_text("utf-8"))["items"]
    statuses = {
        m.dataset_id: m.status
        for m in map(read_manifest, sorted((root / "data/manifests").glob("*.yaml")))
    }
    results = []
    for item in items:
        answer = answer_question(item["question"], root)
        results.append((item, answer, check_item(item, answer)))
    exp_ans = [(i, a, p) for i, a, p in results if i["expect"]["status"] == "answered"]
    exp_ref = [(i, a, p) for i, a, p in results if i["expect"]["status"] == "refused"]
    answered = [(i, a) for i, a, _ in results if a.status == "answered"]
    data_answers = [(i, a) for i, a in answered if a.operation != "data_coverage"]
    with_datasets = [(i, a) for i, a in answered if "datasets" in i["expect"]]
    domain_items = [(i, a) for i, a, _ in results if i.get("coverage")]
    by_class: dict[str, dict] = {}
    for item, _, problems in results:
        row = by_class.setdefault(item["class"], {"items": 0, "correct": 0})
        row["items"] += 1
        row["correct"] += not problems
    return {
        "set": str(SET.relative_to(root)).replace("\\", "/"),
        "items": len(items),
        "correct_answer_rate": _rate(sum(not p for _, _, p in exp_ans), len(exp_ans)),
        "correct_refusal_rate": _rate(sum(not p for _, _, p in exp_ref), len(exp_ref)),
        "unsupported_answer_rate": _rate(
            sum(a.status == "answered" for _, a, _ in exp_ref), len(exp_ref)
        ),
        "evidence_completeness": _rate(
            sum(_complete(a) for _, a in data_answers), len(data_answers)
        ),
        "provenance_correctness": _rate(
            sum(
                [ev["dataset_id"] for ev in a.evidence] == i["expect"]["datasets"]
                for i, a in with_datasets
            ),
            len(with_datasets),
        ),  # fmt: skip
        "comparability_violations": sum(
            _violates_comparability(a, statuses) for _, a in data_answers
        ),
        "freshness_coverage": _rate(
            sum(
                bool(a.coverage and a.coverage.get("latest_trusted_period"))
                for _, a in domain_items
            ),
            len(domain_items),
        ),
        "by_class": dict(sorted(by_class.items())),
        "failures": {i["id"]: p for i, _, p in results if p},
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
