"""Batch 02 controlled preparation: proposed manifests, schema registrations and a dry run.

Writes, under docs/acquisition/batch-02/:

* ``proposed_manifests/<DATASET-ID>.yaml``: one manifest per candidate, built with the
  project's own ``Manifest`` model. They are deliberately NOT in ``data/manifests/`` so the
  planner and ingestion never see them. None is promoted; ``human_review`` is ``pending``.
* ``proposed_schemas.yaml``: verbatim headers for the schema versions that would need to be
  registered in ``catalog/schemas.py`` (nothing is registered by this script).
* ``dry_run_ingest.json``: each advancing candidate copied into a temporary directory and
  run through ``civicmind.catalog.ingest.ingest(mode="trusted")`` with a *simulated* accept
  review, plus negative controls. The proposed A47 schemas are registered in memory for that
  process only. The temporary directory is deleted; no repository file is promoted.

Source files are read from data/external/batch-02/ and never modified or moved.

Usage: python scripts/propose_batch_02.py
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from profile_batch_02 import CANDIDATES, STAGE, a47_summary, load, water_table

from civicmind.catalog import schemas as schema_registry
from civicmind.catalog.ingest import IngestionRefused, ingest
from civicmind.catalog.manifest import Manifest, Review, write_manifest
from civicmind.catalog.sensitivity import METHOD as SENSITIVITY_METHOD
from civicmind.catalog.sensitivity import scan_header
from civicmind.catalog.validators import bwssb_monthly, morth_city_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/acquisition/batch-02"
DOWNLOADS = Path.home() / "Downloads"
IST = timezone(timedelta(hours=5, minutes=30))

F = "https://www.data.gov.in/files/ogdpv2dms/s3fs-public/"
F2 = "https://data.gov.in/files/ogdpv2dms/s3fs-public/"
OGD20 = "https://data.gov.in/files/ogd20/ogdpv2dms/s3fs-public/"
RES = "https://www.data.gov.in/resource/"
BWSSB = "Bangalore Water Supply and Sewerage Board"
MORTH = "Ministry of Road Transport and Highways"
GODL = {
    "name": "Government Open Data License - India",
    "url": "https://www.data.gov.in/Godl",
    "evidence": (
        "Portal footer on each resource page read 2026-10-17 ('licensed under the Government "
        "Open Data License-India'); GODL text recorded in "
        "data/external/verify_2026-10-17/licence/GODL_evidence_note.md"
    ),
    "exemptions_checked": True,
}
PORTAL_READ = (
    "Resource page rendered in a browser on 2026-10-17 (metadata only; no file downloaded "
    "by this session). Listed file size is rounded to 0.1 KB on the page."
)

# Metadata read from each resource page on 2026-10-17 (title, catalogue, published/updated
# dd/mm/yyyy, listed size, publisher note). Download URLs come from the catalogue-API records
# in docs/acquisition/ACQUISITION_DECISION_REPORT.md section 1.2 (not fetched).
PORTAL = {
    "WATER-BWSSB-2025-06": (
        "water-consumption-data-month-june-2025",
        "Water consumption Data for the month of June 2025",
        "Water consumption data",
        "10/07/2025",
        "10/07/2025",
        "6.5 KB",
        None,
        F2 + "Water_Consumption_Data_June_2025.csv",
    ),
    "WATER-BWSSB-2025-07": (
        "bwssb-water-consumption-data-month-july-2025",
        "BWSSB Water consumption data for the month of July-2025",
        "Water consumption data",
        "30/08/2025",
        "30/08/2025",
        "5.7 KB",
        None,
        F + "Water_Consumption_Data_July_2025_0.csv",
    ),
    "WATER-BWSSB-2025-09": (
        "bwssb-water-consumption-data-month-septemeber-2025",
        "BWSSB Water Consumption data for the month of Septemeber 2025",
        "Water consumption data",
        "09/12/2025",
        "09/12/2025",
        "5.7 KB",
        None,
        "UNRECORDED: the catalogue exposed only a signed, expiring link; the route used for "
        "this copy is not recorded",
    ),
    "WATER-BWSSB-2025-10": (
        "water-consumption-data-month-october-25",
        "Water consumption data for the month of October-25",
        "Water consumption data",
        "05/02/2026",
        "05/02/2026",
        "5.7 KB",
        None,
        F + "Water_Consumption_Data_Oct_25_3.csv",
    ),
    "WATER-BWSSB-2025-11": (
        "water-consumption-data-month-november-25",
        "Water consumption data for the month of November-25",
        "Water consumption data",
        "05/02/2026",
        "05/02/2026",
        "5.7 KB",
        None,
        F + "Water_Consumption_Data_Nov_25_2.csv",
    ),
    "WATER-BWSSB-2025-12": (
        "bwssb-water-consumption-data-month-december-25",
        "BWSSB Water consumption data for the month of December-25",
        "Water consumption data",
        "05/02/2026",
        "05/02/2026",
        "5.7 KB",
        None,
        F + "Water_Consumption_Data_Dec_25_5.csv",
    ),
    "WATER-BWSSB-2026-01": (
        "water-consumption-data-month-january-2026",
        "Water consumption data for the month of January-2026",
        "Water Consumption Data-2026",
        "04/05/2026",
        "04/05/2026",
        "5.7 KB",
        None,
        F + "Water_Consumption_Data_Jan_26_0_0.csv",
    ),
    "WATER-BWSSB-2026-02": (
        "water-consumption-data-month-february-2026",
        "Water consumption data for the month of February-2026",
        "Water Consumption Data-2026",
        "04/05/2026",
        "04/05/2026",
        "5.7 KB",
        None,
        F + "Water_Consumption_Data_Feb_26_0_1.csv",
    ),
    "ROAD-RA2020-A47": (
        "cities-wise-accidents-classified-according-type-traffic-violations-million-plus-cities-0",
        "Cities-wise Accidents Classified according to Type of Traffic Violations in Million "
        "Plus Cities during 2020",
        "Road Accidents in India 2020",
        "26/04/2023",
        "26/04/2023",
        "6.5 KB",
        "NA- Not Available. Data values are in Numbers",
        OGD20 + "RA2020_A47.csv",
    ),
    "ROAD-RA2021-A47": (
        "cities-wise-accidents-classified-according-type-traffic-violations-million-plus-cities-1",
        "Cities-wise Accidents Classified according to Type of Traffic Violations in Million "
        "Plus Cities during 2021",
        "Road Accidents in India 2021",
        "25/09/2023",
        "25/09/2023",
        "6.5 KB",
        "NA- Not Available. Data values are in Numbers. Note- 1. The Data for the "
        "years 2017, 2018, 2019 and 2020 of Tamil Nadu is undergoing revision.",
        OGD20 + "RA2021_A47.csv",
    ),
    "ROAD-RA2022-A47": (
        "million-plus-city-wise-number-accidents-classified-according-type-traffic-violations",
        "Million Plus City-wise Number of Accidents Classified According to Type of Traffic "
        "Violations in Million Plus Cities during 2022",
        "Road Accidents in India 2022",
        "05/06/2026",
        "05/06/2026",
        "6.7 KB",
        "NA - Not Available.",
        F + "604784046/Version_1/Transport_2022_Annexure_47.csv",
    ),
    "ROAD-RA2023-A47": (
        "million-plus-cities-wise-number-accidents-classified-according-type-traffic-rule",
        "Million Plus Cities-wise Number of Accidents Classified according to Type of Traffic "
        "Rule Violations in Million Plus Cities during 2023",
        "Road Accidents in India 2023",
        "30/05/2026",
        "30/05/2026",
        "6.8 KB",
        "Data Figures are in Number. NA - Not Available.",
        F + "604777242/Version_1/Transport_2023_Annexure_47.csv",
    ),
    "ROAD-RA2024-A1": (
        "year-wise-details-road-accidents-persons-killed-and-injured-1970-2024",
        "Year-wise Details of Road Accidents, Persons Killed and Injured from 1970 to 2024",
        "Road Accidents in India 2024",
        "19/06/2026",
        "19/06/2026",
        "3.8 KB",
        "Sources - 1. Accidents - State Police Authorities. 2. Population- For year 2021 "
        "onwards, as per projections of Registrar General of India (July, 2020). 3. Road Length "
        "- Basic Road Statistics (M/o Road Transport and Highways). 4. Vehicles - Road "
        "Transport Year Book (M/o Road Transport and Highways). 1. Road length is inclusive of "
        "all roads constructed under Jawahar Rozgar Yojana. 2. Road Length for year 2021 and "
        "2022 is provisional. 3. Data have been reconciled for West Bengal for the calendar "
        "year 2015 to 2017, 2019 & 2020 and Tamil Nadu for the calendar year 2017 to 2020. "
        "4. Data for Road Length and Registered Motor Vehicles is for the financial year. "
        "5. Data for Road Accident is for the calendar year. * Figures for road length for the "
        "year 2023 and 2024 are not available. # Data for the year 1971. ## Data for the year "
        "1981. Kilometers (kms). CAGR - Compound Annual Growth Rate. NA - Not Available.",
        F + "604807230/Version_1/Transport_2024_Annexure_1.csv",
    ),
    "ROAD-RA2024-A2": (
        "stateut-wise-number-road-accidents-india-2021-2024",
        "State/UT-wise Number of Road Accidents in India from 2021 to 2024",
        "Road Accidents in India 2024",
        "19/06/2026",
        "19/06/2026",
        "4.0 KB",
        "1. Road length is exclusive of all roads constructed under Jawahar Rozgar Yojana. "
        "2. Road Length for year 2022 is provisional. (P) - Provisional. NA - Not Available.",
        F + "604807238/Version_1/Transport_2024_Annexure_2.csv",
    ),
    "ROAD-RA2024-A49": (
        "million-plus-city-wise-accidents-classified-according-type-junctions-during-2024",
        "Million Plus City-wise Accidents Classified According to Type of Junctions during 2024",
        "Road Accidents in India 2024",
        "18/06/2026",
        "18/06/2026",
        "5.6 KB",
        "Data Figures are in Number. NA - Not Available",
        F + "604807642/Version_1/Transport_2024_Annexure_49.csv",
    ),
}

# Catalogue-API sizes recorded on 2026-10-17 (docs/discovery/civicmind_dataset_catalog.csv).
PORTAL_BYTES = {
    "WATER-BWSSB-2025-06": 6624,
    "WATER-BWSSB-2025-07": 5844,
    "WATER-BWSSB-2025-09": 5845,
    "WATER-BWSSB-2025-10": 5844,
    "WATER-BWSSB-2025-11": 5841,
    "WATER-BWSSB-2025-12": 5843,
    "WATER-BWSSB-2026-01": 5845,
    "WATER-BWSSB-2026-02": 5848,
    "ROAD-RA2020-A47": 6607,
    "ROAD-RA2021-A47": 6640,
    "ROAD-RA2022-A47": 6870,
    "ROAD-RA2023-A47": 6918,
    "ROAD-RA2024-A1": 3939,
    "ROAD-RA2024-A2": 4074,
    "ROAD-RA2024-A49": 5762,
}

# Owner decisions of this stage (chat, 2026-10-17): advance / keep quarantined / separate.
ADVANCE_WATER = ("2025-07", "2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02")
ADVANCE_A47 = ("ROAD-RA2020-A47", "ROAD-RA2021-A47", "ROAD-RA2022-A47", "ROAD-RA2023-A47")
SEPARATE_2024 = ("ROAD-RA2024-A1", "ROAD-RA2024-A2", "ROAD-RA2024-A49")

BWSSB_LIMITS = [
    "Recorded consumption, not supply; bulk and commercial connections included.",
    "Ward numbering (1-198) does not by itself establish the BBMP-2010 scheme.",
]
MORTH_LIMITS = [
    "City-level only; MoRTH's city boundary definition is not established - never join to "
    "ward data.",
    "Later editions may restate earlier years; cite the edition.",
    "Category allocation between violation types (notably Over-Speeding vs Others) varies by "
    "city and year; single-city category trends need the per-city stability caveat.",
    "Whether the six categories partition all city accidents is not established; never "
    "report their sum as 'total accidents'.",
]
TN_CITIES = "Chennai, Coimbatore, Madurai, Tiruchirapalli"

SWING_THRESHOLD = 0.30
PROPOSED = "proposed check (Batch 02 intake), not yet implemented in the validator"


def finding(code, severity, message, details=None) -> dict:
    return {"code": code, "severity": severity, "message": message, "details": details or {}}


def iso(ddmmyyyy: str) -> str:
    d, m, y = ddmmyyyy.split("/")
    return f"{y}-{m}-{d}"


def attribution(publisher: str, title: str, published: str, page: str) -> str:
    d, m, y = published.split("/")
    return (
        f"{publisher}, {y}, {title}, Open Government Data Platform India, {d}/{m}, {page}. "
        "Published under Government Open Data License - India: https://www.data.gov.in/Godl."
    )


def downloads_mtime(name: str) -> str | None:
    path = DOWNLOADS / name
    if not path.is_file():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, IST).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- proposed checks
def water_series() -> dict[str, object]:
    """Trusted + advancing months only, aligned on the identical (ward, name) row sequence."""
    months = {
        "2025-08": ROOT / "data/raw/water/BWSSB_Water_Consumption_August_2025.csv",
        "2026-03": ROOT / "data/raw/water/Water_Consumption_Data_Mar_26_0.csv",
    }
    for _d, rel, fam, period in CANDIDATES:
        if fam == "bwssb" and period in ADVANCE_WATER:
            months[period] = STAGE / rel
    return {m: water_table(load(p)[2]) for m, p in sorted(months.items())}


def swing_findings(series: dict, month: str) -> list[dict]:
    order = sorted(series)
    i = order.index(month)
    if i == 0:
        return []
    prev = order[i - 1]
    y, mm = map(int, prev.split("-"))
    expected = f"{y + (mm == 12)}-{(mm % 12) + 1:02d}"
    if expected != month:
        return []  # predecessor month not in the trusted/advancing series (e.g. June)
    a, b = series[prev], series[month]
    if list(zip(a.ward, a.name, strict=True)) != list(zip(b.ward, b.name, strict=True)):
        return [
            finding(
                "series.row_keys_changed",
                "warning",
                f"(ward, name) rows differ from {prev}; rows not compared",
                {},
            )
        ]
    rows = []
    for k in range(len(a)):
        for col, floor in (("connections", 200), ("ml", 10.0)):
            x, z = float(a[col].iat[k]), float(b[col].iat[k])
            if max(x, z) < floor or x == 0:
                continue
            rel = (z - x) / x
            if abs(rel) >= SWING_THRESHOLD:
                rows.append(
                    {
                        "ward": int(a.ward.iat[k]),
                        "name": a.name.iat[k],
                        "column": col,
                        prev: x,
                        month: z,
                        "relative_change": round(rel, 3),
                    }
                )
    if not rows:
        return []
    return [
        finding(
            "series.swing",
            "warning",
            f"{len(rows)} row values changed by >= 30% from {prev} (published as-is; "
            f"not corrected; cause not established) [{PROPOSED}]",
            {"rows": rows},
        )
    ]


def zero_accident_findings(frame) -> list[dict]:
    rows = a47_summary(frame)["casualties_with_zero_accidents"]
    if not rows:
        return []
    return [
        finding(
            "casualties.zero_accidents",
            "warning",
            f"{len(rows)} category rows report casualties with zero accidents "
            f"(published as-is; unresolved source inconsistency) [{PROPOSED}]",
            {"rows": rows},
        )
    ]


# --------------------------------------------------------------------------- manifests
def build(dataset_id: str, rel: str, family: str, period: str, series: dict) -> Manifest:
    slug, title, catalog, published, updated, size, note, url = PORTAL[dataset_id]
    page = RES + slug
    path = STAGE / rel
    fp, header, frame = load(path)
    publisher = BWSSB if dataset_id.startswith("WATER") else MORTH
    water = dataset_id.startswith("WATER")
    findings: list[dict] = []
    if fp.newline not in ("CRLF", "LF"):
        findings.append(
            finding(
                "file.newline_style",
                "warning",
                f"Unusual line endings ({fp.newline}); parsed with universal "
                "newlines in memory, file unchanged",
                fp.newline_counts,
            )
        )
    validator = None
    if family == "bwssb":
        validator = "bwssb@v1"
        findings += [f.to_dict() for f in bwssb_monthly.validate(frame, header)]
        if period in ADVANCE_WATER:
            findings += swing_findings(series, period)
    elif dataset_id in ADVANCE_A47:
        validator = "morth_city@v1"
        findings += [f.to_dict() for f in morth_city_table.validate(frame, header)]
        findings += zero_accident_findings(frame)
    elif dataset_id == "ROAD-RA2024-A49":
        # Provisional: the A47 validator's generic checks apply, but no A49 family exists.
        findings += [
            {**f.to_dict(), "message": f.message + " [morth_city@v1 run provisionally]"}
            for f in morth_city_table.validate(frame, header)
        ]
    hits = scan_header(header)
    findings.append(
        finding(
            "sensitivity.header_scan",
            "info",
            "No column name suggests personal data",
            {"method": SENSITIVITY_METHOD, "matched": hits},
        )
    )
    errors = sum(f["severity"] == "error" for f in findings)
    warnings = sum(f["severity"] == "warning" for f in findings)
    if dataset_id == "WATER-BWSSB-2025-06":
        status = "quarantined"
    elif validator is None or dataset_id in SEPARATE_2024:
        status = "integrity_passed"
    else:
        status = "quarantined" if errors else "validated"

    limits = list(BWSSB_LIMITS if water else MORTH_LIMITS[:2])
    if dataset_id in ADVANCE_A47:
        limits = list(MORTH_LIMITS)
    if dataset_id == "ROAD-RA2020-A47":
        limits.append(
            "Publisher note on the 2021 edition: Tamil Nadu data for 2017-2020 was 'undergoing "
            "revision'; A1 (2024 edition) says it was reconciled. Values for "
            f"{TN_CITIES} in this 2020 edition may be superseded."
        )
    if dataset_id == "ROAD-RA2021-A47":
        limits.append(
            "Pune Over-Speeding: 0 accidents with 6 killed and 15 injured "
            "(published as-is; unresolved)."
        )
    if dataset_id == "ROAD-RA2024-A1":
        limits += [
            "National series; irregular years (1970, 1980, 1990, 1995-2024); exclude the "
            "'CAGR 2014/2024' row.",
            "Publisher note: '# Data for the year 1971. ## Data for the year 1981.' The CSV does "
            "not carry the markers; the 1970/1980 per-10,000-km rates do not reproduce from the "
            "1970/1980 road length (probably because a 1971/1981 value was used; not confirmed).",
            "Road length and vehicles are financial-year; accidents calendar-year (publisher).",
        ]
    if dataset_id == "ROAD-RA2024-A2":
        limits += [
            "State/UT level; 2021-2023 values are as restated in the 2024 edition.",
            "Shares rounded to 0.1; 2022 per-km rates provisional (P); Ladakh per-vehicle NA.",
        ]
    if dataset_id == "ROAD-RA2024-A49":
        limits += [
            "Five junction types only (no 'not at junction'/'others'): not a partition of all "
            "city accidents; never combine with Annexure 47.",
        ]

    retrieval_note = (
        "Copied byte-identically (cp -p, hash-checked) from the project owner's Downloads "
        f"folder to {(STAGE / rel).relative_to(ROOT).as_posix()}. retrieved_at is the Downloads "
        "file's modification time. UNVERIFIED: who downloaded it and by which route "
        "(resource-page form or direct link) is not recorded."
    )
    if status == "quarantined":
        retrieval_note += (
            " PROPOSED: move to data/quarantine/batch-02/ when the processor runs (not moved "
            "in this stage)."
        )
    geo = (
        {"state": "Karnataka", "city": "Bengaluru", "level": "ward"}
        if water
        else (
            {"level": "national"}
            if dataset_id.endswith("-A1")
            else {"level": "state"}
            if dataset_id.endswith("-A2")
            else {"level": "million-plus city"}
        )
    )
    if water:
        y, m = map(int, period.split("-"))
        end = (datetime(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).date().isoformat()
        per = {"start": f"{period}-01", "end": end, "granularity": "month"}
    elif dataset_id.endswith("-A1"):
        per = {"start": "1970-01-01", "end": "2024-12-31", "granularity": "year"}
    elif dataset_id.endswith("-A2"):
        per = {"start": "2021-01-01", "end": "2024-12-31", "granularity": "year"}
    else:
        per = {"start": f"{period}-01-01", "end": f"{period}-12-31", "granularity": "year"}
    semantic = (
        {"validator": validator, "errors": errors, "warnings": warnings}
        if validator
        else {
            "validator": None,
            "note": "No validator for this family yet; profiled only. "
            "Not eligible for promotion until a family validator is approved and passes.",
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
                "retrieved_by": "UNVERIFIED (project owner, outside the repository)",
                "method": "UNRECORDED (manual acquisition outside the repository)",
                "original_filename": path.name,
                "local_path": (STAGE / rel).relative_to(ROOT).as_posix(),
                "note": retrieval_note,
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
                "passed": fp.bytes == PORTAL_BYTES[dataset_id]
                and fp.encoding is not None
                and not fp.looks_like_html
                and not fp.contains_nul,
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
            "known_limitations": limits,
        }
    )


# --------------------------------------------------------------------------- schemas
def proposed_schemas() -> dict:
    out = {}
    specs = {
        "morth_city_a47/ra2020": ("RA2020_A47.csv", "ROAD-RA2020-A47, ROAD-RA2021-A47"),
        "morth_city_a47/ra2022": ("Transport_2022_Annexure_47.csv", "ROAD-RA2022-A47"),
        "morth_city_a47/ra2023": ("Transport_2023_Annexure_47.csv", "ROAD-RA2023-A47"),
        "morth_city_a49/ra2024": ("Transport_2024_Annexure_49.csv", "ROAD-RA2024-A49"),
        "morth_state_a2/ra2024": ("Transport_2024_Annexure_2.csv", "ROAD-RA2024-A2"),
        "morth_national_a1/ra2024": ("Transport_2024_Annexure_1.csv", "ROAD-RA2024-A1"),
    }
    for version, (name, applies) in specs.items():
        _fp, header, _ = load(STAGE / "roads" / name)
        label = next(h for h in header if h in ("Million Plus Cities", "State/UT", "Years"))
        serial = [h for h in header if re.fullmatch(r"Sl\. ?No\.?", h)]
        numeric = [h for h in header if h not in (label, *serial)]
        out[version] = {
            "family": version.split("/")[0],
            "applies_to": applies,
            "level": {"Years": "national", "State/UT": "state"}.get(label, "million-plus city"),
            "label_column": label,
            "serial_columns": serial,
            "rank_columns": [h for h in header if h.strip().lower().endswith("rank")],
            "numeric_columns": numeric,
            "columns": header,
            "registered": False,
        }
    return out


def register_in_memory(specs: dict, versions: tuple[str, ...]) -> None:
    """Dry run only: add proposed versions to this process's registry (no file changes)."""
    for v in versions:
        s = specs[v]
        sv = schema_registry.SchemaVersion(
            family=s["family"],
            version=v,
            columns=tuple(s["columns"]),
            level=s["level"],
            id_column=None,
            label_column=s["label_column"],
            numeric_columns=tuple(s["numeric_columns"]),
            rank_columns=tuple(s["rank_columns"]),
            validator="morth_city",
        )
        schema_registry._BY_HEADER[sv.columns] = sv
        schema_registry._BY_VERSION[sv.version] = sv


