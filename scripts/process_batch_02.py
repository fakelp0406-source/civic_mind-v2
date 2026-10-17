"""Batch 02 processor: manifests, review decisions and the promotion gate (mirrors batch 01).

Reads the 15 staged files in data/external/batch-02/, fingerprints and validates them with the
registered validators, applies the person's decisions in
docs/acquisition/batch-02/REVIEW_DECISIONS.yaml, promotes only what passes the existing gate
(``catalog.promote``) and writes one manifest per dataset to data/manifests/.

* Source bytes are never changed. A quarantined file is moved (``os.rename``, never copied
  or rewritten) to data/quarantine/batch-02/; a promoted file is copied byte-identically to
  data/raw/<domain>/ with its hash re-checked.
* Warnings never reject a file by themselves: a dataset is promoted only when a person's
  ``accept`` lists every warning code as an accepted caveat.
* The download method is UNKNOWN until the project owner records it.
* Portal titles, dates and notes were read from the resource pages on 2026-10-17 (see
  scripts/propose_batch_02.py, which holds that verified metadata).

Usage: python scripts/process_batch_02.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from profile_batch_02 import CANDIDATES, STAGE, load
from propose_batch_02 import (
    BWSSB,
    BWSSB_LIMITS,
    GODL,
    MORTH,
    MORTH_LIMITS,
    PORTAL,
    PORTAL_BYTES,
    PORTAL_READ,
    RES,
    TN_CITIES,
    attribution,
    downloads_mtime,
    iso,
)

from civicmind.catalog.ingest import IngestionRefused, ingest
from civicmind.catalog.manifest import Manifest, read_manifest, write_manifest
from civicmind.catalog.promote import gate_reasons, promote
from civicmind.catalog.quarantine import move_to_quarantine
from civicmind.catalog.review import apply_review, load_decisions
from civicmind.catalog.sensitivity import METHOD as SENSITIVITY_METHOD
from civicmind.catalog.sensitivity import scan_header
from civicmind.catalog.validators import bwssb_monthly, morth_city_table

ROOT = Path(__file__).resolve().parents[1]
QUARANTINE = ROOT / "data/quarantine/batch-02"
MANIFESTS = ROOT / "data/manifests"
REPORTS = ROOT / "docs/acquisition/batch-02"
DECISIONS = REPORTS / "REVIEW_DECISIONS.yaml"

VALIDATORS = {"bwssb": ("bwssb@v1", bwssb_monthly.validate)}
A47_VALIDATOR = ("morth_city@v1", morth_city_table.validate)
NO_VALIDATOR = ("ROAD-RA2024-A1", "ROAD-RA2024-A2", "ROAD-RA2024-A49")
UNKNOWN_METHOD = "UNKNOWN (not yet provided by the project owner)"

#: Months already trusted from batch 01, used only as the previous month of a series check.
BATCH01_WATER = {
    "2025-08": ROOT / "data/raw/water/BWSSB_Water_Consumption_August_2025.csv",
    "2026-03": ROOT / "data/raw/water/Water_Consumption_Data_Mar_26_0.csv",
}
DEFERRED = (
    "Owner decision 2026-10-17: derived cross-year growth rates and category summations are "
    "deferred until semantic comparability across editions is established."
)


def finding(code, severity, message, details=None) -> dict:
    return {"code": code, "severity": severity, "message": message, "details": details or {}}


def locate(rel: str) -> Path | None:
    for path in (STAGE / rel, QUARANTINE / Path(rel).name):
        if path.is_file():
            return path
    return None


def previous_month(period: str) -> str:
    y, m = map(int, period.split("-"))
    return f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}"


def series_source(period: str) -> Path | None:
    """The previous month's file if it is trusted or staged (never a quarantined month)."""
    if period in BATCH01_WATER:
        return BATCH01_WATER[period]
    for _id, rel, family, p in CANDIDATES:
        if family == "bwssb" and p == period:
            staged = STAGE / rel
            return staged if staged.is_file() else None  # quarantined files are not used
    return None


