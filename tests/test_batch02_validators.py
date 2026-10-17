"""Batch 02 validator additions: warning flags only, never corrections or automatic rejection.

* ``morth_city_table`` reports ``casualties.zero_accidents`` (persons killed/injured in a
  category whose accident count is 0, e.g. Pune Over-Speeding in the 2021 edition).
* ``bwssb_monthly.series_swing`` compares adjacent months row by row and reports
  ``series.swing`` (>= 30% change) or ``series.not_comparable`` (row keys differ).
* The 2020-2023 Annexure 47 headers are registered as their own verbatim schema versions.
"""

from __future__ import annotations

import pandas as pd
import pytest

from civicmind.catalog.schemas import SCHEMAS, detect_schema, get_schema
from civicmind.catalog.validators import bwssb_monthly, morth_city_table

BATCH02_A47 = ("ra2020_2021", "ra2022", "ra2023")


def _text(rows, columns) -> pd.DataFrame:
    return pd.DataFrame([[str(v) for v in r] for r in rows], columns=columns, dtype=object)


# --------------------------------------------------------------------------- MoRTH A47
def _a47(rows) -> pd.DataFrame:
    cols = list(get_schema("morth_city_a47/ra2020_2021").columns)
    out = []
    for city, accidents, killed, grievous, minor in rows:
        values = dict.fromkeys(cols, "0")
        values["Million Plus Cities"] = city
        values["Over-Speeding - Number of Accidents - Number"] = str(accidents)
        values["Over-Speeding - Persons Killed - Number"] = str(killed)
        values["Over-Speeding - Persons Injured - Greviously Injured"] = str(grievous)
        values["Over-Speeding - Persons Injured - Minor Injury"] = str(minor)
        values["Over-Speeding - Persons Injured - Total Injured"] = str(grievous + minor)
        out.append([values[c] for c in cols])
    body = pd.DataFrame(out, columns=cols, dtype=object)
    total = {c: str(int(pd.to_numeric(body[c]).sum())) for c in cols[1:]}
    total["Million Plus Cities"] = "Total"
    return pd.concat([body, pd.DataFrame([total])[cols]], ignore_index=True)


def test_zero_accident_casualties_are_a_warning_and_values_are_unchanged():
    frame = _a47([("Pune", 0, 6, 11, 4), ("Agra", 10, 2, 1, 1)])
    before = frame.copy()
    findings = morth_city_table.validate(frame, list(frame.columns))
    flagged = [f for f in findings if f.code == "casualties.zero_accidents"]
    assert len(flagged) == 1 and flagged[0].severity == "warning"
    assert flagged[0].details["rows"] == [
        {"row": "Pune", "category": "Over-Speeding", "killed": 6.0, "injured": 15.0}
    ]
    assert not any(f.severity == "error" for f in findings)
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("row", [("Agra", 0, 0, 0, 0), ("Agra", 3, 1, 0, 2)])
def test_no_warning_when_accidents_and_casualties_are_consistent(row):
    frame = _a47([row])
    codes = {f.code for f in morth_city_table.validate(frame, list(frame.columns))}
    assert "casualties.zero_accidents" not in codes


def test_injured_only_with_zero_accidents_is_also_flagged():
    frame = _a47([("X", 0, 0, 2, 3)])
    flagged = [
        f
        for f in morth_city_table.validate(frame, list(frame.columns))
        if f.code == "casualties.zero_accidents"
    ]
    assert flagged and flagged[0].details["rows"][0]["injured"] == 5.0


# --------------------------------------------------------------------------- BWSSB series
COLS = list(bwssb_monthly.EXPECTED_COLUMNS)


def _month(rows) -> pd.DataFrame:
    return _text(rows, COLS)


def test_series_swing_flags_large_changes_as_a_warning_only():
    prev = _month([[1, "A", 1000, "50.00"], [2, "B", 1000, "40.00"], [3, "C", 5, "1.00"]])
    cur = _month([[1, "A", 1300, "50.00"], [2, "B", 1000, "60.00"], [3, "C", 50, "9.00"]])
    before = cur.copy()
    findings = bwssb_monthly.series_swing(prev, cur, "2025-12", "2026-01")
    assert [f.code for f in findings] == ["series.swing"]
    assert findings[0].severity == "warning"
    rows = findings[0].details["rows"]
    assert [(r["name"], r["column"], r["relative_change"]) for r in rows] == [
        ("A", "connections", 0.3),  # exactly at the threshold is flagged
        ("B", "consumption_ml", 0.5),
    ]  # C is below both floors (connections < 200, ML < 10): not flagged
    assert rows[0]["2025-12"] == 1000.0 and rows[0]["2026-01"] == 1300.0
    pd.testing.assert_frame_equal(cur, before)


def test_series_swing_is_silent_for_small_changes():
    prev = _month([[1, "A", 1000, "50.00"]])
    cur = _month([[1, "A", 1290, "64.00"]])
    assert bwssb_monthly.series_swing(prev, cur, "m1", "m2") == []


def test_series_swing_refuses_to_compare_different_row_keys():
    prev = _month([[1, "A", 1000, "50.00"], [2, "B", 10, "1.00"]])
    cur = _month([[1, "A", 5000, "50.00"], [2, "b", 10, "1.00"]])
    findings = bwssb_monthly.series_swing(prev, cur, "m1", "m2")
    assert [f.code for f in findings] == ["series.not_comparable"]
    assert findings[0].severity == "warning"


def test_zero_previous_value_is_not_divided():
    prev = _month([[40, "Doddabidirakalu", 1, "0.00"], [1, "A", 1000, "0"]])
    cur = _month([[40, "Doddabidirakalu", 1, "0.00"], [1, "A", 1000, "25.00"]])
    assert bwssb_monthly.series_swing(prev, cur, "m1", "m2") == []


# --------------------------------------------------------------------------- schemas
@pytest.mark.parametrize("version", BATCH02_A47)
def test_batch02_a47_versions_are_registered_verbatim(version):
    schema = get_schema(f"morth_city_a47/{version}")
    assert schema.family == "morth_city_a47" and schema.validator == "morth_city"
    assert detect_schema(schema.columns) is schema
    assert schema.label_column == "Million Plus Cities"
    assert schema.label_column not in schema.numeric_columns
    assert not any(c.lower().startswith("sl. no") for c in schema.numeric_columns)
    assert set(schema.rank_columns) == {
        "Over-Speeding - Number of Accidents - Rank",
        "Over-Speeding - Persons Killed - Rank",
    }


def test_every_a47_edition_header_is_distinct_and_never_aliased():
    a47 = [s for s in SCHEMAS if s.family == "morth_city_a47"]
    assert len(a47) == 5 and len({s.columns for s in a47}) == 5
    # Only near-miss spellings differ between editions; none is accepted for another.
    ra2022 = list(get_schema("morth_city_a47/ra2022").columns)
    ra2023 = list(get_schema("morth_city_a47/ra2023").columns)
    assert ra2022[0] == "Sl. No." and ra2023[0] == "Sl. No"
    assert detect_schema(["Sl. No", *ra2022[1:]]) is None


def test_annexure_49_header_matches_no_registered_schema():
    junction = [
        "Sl. No.",
        "Million Plus Cities",
        "T-Junction - Total Number of Accidents - Number",
    ]
    assert detect_schema(junction) is None