# --------------------------------------------------------------------------- dry run
def simulate(m: Manifest, rel: str, caveats: list[str] | None = None) -> dict:
    """Run real trusted ingestion on a temporary copy with a simulated accept review."""
    domain = "water" if m.dataset_id.startswith("WATER") else "roads"
    warnings = sorted({f["code"] for f in m.findings if f["severity"] == "warning"})
    accepted = warnings if caveats is None else caveats
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "data/raw" / domain / Path(rel).name
        target.parent.mkdir(parents=True)
        shutil.copyfile(STAGE / rel, target)
        sim = m.model_copy(
            update={
                "status": "promoted",
                "human_review": "accepted",
                "promoted_to": f"data/raw/{domain}/{target.name}",
                "review": Review(
                    decision="accept",
                    reviewed_by="SIMULATION (not a decision)",
                    reviewed_on="2026-10-17",
                    sha256=m.integrity.sha256,
                    accepted_caveats=accepted,
                ),
            }
        )
        try:
            ds = ingest(sim, tmp, "trusted")
        except IngestionRefused as exc:
            return {
                "result": "refused",
                "code": exc.code,
                "details": exc.details,
                "accepted_caveats_simulated": accepted,
            }
        return {
            "result": "ingested",
            "schema_version": ds.schema_version,
            "rows": len(ds.raw),
            "ingest_warnings": sorted({f.code for f in ds.findings if f.severity == "warning"}),
            "manifest_warnings": warnings,
            "accepted_caveats_simulated": accepted,
        }


