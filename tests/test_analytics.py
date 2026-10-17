"""Unit tests for analytics A1-A4 on synthetic fixtures (no real records)."""

from __future__ import annotations

import dataclasses

import pytest

from civicmind.analytics import roads, water
from civicmind.analytics.result import (
    REFUSAL_CODES,
    AnalyticsRefused,
    AnalyticsResult,
    Evidence,
)
from civicmind.catalog.ingest import UseNotPermitted, ingest, require_use
from test_ingest import BWSSB, RA2019, RA2024, _csv, _manifest, _morth_rows

KILLED_2024 = "Over-Speeding - Persons Killed - Number"
ACCIDENTS = "Over-Speeding - Number of Accidents - Number"


def _water(tmp_path, rows, start="2025-08-01", end="2025-08-31", sub="a", dataset_id="W-1"):
    m = _manifest(tmp_path / sub, _csv(BWSSB, rows))
    caveats = [
        "ward.duplicated",
        "consumption_ml.zero",
        "connections.zero",
        "connections.non_integer",
    ]
    m = m.model_copy(
        update={
            "dataset_id": dataset_id,
            "period": m.period.model_copy(update={"start": start, "end": end}),
            "review": m.review.model_copy(update={"accepted_caveats": caveats}),
        }
    )
    return ingest(m, tmp_path / sub)


ROWS = [
    [1, "Alpha", 100, "31"],  # 31 ML over 31 days / 100 conn = 10,000 L/conn/day
    [2, "Beta", 200, "31"],  # 5,000
    [2, "Beta East", 0, "0"],  # repeated ward number; 0 connections
    [3, "Gamma", 50, "15.5"],  # 10,000 (tie with Alpha)
]


def _road(tmp_path, header, rows, sub):
    m = _manifest(
        tmp_path / sub,
        _csv(header, rows),
        domain="roads",
        semantic_checks={"validator": "morth_city@v1"},
    )
    return ingest(m, tmp_path / sub)


# --- A1 ---------------------------------------------------------------------------------


def test_water_total_includes_every_published_row(tmp_path):
    ds = _water(tmp_path, ROWS)
    total = water.water_total(ds, "connections")
    assert (total.value, total.unit) == (350, "connections")
    ml = water.water_total(ds, "consumption_ml")
    assert ml.value == pytest.approx(77.5) and ml.unit == "ML"
    assert ml.evidence[0].columns == ("Consumption in ML",) and ml.evidence[0].rows_used == 4
    assert "repeated ward numbers are not merged" in ml.caveats[0]


def test_water_total_never_truncates_fractional_values(tmp_path):
    # Regression: fractional connections (an accepted warning) were cast with int().
    ds = _water(tmp_path, [[1, "A", "10.6", "1"], [2, "B", "10.6", "1"]])
    assert water.water_total(ds, "connections").value == pytest.approx(21.2)


def test_water_total_states_method_and_repeated_wards(tmp_path):
    res = water.water_total(_water(tmp_path, ROWS), "connections")
    assert "no deduplication" in res.method
    assert any("[2]" in c and "all included" in c for c in res.caveats)


def test_unknown_measure_is_refused(tmp_path):
    with pytest.raises(AnalyticsRefused, match="measure.unknown"):
        water.water_total(_water(tmp_path, ROWS), "water_pressure")


# --- A2 ---------------------------------------------------------------------------------


def test_rank_rows_ties_share_rank_and_order_by_ward_number(tmp_path):
    ds = _water(tmp_path, ROWS)
    res = water.water_rank_rows(ds, "litres_per_connection_per_day", n=3)
    rows = res.value["rows"]
    assert [(r["rank"], r["ward_number"], r["value"]) for r in rows] == [
        (1, 1, 10000),
        (1, 3, 10000),
        (3, 2, 5000),
    ]
    assert rows[2]["ward_number_repeated"] is True
    assert res.caveats[1].startswith("Excluded (0 connections")
    assert "record 4 (ward 2 Beta East)" in res.caveats[1]
    assert res.denominator == "connections on the same row x 31 days in the period"


