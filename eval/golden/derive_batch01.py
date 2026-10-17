"""Independent derivation of the batch-01 golden answers (standard library only).

This module deliberately shares no code with ``civicmind``: it reads the promoted CSVs with
``csv`` and ``decimal``. ``derive()`` returns the expected value of every answerable item in
``batch01_analytics.v1.yaml``; tests/test_golden_analytics.py checks the YAML against it. If
they disagree, the YAML is wrong or a source file changed; investigate before editing either.

Usage (from the repository root), to print the derived values:
    .venv-py313/Scripts/python.exe -I eval/golden/derive_batch01.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = {
    "aug": ("data/raw/water/BWSSB_Water_Consumption_August_2025.csv", "108639ce"),
    "mar": ("data/raw/water/Water_Consumption_Data_Mar_26_0.csv", "798243f9"),
    "r19": ("data/raw/roads/RA2019_A47.csv", "40bed81d"),
    "r24": ("data/raw/roads/Transport_2024_Annexure_47.csv", "702f75f3"),
}
DAYS = {"aug": 31, "mar": 31}  # August 2025 and March 2026
ACCIDENTS = "Over-Speeding - Number of Accidents - Number"
KILLED = "Over-Speeding - Persons Killed - Number"


def available() -> bool:
    return all((ROOT / rel).is_file() for rel, _ in FILES.values())


def rows(key: str) -> list[list[str]]:
    rel, sha_prefix = FILES[key]
    data = (ROOT / rel).read_bytes()
    assert hashlib.sha256(data).hexdigest().startswith(sha_prefix), f"{rel} changed"
    reader = csv.reader(io.StringIO(data.decode("utf-8"), newline=None))
    return [r for r in reader if r]


def _f(value: Decimal, places: int = 6) -> float | int:
    value = round(value, places)
    return int(value) if value == value.to_integral_value() else float(value)


def _water(key: str) -> dict:
    table = rows(key)[1:]
    names: dict[int, list[str]] = {}
    for r in table:
        names.setdefault(int(r[0]), []).append(r[1].strip())
    by_ml = sorted(table, key=lambda r: (-Decimal(r[3]), int(r[0])))
    lpcd = sorted(
        (
            (Decimal(r[3]) * 1_000_000 / int(r[2]) / DAYS[key], int(r[0]), r[1].strip())
            for r in table
            if int(r[2]) > 0
        ),
        key=lambda t: (-round(t[0], 6), t[1]),
    )
    # As a reference month: intensity per exact (ward number, name), or why it is unusable.
    key_counts: dict[tuple[int, str], int] = {}
    for r in table:
        row_key = (int(r[0]), r[1].strip())
        key_counts[row_key] = key_counts.get(row_key, 0) + 1
    as_reference: dict[tuple[int, str], object] = {}
    for r in table:
        row_key = (int(r[0]), r[1].strip())
        if key_counts[row_key] != 1:
            as_reference[row_key] = "no unique match"
        elif int(r[2]) <= 0:
            as_reference[row_key] = "zero connections"
        else:
            intensity = Decimal(r[3]) * 1_000_000 / int(r[2]) / DAYS[key]
            as_reference[row_key] = round(intensity, 6)
    return {
        "lpcd": lpcd,
        "as_reference": as_reference,
        "connections_by_key": {(int(r[0]), r[1].strip()): int(r[2]) for r in table},
        "connections": sum(int(r[2]) for r in table),
        "ml": sum(Decimal(r[3]) for r in table),
        "duplicates": {str(k): v for k, v in sorted(names.items()) if len(v) > 1},
        "top_ml": [
            {
                "rank": i,
                "ward_number": int(r[0]),
                "ward_name": r[1].strip(),
                "value": _f(Decimal(r[3])),
            }
            for i, r in enumerate(by_ml[:3], start=1)
        ],
        "bottom_lpcd": [
            {
                "rank": 1,
                "ward_number": lpcd[-1][1],
                "ward_name": lpcd[-1][2],
                "value": _f(lpcd[-1][0]),
            }
        ],
        "top_lpcd": [
            {
                "rank": 1,
                "ward_number": lpcd[0][1],
                "ward_name": lpcd[0][2],
                "value": _f(lpcd[0][0]),
            }
        ],
    }


def _roads(key: str, label_index: int) -> dict:
    table = rows(key)
    header, body = table[0], table[1:]
    total = next(r for r in body if r[label_index].strip() == "Total")
    city = next(r for r in body if r[label_index].strip() == "Bengaluru")
    col, killed = header.index(ACCIDENTS), header.index(KILLED)
    cities = [r for r in body if r[label_index].strip() != "Total"]
    top = sorted(cities, key=lambda r: (-int(r[killed]), r[label_index].strip()))[:3]
    return {
        "bengaluru": {
            "value": int(city[col]),
            "share_of_total_pct": _f(Decimal(city[col]) / Decimal(total[col]) * 100, 4),
        },
        "top_killed": [
            {"rank": i, "city": r[label_index].strip(), "value": int(r[killed])}
            for i, r in enumerate(top, start=1)
        ],
    }


def _t10(row: dict, month: dict, references: dict[str, dict]) -> dict:
    """water_intensity_flags@v1, re-implemented from its written definition.

    small base: < 100 connections. Per reference: no unique exact (number, name) match or 0
    connections -> not_comparable; otherwise volatile if one intensity is 0 and the other
    positive, or the larger is >= 2x the smaller; else within_threshold (0 vs 0 included).
    Overall: not_assessed without references; volatile > not_comparable > within_threshold.
    """
    key = (row["ward_number"], row["ward_name"])
    value = round(Decimal(str(row["value"])), 6)
    status, values = {}, {}
    for ref_id, ref in references.items():
        found = ref["as_reference"].get(key, "no unique match")
        if isinstance(found, str):
            status[ref_id], values[ref_id] = "not_comparable", None
            continue
        low, high = sorted((value, found))
        volatile = (low == 0 and high > 0) or (low > 0 and high / low >= 2)
        status[ref_id] = "volatile" if volatile else "within_threshold"
        values[ref_id] = _f(found)
    if not status:
        overall = "not_assessed"
    elif "volatile" in status.values():
        overall = "volatile"
    elif "not_comparable" in status.values():
        overall = "not_comparable"
    else:
        overall = "within_threshold"
    flags = ["small_connection_base"] if month["connections_by_key"][key] < 100 else []
    flags += ["volatile_vs_reference"] if "volatile" in status.values() else []
    flags += ["not_comparable"] if "not_comparable" in status.values() else []
    return {
        **row,
        "reference_values": values,
        "reference_status": status,
        "volatility_status": overall,
        "flags": flags,
    }


def _status_counts(month: dict, references: dict[str, dict]) -> dict[str, int]:
    counts = dict.fromkeys(("volatile", "not_comparable", "within_threshold", "not_assessed"), 0)
    small = 0
    for value, ward, name in month["lpcd"]:
        row = {"ward_number": ward, "ward_name": name, "value": _f(value)}
        t = _t10(row, month, references)
        counts[t["volatility_status"]] += 1
        small += "small_connection_base" in t["flags"]
    return {**counts, "small_connection_base": small}


def derive() -> dict[str, object]:
    """Expected value per answerable golden item id."""
    aug, mar = _water("aug"), _water("mar")
    r19, r24 = _roads("r19", 0), _roads("r24", 1)
    change = mar["ml"] - aug["ml"]
    return {
        "G01": aug["connections"],
        "G02": _f(aug["ml"]),
        "G03": _f(mar["ml"]),
        "G04": {
            "earlier": _f(aug["ml"]),
            "later": _f(mar["ml"]),
            "change": _f(change),
            "pct_change": _f(change / aug["ml"] * 100, 4),
            "earlier_days": DAYS["aug"],
            "later_days": DAYS["mar"],
        },
        "G05": {
            "ranked_unit": "published_row",
            "duplicated_ward_numbers": aug["duplicates"],
            "rows": aug["top_ml"],
        },
        "G06": {"ranked_unit": "published_row", "rows": aug["top_lpcd"]},
        "G07": {"ranked_unit": "published_row", "rows": mar["top_lpcd"]},
        "G08": r19["bengaluru"],
        "G09": r24["bengaluru"],
        "G10": r24["top_killed"],
        "G22": {
            "ranked_unit": "published_row",
            "rows": [_t10(row, aug, {}) for row in aug["bottom_lpcd"]],
        },
        "G23": {
            "ranked_unit": "published_row",
            "rows": [_t10(mar["top_lpcd"][0], mar, {"WATER-BWSSB-2025-08": aug})],
        },
        "G25": {
            "flag_summary": {
                "all_ranked_rows": _status_counts(mar, {"WATER-BWSSB-2025-08": aug}),
            }
        },
    }


if __name__ == "__main__":
    print(json.dumps(derive(), indent=2, ensure_ascii=False))
