"""Stage 2A: secure document preparation (single-read hashing, verified I/O, limits, binding).

All documents are SYNTHETIC PDFs generated in memory; every scenario uses a temporary root.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest
import yaml

from civicmind.catalog import safe_fs
from civicmind.catalog.doc_limits import ENV, PreparationLimits
from civicmind.catalog.doc_promote import gate_reasons, promote_document
from civicmind.catalog.doc_review import DocumentDecisionsFile, apply_document_review
from civicmind.catalog.promote import PromotionRefused
from civicmind.catalog.safe_fs import (
    TooLarge,
    UnsafePath,
    move_verified,
    read_verified,
    write_new_verified,
    write_or_match_verified,
)
from civicmind.rag import doc_intake, extract
from civicmind.rag.doc_intake import DocumentIntake, build_document_manifest

pytest.importorskip("pypdf", reason="needs the optional 'rag' extra (pypdf)")
from pdf_synth import make_pdf  # noqa: E402

LOCAL = "data/external/v/docs/roads/r.pdf"
PAGES = ["Chapter one text, long enough to count as a page.", "Chapter two, also long enough."]
LICENCE = {
    "name": "L",
    "url": None,
    "evidence": "t",
    "attribution": "t",
    "exemptions_checked": True,
}


def _intake(**overrides) -> DocumentIntake:
    data = {"document_id": "DOC-T", "title": "Synthetic", "issuing_authority": "A",
            "publisher": "P", "document_type": "act", "domains": ["roads"],
            "source_class": "official", "resource_page": "https://example.invalid",
            "licence": LICENCE, "original_filename": "r.pdf", "local_path": LOCAL}  # fmt: skip
    data.update(overrides)
    return DocumentIntake.model_validate(data)


def _pdf(root: Path, pages=PAGES, rel: str = LOCAL) -> bytes:
    data = make_pdf(pages)
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_bytes(data)
    return data


def _decide(m, **entry):
    body = {"decision": "approve", "sha256": m.integrity.sha256,
            "extraction_sha256": m.extraction.output_sha256, **entry}  # fmt: skip
    return apply_document_review(
        m,
        DocumentDecisionsFile.model_validate(
            {"reviewed_by": "t", "reviewed_on": "2026-10-18", "decisions": {"DOC-T": body}}
        ),
    )


def _link_dir(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            pytest.skip("cannot create directory links here")
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


# --- A1: one byte sequence for hash, inspection and extraction ----------------------------------


def test_hash_and_extraction_come_from_one_verified_read(tmp_path, monkeypatch):
    data = _pdf(tmp_path)
    reads, parsed = [], []
    real_read, real_parse = doc_intake.read_verified, doc_intake.read_pdf_bytes

    def counting_read(*args, **kwargs):
        reads.append(args[1])
        return real_read(*args, **kwargs)

    def capturing_parse(raw, limits):
        parsed.append(raw)
        return real_parse(raw, limits)

    monkeypatch.setattr(doc_intake, "read_verified", counting_read)
    monkeypatch.setattr(doc_intake, "read_pdf_bytes", capturing_parse)
    m = build_document_manifest(_intake(), tmp_path)
    assert reads == [LOCAL]  # exactly one read of the source
    assert len(parsed) == 1 and parsed[0] == data
    assert m.integrity.sha256 == hashlib.sha256(parsed[0]).hexdigest()


def test_text_always_describes_the_hashed_bytes_even_if_the_file_changes(tmp_path, monkeypatch):
    """Simulate the file being replaced right after the single read: the manifest's hash and
    the extracted text both describe the bytes that were read, never a mixture."""
    original = _pdf(tmp_path)
    real_read = doc_intake.read_verified

    def read_then_replace(*args, **kwargs):
        raw = real_read(*args, **kwargs)
        _pdf(tmp_path, ["Replaced after the read, with long enough different text."])
        return raw

    monkeypatch.setattr(doc_intake, "read_verified", read_then_replace)
    m = build_document_manifest(_intake(), tmp_path)
    assert m.integrity.sha256 == hashlib.sha256(original).hexdigest()
    records = extract.read_pages(tmp_path / m.extraction.output_path)
    assert all(r["sha256"] == m.integrity.sha256 for r in records)
    assert "Chapter one" in records[0]["text"]


def test_page_file_records_source_hash_extractor_and_preparation_version(tmp_path):
    _pdf(tmp_path)
    m = build_document_manifest(_intake(), tmp_path)
    assert m.extraction.preparation_version == extract.PREPARATION_VERSION
    assert m.integrity.sha256[:16] in m.extraction.output_path
    assert extract.PREPARATION_VERSION.replace("@", "-") in m.extraction.output_path
    for record in extract.read_pages(tmp_path / m.extraction.output_path):
        assert record["preparation_version"] == extract.PREPARATION_VERSION
        assert record["extractor_version"] == m.extraction.extractor_version
    raw = (tmp_path / m.extraction.output_path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == m.extraction.output_sha256


def test_an_altered_page_file_is_never_overwritten_or_trusted(tmp_path):
    _pdf(tmp_path)
    m = build_document_manifest(_intake(), tmp_path)
    page_file = tmp_path / m.extraction.output_path
    page_file.write_bytes(page_file.read_bytes().replace(b"Chapter", b"Tampered"))
    with pytest.raises(ValueError, match="altered"):
        build_document_manifest(_intake(), tmp_path)
    assert b"Tampered" in page_file.read_bytes()  # left as evidence, not silently replaced


# --- A4: approvals bound to the exact prepared artifact -----------------------------------------


def test_approval_without_extraction_hash_is_not_applied(tmp_path):
    _pdf(tmp_path)
    m = build_document_manifest(_intake(), tmp_path)
    out = _decide(m, extraction_sha256=None)
    assert out.human_review == "pending" and "review.extraction_unbound" in out.warning_codes()


def test_approval_for_other_extracted_text_is_stale(tmp_path):
    _pdf(tmp_path)
    m = build_document_manifest(_intake(), tmp_path)
    out = _decide(m, extraction_sha256="f" * 64)
    assert out.human_review == "pending" and "review.stale_extraction" in out.warning_codes()


def test_preparation_change_invalidates_an_earlier_approval(tmp_path, monkeypatch):
    _pdf(tmp_path)
    before = build_document_manifest(_intake(), tmp_path)
    reviewed_text = before.extraction.output_sha256
    monkeypatch.setattr(extract, "PREPARATION_VERSION", "docprep@v999")
    monkeypatch.setattr(doc_intake, "PREPARATION_VERSION", "docprep@v999")
    after = build_document_manifest(_intake(), tmp_path)
    assert after.integrity.sha256 == before.integrity.sha256  # same source bytes
    assert after.extraction.output_sha256 != reviewed_text  # different text artifact
    out = _decide(after, extraction_sha256=reviewed_text)
    assert "review.stale_extraction" in out.warning_codes()


def test_promotion_rechecks_the_page_file_on_disk(tmp_path):
    _pdf(tmp_path)
    approved = _decide(build_document_manifest(_intake(), tmp_path), excluded_pages=[])
    assert gate_reasons(approved) == []
    page_file = tmp_path / approved.extraction.output_path
    page_file.write_bytes(page_file.read_bytes() + b"\n")
    with pytest.raises(PromotionRefused, match="page file differs"):
        promote_document(approved, tmp_path)
    assert not (tmp_path / "data/docs").exists()


def test_gate_refuses_a_review_not_bound_to_the_current_text(tmp_path):
    _pdf(tmp_path)
    approved = _decide(build_document_manifest(_intake(), tmp_path))
    data = approved.model_dump()
    data["review"] = {**data["review"], "extraction_sha256": "0" * 64}
    from civicmind.catalog.documents import DocumentManifest

    assert "review is not bound to the current extracted text" in gate_reasons(
        DocumentManifest.model_validate(data)
    )


# --- A3: limits -------------------------------------------------------------------------------


def test_oversized_file_is_not_read_beyond_the_limit_and_nothing_is_written(tmp_path):
    data = _pdf(tmp_path)
    limits = PreparationLimits(max_bytes=len(data) - 1)
    m = build_document_manifest(_intake(), tmp_path, limits=limits)
    assert m.status == "received" and "document.too_large" in m.error_codes()
    assert m.integrity is None and m.extraction is None
    assert not (tmp_path / "data/processed").exists()


@pytest.mark.parametrize(
    ("limits", "pages", "code"),
    [
        (PreparationLimits(max_pages=2), PAGES * 2, "pdf.too_many_pages"),
        (PreparationLimits(max_text_chars=40), PAGES, "extraction.too_large"),
    ],
)
def test_page_and_text_limits_fail_without_a_partial_extraction(tmp_path, limits, pages, code):
    _pdf(tmp_path, pages)
    m = build_document_manifest(_intake(), tmp_path, limits=limits)
    assert code in m.error_codes() and m.extraction is None
    assert m.status != "validated"
    assert not (tmp_path / "data/processed").exists()


def test_extraction_time_limit_is_enforced_between_pages(tmp_path, monkeypatch):
    _pdf(tmp_path, PAGES * 3)
    clock = iter(range(0, 10_000, 100))  # every call advances 100 seconds
    monkeypatch.setattr(extract.time, "monotonic", lambda: next(clock))
    m = build_document_manifest(_intake(), tmp_path, limits=PreparationLimits(extract_seconds=150))
    assert "extraction.timeout" in m.error_codes() and m.extraction is None


def test_empty_file_is_not_a_pdf(tmp_path):
    (tmp_path / LOCAL).parent.mkdir(parents=True)
    (tmp_path / LOCAL).write_bytes(b"")
    m = build_document_manifest(_intake(), tmp_path)
    assert "pdf.not_pdf" in m.error_codes() and m.status == "received"


def test_limits_from_environment_and_bad_values_fail_closed():
    limits = PreparationLimits.from_env({ENV["max_bytes"]: "1024", ENV["max_batch"]: "3"})
    assert (limits.max_bytes, limits.max_batch, limits.max_pages) == (1024, 3, 2000)
    for bad in ("0", "-5", "ten", "1.5"):
        with pytest.raises(ValueError):
            PreparationLimits.from_env({ENV["max_pages"]: bad})
    with pytest.raises(ValueError):
        PreparationLimits(max_bytes=True)


def test_batch_size_limit_is_enforced(tmp_path):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("pdb", root / "scripts/process_doc_batch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = tmp_path / "docs/acquisition/b"
    folder.mkdir(parents=True)
    docs = [_intake(document_id=f"DOC-T{i}", local_path=None, original_filename=None).model_dump()
            for i in range(3)]  # fmt: skip
    (folder / "DOCUMENT_INTAKE.yaml").write_text(
        yaml.safe_dump({"batch": "b", "documents": docs}), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="limit is 2"):
        module.process("b", tmp_path, PreparationLimits(max_batch=2))
    assert not (tmp_path / "data/doc_manifests").exists()


# --- A2: handle-verified filesystem operations -------------------------------------------------


def test_read_is_verified_after_opening_even_if_the_precheck_is_bypassed(tmp_path, monkeypatch):
    """With the path pre-check disabled (as in a swap right after it), the opened handle is still
    found to be outside the intake folders and the file is not read."""
    root, outside = tmp_path / "repo", tmp_path / "outside"
    _pdf(outside, rel="r.pdf")
    _link_dir(root / "data/external/v/docs/roads", outside)
    monkeypatch.setattr(doc_intake, "resolves_within", lambda *a, **k: True)
    m = build_document_manifest(_intake(), root)
    assert m.status == "received" and "path.outside_intake" in m.error_codes()
    assert m.integrity is None


def test_write_is_verified_after_creation_and_the_stray_file_removed(tmp_path, monkeypatch):
    root, outside = tmp_path / "repo", tmp_path / "outside"
    outside.mkdir()
    _link_dir(root / "data/docs/roads", outside)
    monkeypatch.setattr(safe_fs, "resolves_within", lambda *a, **k: True)  # bypass the pre-check
    with pytest.raises(UnsafePath, match="created file is outside"):
        write_new_verified(root, "data/docs/roads/r.pdf", "data/docs", b"%PDF-1.4 x")
    assert list(outside.iterdir()) == []  # the file created through the link was removed


def test_verified_write_never_overwrites(tmp_path):
    write_new_verified(tmp_path, "data/docs/a.pdf", "data/docs", b"one")
    with pytest.raises(FileExistsError):
        write_new_verified(tmp_path, "data/docs/a.pdf", "data/docs", b"two")
    assert write_or_match_verified(tmp_path, "data/docs/a.pdf", "data/docs", b"one") == "identical"
    for other in (b"two", b"longer than one"):
        with pytest.raises(UnsafePath, match="different bytes"):
            write_or_match_verified(tmp_path, "data/docs/a.pdf", "data/docs", other)
    assert (tmp_path / "data/docs/a.pdf").read_bytes() == b"one"


def test_read_refuses_directories_oversize_and_traversal(tmp_path):
    (tmp_path / "data/external/d").mkdir(parents=True)
    (tmp_path / "data/external/f.pdf").write_bytes(b"12345")
    with pytest.raises((UnsafePath, PermissionError, IsADirectoryError, OSError)):
        read_verified(tmp_path, "data/external/d", ("data/external",), 10)
    with pytest.raises(TooLarge):
        read_verified(tmp_path, "data/external/f.pdf", ("data/external",), 4)
    for bad in ("data/external/../f.pdf", "/abs/f.pdf", "data/external/f\x00.pdf"):
        with pytest.raises(UnsafePath):
            read_verified(tmp_path, bad, ("data/external",), 10)
    with pytest.raises(UnsafePath):  # inside the root, but not in the permitted folder
        read_verified(tmp_path, "data/external/f.pdf", ("data/docs",), 10)


def test_move_detects_a_swap_during_the_rename(tmp_path, monkeypatch):
    write_new_verified(tmp_path, "data/docs/a.pdf", "data/docs", b"reviewed bytes")
    real_rename = os.rename

    def swapping_rename(src, dst):  # another file ends up at the destination
        real_rename(src, dst)
        Path(dst).write_bytes(b"something else")

    monkeypatch.setattr(safe_fs.os, "rename", swapping_rename)
    with pytest.raises(UnsafePath, match="possible path swap"):
        move_verified(tmp_path, "data/docs/a.pdf", "data/docs", "data/quarantine/a.pdf",
                      "data/quarantine", 100)  # fmt: skip


def test_move_never_replaces_an_existing_destination(tmp_path):
    write_new_verified(tmp_path, "data/docs/a.pdf", "data/docs", b"new")
    write_new_verified(tmp_path, "data/quarantine/a.pdf", "data/quarantine", b"old evidence")
    with pytest.raises(FileExistsError):
        move_verified(tmp_path, "data/docs/a.pdf", "data/docs", "data/quarantine/a.pdf",
                      "data/quarantine", 100)  # fmt: skip
    assert (tmp_path / "data/quarantine/a.pdf").read_bytes() == b"old evidence"
    assert (tmp_path / "data/docs/a.pdf").read_bytes() == b"new"


def test_unsupported_platform_fails_closed(tmp_path, monkeypatch):
    (tmp_path / "data/external").mkdir(parents=True)
    (tmp_path / "data/external/f.pdf").write_bytes(b"x")
    monkeypatch.setattr(safe_fs.sys, "platform", "plan9")
    with pytest.raises(UnsafePath, match="not supported"):
        read_verified(tmp_path, "data/external/f.pdf", ("data/external",), 10)