def test_rank_rows_keeps_repeated_ward_numbers_as_rows(tmp_path):
    res = water.water_rank_rows(_water(tmp_path, ROWS), "connections", n=4, order="asc")
    assert res.value["ranked_unit"] == "published_row"
    assert res.value["duplicated_ward_numbers"] == {"2": ["Beta", "Beta East"]}
    got = [(r["ward_number"], r["ward_name"], r["source_record"]) for r in res.value["rows"]]
    assert got == [(2, "Beta East", 4), (3, "Gamma", 5), (1, "Alpha", 2), (2, "Beta", 3)]
    assert res.caveats[0].startswith("PUBLISHED ROWS, NOT UNIQUE WARDS")
    assert "[2]" in res.caveats[0]


def test_repeated_wards_are_flagged_even_outside_the_top_n(tmp_path):
    res = water.water_rank_rows(_water(tmp_path, ROWS), "connections", n=1)
    assert res.value["rows"][0]["ward_name"] == "Beta"  # 200 connections
    assert res.value["duplicated_ward_numbers"] == {"2": ["Beta", "Beta East"]}


def test_unique_ward_ranking_fails_closed_on_repeated_ward_numbers(tmp_path):
    with pytest.raises(AnalyticsRefused) as exc:
        water.water_rank_wards(_water(tmp_path, ROWS), "connections", n=2)
    assert exc.value.code == "ward.identifiers_not_unique"
    assert exc.value.details == {"2": ["Beta", "Beta East"]}


def test_unique_ward_ranking_answers_when_ward_numbers_are_unique(tmp_path):
    unique = [ROWS[0], ROWS[1], ROWS[3]]
    res = water.water_rank_wards(_water(tmp_path, unique), "consumption_ml", n=2)
    assert res.value["ranked_unit"] == "ward"
    assert [r["ward_number"] for r in res.value["rows"]] == [1, 2]


def test_ranking_ties_are_decided_on_the_reported_rounding(tmp_path):
    # 0.00031 ML / 3 and 0.00062 ML / 6 are equal at 6 decimals but not bit-for-bit.
    ds = _water(tmp_path, [[1, "A", 3, "0.00031"], [2, "B", 6, "0.00062"]])
    res = water.water_rank_rows(ds, "litres_per_connection_per_day", n=2)
    assert [r["rank"] for r in res.value["rows"]] == [1, 1]


@pytest.mark.parametrize(("n", "order"), [(0, "desc"), (5, "desc"), (2, "up")])
def test_rank_rows_rejects_bad_arguments(tmp_path, n, order):
    with pytest.raises(AnalyticsRefused):
        water.water_rank_rows(_water(tmp_path, ROWS), "connections", n=n, order=order)


# --- A3 ---------------------------------------------------------------------------------


def test_month_change_uses_city_totals_only(tmp_path):
    aug = _water(tmp_path, ROWS, sub="a", dataset_id="W-AUG")
    mar = _water(tmp_path, ROWS[:2], "2026-03-01", "2026-03-31", sub="b", dataset_id="W-MAR")
    res = water.water_month_change(aug, mar, "consumption_ml")
    assert res.value == {
        "earlier": 77.5,
        "later": 62,
        "change": -15.5,
        "pct_change": -20.0,
        "earlier_days": 31,
        "later_days": 31,
    }
    assert [e.dataset_id for e in res.evidence] == ["W-AUG", "W-MAR"]
    assert any(c.startswith("[W-AUG] ") for c in res.caveats)  # dataset caveats carried
    with pytest.raises(AnalyticsRefused, match="period.order"):
        water.water_month_change(mar, aug, "consumption_ml")
    with pytest.raises(AnalyticsRefused, match="period.same"):
        water.water_month_change(aug, aug, "consumption_ml")


# --- guards -----------------------------------------------------------------------------


def test_untrusted_or_wrong_family_datasets_are_refused(tmp_path):
    ds = _water(tmp_path, ROWS)
    # Regression: an exploratory dataset whose restrictions were lost reached analytics.
    for restrictions in (("no_trusted_analytics",), ()):
        exploratory = dataclasses.replace(ds, mode="exploratory", restrictions=restrictions)
        with pytest.raises(AnalyticsRefused, match="dataset.not_trusted"):
            water.water_total(exploratory, "connections")
    restricted = dataclasses.replace(ds, restrictions=("no_trusted_analytics",))
    with pytest.raises(AnalyticsRefused, match="use.not_permitted"):
        water.water_total(restricted, "connections")
    with pytest.raises(AnalyticsRefused, match="dataset.wrong_family"):
        roads.road_top_cities(ds, KILLED_2024)


