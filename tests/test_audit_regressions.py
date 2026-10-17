"""Regression tests for defects found in the 2026-10-17 audit. Synthetic fixtures unless noted."""

from __future__ import annotations

from pathlib import Path

import pytest

from civicmind.analytics import roads, water
from civicmind.catalog.ingest import ingest
from civicmind.catalog.manifest import read_manifest
from civicmind.catalog.promote import gate_reasons
from civicmind.catalog.quarantine import QuarantineConflict, move_to_quarantine
from civicmind.catalog.schemas import SCHEMAS, get_schema
from civicmind.catalog.sensitivity import scan_header
from civicmind.orchestrator import pipeline
from civicmind.orchestrator.pipeline import answer_question
from civicmind.planner.parser import parse
from civicmind.planner.spec import PlanRefusal
from test_ingest import RA2024, _csv, _manifest, _morth_rows

ROOT = Path(__file__).resolve().parents[1]
BWSSB = get_schema("bwssb_monthly/v1").columns
KILLED = "Over-Speeding - Persons Killed - Number"

# --- Critical: ward-scoped water questions must never return the city total ---------------


@pytest.mark.parametrize(
    "question",
    [
        "Total water consumption of the ward in August 2025?",
        "What was the water consumption of each ward in August 2025?",
        "How much water did the ward use in August 2025?",
        "What was the water consumption for one ward in August 2025?",
        "Water consumption in a single ward in August 2025",
        "What was water consumption per ward in August 2025?",
        "How many connections did the row have in August 2025?",
        "How did consumption per ward change from August 2025 to March 2026?",
    ],
)
def test_ward_scoped_questions_do_not_return_a_city_total(question):
    result = parse(question)
    assert isinstance(result, PlanRefusal), question
    assert result.code == "query.unsupported_operation"


def test_explicit_all_wards_total_is_still_answered_as_a_city_total():
    spec = parse("Total water consumption across all wards in August 2025?")
    assert spec.intent == "water_total"


# --- High: quarantine never overwrites ------------------------------------------------------


def test_quarantine_refuses_to_overwrite_a_file_with_the_same_name(tmp_path):
    (tmp_path / "ext").mkdir()
    (tmp_path / "q").mkdir()
    new = tmp_path / "ext" / "f.csv"
    old = tmp_path / "q" / "f.csv"
    new.write_bytes(b"NEW BYTES")
    old.write_bytes(b"OLD QUARANTINED BYTES")
    with pytest.raises(QuarantineConflict):
        move_to_quarantine(new, tmp_path / "q")
    assert old.read_bytes() == b"OLD QUARANTINED BYTES"  # evidence kept
    assert new.read_bytes() == b"NEW BYTES"  # source untouched


def test_quarantine_refuses_even_identical_bytes(tmp_path):
    (tmp_path / "q").mkdir()
    (tmp_path / "f.csv").write_bytes(b"same")
    (tmp_path / "q" / "f.csv").write_bytes(b"same")
    with pytest.raises(QuarantineConflict):
        move_to_quarantine(tmp_path / "f.csv", tmp_path / "q")
    assert (tmp_path / "f.csv").exists()


def test_quarantine_moves_bytes_unchanged_and_is_idempotent(tmp_path):
    data = b"a,b\r1,2\r"
    (tmp_path / "f.csv").write_bytes(data)
    target = move_to_quarantine(tmp_path / "f.csv", tmp_path / "q")
    assert target.read_bytes() == data and not (tmp_path / "f.csv").exists()
    assert move_to_quarantine(target, tmp_path / "q") == target  # already there


def test_quarantine_of_a_missing_file_is_an_explicit_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        move_to_quarantine(tmp_path / "absent.csv", tmp_path / "q")


# --- High: personal-data flags come from evidence, not a constant ---------------------------


@pytest.mark.parametrize(
    "column",
    ["Staff Name", "Staff Remarks", "Mobile No", "Phone Number", "Complainant Address",
     "E-mail", "Name", "Aadhaar Number", "Date of Birth"],
)  # fmt: skip
def test_header_scan_flags_personal_data_columns(column):
    assert scan_header(["Ward number ", column])[0]["column"] == column


def test_header_scan_has_no_false_positives_on_registered_schemas():
    for schema in SCHEMAS:  # includes "Ward Name", "City Name", "Use of Mobile Phone - ..."
        assert scan_header(schema.columns) == [], schema.version


