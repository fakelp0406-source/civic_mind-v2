"""Security and data-governance regressions for the document catalogue (Milestone 05 stage 1).

Every scenario runs in a temporary project root with SYNTHETIC PDFs. Paths are built with
``pathlib``; links are real symlinks where the OS allows them, otherwise Windows directory
junctions (which need no administrator rights). Covered: document ids and file names that could
escape storage directories, source and target paths that escape through ``..`` or links, stale
and orphaned promoted copies, cross-batch id reuse, planned-document wording, the optional pypdf
dependency, and invariants over the repository's own document manifests.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from civicmind.catalog.doc_promote import promote_document
from civicmind.catalog.doc_review import DocumentDecisionsFile, apply_document_review
from civicmind.catalog.documents import (
    DocumentManifest,
    path_problem,
    read_document_manifests,
    resolves_within,
)
from civicmind.catalog.promote import PromotionRefused
from civicmind.rag.doc_intake import EXTRACTED_DIR, DocumentIntake, build_document_manifest

pytest.importorskip("pypdf", reason="needs the optional 'rag' extra (pypdf)")
from pdf_synth import make_pdf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
LOCAL = "data/external/v/docs/roads/r.pdf"
PROMOTED = "data/docs/roads/r.pdf"
PAGES = ["Chapter one text, long enough to count as a page.", "Chapter two, also long enough."]
LICENCE = {
    "name": "L",
    "url": None,
    "evidence": "t",
    "attribution": "t",
    "exemptions_checked": True,
}


def _intake(**overrides) -> DocumentIntake:
    data = {
        "document_id": "DOC-T",
        "title": "Synthetic",
        "issuing_authority": "A",
        "publisher": "P",
        "document_type": "act",
        "domains": ["roads"],
        "source_class": "official",
        "resource_page": "https://example.invalid",
        "licence": LICENCE,
        "original_filename": "r.pdf",
        "local_path": LOCAL,
    }
    data.update(overrides)
    return DocumentIntake.model_validate(data)


def _pdf(path: Path, pages=PAGES) -> bytes:
    data = make_pdf(pages)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _approve(m: DocumentManifest) -> DocumentManifest:
    decisions = {"reviewed_by": "t", "reviewed_on": "2026-10-18",
                 "decisions": {m.document_id: {
                     "decision": "approve", "sha256": m.integrity.sha256,
                     "extraction_sha256": m.extraction.output_sha256}}}  # fmt: skip
    return apply_document_review(m, DocumentDecisionsFile.model_validate(decisions))


def _link_dir(link: Path, target: Path) -> str:
    """Make ``link`` point at directory ``target``: a symlink, or a Windows junction."""
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            pytest.skip("cannot create directory links here")
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        return "junction"


def _approval(root: Path, data: bytes) -> dict:
    """An approve decision for the bytes ``data`` at ``LOCAL`` and their extracted text."""
    text_sha = build_document_manifest(_intake(), root).extraction.output_sha256
    return {"decision": "approve", "sha256": hashlib.sha256(data).hexdigest(),
            "extraction_sha256": text_sha}  # fmt: skip


def _files(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def _processor():
    spec = importlib.util.spec_from_file_location("pdb", ROOT / "scripts/process_doc_batch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.process


def _batch(root: Path, batch: str, intakes: list[DocumentIntake], decisions=None) -> None:
    folder = root / "docs/acquisition" / batch
    folder.mkdir(parents=True, exist_ok=True)
    body = {"batch": batch, "documents": [i.model_dump() for i in intakes]}
    (folder / "DOCUMENT_INTAKE.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")
    if decisions is not None:
        body = {"reviewed_by": "t", "reviewed_on": "2026-10-18", "decisions": decisions}
        (folder / "DOCUMENT_REVIEW_DECISIONS.yaml").write_text(
            yaml.safe_dump(body), encoding="utf-8"
        )


# --- 1. document ids cannot write outside the extraction directory -----------------------------


@pytest.mark.parametrize(
    "bad",
    ["../../../../../escaped", "DOC-../../x", "DOC-A/B", "DOC-A\\B", "DOC-A\n", "doc-a",
     "DOC-", "DOC-A.B", "C:DOC-A", ""],
)  # fmt: skip
def test_document_ids_that_are_not_plain_tokens_are_rejected_everywhere(bad):
    with pytest.raises(ValueError):
        _intake(document_id=bad)
    valid = _intake().model_dump()
    with pytest.raises(ValueError):
        DocumentManifest.model_validate(
            {**{k: v for k, v in valid.items() if k in DocumentManifest.model_fields},
             "document_id": bad, "retrieval": {"method": "m", "original_filename": "r.pdf",
                                                "retrieved_at": None, "retrieved_by": None,
                                                "local_path": None},
             "status": "planned"}
        )  # fmt: skip


def test_extraction_output_stays_inside_its_directory(tmp_path):
    root = tmp_path / "repo"
    _pdf(root / LOCAL)
    m = build_document_manifest(_intake(), root)
    assert m.status == "validated"
    assert resolves_within(root, m.extraction.output_path, EXTRACTED_DIR)
    assert _files(tmp_path) == sorted(
        [f"repo/{LOCAL}", f"repo/{m.extraction.output_path}"]
    )  # nothing else written anywhere under the temporary directory


def test_linked_extraction_directory_is_refused_and_nothing_is_written_outside(tmp_path):
    root, outside = tmp_path / "repo", tmp_path / "outside"
    outside.mkdir()
    _pdf(root / LOCAL)
    _link_dir(root / EXTRACTED_DIR, outside)
    with pytest.raises(ValueError, match="outside the project root"):
        build_document_manifest(_intake(), root)
    assert _files(outside) == []


# --- 2. source paths cannot escape the intake directory ----------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["data/external/../../../outside/docs/roads/r.pdf",
     "data/external/v/docs/roads/../../../x.pdf",
     "/abs/docs/roads/r.pdf", "C:/abs/docs/roads/r.pdf", "C:data/external/r.pdf",
     "//server/share/docs/roads/r.pdf", r"data\external\v\docs\roads\r.pdf",
     "data/raw/roads/r.pdf", "data/externalx/docs/roads/r.pdf"],
)  # fmt: skip
def test_intake_refuses_source_paths_outside_data_external(bad):
    with pytest.raises(ValueError):
        _intake(local_path=bad)


@pytest.mark.parametrize("bad", ["../r.pdf", "a/r.pdf", r"a\r.pdf", "C:r.pdf", ".", ".."])
def test_intake_refuses_file_names_that_are_paths(bad):
    with pytest.raises(ValueError):
        _intake(original_filename=bad)


def test_path_problem_is_platform_independent():
    assert path_problem("data/external/v/docs/roads/r.pdf") is None
    for bad in ("../x", "a/../b", "/x", "C:/x", "C:x", r"a\b", "//h/s/x"):
        assert path_problem(bad), bad


def test_linked_source_folder_is_not_read(tmp_path):
    root, outside = tmp_path / "repo", tmp_path / "outside"
    _pdf(outside / "r.pdf")
    _link_dir(root / "data/external/v/docs/roads", outside)
    m = build_document_manifest(_intake(), root)
    assert m.status == "received" and "path.outside_intake" in m.error_codes()
    assert m.integrity is None and m.extraction is None  # bytes were never read
    assert not (root / EXTRACTED_DIR).exists()


def test_promotion_refuses_a_source_that_became_a_link_after_review(tmp_path):
    root, outside = tmp_path / "repo", tmp_path / "outside"
    data = _pdf(root / LOCAL)
    approved = _approve(build_document_manifest(_intake(), root))
    (root / LOCAL).unlink()
    (root / LOCAL).parent.rmdir()
    _pdf(outside / "r.pdf", PAGES)  # identical bytes, now outside the repository
    assert (outside / "r.pdf").read_bytes() == data
    _link_dir(root / "data/external/v/docs/roads", outside)
    with pytest.raises(PromotionRefused, match="outside data/external"):
        promote_document(approved, root)
    assert not (root / PROMOTED).exists()


def test_promotion_refuses_a_linked_target_folder(tmp_path):
    root, outside = tmp_path / "repo", tmp_path / "outside"
    outside.mkdir()
    _pdf(root / LOCAL)
    approved = _approve(build_document_manifest(_intake(), root))
    _link_dir(root / "data/docs/roads", outside)
    with pytest.raises(PromotionRefused, match="resolves outside data/docs"):
        promote_document(approved, root)
    assert _files(outside) == []


def test_orphan_sweep_never_moves_files_through_a_linked_folder(tmp_path):
    root, outside = tmp_path / "repo", tmp_path / "outside"
    _pdf(outside / "r.pdf")
    _pdf(root / LOCAL)
    _link_dir(root / "data/docs/roads", outside)
    _batch(root, "b", [_intake()])  # validated, not approved: a sweep candidate
    [row] = _processor()("b", root)
    assert row["status"] == "validated"
    assert _files(outside) == ["r.pdf"]
    assert not (root / "data/quarantine").exists()


# --- 3. stale or orphaned copies cannot bypass the gate ----------------------------------------


def test_planted_copy_does_not_make_a_document_approved(tmp_path):
    root = tmp_path / "repo"
    data = _pdf(root / LOCAL)
    (root / PROMOTED).parent.mkdir(parents=True)
    (root / PROMOTED).write_bytes(data)  # identical bytes planted without any review
    _batch(root, "b", [_intake()])
    [row] = _processor()("b", root)
    assert (row["status"], row["human_review"], row["promoted_to"]) == (
        "validated",
        "pending",
        None,
    )
    assert not (root / PROMOTED).exists()  # moved out of data/docs/, not trusted
    assert (root / "data/quarantine/b/docs/promoted/r.pdf").read_bytes() == data


def test_planted_copy_with_other_bytes_blocks_promotion_until_removed(tmp_path):
    root = tmp_path / "repo"
    data = _pdf(root / LOCAL)
    (root / PROMOTED).parent.mkdir(parents=True)
    (root / PROMOTED).write_bytes(b"%PDF-1.4 planted, different bytes")
    _batch(root, "b", [_intake()], {"DOC-T": _approval(root, data)})
    process = _processor()
    [first] = process("b", root)
    assert first["status"] == "validated" and "promotion.refused" in first["warnings"]
    planted = root / "data/quarantine/b/docs/promoted/r.pdf"
    assert planted.read_bytes() == b"%PDF-1.4 planted, different bytes"
    [second] = process("b", root)
    assert second["status"] == "approved"
    assert (root / PROMOTED).read_bytes() == data  # only the reviewed bytes are promoted


def test_stale_review_never_promotes_new_bytes(tmp_path):
    root = tmp_path / "repo"
    old = _pdf(root / LOCAL)
    _batch(root, "b", [_intake()], {"DOC-T": _approval(root, old)})
    process = _processor()
    assert process("b", root)[0]["status"] == "approved"
    _pdf(root / LOCAL, ["Replaced after the review with different, long enough text."])
    for _ in range(2):  # repeated runs stay pending
        [row] = process("b", root)
        assert (row["status"], row["human_review"]) == ("validated", "pending")
        assert not (root / PROMOTED).exists()
    assert (root / "data/quarantine/b/docs/promoted/r.pdf").read_bytes() == old


# --- 4. cross-batch document-id reuse ----------------------------------------------------------


def test_document_id_reuse_is_refused_in_both_directions_without_writing(tmp_path):
    root = tmp_path / "repo"
    _batch(root, "b1", [_intake(local_path=None, original_filename=None)])
    _batch(root, "b2", [_intake(title="Other", local_path=None, original_filename=None)])
    process = _processor()
    for batch, other in (("b1", "b2"), ("b2", "b1")):
        with pytest.raises(SystemExit, match=rf"DOC-T \(batch {other}\)"):
            process(batch, root)
    assert not (root / "data/doc_manifests").exists()


def test_duplicate_id_within_one_intake_is_refused(tmp_path):
    root = tmp_path / "repo"
    blank = {"local_path": None, "original_filename": None}
    _batch(root, "b", [_intake(**blank), _intake(title="Again", **blank)])
    with pytest.raises(SystemExit, match="duplicate document_id"):
        _processor()("b", root)


# --- 5. planned documents and repository invariants --------------------------------------------


def _repo_manifests() -> list[DocumentManifest]:
    return read_document_manifests(ROOT)


def test_planned_manifests_claim_no_download_ingestion_or_trust():
    planned = [m for m in _repo_manifests() if m.status == "planned"]
    for m in planned:
        assert m.integrity is None and m.extraction is None, m.document_id
        assert m.retrieval.method == "not yet retrieved"
        assert m.retrieval.original_filename == "not yet retrieved"
        assert m.retrieval.retrieved_at is None and m.retrieval.retrieved_by is None
        assert m.human_review == "pending" and m.review is None
        assert m.promoted_to is None
        assert m.sensitivity == "restricted"  # never presented as screened or public
        assert not m.error_codes()


def test_pilot_batch_trust_follows_recorded_decisions_only():
    """Nothing in docs-01 is approved, promoted or trusted unless a person's decision for those
    exact bytes and that exact page file is recorded; unretrieved entries stay planned."""
    batch = ROOT / "docs/acquisition/docs-01"
    summary = json.loads((batch / "document_summary.json").read_text(encoding="utf-8"))
    intake = yaml.safe_load((batch / "DOCUMENT_INTAKE.yaml").read_text(encoding="utf-8"))
    decisions_file = batch / "DOCUMENT_REVIEW_DECISIONS.yaml"
    decisions = (
        yaml.safe_load(decisions_file.read_text(encoding="utf-8"))["decisions"]
        if decisions_file.is_file()
        else {}
    )
    manifests = {m.document_id: m for m in _repo_manifests()}
    assert [r["document_id"] for r in summary] == [d["document_id"] for d in intake["documents"]]
    for row, entry in zip(summary, intake["documents"], strict=True):
        m = manifests[row["document_id"]]
        assert (row["status"], row["human_review"], row["promoted_to"]) == (
            m.status,
            m.human_review,
            m.promoted_to,
        )
        if not entry.get("local_path"):
            assert m.status == "planned" and m.integrity is None and m.extraction is None
            assert row["sha256"] is None and row["extraction_sha256"] is None
            continue
        assert row["sha256"] == m.integrity.sha256
        assert row["extraction_sha256"] == m.extraction.output_sha256
        decision = decisions.get(m.document_id)
        if m.human_review == "accepted" or m.status == "approved" or m.promoted_to:
            assert decision is not None and decision["decision"] == "approve", m.document_id
            assert decision["sha256"] == m.integrity.sha256
            assert decision["extraction_sha256"] == m.extraction.output_sha256
        if decision is None:
            assert m.human_review == "pending" and m.status != "approved" and not m.promoted_to


def test_every_file_in_data_docs_is_claimed_by_an_approved_manifest():
    claimed = {m.promoted_to for m in _repo_manifests() if m.status == "approved"}
    docs = ROOT / "data/docs"
    present = {
        f"data/docs/{p}" for p in _files(docs) if not p.endswith(".gitkeep")
    } if docs.is_dir() else set()  # fmt: skip
    assert present <= claimed, f"unclaimed files in data/docs/: {sorted(present - claimed)}"


def test_approved_manifests_are_bound_to_their_bytes():
    from civicmind.catalog.fingerprint import sha256_of

    for m in _repo_manifests():
        if m.status != "approved":
            continue
        assert m.review and m.review.decision == "approve"
        assert m.review.sha256 == m.integrity.sha256
        assert sha256_of(ROOT / m.promoted_to) == m.integrity.sha256


# --- 6. the optional dependency ----------------------------------------------------------------

_WITHOUT_PYPDF = """
import sys
sys.modules["pypdf"] = None  # behave as if the 'rag' extra were not installed
sys.path.insert(0, {src!r})
import importlib
for name in ("civicmind.catalog.documents", "civicmind.catalog.doc_review",
             "civicmind.catalog.doc_promote", "civicmind.catalog.ingest", "civicmind.rag.extract",
             "civicmind.rag.screen", "civicmind.rag.doc_intake", "civicmind.orchestrator.pipeline",
             "civicmind.api.app"):
    importlib.import_module(name)