def limitations(dataset_id: str) -> list[str]:
    if dataset_id.startswith("WATER"):
        return list(BWSSB_LIMITS)
    if dataset_id in NO_VALIDATOR:
        limits = [*MORTH_LIMITS[:2], "No analytics are enabled for this table (owner decision)."]
    else:
        limits = [*MORTH_LIMITS, DEFERRED]
    extra = {
        "ROAD-RA2020-A47": "SOURCE CAVEAT: publisher note on the 2021 edition says Tamil Nadu "
        "data for 2017-2020 was 'undergoing revision'; the 2024 Annexure 1 note says it was "
        f"reconciled. Values for {TN_CITIES} in this 2020 edition may be superseded.",
        "ROAD-RA2021-A47": "SOURCE CAVEAT: Pune, Over-Speeding: 0 accidents with 6 persons "
        "killed and 15 injured, published as-is; unresolved source inconsistency (finding "
        "casualties.zero_accidents). Per-accident ratios for this cell are undefined.",
        "ROAD-RA2024-A1": "National series; irregular years (1970, 1980, 1990, 1995-2024); "
        "the 'CAGR 2014/2024' row is not a year. Publisher footnotes '# Data for the year "
        "1971. ## Data for the year 1981.' are not carried in the CSV.",
        "ROAD-RA2024-A2": "State/UT level; 2021-2023 values as restated in the 2024 edition; "
        "2022 per-km rates provisional (P); Ladakh per-vehicle rate NA.",
        "ROAD-RA2024-A49": "Five junction types only (no 'not at junction'/'others'): not a "
        "partition of all city accidents; never combine with Annexure 47.",
    }
    if dataset_id in extra:
        limits.append(extra[dataset_id])
    return limits