def test_manifests_record_the_header_scan_as_evidence():
    for path in sorted((ROOT / "data/manifests").glob("*.yaml")):
        m = read_manifest(path)
        scans = [f for f in m.findings if f["code"].startswith("sensitivity.")]
        assert len(scans) == 1, path.name
        assert scans[0]["details"]["matched"] == []
        assert "column names only" in scans[0]["details"]["method"]
        assert m.contains_personal_data is False and m.sensitivity == "public"


def test_processor_does_not_default_to_public():
    source = (ROOT / "scripts/process_batch_01.py").read_text(encoding="utf-8")
    assert '"contains_personal_data": False' not in source
    assert '"sensitivity": "public",' not in source


# --- High: ties at the ranking cut-off are disclosed -----------------------------------------


def _water(tmp_path, rows):
    m = _manifest(tmp_path, _csv(BWSSB, rows))
    caveats = ["ward.duplicated", "consumption_ml.zero", "connections.zero"]
    m = m.model_copy(update={"review": m.review.model_copy(update={"accepted_caveats": caveats})})
    return ingest(m, tmp_path)


def test_water_rankings_disclose_ties_beyond_the_cut_off(tmp_path):
    ds = _water(tmp_path, [[1, "A", 10, "5"], [2, "B", 10, "3"], [3, "C", 10, "3"]])
    for fn in (water.water_rank_rows, water.water_rank_wards):
        res = fn(ds, "consumption_ml", n=2)
        assert [r["ward_name"] for r in res.value["rows"]] == ["A", "B"]
        assert res.value["ties_beyond_cutoff"] == 1
        assert res.caveats[0].startswith("TIES BEYOND CUT-OFF: 1 more item(s) share rank 2")
        assert "(C)" in res.caveats[0]
        full = fn(ds, "consumption_ml", n=3)
        assert full.value["ties_beyond_cutoff"] == 0
        assert not any(c.startswith("TIES") for c in full.caveats)


def test_city_ranking_discloses_ties_beyond_the_cut_off(tmp_path):
    rows = _morth_rows(RA2024, ("Alpha", "Beta", "Gamma"))
    col = RA2024.index(KILLED)
    rows[0][col], rows[1][col], rows[2][col], rows[3][col] = 9, 5, 5, 19
    m = _manifest(tmp_path, _csv(RA2024, rows), domain="roads",
                  semantic_checks={"validator": "morth_city@v1"})  # fmt: skip
    res = roads.road_top_cities(ingest(m, tmp_path), KILLED, n=2)
    assert [r["city"] for r in res.value] == ["Alpha", "Beta"]
    assert res.caveats[0].startswith("TIES BEYOND CUT-OFF") and "(Gamma)" in res.caveats[0]


HAVE_RA2024 = (ROOT / "data/raw/roads/Transport_2024_Annexure_47.csv").is_file()


@pytest.mark.skipif(not HAVE_RA2024, reason="promoted RA2024 file not present")
def test_real_tie_at_the_cut_off_is_disclosed_end_to_end():
    # Real data: 2024 mobile-phone deaths, top 3; Varanasi ties at rank 3 and was hidden.
    answer = answer_question("Which three cities had the most mobile phone deaths in 2024?", ROOT)
    assert answer.status == "answered", answer.text
    assert any(c.startswith("TIES BEYOND CUT-OFF") and "Varanasi" in c for c in answer.caveats)
    assert "tie at the last rank shown" in answer.text


# --- Medium: internal errors do not leak exception text --------------------------------------


@pytest.mark.skipif(not HAVE_RA2024, reason="promoted data not present")
def test_internal_error_reason_does_not_echo_the_exception(monkeypatch):
    def leak(*args, **kwargs):
        raise FileNotFoundError(r"C:\Users\someone\private\secret-token.csv")

    monkeypatch.setitem(pipeline.DISPATCH, "road_top_cities", leak)
    answer = answer_question("Which three cities had the most mobile phone deaths in 2024?", ROOT)
    assert answer.code == "pipeline.internal_error"
    assert "secret" not in answer.text and "Users" not in answer.reason
    assert "FileNotFoundError" in answer.reason


# --- Medium: modelled data never passes the promotion gate ------------------------------------


def test_promotion_gate_refuses_modelled_values():
    from test_promotion import _accepted

    m = _accepted().model_copy(update={"value_nature": "modelled"})
    assert any("modelled" in r for r in gate_reasons(m))