def main() -> None:
    target = OUT / "proposed_manifests"
    target.mkdir(parents=True, exist_ok=True)
    series = water_series()
    manifests = {}
    for dataset_id, rel, family, period in CANDIDATES:
        m = build(dataset_id, rel, family, period, series)
        write_manifest(m, target)
        manifests[dataset_id] = (m, rel)
    specs = proposed_schemas()
    (OUT / "proposed_schemas.yaml").write_text(
        "# PROPOSED schema registrations for catalog/schemas.py (verbatim headers, no aliasing).\n"
        "# Generated by scripts/propose_batch_02.py from the staged files. NOT registered.\n"
        + yaml.safe_dump(specs, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
        newline="\n",
    )
    register_in_memory(
        specs, ("morth_city_a47/ra2020", "morth_city_a47/ra2022", "morth_city_a47/ra2023")
    )
    dry = {"note": "Simulated accept reviews in a temporary directory; nothing promoted."}
    for dataset_id, (m, rel) in manifests.items():
        if dataset_id in ADVANCE_A47 or (
            dataset_id.startswith("WATER") and dataset_id != "WATER-BWSSB-2025-06"
        ):
            dry[dataset_id] = simulate(m, rel)
    # Negative controls: the gate must still refuse these.
    june, june_rel = manifests["WATER-BWSSB-2025-06"]
    dry["CONTROL June 2025 forced through as promoted"] = simulate(
        june.model_copy(update={"status": "validated"}), june_rel
    )
    jan, jan_rel = manifests["WATER-BWSSB-2026-01"]
    dry["CONTROL Jan 2026 with no caveats accepted"] = simulate(jan, jan_rel, caveats=[])
    a49, a49_rel = manifests["ROAD-RA2024-A49"]
    dry["CONTROL A49 with no registered schema"] = simulate(
        a49.model_copy(update={"status": "validated"}), a49_rel
    )
    (OUT / "dry_run_ingest.json").write_text(json.dumps(dry, indent=2, default=str), "utf-8")
    for k, v in dry.items():
        if k != "note":
            print(
                k,
                "->",
                v["result"],
                v.get("code") or v.get("schema_version"),
                v.get("details") or v.get("manifest_warnings"),
            )


if __name__ == "__main__":
    main()