# --- A4 ---------------------------------------------------------------------------------


def test_city_value_and_share_of_published_total(tmp_path):
    ds = _road(tmp_path, RA2024, _morth_rows(RA2024, ("City A", "City B", "City C")), "r")
    res = roads.road_city_value(ds, " City B ", ACCIDENTS)
    assert res.value == {"value": 2, "share_of_total_pct": pytest.approx(33.3333)}
    assert res.denominator.startswith("published Total row")
    assert res.evidence[0].schema_version == "morth_city_a47/ra2024"


@pytest.mark.parametrize("city", ["Total", "city b", "Bangalore"])
def test_city_lookup_is_exact_and_total_is_not_a_city(tmp_path, city):
    ds = _road(tmp_path, RA2024, _morth_rows(RA2024), "r")
    with pytest.raises(AnalyticsRefused, match="city.not_found"):
        roads.road_city_value(ds, city, ACCIDENTS)


def test_rank_and_serial_columns_are_not_measures(tmp_path):
    ds = _road(tmp_path, RA2024, _morth_rows(RA2024), "r")
    for column in ("Over-Speeding - Number of Accidents - Rank", "Sl. No."):
        with pytest.raises(AnalyticsRefused, match="column.unknown"):
            roads.road_top_cities(ds, column)


def test_columns_are_not_mapped_between_editions(tmp_path):
    ds = _road(tmp_path, RA2019, _morth_rows(RA2019), "r19")
    grievous_2024 = "Over-Speeding - Persons Injured - Grievously Injured"
    with pytest.raises(AnalyticsRefused) as exc:
        roads.road_city_value(ds, "City A", grievous_2024)
    assert exc.value.code == "column.unknown"
    assert exc.value.details["closest_verbatim"][0].endswith("Greviously Injured")


def test_top_cities_excludes_total_and_breaks_ties_by_name(tmp_path):
    rows = _morth_rows(RA2024, ("Zeta", "Alpha", "Mu"))
    col = RA2024.index(KILLED_2024)
    rows[0][col], rows[1][col], rows[2][col] = 5, 5, 9
    rows[3][col] = 19
    ds = _road(tmp_path, RA2024, rows, "r")
    res = roads.road_top_cities(ds, KILLED_2024, n=3)
    assert res.value == [
        {"rank": 1, "city": "Mu", "value": 9},
        {"rank": 2, "city": "Alpha", "value": 5},
        {"rank": 2, "city": "Zeta", "value": 5},
    ]


def test_month_change_reports_unequal_month_lengths(tmp_path):
    aug = _water(tmp_path, ROWS, sub="a", dataset_id="W-AUG")
    feb = _water(tmp_path, ROWS, "2026-02-01", "2026-02-28", sub="b", dataset_id="W-FEB")
    res = water.water_month_change(aug, feb, "consumption_ml")
    assert res.value["change"] == 0
    assert res.value["change_per_day"] == pytest.approx(77.5 / 28 - 77.5 / 31)
    assert any("31 vs 28 days" in c for c in res.caveats)


def test_road_counts_are_never_truncated(tmp_path):
    # Regression: fractional cells were cast with int() in road_top_cities.
    rows = _morth_rows(RA2024)
    col = RA2024.index(KILLED_2024)
    rows[0][col], rows[1][col], rows[2][col] = "1.5", "2.5", "4"
    ds = _road(tmp_path, RA2024, rows, "r")
    assert [r["value"] for r in roads.road_top_cities(ds, KILLED_2024, 2).value] == [2.5, 1.5]


def test_share_is_null_when_the_published_total_is_zero(tmp_path):
    rows = _morth_rows(RA2024)
    col = RA2024.index(ACCIDENTS)
    for row in rows:
        row[col] = 0
    ds = _road(tmp_path, RA2024, rows, "r")
    assert roads.road_city_value(ds, "City A", ACCIDENTS).value["share_of_total_pct"] is None


def test_repeated_city_labels_are_ambiguous(tmp_path):
    # Ingestion refuses repeated labels (validator error); analytics refuses them too.
    ds = _road(tmp_path, RA2024, _morth_rows(RA2024), "r")
    raw = ds.raw.copy()
    raw.loc[1, "Million Plus Cities"] = "City A"
    with pytest.raises(AnalyticsRefused, match="city.ambiguous"):
        roads.road_city_value(dataclasses.replace(ds, raw=raw), "City A", ACCIDENTS)