def build(dataset_id: str, rel: str, family: str, period: str, path: Path) -> Manifest:
    slug, title, catalog, published, updated, size, note, url = PORTAL[dataset_id]
    page = RES + slug
    water = dataset_id.startswith("WATER")
    publisher = BWSSB if water else MORTH
    fp, header, frame = load(path)
    findings: list[dict] = []
    if fp.newline not in ("CRLF", "LF"):
        findings.append(
            finding(
                "file.newline_style",
                "warning",
                f"Unusual line endings ({fp.newline}); parsed with universal newlines in "
                "memory, file unchanged",
                fp.newline_counts,
            )
        )
    validator = None
    if family == "bwssb":
        validator, validate = VALIDATORS["bwssb"]
        findings += [f.to_dict() for f in validate(frame, header)]
        prev = previous_month(period)
        source = series_source(prev)
        if source is None:
            findings.append(
                finding(
                    "series.not_compared",
                    "info",
                    f"No trusted or staged file for {prev} (quarantined or not acquired); "
                    "month-to-month swing check not run",
                    {"previous": prev},
                )
            )
        else:
            prior_fp, prior_header, prior = load(source)
            prior_errors = [
                f.code
                for f in bwssb_monthly.validate(prior, prior_header)
                if f.severity == "error"
            ]
            if prior_errors:  # never compare against a month that fails validation
                findings.append(
                    finding(
                        "series.not_compared",
                        "info",
                        f"{prev} fails validation ({', '.join(prior_errors)}); month-to-month "
                        "swing check not run",
                        {"previous": prev, "previous_sha256": prior_fp.sha256},
                    )
                )
            else:
                findings += [
                    f.to_dict() for f in bwssb_monthly.series_swing(prior, frame, prev, period)
                ]
    elif dataset_id not in NO_VALIDATOR:
        validator, validate = A47_VALIDATOR
        findings += [f.to_dict() for f in validate(frame, header)]
    hits = scan_header(header)
    findings.append(
        finding(
            "sensitivity.personal_data_suspected" if hits else "sensitivity.header_scan",
            "warning" if hits else "info",
            "Column names suggest personal data; needs review before any use"
            if hits
            else "No column name suggests personal data",
            {"method": SENSITIVITY_METHOD, "matched": hits},
        )
    )
    errors = sum(f["severity"] == "error" for f in findings)
    warnings = sum(f["severity"] == "warning" for f in findings)
    integrity_ok = (
        fp.bytes == PORTAL_BYTES[dataset_id]
        and fp.encoding is not None
        and not fp.looks_like_html
        and not fp.contains_nul
    )
    if not integrity_ok or errors:
        status = "quarantined"
    elif validator is None:
        status = "integrity_passed"
    else:
        status = "validated"
    if water:
        y, m = map(int, period.split("-"))
        end = (datetime(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).date().isoformat()
        per = {"start": f"{period}-01", "end": end, "granularity": "month"}
        geo = {"state": "Karnataka", "city": "Bengaluru", "level": "ward"}
    else:
        span = {"ROAD-RA2024-A1": ("1970", "2024"), "ROAD-RA2024-A2": ("2021", "2024")}
        start, stop = span.get(dataset_id, (period, period))
        per = {"start": f"{start}-01-01", "end": f"{stop}-12-31", "granularity": "year"}
        level = {"ROAD-RA2024-A1": "national", "ROAD-RA2024-A2": "state"}
        geo = {"level": level.get(dataset_id, "million-plus city")}
    semantic = (
        {"validator": validator, "errors": errors, "warnings": warnings}
        if validator
        else {
            "validator": None,
            "note": "No validator family for this table; profiled only. Not eligible for "
            "promotion until a family validator is approved and passes.",
        }
    )
    return Manifest.model_validate(
        {
            "dataset_id": dataset_id,
            "title": title,
            "publisher": publisher,
            "host_portal": "karnataka.data.gov.in" if water else "data.gov.in",
            "source_class": "official",
            "resource_page": page,
            "download_url": url,
            "portal_published": iso(published),
            "portal_updated": iso(updated),
            "licence": {**GODL, "attribution": attribution(publisher, title, published, page)},
            "retrieval": {
                "retrieved_at": downloads_mtime(path.name),
                "retrieved_by": UNKNOWN_METHOD,
                "method": UNKNOWN_METHOD,
                "original_filename": path.name,
                "local_path": path.relative_to(ROOT).as_posix(),
                "note": "Copied byte-identically (hash-checked) from the project owner's "
                "Downloads folder into data/external/batch-02/. retrieved_at is that Downloads "
                "file's modification time, not a confirmed download time. Who downloaded the "
                "file and by which route is UNKNOWN until the project owner provides it.",
            },
            "integrity": {
                "bytes": fp.bytes,
                "portal_stated_bytes": PORTAL_BYTES[dataset_id],
                "size_matches_portal": fp.bytes == PORTAL_BYTES[dataset_id],
                "sha256": fp.sha256,
                "format": "csv",
                "encoding": fp.encoding,
                "bom": fp.bom,
                "newline": fp.newline,
                "newline_counts": fp.newline_counts,
                "delimiter": fp.delimiter,
                "looks_like_html": fp.looks_like_html,
                "passed": integrity_ok,
            },
            "schema": [{"name": c, "type": "text (unparsed)"} for c in header],
            "row_count": len(frame),
            "period": per,
            "geography": geo,
            "ward_scheme": "UNKNOWN" if water else None,
            "identifier_evidence": "none" if water else None,
            "sensitivity": "personal_data" if hits else "public",
            "contains_personal_data": bool(hits),
            "semantic_checks": semantic,
            "compatibility": {
                "portal_catalogue": catalog,
                "portal_listed_size": size,
                "portal_metadata_evidence": PORTAL_READ,
                **({"publisher_note": note} if note else {}),
            },
            "findings": findings,
            "value_nature": "unknown",
            "human_review": "pending",
            "status": status,
            "known_limitations": limitations(dataset_id),
        }
    )


def ingest_check(m: Manifest) -> dict:
    """Re-read each dataset through the real ingestion gate in both modes."""
    out = {}
    for mode in ("trusted", "exploratory"):
        try:
            ds = ingest(m, ROOT, mode)
        except IngestionRefused as exc:
            out[mode] = {"result": "refused", "code": exc.code}
        else:
            out[mode] = {"result": "ingested", "schema_version": ds.schema_version}
    return out


def main() -> None:
    decisions = load_decisions(DECISIONS) if DECISIONS.exists() else None
    summary = []
    for dataset_id, rel, family, period in CANDIDATES:
        path = locate(rel)
        if path is None:
            raise FileNotFoundError(f"{dataset_id}: {rel} not found in staging or quarantine")
        decision = decisions.decisions.get(dataset_id) if decisions else None
        manifest = build(dataset_id, rel, family, period, path)
        if manifest.status == "quarantined" or (decision and decision.decision == "quarantine"):
            path = move_to_quarantine(path, QUARANTINE)  # os.rename: bytes unchanged
            data = manifest.model_dump(by_alias=True)
            data["retrieval"]["local_path"] = path.relative_to(ROOT).as_posix()
            data["status"] = "quarantined"
            manifest = Manifest.model_validate(data)
        manifest = apply_review(manifest, decisions)
        reasons = gate_reasons(manifest)
        if not reasons:
            manifest = promote(manifest, ROOT)
        write_manifest(manifest, MANIFESTS)
        manifest = read_manifest(MANIFESTS / f"{dataset_id}.yaml")  # what ingestion will see
        summary.append(
            {
                "dataset_id": dataset_id,
                "status": manifest.status,
                "human_review": manifest.human_review,
                "review_decision": manifest.review.decision if manifest.review else None,
                "permitted_uses": manifest.review.permitted_uses if manifest.review else [],
                "sha256": manifest.integrity.sha256,
                "bytes": manifest.integrity.bytes,
                "local_path": manifest.retrieval.local_path,
                "promoted_to": manifest.promoted_to,
                "errors": manifest.semantic_checks.get("errors"),
                "warnings": sorted(
                    {f["code"] for f in manifest.findings if f["severity"] == "warning"}
                ),
                "gate_reasons": [] if manifest.status == "promoted" else reasons,
                "ingest": ingest_check(manifest),
            }
        )
    (REPORTS / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8", newline="\n"
    )
    for row in summary:
        print(
            row["dataset_id"],
            row["status"],
            row["human_review"],
            row["review_decision"],
            row["warnings"],
            {
                k: v["result"] + ":" + v.get("code", v.get("schema_version", ""))
                for k, v in row["ingest"].items()
            },
        )


if __name__ == "__main__":
    main()
