"""Golden evaluation of analytics A1-A4 on the promoted batch-01 data.

Questions and expected answers live in eval/golden/batch01_analytics.v1.yaml. Answerable
items are also re-derived by eval/golden/derive_batch01.py (standard library only) and the
YAML is checked against that derivation. Data files are git-ignored, so data-dependent tests
skip, not fail, when a source file is absent (e.g. on a fresh clone or CI).
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest
import yaml

from civicmind.analytics import roads, water
from civicmind.analytics.result import REFUSAL_CODES, AnalyticsRefused
from civicmind.catalog.ingest import IngestionRefused, ingest
from civicmind.catalog.manifest import read_manifest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "eval/golden/batch01_analytics.v1.yaml"
ITEMS = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["items"]
FUNCTIONS = {
    "water_total": water.water_total,
    "water_rank_rows": water.water_rank_rows,
    "water_rank_wards": water.water_rank_wards,
    "water_month_change": water.water_month_change,
    "road_city_value": roads.road_city_value,
    "road_top_cities": roads.road_top_cities,
}
CATEGORIES = {"numeric", "ranking", "comparison", "refusal"}
ITEM_KEYS = {
    "id",
    "question",
    "category",
    "datasets",
    "references",
    "call",
    "expected",
    "refusal",
    "fields",
}
INGEST_CODES = {"status.quarantined", "status.rejected", "exploratory.not_permitted"}


def _derivation():
    spec = importlib.util.spec_from_file_location(
        "derive_batch01", ROOT / "eval/golden/derive_batch01.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _close(actual, expected, tol):
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and set(actual) >= set(expected), (actual, expected)
        for key, value in expected.items():
            _close(actual[key], value, tol)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), (actual, expected)
        for a, e in zip(actual, expected, strict=True):
            _close(a, e, tol)
    elif isinstance(expected, float) or isinstance(actual, float):
        assert actual == pytest.approx(expected, abs=tol)
    else:
        assert actual == expected


def _dataset_ids(item):
    return [s if isinstance(s, str) else s["id"] for s in item["datasets"]]


def _datasets(item, key="datasets"):
    loaded = []
    for spec in item.get(key, []):
        dataset_id, mode = (
            (spec, "trusted") if isinstance(spec, str) else (spec["id"], spec["mode"])
        )
        manifest = read_manifest(ROOT / "data/manifests" / f"{dataset_id}.yaml")
        source = manifest.promoted_to if mode == "trusted" else manifest.retrieval.local_path
        blocked = manifest.status in ("quarantined", "rejected")
        if source and not blocked and not (ROOT / source).is_file():
            pytest.skip(f"source file not present: {source}")
        loaded.append(ingest(manifest, ROOT, mode))
    return loaded


def _rows_only(value, fields):
    if isinstance(value, dict) and "rows" in value:
        return {**value, "rows": [{k: row[k] for k in fields} for row in value["rows"]]}
    return [{k: row[k] for k in fields} for row in value]


# --- the question set itself ------------------------------------------------------------


def test_golden_set_is_well_formed():
    ids = [item["id"] for item in ITEMS]
    assert len(ids) == len(set(ids)) == 25
    for item in ITEMS:
        name = item["id"]
        assert set(item) <= ITEM_KEYS, (name, set(item) - ITEM_KEYS)
        assert item["category"] in CATEGORIES and item["question"].strip(), name
        assert item["datasets"], name
        for dataset_id in [*_dataset_ids(item), *item.get("references", [])]:
            assert (ROOT / "data/manifests" / f"{dataset_id}.yaml").is_file(), name
        assert ("expected" in item) != ("refusal" in item), name
        assert (item["category"] == "refusal") == ("refusal" in item), name
        function = item["call"]["function"]
        if "refusal" in item:
            stage, code = item["refusal"]["stage"], item["refusal"]["code"]
            assert stage in {"ingest", "analytics"}, name
            assert code in (INGEST_CODES if stage == "ingest" else REFUSAL_CODES), name
            if stage == "ingest":
                continue
        assert function in FUNCTIONS, name
        params = inspect.signature(FUNCTIONS[function])
        # datasets are positional; every arg must be a real keyword of the function
        refs = {"references": ()} if item.get("references") else {}
        params.bind(*_dataset_ids(item), **item["call"]["args"], **refs)
        if "expected" in item:
            assert {"value", "unit"} <= set(item["expected"]), name


def test_golden_answers_match_the_independent_derivation():
    derivation = _derivation()
    if not derivation.available():
        pytest.skip("source files not present")
    derived = derivation.derive()
    answerable = {i["id"]: i for i in ITEMS if "expected" in i}
    assert set(derived) == set(answerable)
    for item_id, value in derived.items():
        _close(answerable[item_id]["expected"]["value"], value, 1e-9)


# --- running each question ----------------------------------------------------------------


@pytest.mark.parametrize("item", ITEMS, ids=[i["id"] for i in ITEMS])
def test_golden_item(item):
    refusal = item.get("refusal")
    if refusal and refusal["stage"] == "ingest":
        with pytest.raises(IngestionRefused) as exc:
            _datasets(item)
            _datasets(item, "references")
        assert exc.value.code == refusal["code"]
        return
    datasets = _datasets(item)
    args = dict(item["call"]["args"])
    references = _datasets(item, "references")
    if references:
        args["references"] = tuple(references)
    call = FUNCTIONS[item["call"]["function"]]
    if refusal:
        with pytest.raises(AnalyticsRefused) as exc:
            call(*datasets, **args)
        assert exc.value.code == refusal["code"]
        return
    result = call(*datasets, **args)
    expected = item["expected"]
    value = _rows_only(result.value, item["fields"]) if "fields" in item else result.value
    _close(value, expected["value"], 1e-6)
    assert result.unit == expected["unit"]
    used = [*datasets, *references]
    assert [e.dataset_id for e in result.evidence] == [ds.dataset_id for ds in used]
    assert [ds.dataset_id for ds in datasets] == _dataset_ids(item)
    for ev, ds in zip(result.evidence, used, strict=True):
        assert ev.mode == "trusted" and ev.sha256 == ds.sha256
        assert set(ev.columns) <= set(ds.header)
    assert result.method and result.caveats


# --- cross-checks of analytics against the publishers' own figures (real data) ----------


def _trusted(dataset_id):
    manifest = read_manifest(ROOT / "data/manifests" / f"{dataset_id}.yaml")
    if not (ROOT / manifest.promoted_to).is_file():
        pytest.skip(f"source file not present: {manifest.promoted_to}")
    return ingest(manifest, ROOT)


@pytest.mark.parametrize("dataset_id", ["ROAD-RA2019-A47", "ROAD-RA2024-A47"])
def test_city_ranks_match_the_published_rank_columns(dataset_id):
    ds = _trusted(dataset_id)
    label = "States/UTs" if dataset_id.endswith("2019-A47") else "Million Plus Cities"
    for count in (
        "Over-Speeding - Number of Accidents - Number",
        "Over-Speeding - Persons Killed - Number",
    ):
        rank_col = count.removesuffix(" - Number") + " - Rank"
        ours = {r["city"]: r["rank"] for r in roads.road_top_cities(ds, count, 50).value}
        published = {
            row[label].strip(): int(row[rank_col])
            for _, row in ds.raw.iterrows()
            if row[label].strip() != "Total"
        }
        assert ours == published, count


@pytest.mark.parametrize("dataset_id", ["ROAD-RA2019-A47", "ROAD-RA2024-A47"])
def test_city_shares_use_the_total_row_as_denominator(dataset_id):
    ds = _trusted(dataset_id)
    column = "Over-Speeding - Number of Accidents - Number"
    cities = [r["city"] for r in roads.road_top_cities(ds, column, 50).value]
    shares = [roads.road_city_value(ds, c, column).value["share_of_total_pct"] for c in cities]
    assert len(cities) == 50
    assert sum(shares) == pytest.approx(100, abs=50 * 0.00005)  # each share rounded to 4 dp


@pytest.mark.parametrize("dataset_id", ["WATER-BWSSB-2025-08", "WATER-BWSSB-2026-03"])
def test_every_published_water_row_is_ranked_and_sums_to_the_total(dataset_id):
    ds = _trusted(dataset_id)
    ranked = water.water_rank_rows(ds, "consumption_ml", n=len(ds.raw))
    assert len(ranked.value["rows"]) == 202
    assert len({r["source_record"] for r in ranked.value["rows"]}) == 202  # nothing merged
    total = water.water_total(ds, "consumption_ml").value
    assert sum(r["value"] for r in ranked.value["rows"]) == pytest.approx(total, abs=1e-6)