def test_missing_values_are_refused_not_treated_as_zero(tmp_path):
    ds = _water(tmp_path, ROWS)
    values = ds.values.copy()
    values.loc[0, "Consumption in ML"] = float("nan")
    broken = dataclasses.replace(ds, values=values)
    with pytest.raises(AnalyticsRefused, match="values.missing"):
        water.water_total(broken, "consumption_ml")
    with pytest.raises(AnalyticsRefused, match="values.missing"):
        water.water_rank_rows(broken, "consumption_ml", 2)


# --- evidence and refusal contracts -----------------------------------------------------


def test_every_result_carries_complete_evidence(tmp_path):
    w = _water(tmp_path, ROWS, sub="a", dataset_id="W-AUG")
    w2 = _water(tmp_path, ROWS, "2026-03-01", "2026-03-31", sub="b", dataset_id="W-MAR")
    r = _road(tmp_path, RA2024, _morth_rows(RA2024), "r")
    results = [
        water.water_total(w, "consumption_ml"),
        water.water_rank_rows(w, "litres_per_connection_per_day", 2),
        water.water_month_change(w, w2, "connections"),
        roads.road_city_value(r, "City A", ACCIDENTS),
        roads.road_top_cities(r, ACCIDENTS, 2),
    ]
    headers = {ds.dataset_id: set(ds.header) for ds in (w, w2, r)}
    hashes = {ds.dataset_id: ds.sha256 for ds in (w, w2, r)}
    for res in results:
        assert res.unit and res.method and res.caveats, res.operation
        for ev in res.evidence:
            assert ev.sha256 == hashes[ev.dataset_id]
            assert ev.columns and set(ev.columns) <= headers[ev.dataset_id]
            assert ev.mode == "trusted" and ev.rows_used > 0
    assert "Total" in results[3].denominator
    assert "days" in results[1].denominator


def test_results_without_complete_evidence_cannot_be_built():
    good = {"operation": "x", "value": 1, "unit": "ML", "method": "m", "caveats": ("c",)}
    with pytest.raises(ValueError):
        AnalyticsResult(**good, evidence=())
    bad = Evidence("D", "v", "not-a-hash", "p", "trusted", {}, ("c",), 1)
    with pytest.raises(ValueError):
        AnalyticsResult(**good, evidence=(bad,))


def test_refusal_codes_are_declared():
    with pytest.raises(ValueError):
        AnalyticsRefused("made.up", "x")
    assert "ward.identifiers_not_unique" in REFUSAL_CODES


# --- T10: water_intensity_flags@v1 (flags only; never exclude or re-rank) -----------------

LPCD = "litres_per_connection_per_day"
# 31-day months. Intensity = ML * 1e6 / connections / 31.
BASE = [
    [1, "Alpha", 100, "31"],  # 10,000
    [2, "Beta", 200, "31"],  # 5,000
    [3, "Gamma", 500, "155"],  # 10,000
    [4, "Tiny", 1, "0"],  # 0, small base
]


def _months(tmp_path, ref_rows):
    cur = _water(tmp_path, BASE, sub="cur", dataset_id="W-CUR")
    ref = _water(tmp_path, ref_rows, "2026-03-01", "2026-03-31", sub="ref", dataset_id="W-REF")
    return cur, ref


def _by_name(res):
    return {r["ward_name"]: r for r in res.value["rows"]}


def test_small_base_is_flagged_even_without_references(tmp_path):
    cur = _water(tmp_path, BASE, sub="cur", dataset_id="W-CUR")
    res = water.water_rank_rows(cur, LPCD, n=4)
    rows = _by_name(res)
    assert rows["Tiny"]["flags"] == ["small_connection_base"]
    assert rows["Alpha"]["flags"] == [] and rows["Alpha"]["reference_values"] == {}
    assert res.value["flag_policy"]["id"] == "water_intensity_flags@v1"
    assert any("Volatility not assessed" in c for c in res.caveats)


