"""Batch 02 intake profiling (read-only).

Fingerprints, profiles and validates the 15 Batch 02 candidate files staged under
data/external/batch-02/, and runs cross-period comparisons against the Batch 01 trusted files
in data/raw/ (read only). Writes JSON evidence to docs/acquisition/batch-02/profiles/ and
docs/acquisition/batch-02/cross_checks.json. It never modifies, moves, promotes or
quarantines a data file, and it writes no manifests.

Usage: python scripts/profile_batch_02.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from civicmind.catalog.fingerprint import fingerprint
from civicmind.catalog.profile import profile_frame, read_raw_header, read_text_table
from civicmind.catalog.sensitivity import scan_header
from civicmind.catalog.validators import bwssb_monthly, morth_city_table
from civicmind.catalog.validators.base import to_number

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "data/external/batch-02"
OUT = ROOT / "docs/acquisition/batch-02"

# (dataset_id, staged path, validator family, period label)
CANDIDATES = [
    ("WATER-BWSSB-2025-06", "water/Water_Consumption_Data_June_2025.csv", "bwssb", "2025-06"),
    ("WATER-BWSSB-2025-07", "water/Water_Consumption_Data_July_2025_0.csv", "bwssb", "2025-07"),
    ("WATER-BWSSB-2025-09", "water/Water_Consumption_Data_Sept_25_4.csv", "bwssb", "2025-09"),
    ("WATER-BWSSB-2025-10", "water/Water_Consumption_Data_Oct_25_3.csv", "bwssb", "2025-10"),
    ("WATER-BWSSB-2025-11", "water/Water_Consumption_Data_Nov_25_2.csv", "bwssb", "2025-11"),
    ("WATER-BWSSB-2025-12", "water/Water_Consumption_Data_Dec_25_5.csv", "bwssb", "2025-12"),
    ("WATER-BWSSB-2026-01", "water/Water_Consumption_Data_Jan_26_0_0.csv", "bwssb", "2026-01"),
    ("WATER-BWSSB-2026-02", "water/Water_Consumption_Data_Feb_26_0_1.csv", "bwssb", "2026-02"),
    ("ROAD-RA2020-A47", "roads/RA2020_A47.csv", "morth_city", "2020"),
    ("ROAD-RA2021-A47", "roads/RA2021_A47.csv", "morth_city", "2021"),
    ("ROAD-RA2022-A47", "roads/Transport_2022_Annexure_47.csv", "morth_city", "2022"),
    ("ROAD-RA2023-A47", "roads/Transport_2023_Annexure_47.csv", "morth_city", "2023"),
    ("ROAD-RA2024-A1", "roads/Transport_2024_Annexure_1.csv", "morth_national", "1970-2024"),
    ("ROAD-RA2024-A2", "roads/Transport_2024_Annexure_2.csv", "morth_state", "2021-2024"),
    ("ROAD-RA2024-A49", "roads/Transport_2024_Annexure_49.csv", "morth_city", "2024"),
]

# Batch 01 files used only as comparison baselines (read only; statuses unchanged).
BASELINES = {
    "WATER-BWSSB-2025-04 (quarantined)": (
        "data/quarantine/batch-01/Water_consumtion_data_april_2025.csv",
        "2025-04",
    ),
    "WATER-BWSSB-2025-05 (quarantined)": (
        "data/quarantine/batch-01/Water_Consumption_Data_May_2025.csv",
        "2025-05",
    ),
    "WATER-BWSSB-2025-08 (trusted)": (
        "data/raw/water/BWSSB_Water_Consumption_August_2025.csv",
        "2025-08",
    ),
    "WATER-BWSSB-2026-03 (trusted)": (
        "data/raw/water/Water_Consumption_Data_Mar_26_0.csv",
        "2026-03",
    ),
    "ROAD-RA2019-A47 (trusted)": ("data/raw/roads/RA2019_A47.csv", "2019"),
    "ROAD-RA2024-A47 (trusted)": ("data/raw/roads/Transport_2024_Annexure_47.csv", "2024"),
}


def load(path: Path):
    fp = fingerprint(path)
    header = read_raw_header(path, fp.encoding)
    frame = read_text_table(path, fp.encoding)
    return fp, header, frame


def jsonable(value):
    return json.loads(
        json.dumps(value, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    )


# --------------------------------------------------------------------------- water
def water_table(frame: pd.DataFrame) -> pd.DataFrame:
    ward, name, conn, ml = frame.columns[:4]
    return pd.DataFrame(
        {
            "ward": to_number(frame[ward]).astype("Int64"),
            "name": frame[name].str.strip(),
            "connections": to_number(frame[conn]),
            "ml": to_number(frame[ml]),
            "ml_raw": frame[ml].str.strip(),
        }
    )


def decimals(text: str) -> int | None:
    m = re.fullmatch(r"-?\d+(?:\.(\d+))?", text or "")
    return len(m.group(1) or "") if m else None


def water_cross_checks(series: dict[str, pd.DataFrame]) -> dict:
    months = sorted(series)
    keys = {m: list(zip(t["ward"], t["name"], strict=True)) for m, t in series.items()}
    ref_month = "2025-08" if "2025-08" in keys else months[0]  # trusted Batch 01 month
    ref = keys[ref_month]
    totals = {
        m: {
            "rows": int(len(t)),
            "connections": int(t["connections"].sum()),
            "consumption_ml": round(float(t["ml"].sum()), 2),
            "ml_per_1000_connections": round(
                1000 * float(t["ml"].sum() / t["connections"].sum()), 3
            ),
            "max_decimals_ml": max(d for d in map(decimals, t["ml_raw"]) if d is not None)
            if any(decimals(v) is not None for v in t["ml_raw"])
            else None,
            "non_plain_ml_values": sorted({v for v in t["ml_raw"] if decimals(v) is None}),
        }
        for m, t in series.items()
    }
    # Row-key identity: same (ward, name) sequence in the same order every month?
    key_identity = {m: keys[m] == ref for m in months}
    # Per-row month-on-month changes, matched on row position only when keys are identical.
    swings = []
    for prev, cur in zip(months, months[1:], strict=False):
        if keys[prev] != keys[cur]:
            continue
        a, b = series[prev], series[cur]
        for i in range(len(a)):
            for col, floor in (("connections", 200), ("ml", 10.0)):
                x, y = a[col].iat[i], b[col].iat[i]
                if pd.isna(x) or pd.isna(y) or max(x, y) < floor:
                    continue
                rel = (y - x) / x if x else float("inf")
                if abs(rel) >= 0.3:
                    swings.append(
                        {
                            "from": prev,
                            "to": cur,
                            "row": i + 1,
                            "ward": int(a["ward"].iat[i]),
                            "name": a["name"].iat[i],
                            "column": col,
                            "before": float(x),
                            "after": float(y),
                            "relative_change": None if rel == float("inf") else round(rel, 3),
                        }
                    )
    # Byte/content duplicates between months.
    content = {
        m: tuple(map(tuple, t[["ward", "name", "connections", "ml"]].astype(str).values))
        for m, t in series.items()
    }
    same_content = [
        [m1, m2]
        for i, m1 in enumerate(months)
        for m2 in months[i + 1 :]
        if content[m1] == content[m2]
    ]
    # Per-ward trajectories for rows that swing, to show reversals.
    trajectories = {}
    for s in swings:
        k = f"{s['ward']} {s['name']}"
        if k not in trajectories:
            row = s["row"] - 1
            trajectories[k] = {
                m: {
                    "connections": float(series[m]["connections"].iat[row]),
                    "ml": float(series[m]["ml"].iat[row]),
                }
                for m in months
                if keys[m] == ref
            }
    return {
        "months": months,
        "reference_month": ref_month,
        "row_key_identical_to_reference_month": key_identity,
        "totals": totals,
        "identical_content_pairs": same_content,
        "swings_ge_30pct": swings,
        "swing_trajectories": trajectories,
    }


# --------------------------------------------------------------------------- roads
CITY_ALIASES_OBSERVED = {
    "Allahabad(Prayagraj)": "Allahabad (Prayagraj)",
    "Khozikode": "Kozhikode",
    "Thiruvanthapuram": "Thiruvananthapuram",
    "Tiruchirapalli": "Tiruchirappalli",
    "Vadodra": "Vadodara",
    "Vijaywada city": "Vijayawada city",
    "Vizaq": "Vishakhapatnam",
}

CATEGORY_PATTERN = re.compile(
    r"^(?P<cat>.+?)\s*-\s*(?P<measure>Number of Accidents|Persons Killed)"
)


def label_col(frame: pd.DataFrame) -> str:
    return morth_city_table.find_label_column(list(frame.columns)) or frame.columns[0]


def norm_category(cat: str) -> str:
    c = re.sub(r"\s+", " ", cat).strip().lower().replace("&", "and").replace("/ ", "/")
    return c


def a47_summary(frame: pd.DataFrame) -> dict:
    lab = label_col(frame)
    body = frame[frame[lab].str.strip().str.lower() != "total"]
    cats: dict[str, dict[str, str]] = {}
    for col in frame.columns:
        m = CATEGORY_PATTERN.match(col)
        if m and "rank" not in col.lower():
            cats.setdefault(norm_category(m.group("cat")), {})[m.group("measure")] = col
    city = body[lab].str.strip().map(lambda n: CITY_ALIASES_OBSERVED.get(n, n))
    acc = sum(to_number(body[c["Number of Accidents"]]) for c in cats.values())
    killed = sum(to_number(body[c["Persons Killed"]]) for c in cats.values())
    per_city = pd.DataFrame(
        {"city": city.values, "accidents": acc.values, "killed": killed.values}
    )
    # Casualties recorded where the category shows zero accidents.
    zero_acc = []
    for cat, cols in cats.items():
        a = to_number(body[cols["Number of Accidents"]])
        k = to_number(body[cols["Persons Killed"]])
        inj_cols = [
            c
            for c in frame.columns
            if c.startswith(cols["Persons Killed"].split(" - ")[0]) and c.endswith("Total Injured")
        ]
        inj = to_number(body[inj_cols[0]]) if inj_cols else pd.Series(0, index=body.index)
        for i in body.index[(a == 0) & ((k > 0) | (inj > 0))]:
            zero_acc.append(
                {
                    "category": cat,
                    "city": body.at[i, lab].strip(),
                    "killed": float(k[i]),
                    "injured": float(inj[i]),
                }
            )
    return {
        "categories": sorted(cats),
        "cities_raw": body[lab].str.strip().tolist(),
        "per_city": per_city,
        "casualties_with_zero_accidents": zero_acc,
    }


def rank_check(frame: pd.DataFrame) -> list[dict]:
    """Check each 'Rank' column against competition ranking (1 = highest) of its value column."""
    lab = label_col(frame)
    body = frame[frame[lab].str.strip().str.lower() != "total"]
    cols = list(frame.columns)
    out = []
    for i, col in enumerate(cols):
        if not col.strip().lower().endswith("rank") or i == 0:
            continue
        values = to_number(body[cols[i - 1]])
        published = to_number(body[col])
        expected = values.rank(method="min", ascending=False)
        bad = body.loc[(expected != published), lab].str.strip().tolist()
        out.append({"rank_column": col, "value_column": cols[i - 1], "mismatched_rows": bad})
    return out


def national_a1_checks(frame: pd.DataFrame) -> dict:
    year = frame["Years"].str.strip()
    body = frame[year.str.fullmatch(r"\d{4}")]
    acc = to_number(body["Total Number of Road Accidents (in numbers)"])
    pop = to_number(body["Population of India (in thousands)"])
    veh = to_number(body["Total Number of Registered Motor Vehicles (in thousands)"])
    road = to_number(body["Road Length (in kms)"])
    checks = {}
    for label, num, den, scale, col in (
        ("accidents_per_lakh_pop", acc, pop, 100, "Number of Accidents per Lakh Population"),
        (
            "accidents_per_10k_vehicles",
            acc,
            veh,
            10,
            "Number of Accidents per Ten Thousand Vehicles",
        ),
        (
            "accidents_per_10k_km",
            acc,
            road,
            10000,
            "Number of Accidents per Ten Thousand Kms of Roads",
        ),
    ):
        computed = num / (den / scale)
        published = to_number(body[col])
        diff = (computed - published).abs()
        bad = body.loc[diff > 0.1, "Years"].tolist()
        checks[label] = {
            "rows_checked": int(published.notna().sum()),
            "rows_off_by_more_than_0.1": bad,
            "max_abs_diff": round(float(diff.max()), 3),
        }
    gaps = sorted(set(range(1970, 2025)) - set(map(int, year[year.str.fullmatch(r"\d{4}")])))
    return {
        "year_rows": int(len(body)),
        "first_year": year[year.str.fullmatch(r"\d{4}")].iloc[0],
        "last_year": year[year.str.fullmatch(r"\d{4}")].iloc[-1],
        "years_missing_from_1970_2024": gaps,
        "non_year_rows": frame.loc[~year.str.fullmatch(r"\d{4}"), "Years"].tolist(),
        "rate_recomputation": checks,
        "NA_cells_by_column": {
            c: int((frame[c].str.strip() == "NA").sum())
            for c in frame.columns
            if (frame[c].str.strip() == "NA").any()
        },
    }


def state_a2_checks(frame: pd.DataFrame) -> dict:
    lab = "State/UT"
    total_mask = frame[lab].str.strip().str.lower() == "total"
    body = frame[~total_mask]
    out = {"state_rows": int(len(body)), "sum_vs_total": [], "share_sums": {}}
    for col in frame.columns[2:]:
        values = to_number(body[col])
        published = to_number(frame.loc[total_mask, col]).iloc[0]
        if "Number of Road Accidents during" in col and "Rank" not in col:
            out["sum_vs_total"].append(
                {"column": col, "sum": float(values.sum()), "total": float(published)}
            )
        if col.startswith("Share of"):
            out["share_sums"][col] = round(float(values.sum()), 1)
    out["NA_cells"] = {
        c: body.loc[body[c].str.strip() == "NA", lab].tolist()
        for c in frame.columns
        if (body[c].str.strip() == "NA").any()
    }
    karnataka = body[body[lab].str.strip() == "Karnataka"].iloc[0].to_dict()
    out["karnataka_row"] = karnataka
    return out


# --------------------------------------------------------------------------- main
def main() -> None:
    (OUT / "profiles").mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    summary = []
    for dataset_id, rel, family, period in CANDIDATES:
        path = STAGE / rel
        fp, header, frame = load(path)
        frames[dataset_id] = frame
        if family == "bwssb":
            findings = bwssb_monthly.validate(frame, header)
        elif family == "morth_city":
            findings = morth_city_table.validate(frame, header)
        else:
            findings = []  # no Batch 01 validator covers national/state tables
        extra: dict = {}
        if family == "morth_city":
            extra["rank_check"] = rank_check(frame)
            if "47" in dataset_id:
                s = a47_summary(frame)
                extra["a47"] = {k: v for k, v in s.items() if k != "per_city"}
        elif family == "morth_national":
            extra["a1"] = national_a1_checks(frame)
        elif family == "morth_state":
            extra["a2"] = state_a2_checks(frame)
            extra["rank_check"] = rank_check(frame)
        profile = {
            "dataset_id": dataset_id,
            "staged_path": f"data/external/batch-02/{rel}",
            "period_label_from_filename_or_content": period,
            "fingerprint": fp.to_dict(),
            "raw_header": header,
            "profile": profile_frame(frame, header).to_dict(),
            "validator_family": family,
            "findings": [f.to_dict() for f in findings],
            "sensitivity_header_scan": scan_header(header),
            "extra_checks": extra,
        }
        profile["fingerprint"]["path"] = profile["staged_path"]
        (OUT / "profiles" / f"{dataset_id}.json").write_text(
            json.dumps(jsonable(profile), indent=2), encoding="utf-8"
        )
        summary.append(
            {
                "dataset_id": dataset_id,
                "bytes": fp.bytes,
                "sha256": fp.sha256,
                "newline": fp.newline,
                "encoding": fp.encoding,
                "rows": len(frame),
                "cols": len(header),
                "errors": [f.code for f in findings if f.severity == "error"],
                "warnings": [f.code for f in findings if f.severity == "warning"],
            }
        )

    # Water: Batch 02 months plus Batch 01 baselines, read only.
    water = {p: water_table(frames[d]) for d, _, fam, p in CANDIDATES if fam == "bwssb"}
    baseline_meta = {}
    for label, (rel, period) in BASELINES.items():
        fp, header, frame = load(ROOT / rel)
        baseline_meta[label] = {"sha256": fp.sha256, "header": header, "newline": fp.newline}
        if label.startswith("WATER"):
            water[period] = water_table(frame)
    cross = {"water": water_cross_checks(water), "baselines": baseline_meta}

    # Roads: A47 editions 2019-2024 side by side.
    a47 = {}
    headers = {}
    for label, (rel, period) in BASELINES.items():
        if label.startswith("ROAD"):
            _, header, frame = load(ROOT / rel)
            a47[period] = a47_summary(frame)
            headers[period] = header
    for d, rel, _fam, p in CANDIDATES:
        if "A47" in d:
            a47[p] = a47_summary(frames[d])
            headers[p] = read_raw_header(STAGE / rel, "utf-8")
    years = sorted(a47)
    city_sets = {y: sorted(a47[y]["per_city"]["city"]) for y in years}
    base = set(city_sets[years[-1]])
    cross["a47"] = {
        "years": years,
        "categories_by_year": {y: a47[y]["categories"] for y in years},
        "column_count_by_year": {y: len(headers[y]) for y in years},
        "header_drift_vs_2024": {
            y: morth_city_table.schema_drift(headers["2024"], headers[y])
            for y in years
            if y != "2024"
        },
        "city_set_after_observed_aliases": {
            y: {
                "count": len(city_sets[y]),
                "missing_vs_2024": sorted(base - set(city_sets[y])),
                "extra_vs_2024": sorted(set(city_sets[y]) - base),
            }
            for y in years
        },
        "observed_alias_map": CITY_ALIASES_OBSERVED,
        "bengaluru": {
            y: a47[y]["per_city"].set_index("city").loc["Bengaluru"].to_dict() for y in years
        },
        "all_city_sum_of_categories": {
            y: {
                "accidents": float(a47[y]["per_city"]["accidents"].sum()),
                "killed": float(a47[y]["per_city"]["killed"].sum()),
            }
            for y in years
        },
        "bengaluru_rank_by_sum_of_categories": {
            y: int(
                a47[y]["per_city"]["accidents"]
                .rank(method="min", ascending=False)[a47[y]["per_city"]["city"] == "Bengaluru"]
                .iloc[0]
            )
            for y in years
        },
    }
    # A1 national series vs A2 state totals (same 2024 edition).
    a1 = frames["ROAD-RA2024-A1"]
    a2 = frames["ROAD-RA2024-A2"]
    a2_total = a2[a2["State/UT"].str.strip() == "Total"].iloc[0]
    a1_rows = a1.set_index(a1["Years"].str.strip())
    cross["a1_vs_a2"] = [
        {
            "year": y,
            "a1_accidents": a1_rows.at[y, "Total Number of Road Accidents (in numbers)"],
            "a2_total": a2_total[col],
        }
        for y, col in (
            ("2021", "State / UT - wise Total Number of Road Accidents during - 2021"),
            ("2022", "State / UT - wise Total Number of Road Accidents during - 2022"),
            ("2023", "State / UT - wise Total Number of Road Accidents during - 2023"),
            ("2024", "State / UT - wise Total Number of Road Accidents during - 2024 - Number"),
        )
    ]
    (OUT / "cross_checks.json").write_text(json.dumps(jsonable(cross), indent=2), encoding="utf-8")
    print(json.dumps(jsonable(summary), indent=1))


if __name__ == "__main__":
    main()
