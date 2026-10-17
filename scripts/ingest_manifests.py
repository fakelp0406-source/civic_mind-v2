"""Ingest every dataset described in data/manifests/ and write a deterministic report.

Usage (from the repository root):
    .venv-py313/Scripts/python.exe scripts/ingest_manifests.py [--out DIR]

For each manifest, trusted ingestion is attempted first. If it is refused and the review
decision is ``keep_profiled``, exploratory ingestion is attempted (it is itself refused
unless the review lists ``exploratory`` in ``permitted_uses``). Refusals are reported with
their stable code; they are expected outcomes, not script errors.

Output: ``<out>/ingest_report.json`` (default ``data/processed/ingest/``, which is
git-ignored). Source files are only read. The report contains no timestamps or absolute
paths, so two runs over the same inputs produce identical bytes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from civicmind.catalog.ingest import IngestionRefused, ingest
from civicmind.catalog.manifest import read_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "data/manifests"
DEFAULT_OUT = ROOT / "data/processed/ingest"


def ingest_one(manifest) -> list[dict]:
    attempts = []
    modes = ["trusted"]
    if manifest.review is not None and manifest.review.decision == "keep_profiled":
        modes.append("exploratory")
    for mode in modes:
        try:
            ds = ingest(manifest, ROOT, mode)
        except IngestionRefused as exc:
            attempts.append(
                {"mode": mode, "outcome": "refused", "code": exc.code, "reason": str(exc)}
            )
            continue
        attempts.append({"mode": mode, "outcome": "ingested", **ds.summary()})
        break
    return attempts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output folder")
    args = parser.parse_args(argv)
    out = Path(args.out)
    report = {}
    for path in sorted(MANIFESTS.glob("*.yaml")):
        manifest = read_manifest(path)
        report[manifest.dataset_id] = {
            "status": manifest.status,
            "human_review": manifest.human_review,
            "value_nature": manifest.value_nature,
            "attempts": ingest_one(manifest),
        }
    out.mkdir(parents=True, exist_ok=True)
    target = out / "ingest_report.json"
    target.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for dataset_id, entry in report.items():
        last = entry["attempts"][-1]
        detail = last.get("schema_version") or last.get("code")
        print(f"{dataset_id:24} {last['mode']:11} {last['outcome']:9} {detail}")
    print(
        f"report: {target.relative_to(ROOT).as_posix() if target.is_relative_to(ROOT) else target}"
    )


if __name__ == "__main__":
    main()
