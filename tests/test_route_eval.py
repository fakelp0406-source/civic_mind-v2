"""Stage 2D evaluation: the routing scorer and its link to the router's defaults."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from civicmind.orchestrator.router import DEFAULT_ROUTER, RoutedAnswer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("route_metrics", ROOT / "eval/route_metrics.py")
route_metrics = importlib.util.module_from_spec(spec)
sys.modules["route_metrics"] = route_metrics
spec.loader.exec_module(route_metrics)

SUPPORTED = {"id": "S1", "expect": "answer",
             "gold": [{"document_id": "DOC-MORTH-RA2019", "page": 26}]}  # fmt: skip


def routed(status="answered", route="documents", citations=(), analytics=None):
    return RoutedAnswer(route, status, "q", "t", citations=tuple(citations), analytics=analytics)


def test_supported_items_need_a_gold_citation():
    gold = [{"document_id": "DOC-MORTH-RA2019", "page": 26}]
    other = [{"document_id": "DOC-MORTH-RA2023", "page": 9}]
    assert route_metrics.score(SUPPORTED, routed(citations=gold), None) == "correct"
    assert route_metrics.score(SUPPORTED, routed(citations=other), None) == "unsupported_answer"
    assert route_metrics.score(SUPPORTED, routed("refused", "refused"), None) == "abstained"


def test_abstention_items_and_analytics_items():
    item = {"id": "A1", "expect": "abstain"}
    assert route_metrics.score(item, routed("refused", "refused"), None) == "correct"
    assert route_metrics.score(item, routed(), None) == "unsupported_answer"
    analytics = {"id": "R1", "expect": "deterministic"}
    det = {"value": 3041}
    assert (
        route_metrics.score(analytics, routed(route="analytics", analytics=det), det) == "correct"
    )
    assert route_metrics.score(analytics, routed(), det) == "wrong_route"
    assert (
        route_metrics.score({"id": "C1", "expect": "not_supported"}, routed(), None) == "unscored"
    )


def test_router_default_gate_is_the_one_chosen_on_calibration():
    report = ROOT / "eval/reports/route.v1.results.json"
    if not report.is_file():
        pytest.skip("no router evaluation report")
    data = json.loads(report.read_text(encoding="utf-8"))
    assert DEFAULT_ROUTER.gate == data["chosen_gate_on_calibration"]
    assert data["labels"]["sha256"] == route_metrics.FROZEN_SHA


def test_evaluation_refuses_changed_labels(monkeypatch):
    monkeypatch.setattr(route_metrics.rm, "load_labels", lambda: ([], "0" * 64))
    with pytest.raises(SystemExit, match="labels changed"):
        route_metrics.evaluate()
