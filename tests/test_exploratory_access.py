"""Exploratory access for a validated dataset that review kept out of trusted use.

January 2026 BWSSB water (WATER-BWSSB-2026-01) is ``validated`` with a ``keep_profiled``
review permitting ``exploratory`` (Horamavu anomaly unresolved). Exploratory ingestion must
work only through that explicit path, be labelled as exploratory, and never reach trusted
answers: the planner, trusted ingestion, analytics and evidence validation all refuse it.
Synthetic cases prove the gate was widened by exactly one status (``validated``) and nothing
else.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from civicmind.analytics import water
from civicmind.analytics.result import AnalyticsRefused
from civicmind.catalog.ingest import IngestionRefused, UseNotPermitted, ingest, require_use
from civicmind.catalog.manifest import read_manifest
from civicmind.evidence.model import EvidenceItem, EvidencePackage, validate_package
from civicmind.orchestrator.pipeline import answer_question, sources
from civicmind.planner.catalog_index import load_index
from civicmind.planner.feasibility import check
from civicmind.planner.parser import parse
from civicmind.planner.spec import PlanRefusal
from test_ingest import BWSSB, _bwssb_rows, _csv, _manifest

ROOT = Path(__file__).resolve().parents[1]
JANUARY = "WATER-BWSSB-2026-01"
JANUARY_MANIFEST = ROOT / "data/manifests" / f"{JANUARY}.yaml"
LABEL = "EXPLORATORY: not promoted to trusted use"
RESTRICTIONS = {
    "no_cross_dataset_join",
    "no_measured_performance",
    "no_trusted_analytics",
    "no_ward_efficiency_ranking",
    "no_ward_ranking",
}


def _january():
    if not JANUARY_MANIFEST.is_file():
        pytest.skip("batch 02 manifests not catalogued")
    m = read_manifest(JANUARY_MANIFEST)
    if not (ROOT / m.retrieval.local_path).is_file():
        pytest.skip("January 2026 staged file not present (data is not in Git)")
    return m


# --------------------------------------------------------------------------- real January
def test_january_manifest_is_validated_keep_profiled_and_not_promoted():
    m = _january()
    assert m.status == "validated" and m.human_review == "pending"
    assert m.review.decision == "keep_profiled" and m.review.permitted_uses == ["exploratory"]
    assert m.promoted_to is None
    assert m.review.sha256 == m.integrity.sha256


def test_january_exploratory_ingestion_is_labelled_and_restricted():
    m = _january()
    ds = ingest(m, ROOT, "exploratory")
    assert ds.mode == "exploratory"
    assert ds.source_path == m.retrieval.local_path
    assert ds.source_path.startswith("data/external/batch-02/water/")
    assert ds.sha256 == m.integrity.sha256 and len(ds.raw) == 202
    assert ds.caveats[0].startswith(LABEL)
    assert "modelled" not in ds.caveats[0]  # measured values, not modelled ones
    assert set(ds.restrictions) == RESTRICTIONS
    for use in ("trusted_analytics", "measured_performance", "ward_ranking"):
        with pytest.raises(UseNotPermitted):
            require_use(ds, use)


def test_january_trusted_ingestion_is_refused():
    with pytest.raises(IngestionRefused) as exc:
        ingest(_january(), ROOT, "trusted")
    assert exc.value.code == "status.not_trusted"


def test_january_exploratory_dataset_cannot_reach_trusted_analytics():
    ds = ingest(_january(), ROOT, "exploratory")
    with pytest.raises(AnalyticsRefused, match="dataset.not_trusted"):
        water.water_total(ds, "consumption_ml")
    # Even with restrictions stripped, the mode check alone refuses it.
    with pytest.raises(AnalyticsRefused, match="dataset.not_trusted"):
        water.water_total(dataclasses.replace(ds, restrictions=()), "consumption_ml")


def test_january_exploratory_evidence_is_rejected():
    ds = ingest(_january(), ROOT, "exploratory")
    item = EvidenceItem(
        dataset_id=JANUARY,
        role="primary",
        schema_version=ds.schema_version,
        sha256=ds.sha256,
        source_path=ds.source_path,
        mode=ds.mode,
        period_start="2026-01-01",
        period_end="2026-01-31",
        columns=("Consumption in ML",),
        rows_used=len(ds.raw),
    )
    package = EvidencePackage(
        question="q",
        intent="water_total",
        operation="water_total",
        value=1.0,
        unit="ML",
        method="sum",
        denominator=None,
        caveats=(),
        filters={},
        assumptions=(),
        items=(item,),
    )
    report = validate_package(package, sources(ROOT), [JANUARY])
    assert not report.ok


def test_january_trusted_questions_are_refused_by_planner_and_pipeline():
    _january()
    question = "What was water consumption in January 2026?"
    refusal = check(parse(question), load_index(ROOT))
    assert isinstance(refusal, PlanRefusal) and refusal.code == "dataset.not_trusted"
    answer = answer_question(question, ROOT)
    assert answer.status == "refused" and answer.code == "dataset.not_trusted"


# --------------------------------------------------------------------------- synthetic gate
def _validated(tmp_path, **overrides):
    """A validated, measured dataset with a keep_profiled review permitting exploratory."""
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()), mode="exploratory")
    return m.model_copy(update={"status": "validated", "value_nature": "unknown", **overrides})


def _refused(m, tmp_path, code):
    with pytest.raises(IngestionRefused) as exc:
        ingest(m, tmp_path, "exploratory")
    assert exc.value.code == code


def test_validated_keep_profiled_exploratory_is_admitted(tmp_path):
    ds = ingest(_validated(tmp_path), tmp_path, "exploratory")
    assert ds.mode == "exploratory" and ds.caveats[0].startswith(LABEL)
    assert set(ds.restrictions) == RESTRICTIONS


def test_validated_without_a_review_is_refused(tmp_path):
    _refused(_validated(tmp_path, review=None), tmp_path, "exploratory.not_permitted")


def test_validated_keep_profiled_without_permitted_use_is_refused(tmp_path):
    m = _validated(tmp_path)
    m = m.model_copy(update={"review": m.review.model_copy(update={"permitted_uses": []})})
    _refused(m, tmp_path, "exploratory.not_permitted")


def test_validated_with_an_accept_review_is_refused(tmp_path):
    m = _validated(tmp_path)
    review = m.review.model_copy(update={"decision": "accept", "permitted_uses": []})
    _refused(m.model_copy(update={"review": review}), tmp_path, "exploratory.not_permitted")


@pytest.mark.parametrize("status", ["promoted", "received", "planned"])
def test_other_statuses_are_refused_in_exploratory_mode(tmp_path, status):
    _refused(_validated(tmp_path, status=status), tmp_path, "exploratory.not_permitted")


def test_quarantined_and_rejected_are_refused_in_exploratory_mode(tmp_path):
    _refused(_validated(tmp_path, status="quarantined"), tmp_path, "status.quarantined")
    _refused(_validated(tmp_path, status="rejected"), tmp_path, "status.rejected")


def test_stale_review_is_refused_in_exploratory_mode(tmp_path):
    m = _validated(tmp_path)
    stale = m.review.model_copy(update={"sha256": "0" * 64})
    _refused(m.model_copy(update={"review": stale}), tmp_path, "review.stale")


def test_validated_keep_profiled_is_still_refused_in_trusted_mode(tmp_path):
    with pytest.raises(IngestionRefused) as exc:
        ingest(_validated(tmp_path), tmp_path, "trusted")
    assert exc.value.code == "status.not_trusted"


def test_modelled_exploratory_label_is_unchanged(tmp_path):
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()), mode="exploratory")
    assert m.value_nature == "modelled" and m.status == "integrity_passed"
    ds = ingest(m, tmp_path, "exploratory")
    assert ds.caveats[0] == "EXPLORATORY: modelled or profile-only values; not measurements."
