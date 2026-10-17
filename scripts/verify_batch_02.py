"""Batch 02 closure checks (read-only). Writes docs/acquisition/batch-02/closure_checks.json.

1. Every manifest's SHA-256 equals its files (local_path, promoted_to) on disk.
2. Recorded review decisions equal what the manifests carry (decision, SHA-256, caveats).
3. Source caveats are present on the manifests the owner named.
4. Batch 01 manifests equal Git HEAD byte-for-byte; trusted 2019/2024 A47 hashes unchanged.
5. A47 road questions resolve to Annexure 47 for every catalogued year; A1/A2/A49 never.
6. The 55-item evaluation set: actual pipeline outcome vs expected, item by item.

Usage: python scripts/verify_batch_02.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

from civicmind.catalog.manifest import read_manifest
from civicmind.catalog.review import load_decisions
from civicmind.orchestrator.pipeline import answer_question
from civicmind.planner.catalog_index import load_index
from civicmind.planner.feasibility import Plan, check
from civicmind.planner.parser import parse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/acquisition/batch-02/closure_checks.json"
BATCH01 = (
    "DEMO-SC-BLR-2011-DEM",
    "ROAD-RA2019-A47",
    "ROAD-RA2024-A47",
    "WASTE-BLR-GCP",
    "WATER-BWSSB-2025-04",
    "WATER-BWSSB-2025-05",
    "WATER-BWSSB-2025-08",
    "WATER-BWSSB-2026-03",
)
BATCH01_A47_SHA = {
    "ROAD-RA2019-A47": "40bed81dc88f3350b2bd13f3f3699d2d07e7b6afdfdf7e02a286e568897bedcc",
    "ROAD-RA2024-A47": "702f75f332a273e9c09eb500a7d2f90c2ae71eec3bf06fe01d48a6fc56bd37e9",
}
CAVEATS = {
    "ROAD-RA2020-A47": "Tamil Nadu",
    "ROAD-RA2021-A47": "Pune",
    "ROAD-RA2022-A47": "deferred",
    "ROAD-RA2023-A47": "deferred",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    out: dict = {}
    manifests = {
        p.stem: read_manifest(p) for p in sorted((ROOT / "data/manifests").glob("*.yaml"))
    }

    files = {}
    for ds, m in manifests.items():
        if not m.integrity:
            continue
        for rel in filter(None, (m.retrieval.local_path, m.promoted_to)):
            path = ROOT / rel
            files[f"{ds}:{rel}"] = path.is_file() and sha(path) == m.integrity.sha256
    out["manifest_hash_matches_files"] = {
        "checked": len(files),
        "failed": [k for k, v in files.items() if not v],
    }

    decisions = load_decisions(ROOT / "docs/acquisition/batch-02/REVIEW_DECISIONS.yaml")
    mismatches = []
    for ds, d in decisions.decisions.items():
        m = manifests[ds]
        r = m.review
        if (
            r is None
            or r.decision != d.decision
            or r.sha256 != d.sha256 != m.integrity.sha256
            or r.sha256 != m.integrity.sha256
            or sorted(r.accepted_caveats) != sorted(d.accepted_caveats)
            or r.permitted_uses != d.permitted_uses
        ):
            mismatches.append(ds)
    out["review_decisions_applied"] = {
        "decisions": len(decisions.decisions),
        "mismatches": mismatches,
        "by_dataset": {
            ds: {"decision": d.decision, "status": manifests[ds].status}
            for ds, d in decisions.decisions.items()
        },
    }
    batch02 = [ds for ds in manifests if ds not in BATCH01]
    out["batch02_status"] = {ds: manifests[ds].status for ds in batch02}
    out["download_method_unknown"] = all(
        manifests[ds].retrieval.method.startswith("UNKNOWN")
        and manifests[ds].retrieval.retrieved_by.startswith("UNKNOWN")
        for ds in batch02
    )
    out["source_caveats_present"] = {
        ds: any(word in limit for limit in manifests[ds].known_limitations)
        for ds, word in CAVEATS.items()
    }

    head = {}
    for ds in BATCH01:
        rel = f"data/manifests/{ds}.yaml"
        committed = subprocess.run(
            ["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, check=True
        ).stdout
        head[ds] = committed == (ROOT / rel).read_bytes()
    out["batch01_manifests_equal_git_head"] = head
    out["batch01_trusted_a47_hashes"] = {
        ds: manifests[ds].status == "promoted"
        and manifests[ds].integrity.sha256 == expected
        and sha(ROOT / manifests[ds].promoted_to) == expected
        for ds, expected in BATCH01_A47_SHA.items()
    }

    index = load_index(ROOT)
    roads = [e for e in index if e.family == "roads"]
    years = sorted({e.dataset_id[7:11] for e in roads})
    resolution = {}
    for year in years:
        q = f"How many over-speeding accidents did Bengaluru record in {year}?"
        r = check(parse(q), index)
        resolution[year] = r.dataset_ids[0] if isinstance(r, Plan) else f"refused:{r.code}"
    q = "Which three million-plus cities had the most over-speeding deaths in 2024?"
    top = check(parse(q), index)
    out["a47_query_resolution"] = {
        "catalogued_road_tables": {e.dataset_id: e.table for e in roads},
        "city_value_by_year": resolution,
        "top_cities_2024": top.dataset_ids[0] if isinstance(top, Plan) else top.code,
        "non_a47_ever_selected": any(
            str(v).startswith("ROAD-") and not str(v).endswith("-A47")
            for v in [*resolution.values(), getattr(top, "dataset_ids", ("",))[0]]
        ),
    }

    items = yaml.safe_load((ROOT / "eval/questions/pipeline.v1.yaml").read_text("utf-8"))["items"]
    results, wrong = [], []
    for item in items:
        a = answer_question(item["question"], ROOT)
        e = item["expect"]
        ok = a.status == e["status"] and (e["status"] == "answered" or a.code == e.get("code"))
        results.append({"id": item["id"], "expected": e.get("code", e["status"]),
                        "actual": a.code or a.status, "ok": ok})  # fmt: skip
        if not ok:
            wrong.append(item["id"])
    out["eval_set"] = {
        "items": len(items),
        "answered_expected": sum(i["expect"]["status"] == "answered" for i in items),
        "refused_expected": sum(i["expect"]["status"] == "refused" for i in items),
        "status_and_code_match": len(items) - len(wrong),
        "mismatches": wrong,
        "results": results,
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
    printable = {k: v for k, v in out.items() if k != "eval_set"}
    printable["eval_set"] = {k: v for k, v in out["eval_set"].items() if k != "results"}
    print(json.dumps(printable, indent=1))


if __name__ == "__main__":
    main()
