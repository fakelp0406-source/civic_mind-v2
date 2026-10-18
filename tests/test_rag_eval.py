"""Stage 2E: the evaluation's scoring functions, split and label integrity.

The scoring tests use hand-built candidate lists, so they check what the metrics compute, not
how well the system does. The label-integrity test reads the approved corpus and skips when the
git-ignored documents are absent.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rag_metrics", ROOT / "eval/rag_metrics.py")
rm = importlib.util.module_from_spec(spec)
sys.modules["rag_metrics"] = rm  # dataclasses resolve their module
spec.loader.exec_module(rm)

ITEMS = [
    {"id": "S1", "category": "supported", "expect": "answer", "edition": "2019",
     "key_phrases": ["fatal accident"],
     "gold": [{"document_id": "DOC-MORTH-RA2019", "page": 26}]},
    {"id": "S2", "category": "supported", "expect": "answer", "key_phrases": ["formats"],
     "gold": [{"document_id": "DOC-MORTH-RA2023", "page": 132}]},
    {"id": "A1", "category": "absent", "expect": "abstain"},
    {"id": "A2", "category": "absent", "expect": "abstain"},
]  # fmt: skip


def run(item_id, scores, pages, texts=None):
    texts = texts or tuple("" for _ in scores)
    return rm.ItemRun(item_id, tuple(scores), tuple(pages), tuple(texts), 0.0)


RUNS = {
    # gold at rank 2 via a collapsed duplicate page (27 duplicates 26)
    "S1": run(
        "S1",
        [9.0, 8.0],
        [("DOC-MORTH-RA2023", 5, ()), ("DOC-MORTH-RA2019", 27, (26,))],
        ["x", "a fatal accident is one"],
    ),  # fmt: skip
    # gold never retrieved
    "S2": run("S2", [3.0], [("DOC-MORTH-RA2019", 1, ())], ["nothing"]),
    "A1": run("A1", [7.0], [("DOC-MORTH-RA2019", 2, ())]),
    "A2": run("A2", [], []),
}


def test_retrieval_metrics_count_duplicate_pages_and_misses():
    m = rm.retrieval_metrics(RUNS, ITEMS)
    assert m == {"n": 2, "recall@1": 0.0, "recall@3": 0.5, "recall@5": 0.5, "mrr@10": 0.25}


def test_decision_metrics_at_a_threshold():
    m = rm.decision_metrics(RUNS, ITEMS, threshold=5.0)
    assert m["answer_rate"] == 0.5  # S1 answered, S2 (3.0) abstained
    assert m["evidence_supported_rate"] == 0.5 and m["supported_given_answered"] == 1.0
    assert m["chunk_supported_rate"] == 0.5  # the gold chunk contains the key phrase
    assert m["citation_page_precision"] == 0.5  # 1 of 2 citations on a gold page
    assert m["edition_accuracy"] == 0.0  # top citation is from 2023, 2019 was asked
    assert m["abstain_rate"] == 0.5 and m["unsupported_answer_rate"] == 0.5  # A1 answered
    assert m["balanced_accuracy"] == 0.5


def test_infinite_threshold_abstains_on_everything():
    m = rm.decision_metrics(RUNS, ITEMS, threshold=float("inf"))
    assert m["answer_rate"] == 0.0 and m["abstain_rate"] == 1.0
    assert m["balanced_accuracy"] == 0.5


def test_calibration_prefers_the_higher_threshold_on_ties():
    t = rm.calibrate(RUNS, ITEMS)
    best = rm.decision_metrics(RUNS, ITEMS, t)["balanced_accuracy"]
    for other in (3.0, 7.0, 9.0, float("inf")):
        m = rm.decision_metrics(RUNS, ITEMS, other)["balanced_accuracy"]
        assert m < best or (m == best and other <= t)


def test_split_is_deterministic_and_stratified():
    items = [{"id": f"S{n:02d}", "category": "supported"} for n in range(5)] + [
        {"id": f"A{n}", "category": "absent"} for n in range(3)
    ]
    first, second = rm.split(items), rm.split(list(reversed(items)))
    assert first == second
    assert [first[f"S{n:02d}"] for n in range(5)] == ["calibration", "test"] * 2 + ["calibration"]
    assert [first[f"A{n}"] for n in range(3)] == ["calibration", "test", "calibration"]


def test_labels_are_well_formed_and_frozen_by_hash():
    items, sha = rm.load_labels()
    assert len(sha) == 64 and len({i["id"] for i in items}) == len(items)
    for item in items:
        assert item["expect"] in {"answer", "abstain", "deterministic", "not_supported"}
        if item["expect"] == "answer":
            assert item["gold"] and item["key_phrases"]


def test_gold_pages_contain_their_key_phrases_and_absent_facts_are_absent():
    """Re-derives the labels from the approved corpus: every gold page contains a key phrase,
    every page containing one is gold (within the asked edition), and verification phrases of
    absent/misleading items match no page."""
    pytest.importorskip("pypdf", reason="needs the optional 'rag' extra")
    from civicmind.rag.corpus import load_corpus

    try:
        corpus = load_corpus(ROOT)
    except Exception as exc:  # noqa: BLE001 - documents are git-ignored
        pytest.skip(f"approved corpus unavailable: {type(exc).__name__}")
    if not corpus.documents:
        pytest.skip("no approved documents present")
    pages = [(p.document_id, p.page, " ".join(p.text.split()).lower()) for p in corpus.pages]
    items, _ = rm.load_labels()
    for item in items:
        if item["expect"] == "answer":
            docs = {f"DOC-MORTH-RA{item['edition']}"} if item.get("edition") else None
            phrases = [p.lower() for p in item["key_phrases"]]
            found = {(d, n) for d, n, t in pages
                     if (docs is None or d in docs) and any(p in t for p in phrases)}  # fmt: skip
            assert found == rm.gold_set(item), item["id"]
        elif item["category"] in ("absent", "misleading"):
            phrases = [p.lower() for p in item["absent_phrases"]]
            assert not any(any(p in t for p in phrases) for _, _, t in pages), item["id"]


def test_default_thresholds_are_the_reported_calibrated_values():
    """The thresholds in code must be the ones the committed evaluation report calibrated."""
    import json

    from civicmind.rag.retrieve import DEFAULT_RETRIEVAL

    report = ROOT / "eval/reports/rag.v1.results.json"
    if not report.is_file():
        pytest.skip("no evaluation report")
    methods = json.loads(report.read_text(encoding="utf-8"))["methods"]
    assert DEFAULT_RETRIEVAL.bm25_min_score == methods["bm25"]["calibrated_threshold"]
    assert DEFAULT_RETRIEVAL.dense_min_score == methods["dense"]["calibrated_threshold"]
