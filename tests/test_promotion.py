"""Tests for review decisions and the promotion gate. All fixtures are synthetic."""

from __future__ import annotations

import hashlib

import pytest

from civicmind.catalog.manifest import Manifest
from civicmind.catalog.promote import PromotionRefused, gate_reasons, promote
from civicmind.catalog.review import DecisionsFile, apply_review

DATA = b"Ward number ,Ward Name\r\n1,A\r\n"
SHA = hashlib.sha256(DATA).hexdigest()
SOURCE = "data/external/verify_test/water/f.csv"
WARN = {"code": "ward.duplicated", "severity": "warning", "message": "dup", "details": {}}


def _manifest(**overrides) -> Manifest:
    data = {
        "dataset_id": "TEST-1",
        "title": "Synthetic",
        "publisher": "Nobody",
        "host_portal": "example.invalid",
        "source_class": "official",
        "resource_page": "https://example.invalid/r",
        "download_url": "https://example.invalid/f.csv",
        "licence": {
            "name": "L",
            "url": None,
            "evidence": "test",
            "attribution": "test",
            "exemptions_checked": True,
        },
        "retrieval": {
            "retrieved_at": None,
            "retrieved_by": None,
            "method": "test",
            "original_filename": "f.csv",
            "local_path": SOURCE,
        },
        "integrity": {
            "bytes": len(DATA),
            "portal_stated_bytes": len(DATA),
            "size_matches_portal": True,
            "sha256": SHA,
            "format": "csv",
            "encoding": "utf-8",
            "bom": False,
            "newline": "CRLF",
            "delimiter": ",",
            "passed": True,
        },
        "period": {"start": None, "end": None, "granularity": "month"},
        "geography": {"level": "ward"},
        "sensitivity": "public",
        "contains_personal_data": False,
        "semantic_checks": {"validator": "test@v1", "errors": 0, "warnings": 1},
        "findings": [WARN],
        "status": "validated",
    }
    data.update(overrides)
    return Manifest.model_validate(data)


def _decisions(**entry) -> DecisionsFile:
    base = {"decision": "accept", "sha256": SHA, "accepted_caveats": ["ward.duplicated"]}
    base.update(entry)
    return DecisionsFile.model_validate(
        {"reviewed_by": "tester", "reviewed_on": "2026-01-01", "decisions": {"TEST-1": base}}
    )


@pytest.fixture
def repo(tmp_path):
    src = tmp_path / SOURCE
    src.parent.mkdir(parents=True)
    src.write_bytes(DATA)
    return tmp_path


def _accepted() -> Manifest:
    return apply_review(_manifest(), _decisions())


# --- review -----------------------------------------------------------------------------


def test_review_absent_leaves_manifest_pending():
    m = apply_review(_manifest(), None)
    assert m.human_review == "pending" and m.review is None


def test_accept_covering_all_warnings_is_applied():
    m = _accepted()
    assert m.human_review == "accepted" and m.status == "validated"
    assert m.review.reviewed_by == "tester" and m.review.sha256 == SHA


def test_accept_missing_a_warning_fails_closed():
    m = apply_review(_manifest(), _decisions(accepted_caveats=[]))
    assert m.human_review == "pending" and m.review is None
    assert m.findings[-1]["code"] == "review.incomplete"


def test_review_for_other_bytes_is_stale():
    m = apply_review(_manifest(), _decisions(sha256="0" * 64))
    assert m.human_review == "pending" and m.findings[-1]["code"] == "review.stale"


def test_accept_on_unvalidated_manifest_is_not_applied():
    m = apply_review(_manifest(status="integrity_passed"), _decisions())
    assert m.human_review == "pending" and m.findings[-1]["code"] == "review.not_applicable"


def test_quarantine_and_keep_profiled_decisions():
    q = apply_review(_manifest(status="integrity_passed"), _decisions(decision="quarantine"))
    assert (q.status, q.human_review) == ("quarantined", "rejected")
    k = apply_review(
        _manifest(status="integrity_passed"),
        _decisions(decision="keep_profiled", value_nature="modelled", add_limitations=["x"]),
    )
    assert (k.status, k.human_review) == ("integrity_passed", "pending")
    assert k.value_nature == "modelled"
    assert k.known_limitations[-1] == "x"


# --- promotion --------------------------------------------------------------------------


def test_promote_copies_byte_identically_and_is_idempotent(repo):
    m = promote(_accepted(), repo)
    target = repo / "data/raw/water/f.csv"
    assert target.read_bytes() == DATA
    assert (m.status, m.promoted_to, m.git_tracked) == ("promoted", "data/raw/water/f.csv", False)
    mtime = target.stat().st_mtime_ns
    assert promote(_accepted(), repo).promoted_to == m.promoted_to
    assert target.stat().st_mtime_ns == mtime
    assert not (repo / "data/raw/water/f.csv.partial").exists()
    assert (repo / SOURCE).read_bytes() == DATA


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda m: _manifest(), "no accepted person review"),
        (lambda m: m.model_copy(update={"status": "integrity_passed"}), "status"),
        (lambda m: m.model_copy(update={"sensitivity": "personal_data"}), "not public"),
        (lambda m: m.model_copy(update={"contains_personal_data": True}), "not public"),
        (
            lambda m: m.model_copy(update={"semantic_checks": {"validator": None}}),
            "no validator",
        ),
        (
            lambda m: m.model_copy(update={"semantic_checks": {"validator": "v", "errors": 1}}),
            "no validator",
        ),
        (
            lambda m: m.model_copy(
                update={"licence": m.licence.model_copy(update={"name": "UNKNOWN"})}
            ),
            "licence unknown",
        ),
        (
            lambda m: m.model_copy(
                update={
                    "retrieval": m.retrieval.model_copy(
                        update={"local_path": "data/quarantine/batch-01/f.csv"}
                    )
                }
            ),
            "not under data/external/",
        ),
        (
            lambda m: m.model_copy(
                update={
                    "retrieval": m.retrieval.model_copy(
                        update={"local_path": "data/external/v/other/f.csv"}
                    )
                }
            ),
            "unknown domain",
        ),
        (
            lambda m: m.model_copy(
                update={
                    "retrieval": m.retrieval.model_copy(update={"original_filename": "../f.csv"})
                }
            ),
            "unsafe original_filename",
        ),
        (
            lambda m: m.model_copy(
                update={"integrity": m.integrity.model_copy(update={"passed": False})}
            ),
            "integrity",
        ),
    ],
)
def test_gate_refuses_and_writes_nothing(repo, change, reason):
    m = change(_accepted())
    assert any(reason in r for r in gate_reasons(m))
    with pytest.raises(PromotionRefused):
        promote(m, repo)
    assert not (repo / "data/raw").exists()


def test_promote_refuses_when_source_bytes_changed(repo):
    (repo / SOURCE).write_bytes(DATA + b"2,B\r\n")
    with pytest.raises(PromotionRefused, match="source bytes differ"):
        promote(_accepted(), repo)
    assert not (repo / "data/raw").exists()


def test_promote_refuses_to_overwrite_different_target(repo):
    target = repo / "data/raw/water/f.csv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"other")
    with pytest.raises(PromotionRefused, match="different bytes"):
        promote(_accepted(), repo)
    assert target.read_bytes() == b"other"
