"""End-to-end tests for the QuerySpec pipeline (planner -> orchestrator -> evidence -> respond).

The versioned question set is eval/questions/pipeline.v1.yaml. Answered items are checked
against the golden values in eval/golden/batch01_analytics.v1.yaml (independently derived).
Items that need the git-ignored data files skip when those files are absent; planner and
feasibility refusals need only the tracked manifests and always run.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from pathlib import Path

import pytest
import yaml

from civicmind.analytics import roads, water
from civicmind.analytics.result import REFUSAL_CODES
from civicmind.evidence.model import (
    EVIDENCE_CODES,
    EvidenceItem,
    EvidencePackage,
    SourceRecord,
    ValidationReport,
    validate_package,
)
from civicmind.orchestrator import pipeline
from civicmind.orchestrator.pipeline import DISPATCH, PIPELINE_CODES, answer_question, sources
from civicmind.planner.parser import parse
from civicmind.planner.spec import FEASIBILITY_CODES, PLANNER_CODES, PlanRefusal, QuerySpec
from civicmind.respond.compose import check_numbers, compose_answer

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = yaml.safe_load((ROOT / "eval/questions/pipeline.v1.yaml").read_text("utf-8"))
ITEMS = QUESTIONS["items"]
GOLDEN = {
    i["id"]: i
    for i in yaml.safe_load((ROOT / "eval/golden/batch01_analytics.v1.yaml").read_text("utf-8"))[
        "items"
    ]
}
CATEGORIES = {
    "answerable",
    "ambiguous_entity",
    "missing_filter",
    "invalid_unit",
    "untrusted_data",
    "unavailable_period",
    "prompt_injection",
    "unsupported_claim",
    "out_of_scope",
}
INGEST_CODES = {"status.quarantined", "status.rejected", "modelled.not_trusted"}
ALL_CODES = (
    PLANNER_CODES | FEASIBILITY_CODES | REFUSAL_CODES | EVIDENCE_CODES | PIPELINE_CODES
) | INGEST_CODES
DATA_FILES = [
    "data/raw/water/BWSSB_Water_Consumption_August_2025.csv",
    "data/raw/water/Water_Consumption_Data_Mar_26_0.csv",
    "data/raw/roads/RA2019_A47.csv",
    "data/raw/roads/Transport_2024_Annexure_47.csv",
]
HAVE_DATA = all((ROOT / f).is_file() for f in DATA_FILES)


def _close(actual, expected):
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and set(actual) >= set(expected), (actual, expected)
        for key, value in expected.items():
            _close(actual[key], value)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), (actual, expected)
        for a, e in zip(actual, expected, strict=True):
            _close(a, e)
    elif isinstance(expected, float) or isinstance(actual, float):
        assert actual == pytest.approx(expected, abs=1e-6)
    else:
        assert actual == expected


def _needs_data(item) -> bool:
    e = item["expect"]
    return e["status"] == "answered" or e.get("stage") in ("ingest", "analytics")


# --- the question set ---------------------------------------------------------------------


def test_question_set_is_well_formed():
    ids = [i["id"] for i in ITEMS]
    assert QUESTIONS["version"] == 1
    assert len(ids) == len(set(ids)) == 55
    for item in ITEMS:
        e = item["expect"]
        assert item["category"] in CATEGORIES, item["id"]
        assert (item["category"] == "answerable") == (e["status"] == "answered"), item["id"]
        if e["status"] == "answered":
            assert e["golden"] in GOLDEN and "expected" in GOLDEN[e["golden"]], item["id"]
            assert e["operation"] in DISPATCH, item["id"]
        else:
            assert e["code"] in ALL_CODES, item["id"]
            assert e["stage"] in {"planner", "feasibility", "ingest", "analytics"}, item["id"]
    assert {i["category"] for i in ITEMS} == CATEGORIES


@pytest.mark.parametrize("item", ITEMS, ids=[i["id"] for i in ITEMS])
def test_question(item):
    if _needs_data(item) and not HAVE_DATA:
        pytest.skip("promoted data files are not present")
    expect = item["expect"]
    answer = answer_question(item["question"], ROOT)
    assert answer.status == expect["status"], answer.text
    assert answer.code != "pipeline.internal_error", answer.reason
    if expect["status"] == "refused":
        assert (answer.code, answer.stage) == (expect["code"], expect["stage"]), answer.text
        assert answer.reason and answer.text.startswith(f"Cannot answer ({answer.code})")
        assert answer.value is None and not answer.evidence
        if item["category"] == "prompt_injection":
            assert answer.trace == ("parse",)  # refused before any data was touched
        return
    assert answer.operation == expect["operation"]
    assert [e["dataset_id"] for e in answer.evidence] == expect["datasets"]
    golden = GOLDEN[expect["golden"]]["expected"]
    value = answer.value
    if "fields" in expect:
        value = {**value, "rows": [{k: r[k] for k in expect["fields"]} for r in value["rows"]]}
    _close(value, golden["value"])
    assert answer.unit == golden["unit"]
    _assert_complete(answer)


def _assert_complete(answer):
    """Every answer names dataset, hash, metric, unit, period, method, caveats and evidence."""
    manifests = sources(ROOT)
    assert answer.metric and answer.unit and answer.method and answer.caveats
    assert answer.periods and all(answer.periods)
    for ev in answer.evidence:
        assert ev["sha256"] == manifests[ev["dataset_id"]].sha256
        assert ev["dataset_id"] in answer.text and ev["sha256"][:12] in answer.text
        assert ev["mode"] == "trusted" and ev["columns"] and ev["rows_used"] > 0
    for period in answer.periods:
        assert period in answer.text
    assert answer.trace[-2:] == ("evidence", "compose")


# --- planner ------------------------------------------------------------------------------


def test_parser_is_deterministic():
    for item in ITEMS:
        assert parse(item["question"]) == parse(item["question"])


def test_queryspec_only_accepts_allowlisted_intents():
    with pytest.raises(ValueError):
        QuerySpec(intent="run_sql", domain="water", periods=())
    with pytest.raises(ValueError):
        PlanRefusal(code="made.up", reason="x")


def test_parser_records_its_assumptions():
    spec = parse("Which published rows had the highest water consumption in August 2025?")
    assert spec.intent == "water_rank_rows" and spec.params["n"] == 10
    assert any("default" in a for a in spec.assumptions)
    spec = parse("Which ward had the highest water consumption in August 2025?")
    assert spec.intent == "water_rank_wards" and spec.params["n"] == 1
    assert any("unique wards" in a for a in spec.assumptions)


def test_city_phrase_is_kept_exactly_as_written():
    spec = parse("How many over-speeding accidents did Allahabad (Prayagraj) record in 2024?")
    assert spec.params["city"] == "Allahabad (Prayagraj)"


def test_water_terms_outside_the_vocabulary_are_refused_not_ignored():
    # "for jayanagar" must not be silently dropped (that would return the city total).
    for q in (
        "What was the total water consumption for jayanagar in August 2025?",
        "Total water consumption in ward 85 in August 2025?",
    ):
        result = parse(q)
        assert isinstance(result, PlanRefusal), q
        assert result.code in ("query.unrecognised_terms", "query.unsupported_operation"), q


# --- dispatcher and limits ----------------------------------------------------------------


def test_dispatch_is_exactly_the_public_analytics_operations():
    public = {
        name
        for module in (water, roads)
        for name in module.__all__
        if name.startswith(("water_", "road_"))
    }
    assert set(DISPATCH) == public
    assert all(fn.__module__.startswith("civicmind.analytics.") for fn in DISPATCH.values())


@pytest.mark.skipif(not HAVE_DATA, reason="promoted data files are not present")
def test_step_limit_refuses():
    answer = answer_question("How much water did BWSSB record as consumed in August 2025?",
                             ROOT, max_steps=2)  # fmt: skip
    assert (answer.status, answer.code) == ("refused", "pipeline.step_limit")


@pytest.mark.skipif(not HAVE_DATA, reason="promoted data files are not present")
def test_unexpected_errors_are_refusals_not_answers(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(pipeline.DISPATCH, "water_total", broken)
    answer = answer_question("How much water did BWSSB record as consumed in August 2025?", ROOT)
    assert (answer.status, answer.code) == ("refused", "pipeline.internal_error")
    assert answer.value is None


# --- evidence validation ------------------------------------------------------------------

SHA = "a" * 64


def _package(**item_overrides) -> tuple[EvidencePackage, dict[str, SourceRecord]]:
    item = EvidenceItem(
        dataset_id="D1",
        role="primary",
        schema_version="v",
        sha256=SHA,
        source_path="data/raw/water/f.csv",
        mode="trusted",
        period_start="2025-08-01",
        period_end="2025-08-31",
        columns=("Consumption in ML",),
        rows_used=3,
    )
    item = dataclasses.replace(item, **item_overrides)
    package = EvidencePackage(
        question="q",
        intent="water_total",
        operation="water_total",
        value=12.5,
        unit="ML",
        method="sum",
        denominator=None,
        caveats=("c",),
        filters={"measure": "consumption_ml"},
        assumptions=(),
        items=(item,),
    )
    src = SourceRecord(
        dataset_id="D1",
        sha256=SHA,
        status="promoted",
        source_path="data/raw/water/f.csv",
        columns=("Ward number ", "Consumption in ML"),
        period_start="2025-08-01",
        period_end="2025-08-31",
    )
    return package, {"D1": src}


def test_valid_evidence_passes():
    package, srcs = _package()
    assert validate_package(package, srcs, ["D1"]).ok


@pytest.mark.parametrize(
    "override",
    [
        {"sha256": "b" * 64},
        {"sha256": "not-a-hash"},
        {"mode": "exploratory"},
        {"source_path": "data/external/x.csv"},
        {"columns": ("Invented column",)},
        {"period_end": "2025-08-30"},
        {"dataset_id": "UNKNOWN"},
        {"rows_used": 0},
    ],
)
def test_tampered_evidence_is_rejected(override):
    package, srcs = _package(**override)
    assert not validate_package(package, srcs, [package.items[0].dataset_id]).ok


def test_evidence_for_a_non_promoted_source_is_rejected():
    package, srcs = _package()
    srcs = {"D1": dataclasses.replace(srcs["D1"], status="quarantined")}
    assert not validate_package(package, srcs, ["D1"]).ok


def test_evidence_must_cover_exactly_the_planned_datasets():
    package, srcs = _package()
    assert not validate_package(package, srcs, ["D1", "D2"]).ok


# --- composer -----------------------------------------------------------------------------


def _validated(package, srcs):
    report = validate_package(package, srcs, [i.dataset_id for i in package.items])
    assert report.ok, report.problems
    return report


def test_composer_text_contains_only_evidenced_numbers():
    package, srcs = _package()
    answer = compose_answer(package, _validated(package, srcs))
    assert "12.5 ML" in answer.text and "D1" in answer.text and "August 2025" in answer.text
    assert check_numbers(answer.text, package) == []
    assert check_numbers(answer.text + " Up 17% on last year.", package) == ["17"]


def test_composer_refuses_to_emit_an_unevidenced_number(monkeypatch):
    package, srcs = _package()
    monkeypatch.setitem(compose_answer.__globals__, "_text", lambda p: "Consumption was 99 ML.")
    with pytest.raises(ValueError, match="numbers not in evidence"):
        compose_answer(package, _validated(package, srcs))


def test_composer_refuses_unvalidated_or_altered_packages():
    # Regression: compose_answer could format any package, validated or not.
    package, srcs = _package()
    report = _validated(package, srcs)
    with pytest.raises(ValueError, match="not validated"):
        compose_answer(package, ValidationReport())  # no validation at all
    altered = dataclasses.replace(package, value=13.5)  # changed after validation
    with pytest.raises(ValueError, match="not validated"):
        compose_answer(altered, report)
    tampered, _ = _package(sha256="b" * 64)
    failed = validate_package(tampered, srcs, ["D1"])
    with pytest.raises(ValueError, match="not validated"):
        compose_answer(tampered, failed)  # validation ran but found problems


# --- architectural boundaries -------------------------------------------------------------

ALLOWED = {
    "catalog": {"catalog"},
    "rag": {"catalog", "evidence", "rag"},
    "evidence": set(),
    "planner": {"catalog", "planner"},
    "respond": {"evidence", "respond"},
    "orchestrator": {
        "planner",
        "analytics",
        "catalog",
        "evidence",
        "respond",
        "rag",
        "orchestrator",
    },
    "api": {"orchestrator", "respond", "catalog", "api"},
}


@pytest.mark.parametrize("layer", sorted(ALLOWED))
def test_layer_imports_respect_the_architecture(layer):
    for path in (ROOT / "src/civicmind" / layer).glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                if name.startswith("civicmind."):
                    target = name.split(".")[1]
                    assert target in ALLOWED[layer] | {layer}, f"{path.name} imports {name}"
                assert not re.match(r"(anthropic|openai|langchain|langgraph|requests)", name)
