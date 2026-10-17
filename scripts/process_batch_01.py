"""Process acquisition batch 01: fingerprint, profile, validate, write manifests.

Usage (from the repository root):
    .venv-py313/Scripts/python.exe scripts/process_batch_01.py [--legacy-raw DIR]

Optional legacy comparison: pass --legacy-raw DIR, or set CIVICMIND_LEGACY_RAW=DIR, to the
read-only legacy clone's data/raw folder (lp-0406/civicmind-ai at e3b194f).
The CLI argument wins over the variable. When neither is set, or the folder or a reference
file is missing, the comparison is skipped with a printed note (never an error); a
``same_bytes_as`` value already recorded in the previous manifest for the same SHA-256 is
kept, because it was verified earlier and the bytes have not changed.

Reads downloads from data/external/verify_2026-10-17/, the automated download log and the
manual-download log. Writes manifests to data/manifests/ and machine-readable reports to
docs/acquisition/batch-01/. Files that fail integrity or have validator errors are moved to
data/quarantine/batch-01/. Datasets without a validator yet are profiled only
(status "integrity_passed"). Person review decisions are read from
docs/acquisition/batch-01/REVIEW_DECISIONS.yaml and applied to each regenerated manifest; a
"quarantine" decision moves the file to the quarantine folder before it is fingerprinted.
Datasets whose manifest passes the promotion gate (docs/MANIFEST_SPEC.md, section 3) are
copied byte-identically to data/raw/<domain>/; Git tracking is unchanged.

Legacy files are read (never written) only for byte-identity checks. Cross-dataset
identifier assessments never join anything.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from civicmind.catalog.fingerprint import fingerprint
from civicmind.catalog.identifiers import assess_identifiers, names_shared_by_multiple_ids
from civicmind.catalog.manifest import Manifest, read_manifest, write_manifest
from civicmind.catalog.profile import profile_frame, read_raw_header, read_text_table
from civicmind.catalog.promote import gate_reasons, promote
from civicmind.catalog.quarantine import move_to_quarantine
from civicmind.catalog.review import DecisionsFile, apply_review, load_decisions
from civicmind.catalog.sensitivity import METHOD as SENSITIVITY_METHOD
from civicmind.catalog.sensitivity import scan_header
from civicmind.catalog.validators import bwssb_monthly, morth_city_table
from civicmind.catalog.validators.base import has_errors

ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = ROOT / "data/external/verify_2026-10-17"
QUARANTINE = ROOT / "data/quarantine/batch-01"
MANIFESTS = ROOT / "data/manifests"
REPORTS = ROOT / "docs/acquisition/batch-01"
DECISIONS = REPORTS / "REVIEW_DECISIONS.yaml"
LEGACY_ENV = "CIVICMIND_LEGACY_RAW"  # optional read-only legacy data/raw folder

GODL = {
    "name": "Government Open Data License - India",
    "url": "https://www.data.gov.in/Godl",
    "evidence": (
        "Catalogue field 'Released under NDSAP' / portal footer; GODL text rendered at "
        "https://www.data.gov.in/Godl on 2026-10-17 (raw HTML in this batch is an app shell; "
        "see data/external/verify_2026-10-17/licence/GODL_evidence_note.md)"
    ),
    "exemptions_checked": True,
}
NOT_RETRIEVED_NOTE = (
    "Direct file URL from the catalogue API returned HTTP 403 (redirect to /page_not_found, "
    "empty body). The resource page's official Download requires a usage/purpose form with a "
    "CAPTCHA, which was not completed. Manual download by a person is required."
)


@dataclass(frozen=True)
class Planned:
    dataset_id: str
    domain: str
    title: str
    publisher: str
    host_portal: str
    resource_slug: str
    download_url: str
    portal_bytes: int
    published: str
    updated: str
    period: dict
    geography: dict
    family: str  # validator family
    ward_scheme: str | None = None
    limitations: tuple[str, ...] = ()

    @property
    def filename(self) -> str:
        return self.download_url.rsplit("/", 1)[-1]

    @property
    def resource_page(self) -> str:
        return f"https://www.data.gov.in/resource/{self.resource_slug}"


BWSSB = "Bangalore Water Supply and Sewerage Board"
BWSSB_LIMITS = (
    "Recorded consumption, not supply; bulk and commercial connections included.",
    "Ward numbering (1-198) does not by itself establish the BBMP-2010 scheme.",
)
SC = "Bruhat Bengaluru Mahanagara Palike (published via Smart Cities Mission, MoHUA)"
MORTH = "Ministry of Road Transport and Highways"
MORTH_LIMITS = (
    "City-level only; MoRTH's city boundary definition is not established - "
    "never join to ward data.",
    "Later editions may restate earlier years; cite the edition.",
)
BLR_WARD = {"state": "Karnataka", "city": "Bengaluru", "level": "ward"}
CITY = {"level": "million-plus city"}
F = "https://www.data.gov.in/files/ogdpv2dms/s3fs-public/"
F2 = "https://data.gov.in/files/ogdpv2dms/s3fs-public/"

PLAN = [
    Planned(
        "WATER-BWSSB-2025-08",
        "water",
        "Water consumption data for the month of August-2025",
        BWSSB,
        "karnataka.data.gov.in",
        "water-consumption-data-month-august-2025",
        F + "BWSSB_Water_Consumption_August_2025.csv",
        6045,
        "2025-09-17",
        "2025-09-17",
        {"start": "2025-08-01", "end": "2025-08-31", "granularity": "month"},
        BLR_WARD,
        "bwssb",
        "UNKNOWN",
        BWSSB_LIMITS,
    ),
    Planned(
        "WATER-BWSSB-2025-04",
        "water",
        "Water consumption data for the month of April-2025",
        BWSSB,
        "karnataka.data.gov.in",
        "water-consumption-data-month-april-2025",
        F + "Water_consumtion_data_april_2025.csv",
        5845,
        "2025-06-21",
        "2025-06-21",
        {"start": "2025-04-01", "end": "2025-04-30", "granularity": "month"},
        BLR_WARD,
        "bwssb",
        "UNKNOWN",
        BWSSB_LIMITS,
    ),
    Planned(
        "WATER-BWSSB-2025-05",
        "water",
        "Water consumption data for the month of May 2025",
        BWSSB,
        "karnataka.data.gov.in",
        "water-consumption-data-month-may-2025",
        F2 + "Water_Consumption_Data_May_2025.csv",
        6625,
        "2025-07-10",
        "2025-07-10",
        {"start": "2025-05-01", "end": "2025-05-31", "granularity": "month"},
        BLR_WARD,
        "bwssb",
        "UNKNOWN",
        BWSSB_LIMITS,
    ),
    Planned(
        "WATER-BWSSB-2026-03",
        "water",
        "Water consumption data for the month of March-2026",
        BWSSB,
        "karnataka.data.gov.in",
        "water-consumption-data-month-march-2026",
        F + "Water_Consumption_Data_Mar_26_0.csv",
        5844,
        "2026-05-04",
        "2026-05-04",
        {"start": "2026-03-01", "end": "2026-03-31", "granularity": "month"},
        BLR_WARD,
        "bwssb",
        "UNKNOWN",
        BWSSB_LIMITS,
    ),
    Planned(
        "DEMO-SC-BLR-2011-DEM",
        "demographics",
        "Demographic Profile: Bengaluru as on 01-03-2011",
        SC,
        "smartcities.data.gov.in",
        "demographic-profile-bengaluru-01-03-2011",
        F2 + "datafile/Demographic_Profile_Bengaluru_ason_01-03-2011_1.csv",
        14921,
        "2019-04-23",
        "2025-02-17",
        {"start": None, "end": None, "granularity": "decadal", "as_on": "2011-03-01"},
        BLR_WARD,
        "census_profile",
        "UNKNOWN",
        ("Census 2011 population; population in thousands.",),
    ),
    Planned(
        "WASTE-BLR-GCP",
        "waste",
        "Solid Waste Generated, Collected, Processed Data Bengaluru from 2015-16 to 2017-18",
        SC,
        "smartcities.data.gov.in",
        "solid-waste-generated-collected-processed-data-bengaluru-2015-16-2017-18",
        F2 + "datafile/Solid_Waste_Generated_Collected_Processed_Data_Bengaluru_"
        "from_2015-16to2017-18_1.csv",
        23868,
        "2019-04-23",
        "2025-02-17",
        {"start": "2015-04-01", "end": "2018-03-31", "granularity": "financial_year"},
        BLR_WARD,
        "swm_gcp",
        "UNKNOWN",
        ("2015-2018 data under SWM Rules 2016; no post-2019 ward waste data.",),
    ),
    Planned(
        "ROAD-RA2019-A47",
        "roads",
        "Cities-wise Accidents Classified according to Type of Traffic Violations "
        "in Million Plus Cities during 2019",
        MORTH,
        "data.gov.in",
        "cities-wise-accidents-classified-according-type-traffic-violations-million-plus-cities",
        "https://data.gov.in/files/ogd20/ogdpv2dms/s3fs-public/RA2019_A47.csv",
        6807,
        "2023-02-15",
        "2023-02-15",
        {"start": "2019-01-01", "end": "2019-12-31", "granularity": "year"},
        CITY,
        "morth_city",
        None,
        MORTH_LIMITS,
    ),
    Planned(
        "ROAD-RA2024-A47",
        "roads",
        "Million Plus City-wise Accidents Classified According to Type of "
        "Traffic Rule Violations during 2024",
        MORTH,
        "data.gov.in",
        "million-plus-city-wise-accidents-classified-according-type-traffic-rule-violations-during",
        F + "604807629/Version_1/Transport_2024_Annexure_47.csv",
        6925,
        "2026-06-18",
        "2026-06-18",
        {"start": "2024-01-01", "end": "2024-12-31", "granularity": "year"},
        CITY,
        "morth_city",
        None,
        MORTH_LIMITS,
    ),
]


LEGACY_REF = "legacy repo lp-0406/civicmind-ai e3b194f:data/raw/"
VALIDATORS = {"bwssb": bwssb_monthly.validate, "morth_city": morth_city_table.validate}


def download_log() -> dict[str, dict]:
    with open(BATCH_DIR / "download_log.tsv", encoding="utf-8") as fh:
        return {row["url"]: row for row in csv.DictReader(fh, delimiter="\t")}


def manual_log() -> dict[str, dict]:
    path = BATCH_DIR / "manual_downloads.tsv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return {row["dataset_id"]: row for row in csv.DictReader(fh, delimiter="\t")}


def locate(p: Planned) -> Path | None:
    for candidate in (BATCH_DIR / p.domain / p.filename, QUARANTINE / p.filename):
        if candidate.exists():
            return candidate
    return None


def legacy_identity(
    filename: str, sha256: str, legacy_raw: Path | None
) -> tuple[bool, str | None]:
    """Compare with the legacy copy. Returns (compared, same_bytes_as); never raises."""
    if legacy_raw is None:
        return False, None
    legacy = legacy_raw / filename
    if not legacy.is_file():
        print(f"note: legacy comparison skipped for {filename}: no reference file at {legacy}")
        return False, None
    if hashlib.sha256(legacy.read_bytes()).hexdigest() == sha256:
        return True, f"{LEGACY_REF}{filename} (byte-identical, sha256 {sha256})"
    print(f"note: {filename} differs from the legacy reference {legacy}")
    return True, None


def previous_same_bytes_as(dataset_id: str, sha256: str) -> str | None:
    """same_bytes_as from the existing manifest, only if it describes the same bytes."""
    path = MANIFESTS / f"{dataset_id}.yaml"
    if not path.is_file():
        return None
    try:
        old = read_manifest(path)
    except (OSError, ValueError) as exc:
        print(f"note: could not read previous manifest {path.name}: {exc}")
        return None
    if old.integrity is not None and old.integrity.sha256 == sha256:
        return old.same_bytes_as
    return None


def resolve_legacy_raw(cli_value: str | None) -> Path | None:
    value = cli_value or os.environ.get(LEGACY_ENV) or None
    if value is None:
        print(
            f"note: legacy comparison skipped (pass --legacy-raw DIR or set {LEGACY_ENV}); "
            "previously recorded same_bytes_as values are kept when the SHA-256 is unchanged"
        )
        return None
    path = Path(value)
    if not path.is_dir():
        print(f"note: legacy comparison skipped: folder not found: {path}")
        return None
    print(f"legacy comparison against (read-only): {path}")
    return path


def quarantine(path: Path) -> Path:
    # Never overwrites: a name collision in the quarantine folder stops the run.
    return move_to_quarantine(path, QUARANTINE)


def attribution(p: Planned) -> str:
    y, m, d = p.published.split("-")
    return (
        f"{p.publisher}, {y}, {p.title}, Open Government Data Platform India, {d}/{m}, "
        f"{p.resource_page}. Published under Government Open Data License - India: "
        "https://www.data.gov.in/Godl."
    )


def process(
    p: Planned,
    log: dict[str, dict],
    manual: dict[str, dict],
    decisions: DecisionsFile | None = None,
    legacy_raw: Path | None = None,
) -> tuple[Manifest, dict]:
    entry = log.get(p.download_url, {})
    manual_entry = manual.get(p.dataset_id)
    local = locate(p)
    decision = decisions.decisions.get(p.dataset_id) if decisions else None
    if local is not None and decision is not None and decision.decision == "quarantine":
        local = quarantine(local)  # a person's decision; the bytes are unchanged
    if manual_entry:
        saved_name = manual_entry["downloaded_file"]
        retrieval = {
            "retrieved_at": manual_entry["download_mtime"],
            "retrieved_by": "project owner (manual download; CAPTCHA completed by a person)",
            "method": "resource page Data > CSV Download (usage/purpose form)",
            "http_status": None,
            "content_type": None,
            "original_filename": p.filename,
            "local_path": None,
            "note": (
                f"Browser saved the file as '{saved_name}'; copied byte-identically "
                f"(sha256 {manual_entry['sha256']}) and stored under the served name. "
                "retrieved_at is the downloaded file's modification time. An earlier "
                "automated GET of the catalogue direct URL returned HTTP "
                f"{entry.get('http_status', 'n/a')}."
            ),
        }
    else:
        retrieval = {
            "retrieved_at": entry.get("retrieved_at"),
            "retrieved_by": (
                "Claude Code session (plain HTTPS GET of the catalogue direct URL; no form)"
            ),
            "method": "direct file URL from data.gov.in catalogue API",
            "http_status": int(entry["http_status"]) if entry.get("http_status") else None,
            "content_type": entry.get("content_type") or None,
            "original_filename": p.filename,
            "local_path": None,
        }
    base = {
        "dataset_id": p.dataset_id,
        "title": p.title,
        "publisher": p.publisher,
        "host_portal": p.host_portal,
        "source_class": "official",
        "resource_page": p.resource_page,
        "download_url": p.download_url,
        "portal_published": p.published,
        "portal_updated": p.updated,
        "licence": {**GODL, "attribution": attribution(p)},
        "period": p.period,
        "geography": p.geography,
        "ward_scheme": p.ward_scheme,
        "identifier_evidence": "none" if p.ward_scheme else None,
        # Unknown until the header has been screened below: fail safe, never "public" by default.
        "sensitivity": "restricted",
        "contains_personal_data": True,
        "known_limitations": list(p.limitations),
    }
    report: dict = {"dataset_id": p.dataset_id}
    if local is None:
        retrieval["note"] = NOT_RETRIEVED_NOTE
        manifest = Manifest.model_validate(
            {**base, "retrieval": retrieval, "status": "not_retrieved"}
        )
        report["status"] = "not_retrieved"
        return manifest, report

    fp = fingerprint(local)
    integrity_ok = (
        fp.bytes == p.portal_bytes
        and fp.encoding is not None
        and not fp.looks_like_html
        and not fp.contains_nul
    )
    integrity = {
        "bytes": fp.bytes,
        "portal_stated_bytes": p.portal_bytes,
        "size_matches_portal": fp.bytes == p.portal_bytes,
        "sha256": fp.sha256,
        "format": "csv",
        "encoding": fp.encoding,
        "bom": fp.bom,
        "newline": fp.newline,
        "newline_counts": fp.newline_counts,
        "delimiter": fp.delimiter,
        "looks_like_html": fp.looks_like_html,
        "passed": integrity_ok,
    }
    report["fingerprint"] = fp.to_dict()
    compared, same = legacy_identity(p.filename, fp.sha256, legacy_raw)
    base["same_bytes_as"] = same if compared else previous_same_bytes_as(p.dataset_id, fp.sha256)
    if not integrity_ok:
        target = quarantine(local)
        retrieval["local_path"] = target.relative_to(ROOT).as_posix()
        manifest = Manifest.model_validate(
            {**base, "retrieval": retrieval, "integrity": integrity, "status": "quarantined"}
        )
        report["status"] = "quarantined"
        report["fingerprint"]["path"] = retrieval["local_path"]
        return manifest, report

    header = read_raw_header(local, fp.encoding, fp.delimiter or ",")
    frame = read_text_table(local, fp.encoding, fp.delimiter or ",")
    prof = profile_frame(frame, header)
    validator = VALIDATORS.get(p.family)
    findings = validator(frame, header) if validator else []
    if fp.newline != "CRLF" and fp.newline != "LF":
        findings.insert(
            0,
            _finding(
                "file.newline_style",
                "warning",
                f"Unusual line endings ({fp.newline}); parsed with universal newlines in memory, "
                "file unchanged",
                fp.newline_counts,
            ),
        )
    hits = scan_header(header)
    base["sensitivity"] = "personal_data" if hits else "public"
    base["contains_personal_data"] = bool(hits)
    findings.append(
        _finding(
            "sensitivity.personal_data_suspected" if hits else "sensitivity.header_scan",
            "warning" if hits else "info",
            (
                "Column names suggest personal data; needs review before any use"
                if hits
                else "No column name suggests personal data"
            ),
            {"method": SENSITIVITY_METHOD, "matched": hits},
        )
    )
    report.update(profile=prof.to_dict(), findings=[f.to_dict() for f in findings])
    schema = [{"name": c, "type": "text (unparsed)"} for c in header]
    if validator is None:
        status = "integrity_passed"
        semantic = {
            "validator": None,
            "note": "No validator for this dataset family yet; profiled only. "
            "Not eligible for promotion until a validator is approved and passes.",
        }
    else:
        status = "quarantined" if has_errors(findings) else "validated"
        semantic = {
            "validator": f"{p.family}@v1",
            "errors": sum(f.severity == "error" for f in findings),
            "warnings": sum(f.severity == "warning" for f in findings),
        }
    if status == "quarantined":
        local = quarantine(local)
    retrieval["local_path"] = local.relative_to(ROOT).as_posix()
    manifest = Manifest.model_validate(
        {
            **base,
            "retrieval": retrieval,
            "integrity": integrity,
            "schema": schema,
            "row_count": prof.rows,
            "semantic_checks": semantic,
            "findings": [f.to_dict() for f in findings],
            "status": status,
        }
    )
    report["status"] = status
    report["fingerprint"]["path"] = retrieval["local_path"]
    return manifest, report


def _finding(code, severity, message, details):
    from civicmind.catalog.validators.base import Finding

    return Finding(code, severity, message, details)


def _load(dataset_id: str):
    p = next(x for x in PLAN if x.dataset_id == dataset_id)
    path = locate(p)
    if path is None:
        return None, None
    fp = fingerprint(path)
    return read_raw_header(path, fp.encoding), read_text_table(path, fp.encoding)


def _ids(frame, id_hint: str, name_hint: str) -> tuple[str, str]:
    cols = list(frame.columns)
    id_col = next(c for c in cols if c.strip().lower().startswith(id_hint))
    name_col = next(c for c in cols if c.strip().lower().startswith(name_hint))
    return id_col, name_col


WARD_DATASETS = {
    "WATER-BWSSB-2025-08": ("ward number", "ward name"),
    "DEMO-SC-BLR-2011-DEM": ("ward no", "ward name"),
    "WASTE-BLR-GCP": ("ward_no", "ward_name"),
}


def cross_dataset_checks() -> dict:
    """Identifier assessments and observations across official batch files. No joins."""
    out: dict = {}
    frames = {}
    for ds, (id_hint, name_hint) in WARD_DATASETS.items():
        _, frame = _load(ds)
        if frame is not None:
            frames[ds] = (frame, *_ids(frame, id_hint, name_hint))
    for ds, (frame, id_col, name_col) in frames.items():
        shared = names_shared_by_multiple_ids(frame, id_col, name_col)
        out[f"names_reused_across_ward_numbers::{ds}"] = {
            "note": "Normalised names that appear under more than one ward number in the "
            "same file. Many entries mean the name column is not a reliable label.",
            "count": len(shared),
            "examples": dict(list(shared.items())[:10]),
        }
    pairs = [
        ("WATER-BWSSB-2025-08", "DEMO-SC-BLR-2011-DEM"),
        ("WATER-BWSSB-2025-08", "WASTE-BLR-GCP"),
        ("WASTE-BLR-GCP", "DEMO-SC-BLR-2011-DEM"),
    ]
    for left, right in pairs:
        if left not in frames or right not in frames:
            continue
        lf, lid, lname = frames[left]
        rf, rid, rname = frames[right]
        result = assess_identifiers(
            lf,
            rf,
            left_id=lid,
            left_name=lname,
            right_id=rid,
            right_name=rname,
            left_label=left,
            right_label=right,
        )
        out[f"identifiers::{left}__vs__{right}"] = {
            "note": "Ward numbers compared with their names. join_authorised is always false: "
            "no document yet defines either side's ward scheme.",
            "counts": result.counts(),
            **result.to_dict(),
        }
    _, mar = _load("WATER-BWSSB-2026-03")
    if mar is not None and "WATER-BWSSB-2025-08" in frames:
        aug, aid, aname = frames["WATER-BWSSB-2025-08"]
        mid, mname = _ids(mar, "ward number", "ward name")
        result = assess_identifiers(
            aug,
            mar,
            left_id=aid,
            left_name=aname,
            right_id=mid,
            right_name=mname,
            left_label="WATER-BWSSB-2025-08",
            right_label="WATER-BWSSB-2026-03",
        )
        out["identifiers::WATER-BWSSB-2025-08__vs__WATER-BWSSB-2026-03"] = {
            "note": "Series consistency within one publisher. No join.",
            "counts": result.counts(),
            **result.to_dict(),
        }
    if "WASTE-BLR-GCP" in frames:
        waste = frames["WASTE-BLR-GCP"][0]
        obs = {}
        for year in ("2015-16", "2016-17", "2017-18"):
            gen = next(c for c in waste.columns if "generated" in c and c.endswith(year))
            col = next(c for c in waste.columns if "collected" in c and c.endswith(year))
            g = waste[gen].astype(float)
            c = waste[col].astype(float)
            obs[year] = {
                "wards": int(len(waste)),
                "collected_gt_generated": int((c > g + 1e-9).sum()),
                "collected_eq_generated": int(((c - g).abs() <= 1e-9).sum()),
                "total_generated_MT": round(float(g.sum()), 2),
                "total_collected_MT": round(float(c.sum()), 2),
            }
        out["observations::WASTE-BLR-GCP::collected_vs_generated"] = {
            "note": "Descriptive observation only (no SWM validator approved yet).",
            **obs,
        }
    _, ra19 = _load("ROAD-RA2019-A47")
    _, ra24 = _load("ROAD-RA2024-A47")
    if ra19 is not None and ra24 is not None:
        h19 = list(ra19.columns)
        h24 = list(ra24.columns)
        out["schema_drift::ROAD-RA2019-A47__vs__ROAD-RA2024-A47"] = {
            "note": "Verbatim header comparison of two official downloads.",
            **morth_city_table.schema_drift(h19, h24),
        }
        l19 = morth_city_table.find_label_column(h19)
        l24 = morth_city_table.find_label_column(h24)
        s19 = {v.strip() for v in ra19[l19]} - {"Total"}
        s24 = {v.strip() for v in ra24[l24]} - {"Total"}
        out["city_labels::2019_vs_2024"] = {
            "note": "Spelling differences are NOT equated without a cited alias table.",
            "only_2019": sorted(s19 - s24),
            "only_2024": sorted(s24 - s19),
            "common": len(s19 & s24),
        }
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--legacy-raw",
        metavar="DIR",
        help=f"read-only legacy data/raw folder for byte-identity checks (or set {LEGACY_ENV})",
    )
    args = parser.parse_args(argv)
    legacy_raw = resolve_legacy_raw(args.legacy_raw)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "profiles").mkdir(parents=True, exist_ok=True)
    log = download_log()
    manual = manual_log()
    decisions = load_decisions(DECISIONS) if DECISIONS.exists() else None
    summary = []
    for p in PLAN:
        manifest, report = process(p, log, manual, decisions, legacy_raw)
        manifest = apply_review(manifest, decisions)
        if not gate_reasons(manifest):
            manifest = promote(manifest, ROOT)
        report["status"] = manifest.status
        write_manifest(manifest, MANIFESTS)
        if "profile" in report or "fingerprint" in report:
            (REPORTS / "profiles" / f"{p.dataset_id}.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
            )
        summary.append(
            {
                "dataset_id": p.dataset_id,
                "status": manifest.status,
                "sha256": manifest.integrity.sha256 if manifest.integrity else None,
                "bytes": manifest.integrity.bytes if manifest.integrity else None,
                "errors": manifest.semantic_checks.get("errors"),
                "warnings": manifest.semantic_checks.get("warnings"),
                "same_bytes_as_legacy": manifest.same_bytes_as is not None,
                "human_review": manifest.human_review,
                "value_nature": manifest.value_nature,
                "promoted_to": manifest.promoted_to,
            }
        )
    comparisons = cross_dataset_checks()
    (REPORTS / "cross_dataset_checks.json").write_text(
        json.dumps(comparisons, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    (REPORTS / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8", newline="\n"
    )
    for row in summary:
        print(row)
    for key, value in comparisons.items():
        print(key, value.get("counts", value.get("count", "")))


if __name__ == "__main__":
    main()
