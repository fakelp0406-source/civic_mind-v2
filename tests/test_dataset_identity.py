"""Road dataset identity: a source table (MoRTH annexure), not only a family and a year.

MoRTH publishes several annexures per edition (A1 national, A2 state, A47 city by traffic
violation, A49 city by junction type). The road analytics read Annexure 47 only, so the
planner must never resolve a road question to another annexure of the same year, and must
keep refusing (never choosing) when two Annexure 47 datasets claim the same year.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from civicmind.catalog.schemas import get_schema
from civicmind.planner.catalog_index import DatasetEntry, load_index, source_table
from civicmind.planner.feasibility import Plan, check
from civicmind.planner.parser import parse
from civicmind.planner.spec import PlanRefusal

ROOT = Path(__file__).resolve().parents[1]
A47_2024 = get_schema("morth_city_a47/ra2024").columns
QUESTION_2024 = "How many over-speeding accidents did Bengaluru record in 2024?"


def _entry(dataset_id: str, period_key: str, family: str = "roads", **kw) -> DatasetEntry:
    base = DatasetEntry(
        dataset_id=dataset_id,
        family=family,
        period_key=period_key,
        period_start=None,
        period_end=None,
        status="promoted",
        human_review="accepted",
        value_nature="unknown",
        review_note=None,
        title=dataset_id,
        columns=A47_2024,
        table=source_table(dataset_id),
    )
    return dataclasses.replace(base, **kw)


@pytest.mark.parametrize(
    ("dataset_id", "table"),
    [
        ("ROAD-RA2019-A47", "A47"),
        ("ROAD-RA2024-A47", "A47"),
        ("ROAD-RA2024-A1", "A1"),
        ("ROAD-RA2024-A2", "A2"),
        ("ROAD-RA2024-A49", "A49"),
        ("ROAD-RA2024", None),  # no annexure: no table, never matched
        ("ROAD-RA2024-A47-X", None),
        ("WATER-BWSSB-2025-08", None),
    ],
)
def test_source_table_is_parsed_from_the_dataset_id(dataset_id, table):
    assert source_table(dataset_id) == table


def test_catalogued_road_manifests_are_indexed_by_annexure():
    roads = {e.dataset_id: e.table for e in load_index(ROOT) if e.family == "roads"}
    assert roads["ROAD-RA2019-A47"] == roads["ROAD-RA2024-A47"] == "A47"  # batch 01
    for dataset_id, table in roads.items():
        assert table == dataset_id.rsplit("-", 1)[1], dataset_id
    assert all(e.table is None for e in load_index(ROOT) if e.family != "roads")


def test_real_catalogue_answers_2024_from_annexure_47_beside_other_2024_annexures():
    index = load_index(ROOT)
    others = {"ROAD-RA2024-A1", "ROAD-RA2024-A2", "ROAD-RA2024-A49"}
    if not others <= {e.dataset_id for e in index}:
        pytest.skip("batch 02 road manifests not catalogued")
    plan = check(parse(QUESTION_2024), index)
    assert isinstance(plan, Plan) and plan.dataset_ids == ("ROAD-RA2024-A47",)


def test_exploratory_only_january_2026_is_refused_for_analytics():
    index = load_index(ROOT)
    if "WATER-BWSSB-2026-01" not in {e.dataset_id for e in index}:
        pytest.skip("batch 02 water manifests not catalogued")
    refusal = check(parse("What was water consumption in January 2026?"), index)
    assert isinstance(refusal, PlanRefusal) and refusal.code == "dataset.not_trusted"


def test_road_question_resolves_to_annexure_47_when_other_2024_annexures_exist():
    spec = parse(QUESTION_2024)
    index = (
        _entry("ROAD-RA2024-A1", "2024"),  # even if an A1 manifest keyed its period as 2024
        _entry("ROAD-RA2024-A2", "2024"),
        _entry("ROAD-RA2024-A49", "2024"),
        _entry("ROAD-RA2024-A47", "2024"),
    )
    plan = check(spec, index)
    assert isinstance(plan, Plan)
    assert plan.dataset_ids == ("ROAD-RA2024-A47",)


def test_other_annexures_never_stand_in_for_a_missing_annexure_47():
    spec = parse(QUESTION_2024)
    index = (_entry("ROAD-RA2024-A49", "2024"), _entry("ROAD-RA2024-A1", "2024"))
    refusal = check(spec, index)
    assert isinstance(refusal, PlanRefusal)
    assert refusal.code == "period.unavailable"
    assert refusal.details == []  # no A47 catalogued at all


def test_state_table_restating_an_earlier_year_is_not_matched_for_that_year():
    # A2 (2024 edition) covers 2021-2024, so its period_key would be "2021".
    spec = parse("How many over-speeding accidents did Bengaluru record in 2021?")
    index = (_entry("ROAD-RA2024-A2", "2021"), _entry("ROAD-RA2024-A47", "2024"))
    refusal = check(spec, index)
    assert isinstance(refusal, PlanRefusal) and refusal.code == "period.unavailable"
    assert refusal.details == ["2024 (promoted)"]


def test_two_annexure_47_datasets_for_one_year_are_still_refused():
    spec = parse(QUESTION_2024)
    index = (_entry("ROAD-RA2024-A47", "2024"), _entry("ROAD-RA2024-A47", "2024", title="dup"))
    refusal = check(spec, index)
    assert isinstance(refusal, PlanRefusal) and refusal.code == "period.unavailable"
    assert "none is chosen" in refusal.reason


def test_road_id_without_an_annexure_is_never_used_for_road_analytics():
    spec = parse(QUESTION_2024)
    refusal = check(spec, (_entry("ROAD-RA2024", "2024"),))
    assert isinstance(refusal, PlanRefusal) and refusal.code == "period.unavailable"


def test_untrusted_annexure_47_is_still_refused_after_table_matching():
    spec = parse(QUESTION_2024)
    index = (
        _entry("ROAD-RA2024-A49", "2024"),
        _entry("ROAD-RA2024-A47", "2024", status="validated", human_review="pending"),
    )
    refusal = check(spec, index)
    assert isinstance(refusal, PlanRefusal) and refusal.code == "dataset.not_trusted"
    assert "ROAD-RA2024-A47" in refusal.reason


def test_water_resolution_is_unchanged_by_table_matching():
    spec = parse("What was the total water consumption in August 2025?")
    index = load_index(ROOT)
    plan = check(spec, index)
    assert isinstance(plan, Plan)
    assert plan.dataset_ids == ("WATER-BWSSB-2025-08",)
