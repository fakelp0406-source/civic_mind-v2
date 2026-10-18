"""Document promotion gate: copy an approved PDF byte-identically into ``data/docs/<domain>/``.

See docs/DOCUMENT_MANIFEST_SPEC.md. Only an ``approved`` document is a retrieval source, and a
document becomes ``approved`` only here. ``promote_document`` never edits the source file and
never overwrites a different file (it shares ``copy_verified`` with dataset promotion).
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from civicmind.catalog.documents import DocumentManifest, path_problem, resolves_within
from civicmind.catalog.fingerprint import sha256_of
from civicmind.catalog.promote import SOURCE_PREFIX, PromotionRefused, copy_verified

DOC_DOMAINS = frozenset({"water", "roads"})
DOCS_DIR = "data/docs"


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


def promote_document(manifest: DocumentManifest, root: str | Path) -> DocumentManifest:
    """Copy the document into data/docs/<domain>/ and return the approved manifest.

    Idempotent: if the target already holds identical bytes, nothing is written.
    Raises ``PromotionRefused`` if any gate condition fails or bytes differ anywhere.
    """
    root = Path(root)
    reasons = gate_reasons(manifest)
    if reasons:
        raise PromotionRefused(manifest.document_id, reasons)
    expected = manifest.integrity.sha256
    source = root / manifest.retrieval.local_path
    if not resolves_within(root, manifest.retrieval.local_path, "data/external"):
        raise PromotionRefused(manifest.document_id, ["source resolves outside data/external/"])
    if not source.is_file():
        raise PromotionRefused(manifest.document_id, ["source file missing"])
    if source.stat().st_size != manifest.integrity.bytes or sha256_of(source) != expected:
        raise PromotionRefused(manifest.document_id, ["source bytes differ from manifest"])
    domain = PurePosixPath(manifest.retrieval.local_path).parent.name
    rel_target = f"{DOCS_DIR}/{domain}/{manifest.retrieval.original_filename}"
    if not resolves_within(root, rel_target, DOCS_DIR):
        raise PromotionRefused(
            manifest.document_id, [f"{rel_target} resolves outside {DOCS_DIR}/"]
        )
    copy_verified(source, root, rel_target, expected, manifest.document_id)
    data = manifest.model_dump()
    data.update(status="approved", promoted_to=rel_target)
    return DocumentManifest.model_validate(data)


__all__ = ["DOCS_DIR", "DOC_DOMAINS", "gate_reasons", "promote_document"]
