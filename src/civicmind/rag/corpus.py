"""The retrieval corpus: approved documents only, re-verified from their bytes every time.

``load_corpus`` reads the document manifests and admits a document only if **all** of these
hold (otherwise it is listed in ``Corpus.skipped`` with the reason, and never indexed):

* ``status: approved`` with an ``approve`` review that binds the current source SHA-256 *and*
  the current page-file SHA-256 (``review.sha256``, ``review.extraction_sha256``);
* public, no personal data, not a duplicate (``same_bytes_as``), promoted to ``data/docs/``;
* the promoted PDF, read through a verified handle, hashes to the recorded SHA-256;
* the page file, read through a verified handle, hashes to the reviewed ``extraction_sha256``,
  and every record in it names this document, these source bytes and this preparation version.

A failed hash raises ``CorpusIntegrityError``: the corpus is never built from bytes that do not
match their approval. Pages without extractable text and the reviewer's ``excluded_pages`` are
dropped here, so no later stage can index or cite them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from civicmind.catalog.doc_limits import DEFAULT_LIMITS, PreparationLimits
from civicmind.catalog.doc_promote import DOCS_DIR, EXTRACTED_DIR, page_file_limit
from civicmind.catalog.documents import DocumentManifest, read_document_manifests
from civicmind.catalog.safe_fs import TooLarge, UnsafePath, read_verified


class CorpusIntegrityError(RuntimeError):
    """An approved document's bytes or page file no longer match its approval."""


@dataclass(frozen=True)
class CorpusDocument:
    document_id: str
    title: str
    edition: str | None
    issuing_authority: str
    source_class: str
    resource_page: str
    download_url: str | None
    publication_date: str | None
    sha256: str
    extraction_sha256: str
    preparation_version: str | None
    pages_indexed: tuple[int, ...]
    excluded_pages: tuple[int, ...]
    no_text_pages: tuple[int, ...]
    limitations: tuple[str, ...]

    def provenance(self) -> dict:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "edition": self.edition,
            "issuing_authority": self.issuing_authority,
            "source_class": self.source_class,
            "resource_page": self.resource_page,
            "download_url": self.download_url,
            "publication_date": self.publication_date,
            "document_sha256": self.sha256,
            "extraction_sha256": self.extraction_sha256,
            "preparation_version": self.preparation_version,
        }


@dataclass(frozen=True)
class CorpusPage:
    document_id: str
    page: int  # 1-based PDF page number
    text: str


@dataclass(frozen=True)
class Corpus:
    documents: tuple[CorpusDocument, ...]
    pages: tuple[CorpusPage, ...]
    skipped: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # (document_id, reason)

    def digest(self) -> str:
        """Identifies the exact approved inputs: ids, both hashes, exclusions, versions."""
        basis = [
            [d.document_id, d.sha256, d.extraction_sha256, d.preparation_version,
             list(d.excluded_pages)]
            for d in sorted(self.documents, key=lambda d: d.document_id)
        ]  # fmt: skip
        return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()

    def document(self, document_id: str) -> CorpusDocument:
        return next(d for d in self.documents if d.document_id == document_id)


def _skip_reason(m: DocumentManifest) -> str | None:
    if m.status != "approved":
        return f"status {m.status}"
    r = m.review
    if r is None or r.decision != "approve" or m.human_review != "accepted":
        return "no approving review"
    if m.integrity is None or m.extraction is None or not m.promoted_to:
        return "not prepared or not promoted"
    if r.sha256 != m.integrity.sha256:
        return "review bound to other bytes"
    if not r.extraction_sha256 or r.extraction_sha256 != m.extraction.output_sha256:
        return "review not bound to the current page file"
    if m.same_bytes_as:
        return f"duplicate of {m.same_bytes_as}"
    if m.sensitivity != "public" or m.contains_personal_data:
        return "not public"
    return None


def approved_digest(root: str | Path) -> str:
    """``Corpus.digest()`` of what the manifests approve *now*, from manifest metadata only.

    It reads no PDF or page file, so it is cheap enough to run before every use of a loaded
    index: a document withdrawn, quarantined or re-reviewed (other hashes or exclusions) after
    the index was loaded changes this digest. It is not a byte check; ``load_corpus`` is.
    """
    approved = [m for m in read_document_manifests(root) if _skip_reason(m) is None]
    basis = [
        [m.document_id, m.integrity.sha256, m.extraction.output_sha256,
         m.extraction.preparation_version, sorted(m.review.excluded_pages)]
        for m in sorted(approved, key=lambda m: m.document_id)
    ]  # fmt: skip
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()


def load_corpus(root: str | Path, limits: PreparationLimits = DEFAULT_LIMITS) -> Corpus:
    root = Path(root)
    documents, pages, skipped = [], [], []
    for m in read_document_manifests(root):
        reason = _skip_reason(m)
        if reason:
            skipped.append((m.document_id, reason))
            continue
        try:
            raw = read_verified(root, m.promoted_to, (DOCS_DIR,), limits.max_bytes)
            page_file = read_verified(
                root, m.extraction.output_path, (EXTRACTED_DIR,), page_file_limit(limits)
            )
        except (UnsafePath, TooLarge, OSError) as exc:
            raise CorpusIntegrityError(f"{m.document_id}: verified read failed ({exc})") from None
        if hashlib.sha256(raw).hexdigest() != m.integrity.sha256:
            raise CorpusIntegrityError(f"{m.document_id}: promoted PDF differs from its approval")
        del raw
        if hashlib.sha256(page_file).hexdigest() != m.review.extraction_sha256:
            raise CorpusIntegrityError(f"{m.document_id}: page file differs from the reviewed one")
        skip = set(m.extraction.pages_without_text) | set(m.review.excluded_pages)
        indexed = []
        for line in page_file.decode("utf-8").splitlines():
            record = json.loads(line)
            if (
                record["document_id"] != m.document_id
                or record["sha256"] != m.integrity.sha256
                or record.get("preparation_version") != m.extraction.preparation_version
            ):
                raise CorpusIntegrityError(f"{m.document_id}: page record does not match")
            if record["page"] in skip:
                continue
            pages.append(CorpusPage(m.document_id, record["page"], record["text"]))
            indexed.append(record["page"])
        documents.append(
            CorpusDocument(
                document_id=m.document_id,
                title=m.title,
                edition=m.edition,
                issuing_authority=m.issuing_authority,
                source_class=m.source_class,
                resource_page=m.resource_page,
                download_url=m.download_url,
                publication_date=m.publication_date,
                sha256=m.integrity.sha256,
                extraction_sha256=m.extraction.output_sha256,
                preparation_version=m.extraction.preparation_version,
                pages_indexed=tuple(indexed),
                excluded_pages=tuple(sorted(m.review.excluded_pages)),
                no_text_pages=tuple(m.extraction.pages_without_text),
                limitations=tuple(m.known_limitations),
            )
        )
    return Corpus(tuple(documents), tuple(pages), tuple(skipped))


__all__ = [
    "Corpus",
    "CorpusDocument",
    "CorpusIntegrityError",
    "CorpusPage",
    "approved_digest",
    "load_corpus",
]