from pathlib import Path
from civicmind.rag.extract import PdfSupportMissing, read_pdf
p = Path({tmp!r}) / "a.pdf"
p.write_bytes(b"%PDF-1.4\\n%%EOF\\n")
try:
    read_pdf(p)
    print("NO-ERROR")
except PdfSupportMissing as exc:
    assert isinstance(exc, ImportError) and "optional 'rag' extra" in str(exc), exc
    print("IMPORT-ERROR")
not_pdf = Path({tmp!r}) / "b.pdf"
not_pdf.write_bytes(b"<html></html>")
print(read_pdf(not_pdf)[0].error)
"""


def test_unrelated_imports_work_without_pypdf(tmp_path):
    code = _WITHOUT_PYPDF.format(src=str(SRC), tmp=str(tmp_path))
    out = subprocess.run(
        [sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=120, check=True
    ).stdout.split()
    # Importing never needs pypdf; reading a PDF says so plainly; non-PDF bytes need no pypdf.
    assert out == ["IMPORT-ERROR", "pdf.not_pdf"]


def test_planned_only_batch_processes_without_pypdf(tmp_path):
    root = tmp_path / "repo"
    _batch(root, "b", [_intake(local_path=None, original_filename=None)])
    code = (
        "import sys, importlib.util\n"
        "sys.modules['pypdf'] = None\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        "spec = importlib.util.spec_from_file_location('p', "
        f"{str(ROOT / 'scripts/process_doc_batch.py')!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        f"print(m.process('b', __import__('pathlib').Path({str(root)!r}))[0]['status'])\n"
    )
    out = subprocess.run(
        [sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=120, check=True
    )
    assert out.stdout.strip() == "planned"


def test_processing_a_pdf_without_pypdf_fails_with_a_controlled_error(tmp_path):
    root = tmp_path / "repo"
    _pdf(root / LOCAL)
    _batch(root, "b", [_intake()])
    code = (
        "import sys, importlib.util\n"
        "sys.modules['pypdf'] = None\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        "from civicmind.rag.extract import PdfSupportMissing\n"
        "spec = importlib.util.spec_from_file_location('p', "
        f"{str(ROOT / 'scripts/process_doc_batch.py')!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "try:\n"
        f"    m.process('b', __import__('pathlib').Path({str(root)!r}))\n"
        "except PdfSupportMissing as exc:\n"
        "    print('CONTROLLED:', exc)\n"
    )
    out = subprocess.run(
        [sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=120, check=True
    ).stdout
    assert out.startswith("CONTROLLED:") and 'pip install -e ".[rag]"' in out
    assert not (root / "data/doc_manifests").exists()
    assert not (root / "docs/acquisition/b/document_summary.json").exists()


# --- 7. malformed paths, dangling links, filesystem errors, operation-boundary checks ----------


@pytest.mark.parametrize(
    "bad",
    ["data/external/v/docs/roads/r\x00.pdf", "data/external/v/docs/roads/r\n.pdf",
     "data/external/v/docs/roads/r\x7f.pdf", "data/external/v/docs/roads/r.pdf:stream"],
)  # fmt: skip
def test_control_characters_and_streams_are_rejected_in_source_paths(bad):
    assert path_problem(bad)
    with pytest.raises(ValueError):
        _intake(local_path=bad)


@pytest.mark.parametrize(
    "bad",
    ["r\x00.pdf", "r\n.pdf", "r.pdf:stream", "CON.pdf", "nul.pdf", "com1.pdf", "lpt9",
     "r.pdf.", "r.pdf ", ""],
)  # fmt: skip
def test_unportable_file_names_are_rejected(bad):
    with pytest.raises(ValueError):
        _intake(original_filename=bad)


def test_resolves_within_fails_closed_on_malformed_paths(tmp_path):
    assert not resolves_within(tmp_path, "data/docs/r\x00.pdf", "data/docs")
    assert not resolves_within(tmp_path, "../outside.pdf", "data/docs")
    assert resolves_within(tmp_path, "data/docs/roads/r.pdf", "data/docs")


def _dangling_link(link: Path, target: Path) -> None:
    target.mkdir(parents=True)
    _link_dir(link, target)
    target.rmdir()


def test_dangling_source_link_is_never_read(tmp_path):
    root = tmp_path / "repo"
    _dangling_link(root / "data/external/v/docs/roads", tmp_path / "gone")
    m = build_document_manifest(_intake(), root)
    assert m.status == "planned" and m.integrity is None and m.extraction is None
    assert not (tmp_path / "gone").exists()


def test_dangling_target_link_refuses_promotion_and_creates_nothing(tmp_path):
    root = tmp_path / "repo"
    _pdf(root / LOCAL)
    approved = _approve(build_document_manifest(_intake(), root))
    _dangling_link(root / "data/docs/roads", tmp_path / "gone")
    with pytest.raises(PromotionRefused, match="resolves outside data/docs"):
        promote_document(approved, root)
    assert not (tmp_path / "gone").exists()


def test_filesystem_error_while_building_aborts_before_any_manifest_is_written(
    tmp_path, monkeypatch
):
    import civicmind.rag.doc_intake as doc_intake

    def denied(*_args, **_kwargs):
        raise PermissionError("access denied")

    root = tmp_path / "repo"
    _pdf(root / LOCAL)
    _batch(root, "b", [_intake()])
    monkeypatch.setattr(doc_intake, "read_verified", denied)  # the single verified read
    with pytest.raises(PermissionError):
        _processor()("b", root)
    assert not (root / "data/doc_manifests").exists()
    assert not (root / "docs/acquisition/b/document_summary.json").exists()
    assert not (root / "data/docs").exists()


def test_read_boundary_is_enforced_for_an_explicit_file_argument(tmp_path):
    """``build_document_manifest(file=...)`` (used for quarantined copies) checks the actual
    file, not only the intake schema: a file outside the intake folders is not read."""
    root, outside = tmp_path / "repo", tmp_path / "outside.pdf"
    _pdf(outside)
    m = build_document_manifest(_intake(), root, file=outside)
    assert m.status == "received" and "path.outside_intake" in m.error_codes()
    assert m.integrity is None


def test_orphan_sweep_ignores_a_hand_edited_manifest_with_an_unsafe_file_name(tmp_path):
    root = tmp_path / "repo"
    victim = root / "data/victim.txt"
    victim.parent.mkdir(parents=True)
    victim.write_text("keep me", encoding="utf-8")
    data = build_document_manifest(_intake(local_path=None, original_filename=None), root)
    hand_edited = DocumentManifest.model_validate(
        {**data.model_dump(), "status": "validated",
         "retrieval": {**data.model_dump()["retrieval"], "local_path": LOCAL,
                       "original_filename": "../../victim.txt"}}
    )  # fmt: skip
    module = importlib.util.module_from_spec(
        spec := importlib.util.spec_from_file_location(
            "pdb2", ROOT / "scripts/process_doc_batch.py"
        )
    )
    spec.loader.exec_module(module)
    assert module.promoted_path(hand_edited) is None
    assert (
        module.quarantine_orphans(root, root / "data/quarantine/b/docs", [hand_edited], []) == []
    )
    assert victim.read_text(encoding="utf-8") == "keep me"