def test_volatility_threshold_is_inclusive_at_2x(tmp_path):
    ref_rows = [
        [1, "Alpha", 100, "15.5"],  # 5,000: current is exactly 2x -> volatile
        [2, "Beta", 200, "15.6"],  # 2,516: current is 1.99x -> not volatile
        [3, "Gamma", 500, "620"],  # 40,000: current is 0.25x -> volatile
        [4, "Tiny", 1, "0"],  # 0 vs 0 -> not volatile
    ]
    cur, ref = _months(tmp_path, ref_rows)
    rows = _by_name(water.water_rank_rows(cur, LPCD, n=4, references=(ref,)))
    assert rows["Alpha"]["flags"] == ["volatile_vs_reference"]
    assert rows["Beta"]["flags"] == []
    assert rows["Gamma"]["flags"] == ["volatile_vs_reference"]
    assert rows["Tiny"]["flags"] == ["small_connection_base"]
    assert rows["Alpha"]["reference_values"] == {"W-REF": 5000}


def test_zero_against_positive_is_volatile(tmp_path):
    ref_rows = [r[:] for r in BASE]
    ref_rows[3] = [4, "Tiny", 1, "0.01"]
    cur, ref = _months(tmp_path, ref_rows)
    rows = _by_name(water.water_rank_rows(cur, LPCD, n=4, references=(ref,)))
    assert rows["Tiny"]["flags"] == ["small_connection_base", "volatile_vs_reference"]


def test_reference_rows_match_only_on_exact_number_and_name(tmp_path):
    ref_rows = [
        [1, "alpha", 100, "31"],  # case differs -> no match
        [2, "Beta", 200, "31"],
        [2, "Beta", 10, "1"],  # same key twice -> ambiguous
        [3, "Gamma", 0, "0"],  # 0 connections -> intensity undefined
        [4, "Tiny", 1, "0"],
    ]
    cur, ref = _months(tmp_path, ref_rows)
    rows = _by_name(water.water_rank_rows(cur, LPCD, n=4, references=(ref,)))
    for name in ("Alpha", "Beta", "Gamma"):
        assert rows[name]["flags"] == ["not_comparable"], name
        assert rows[name]["reference_values"] == {"W-REF": None}


def test_flags_never_exclude_rows_or_change_ranks_or_values(tmp_path):
    ref_rows = [[1, "Alpha", 100, "1"], [2, "Beta", 200, "1"], [3, "Gamma", 500, "1"]]
    cur, ref = _months(tmp_path, ref_rows)
    plain = water.water_rank_rows(cur, LPCD, n=4)
    flagged = water.water_rank_rows(cur, LPCD, n=4, references=(ref,))
    keep = ("rank", "source_record", "ward_number", "ward_name", "value")
    assert [{k: r[k] for k in keep} for r in plain.value["rows"]] == [
        {k: r[k] for k in keep} for r in flagged.value["rows"]
    ]
    assert len(flagged.value["rows"]) == 4
    assert [e.dataset_id for e in flagged.evidence] == ["W-CUR", "W-REF"]
    assert flagged.filters["references"] == ["W-REF"]


def test_reference_months_are_validated(tmp_path):
    cur, ref = _months(tmp_path, BASE)
    with pytest.raises(AnalyticsRefused, match="period.same"):
        water.water_rank_rows(cur, LPCD, references=(cur,))
    with pytest.raises(AnalyticsRefused, match="period.same"):
        water.water_rank_rows(cur, LPCD, references=(ref, ref))
    with pytest.raises(AnalyticsRefused, match="measure.unknown"):
        water.water_rank_rows(cur, "consumption_ml", references=(ref,))
    untrusted = dataclasses.replace(ref, mode="exploratory")
    with pytest.raises(AnalyticsRefused, match="dataset.not_trusted"):
        water.water_rank_rows(cur, LPCD, references=(untrusted,))
    road = _road(tmp_path, RA2024, _morth_rows(RA2024), "r")
    with pytest.raises(AnalyticsRefused, match="dataset.wrong_family"):
        water.water_rank_rows(cur, LPCD, references=(road,))


