"""Document promotion gate: copy an approved PDF byte-identically into ``data/docs/<domain>/``.

See docs/DOCUMENT_MANIFEST_SPEC.md. Only an ``approved`` document is a retrieval source, and a
document becomes ``approved`` only here. ``promote_document`` never edits the source file and
never overwrites a different file.

An approval must be current for the exact prepared artifact: the review binds the source
SHA-256 *and* the SHA-256 of the extracted page file, and both are re-checked here against the
files on disk. All reads and the copy go through handle-verified operations
(``catalog.safe_fs``): the source must really be inside ``data/external/``, the page file inside
``data/processed/rag/extracted/``, and the copy is created (never replaced) inside ``data/docs/``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from civicmind.catalog.doc_limits import DEFAULT_LIMITS, PreparationLimits
from civicmind.catalog.documents import DocumentManifest, path_problem, resolves_within
from civicmind.catalog.promote import SOURCE_PREFIX, PromotionRefused
from civicmind.catalog.safe_fs import (
    TooLarge,
    UnsafePath,
    read_verified,
    write_or_match_verified,
)

DOC_DOMAINS = frozenset({"water", "roads"})
DOCS_DIR = "data/docs"
EXTRACTED_DIR = "data/processed/rag/extracted"


def page_file_limit(limits: PreparationLimits) -> int:
    """Upper bound on a page file's size: UTF-8 text (<= 4 bytes a character, JSON-escaped)
    plus per-page record overhead."""
    return limits.max_text_chars * 6 + limits.max_pages * 1024


def gate_reasons(manifest: DocumentManifest) -> list[str]:
    """Every manifest-level reason promotion is not allowed (empty list = gate open)."""
    m = manifest
    reasons = []
    if m.status != "validated":
        reasons.append(f"status is {m.status!r}, not 'validated'")
    if m.human_review != "accepted" or m.review is None or m.review.decision != "approve":
        reasons.append("no approving person review")
    if m.integrity is None or not m.integrity.passed or not m.integrity.sha256:
        reasons.append("integrity not passed or hash missing")
    elif m.review is not None and m.review.sha256 != m.integrity.sha256:
        reasons.append("review was made for different bytes")
    if m.extraction is None or m.extraction.pages_with_text == 0:
        reasons.append("no extracted page text")
    elif m.review is not None and (
        not m.review.extraction_sha256 or m.review.extraction_sha256 != m.extraction.output_sha256
    ):
        reasons.append("review is not bound to the current extracted text")
    if m.error_codes():
        reasons.append(f"error findings: {sorted(m.error_codes())}")
    if m.same_bytes_as:
        reasons.append(f"same bytes as {m.same_bytes_as}; the document is promoted once")
    if not m.licence.name or m.licence.name.strip().upper() == "UNKNOWN":
        reasons.append("licence unknown")
    if m.sensitivity != "public" or m.contains_personal_data:
        reasons.append("not public, or contains personal data")
    local = m.retrieval.local_path or ""
    folder = PurePosixPath(local).parent
    if path_problem(local):
        reasons.append(path_problem(local))
    elif not local.startswith(SOURCE_PREFIX):
        reasons.append(f"source is not under {SOURCE_PREFIX}: {local!r}")
    elif folder.parent.name != "docs" or folder.name not in DOC_DOMAINS:
        reasons.append(f"source folder is not docs/<{'|'.join(sorted(DOC_DOMAINS))}>")
    elif folder.name not in m.domains:
        reasons.append(f"source folder {folder.name!r} is not one of the domains {m.domains}")
    name = m.retrieval.original_filename
    if not name or name != PurePosixPath(name).name or "\\" in name or name in {".", ".."}:
        reasons.append(f"unsafe original_filename {name!r}")
    elif not name.lower().endswith(".pdf"):
        reasons.append(f"original_filename {name!r} is not a .pdf")
    return reasons


def promote_document(
    manifest: DocumentManifest, root: str | Path, limits: PreparationLimits = DEFAULT_LIMITS
) -> DocumentManifest:
    """Copy the document into data/docs/<domain>/ and return the approved manifest.

    Idempotent: if the target already holds identical bytes, nothing is written.
    Raises ``PromotionRefused`` if any gate condition fails or bytes differ anywhere.
    """
    root = Path(root)
    ident = manifest.document_id
    reasons = gate_reasons(manifest)
    if reasons:
        raise PromotionRefused(ident, reasons)
    expected = manifest.integrity.sha256
    local = manifest.retrieval.local_path
    if not resolves_within(root, local, "data/external"):
        raise PromotionRefused(ident, ["source resolves outside data/external/"])
    if not (root / local).is_file():
        raise PromotionRefused(ident, ["source file missing"])
    try:
        data = read_verified(root, local, ("data/external",), limits.max_bytes)
        page_rel = manifest.extraction.output_path or ""
        pages = read_verified(root, page_rel, (EXTRACTED_DIR,), page_file_limit(limits))
    except (UnsafePath, TooLarge, OSError) as exc:
        raise PromotionRefused(ident, [f"verified read refused: {type(exc).__name__}"]) from None
    if len(data) != manifest.integrity.bytes or hashlib.sha256(data).hexdigest() != expected:
        raise PromotionRefused(ident, ["source bytes differ from manifest"])
    if hashlib.sha256(pages).hexdigest() != manifest.extraction.output_sha256:
        raise PromotionRefused(ident, ["extracted page file differs from the reviewed one"])
    domain = PurePosixPath(local).parent.name
    rel_target = f"{DOCS_DIR}/{domain}/{manifest.retrieval.original_filename}"
    if not resolves_within(root, rel_target, DOCS_DIR):
        raise PromotionRefused(ident, [f"{rel_target} resolves outside {DOCS_DIR}/"])
    try:
        write_or_match_verified(root, rel_target, DOCS_DIR, data)
    except UnsafePath as exc:
        reason = (
            f"{rel_target} exists with different bytes"
            if "different bytes" in str(exc)
            else f"{rel_target} resolves outside {DOCS_DIR}/"
        )
        raise PromotionRefused(ident, [reason]) from None
    data = manifest.model_dump()
    data.update(status="approved", promoted_to=rel_target)
    return DocumentManifest.model_validate(data)


__all__ = ["DOCS_DIR", "DOC_DOMAINS", "gate_reasons", "page_file_limit", "promote_document"]