def test_not_comparable_rows_are_explicit_and_counted_separately(tmp_path):
    ref_rows = [
        [1, "alpha", 100, "31"],  # name case differs -> no exact match
        [2, "Beta", 200, "31"],  # 5,000 vs 5,000 -> within threshold
        [3, "Gamma", 0, "0"],  # 0 connections -> intensity undefined
        [4, "Tiny", 1, "0"],  # 0 vs 0 -> within threshold
    ]
    cur, ref = _months(tmp_path, ref_rows)
    res = water.water_rank_rows(cur, LPCD, n=1, references=(ref,))
    rows = _by_name(water.water_rank_rows(cur, LPCD, n=4, references=(ref,)))
    assert rows["Alpha"]["volatility_status"] == "not_comparable"
    assert rows["Alpha"]["reference_status"] == {"W-REF": "not_comparable"}
    assert rows["Alpha"]["reference_notes"] == {"W-REF": water.NO_UNIQUE_MATCH}
    assert rows["Gamma"]["reference_notes"] == {"W-REF": water.ZERO_CONNECTIONS}
    assert rows["Beta"]["volatility_status"] == "within_threshold"
    assert rows["Beta"]["reference_notes"] == {}
    summary = res.value["flag_summary"]
    assert summary["all_ranked_rows"] == {
        "volatile": 0,
        "not_comparable": 2,
        "within_threshold": 2,
        "not_assessed": 0,
        "small_connection_base": 1,
    }
    assert sum(summary["returned_rows"][s] for s in water.VOLATILITY_STATUSES) == 1
    assert any("2 NOT COMPARABLE (not assessed, not passed)" in c for c in res.caveats)


def test_rows_without_references_are_not_assessed_not_passed(tmp_path):
    cur = _water(tmp_path, BASE, sub="cur", dataset_id="W-CUR")
    res = water.water_rank_rows(cur, LPCD, n=4)
    assert {r["volatility_status"] for r in res.value["rows"]} == {"not_assessed"}
    assert res.value["flag_summary"]["all_ranked_rows"]["within_threshold"] == 0


@pytest.mark.parametrize(
    ("current_ml", "reference_ml", "status"),
    [
        ("0", "0.01", "volatile"),  # zero consumption now, positive in reference
        ("0.01", "0", "volatile"),  # positive now, zero consumption in reference
        ("0", "0", "within_threshold"),  # zero consumption in both: no change
    ],
)
def test_zero_consumption_is_comparable(tmp_path, current_ml, reference_ml, status):
    cur = _water(tmp_path, [[1, "Solo", 500, current_ml]], sub="c", dataset_id="W-CUR")
    ref = _water(
        tmp_path,
        [[1, "Solo", 500, reference_ml]],
        "2026-03-01",
        "2026-03-31",
        sub="r",
        dataset_id="W-REF",
    )
    row = water.water_rank_rows(cur, LPCD, n=1, references=(ref,)).value["rows"][0]
    assert row["volatility_status"] == status
    assert row["reference_values"]["W-REF"] is not None


def test_zero_connections_in_reference_is_not_comparable(tmp_path):
    cur = _water(tmp_path, [[1, "Solo", 500, "1"]], sub="c", dataset_id="W-CUR")
    ref = _water(
        tmp_path, [[1, "Solo", 0, "0"]], "2026-03-01", "2026-03-31", sub="r", dataset_id="W-REF"
    )
    row = water.water_rank_rows(cur, LPCD, n=1, references=(ref,)).value["rows"][0]
    assert row["volatility_status"] == "not_comparable"
    assert row["reference_values"] == {"W-REF": None}
    assert row["reference_notes"] == {"W-REF": water.ZERO_CONNECTIONS}


def test_flag_wording_is_descriptive_and_threshold_is_provisional(tmp_path):
    cur, ref = _months(tmp_path, BASE)
    res = water.water_rank_rows(cur, LPCD, n=2, references=(ref,))
    policy = res.value["flag_policy"]
    assert "not evidence of an anomaly" in policy["definitions"]["volatile_vs_reference"]
    assert "provisional operational threshold" in policy["definitions"]["small_connection_base"]
    assert "not a statistical" in policy["min_connections_basis"]
    assert "This is not a pass" in policy["definitions"]["not_comparable"]
    text = " ".join(res.caveats)
    assert "compares 2 months" in text and "descriptive difference" in text


def test_reference_lookup_does_not_authorise_other_joins(tmp_path):
    cur, ref = _months(tmp_path, BASE)
    water.water_rank_rows(cur, LPCD, n=2, references=(ref,))
    for ds in (cur, ref):
        with pytest.raises(UseNotPermitted):
            require_use(ds, "cross_dataset_join")
    import inspect

    only = {
        name
        for module in (water, roads)
        for name, fn in inspect.getmembers(module, inspect.isfunction)
        if not name.startswith("_")
        and fn.__module__ == module.__name__
        and "references" in inspect.signature(fn).parameters
    }
    assert only == {"water_rank_rows"}
