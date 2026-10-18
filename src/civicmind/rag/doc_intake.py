"""Build document manifests from a person's intake record and the received PDF.

The intake file (``docs/acquisition/<batch>/DOCUMENT_INTAKE.yaml``) holds what only a person can
know: title, issuing authority, URLs, dates, licence evidence, who retrieved the file and where
it was saved. ``build_document_manifest`` adds what the bytes say: size and SHA-256, PDF checks,
page-text extraction (written to ``data/processed/rag/extracted/``) and screening findings, and
derives the lifecycle status. It records findings and never edits the file.

The file is read **once**, through a handle verified to lie inside ``data/external/`` or
``data/quarantine/`` (``catalog.safe_fs``), and bounded by ``PreparationLimits``. The SHA-256,
the PDF inspection and the extracted text are all computed from that single byte sequence, so
the recorded hash always describes exactly the bytes whose text was extracted and screened. The
page file's name and content carry the source hash, the extractor version and the preparation
version; its own SHA-256 (``extraction.output_sha256``) is what an approval binds to.

Status after a build (before review): no file -> ``planned``; integrity failed -> ``received``;
the PDF cannot be read -> ``integrity_passed``; text extracted but an error finding exists ->
``extracted``; no error findings -> ``validated`` (ready for person review).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from civicmind.catalog.doc_limits import DEFAULT_LIMITS, PreparationLimits
from civicmind.catalog.documents import (
    DOCUMENT_ID_PATTERN,
    DocumentDomain,
    DocumentIntegrity,
    DocumentManifest,
    DocumentType,
    Extraction,
    filename_problem,
    path_problem,
    resolves_within,
)
from civicmind.catalog.manifest import Licence, Retrieval
from civicmind.catalog.safe_fs import TooLarge, UnsafePath, read_verified, write_or_match_verified
from civicmind.rag.extract import PREPARATION_VERSION, pages_bytes, read_pdf_bytes
from civicmind.rag.screen import screen_pages

EXTRACTED_DIR = "data/processed/rag/extracted"
NOT_RETRIEVED = "not yet retrieved"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentIntake(_Strict):
    """Person-recorded facts about one document (nothing here is derived from its bytes)."""

    document_id: str = Field(pattern=DOCUMENT_ID_PATTERN)  # also used in output paths
    title: str
    issuing_authority: str
    publisher: str
    document_type: DocumentType
    language: str = "en"
    domains: list[DocumentDomain] = Field(min_length=1)
    source_class: Literal["official", "secondary_mirror"]
    resource_page: str
    download_url: str | None = None
    publication_date: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    edition: str | None = None
    version_label: str | None = None
    licence: Licence
    retrieved_at: str | None = None
    retrieved_by: str | None = None
    retrieval_method: str = "manual download by a person"
    http_status: int | None = None  # as observed at retrieval, if recorded
    content_type: str | None = None
    original_filename: str | None = None
    local_path: str | None = None  # relative to the project root, under data/external/
    stated_bytes: int | None = None
    relates_to_datasets: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    note: str | None = None

    @field_validator("local_path")
    @classmethod
    def _safe_local_path(cls, value: str | None) -> str | None:
        """Only a relative path under data/external/ may be read (never outside the root)."""
        if value is None:
            return value
        problem = path_problem(value)
        if problem:
            raise ValueError(problem)
        if not value.startswith("data/external/"):
            raise ValueError(f"local_path {value!r} is not under data/external/")
        return value

    @field_validator("original_filename")
    @classmethod
    def _plain_filename(cls, value: str | None) -> str | None:
        """The name is used in data/docs/ and quarantine paths: a plain file name only."""
        if value is not None and filename_problem(value):
            raise ValueError(filename_problem(value))
        return value


#: Where a document's bytes may be read from, after links are resolved.
READABLE_DIRS = ("data/external", "data/quarantine")


def extraction_path(document_id: str, sha256: str, extractor_version: str) -> str:
    """Page-file path: one file per (document, exact bytes, extractor, preparation version)."""
    prep = PREPARATION_VERSION.replace("@", "-")
    return f"{EXTRACTED_DIR}/{document_id}/{sha256[:16]}-{prep}-pypdf-{extractor_version}.jsonl"


class DocumentIntakeFile(_Strict):
    batch: str
    documents: list[DocumentIntake]


def load_intake(path: str | Path) -> DocumentIntakeFile:
    return DocumentIntakeFile.model_validate(
        yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    )


def finding(code: str, severity: str, message: str, details: dict | None = None) -> dict:
    return {"code": code, "severity": severity, "message": message, "details": details or {}}


def _base(intake: DocumentIntake) -> dict:
    return {
        "document_id": intake.document_id,
        "title": intake.title,
        "issuing_authority": intake.issuing_authority,
        "publisher": intake.publisher,
        "document_type": intake.document_type,
        "language": intake.language,
        "domains": list(intake.domains),
        "source_class": intake.source_class,
        "resource_page": intake.resource_page,
        "download_url": intake.download_url,
        "publication_date": intake.publication_date,
        "effective_from": intake.effective_from,
        "effective_to": intake.effective_to,
        "edition": intake.edition,
        "version_label": intake.version_label,
        "licence": intake.licence.model_dump(),
        "retrieval": Retrieval(
            retrieved_at=intake.retrieved_at,
            retrieved_by=intake.retrieved_by,
            method=intake.retrieval_method,
            http_status=intake.http_status,
            content_type=intake.content_type,
            original_filename=intake.original_filename or NOT_RETRIEVED,
            local_path=intake.local_path,
        ).model_dump(),
        "relates_to_datasets": list(intake.relates_to_datasets),
        "supersedes": list(intake.supersedes),
        "known_limitations": list(intake.known_limitations),
    }


def build_document_manifest(
    intake: DocumentIntake,
    root: str | Path,
    file: str | Path | None = None,
    limits: PreparationLimits = DEFAULT_LIMITS,
) -> DocumentManifest:
    """Manifest for one intake record. ``file`` overrides where the bytes are read from
    (e.g. a quarantined copy); by default ``root / intake.local_path``."""
    root = Path(root)
    data = _base(intake)
    findings: list[dict] = []
    if intake.source_class == "secondary_mirror":
        findings.append(
            finding(
                "source.secondary_mirror",
                "warning",
                "Copy obtained from a mirror, not the issuing authority; every answer will "
                "carry this caveat",
                {"resource_page": intake.resource_page},
            )
        )
    path = (
        Path(file)
        if file is not None
        else (root / intake.local_path if intake.local_path else None)
    )
    if path is None or not path.is_file():
        if intake.local_path:
            findings.append(
                finding("file.missing", "info", "No file at the recorded local path yet", {})
            )
        # Nothing was retrieved: do not let the intended method read as if it happened.
        data["retrieval"] = {**data["retrieval"], "method": NOT_RETRIEVED}
        return DocumentManifest.model_validate({**data, "findings": findings, "status": "planned"})

    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    if not any(resolves_within(root, rel, base) for base in READABLE_DIRS):
        # A symlink or junction points outside the intake folders: the file is not read.
        findings.append(
            finding(
                "path.outside_intake",
                "error",
                "The file resolves (through a link) outside data/external/ and "
                "data/quarantine/; it was not read",
                {},
            )
        )
        return DocumentManifest.model_validate(
            {**data, "findings": findings, "status": "received"}
        )
    try:
        raw = read_verified(root, rel, READABLE_DIRS, limits.max_bytes)
    except UnsafePath:
        findings.append(
            finding(
                "path.outside_intake",
                "error",
                "The opened file is outside data/external/ and data/quarantine/ (or is not a "
                "regular file); it was not read",
                {},
            )
        )
        return DocumentManifest.model_validate(
            {**data, "findings": findings, "status": "received"}
        )
    except TooLarge as exc:
        findings.append(
            finding(
                "document.too_large",
                "error",
                "The file exceeds the configured size limit; it was not read further",
                {"bytes_at_least": exc.size, "max_bytes": exc.limit},
            )
        )
        return DocumentManifest.model_validate(
            {**data, "findings": findings, "status": "received"}
        )
    size = len(raw)
    sha = hashlib.sha256(raw).hexdigest()
    inspection, extraction = read_pdf_bytes(raw, limits)  # the same bytes that were hashed
    del raw
    size_ok = None if intake.stated_bytes is None else size == intake.stated_bytes
    if size_ok is False:
        findings.append(
            finding(
                "integrity.size_mismatch",
                "error",
                "File size differs from the size stated by the publisher",
                {"bytes": size, "stated_bytes": intake.stated_bytes},
            )
        )
    if inspection.error:
        findings.append(
            finding(inspection.error, "error", "The file cannot be used as a PDF document", {})
        )
    elif inspection.encrypted:
        findings.append(
            finding(
                "pdf.permissions_restricted",
                "info",
                "Encrypted with an empty user password (permissions only); text was readable",
                {},
            )
        )
    passed = inspection.pdf_header and size_ok is not False
    data["integrity"] = DocumentIntegrity(
        bytes=size,
        stated_bytes=intake.stated_bytes,
        size_matches_stated=size_ok,
        sha256=sha,
        pdf_header=inspection.pdf_header,
        pdf_version=inspection.pdf_version,
        pages=inspection.pages,
        encrypted=inspection.encrypted,
        producer=inspection.producer,
        passed=passed,
    ).model_dump()
    status = "received" if not passed else "integrity_passed"
    if passed and extraction is not None:
        rel_out = extraction_path(intake.document_id, sha, extraction.extractor_version)
        if not resolves_within(root, rel_out, EXTRACTED_DIR):
            raise ValueError(f"{EXTRACTED_DIR} resolves outside the project root")
        page_file = pages_bytes(extraction, intake.document_id, sha)
        try:  # never overwrites: an existing page file must hold exactly these bytes
            write_or_match_verified(root, rel_out, EXTRACTED_DIR, page_file)
        except UnsafePath as exc:
            raise ValueError(
                f"page file refused ({exc}); outside the project root or altered"
            ) from exc
        out_sha = hashlib.sha256(page_file).hexdigest()
        data["extraction"] = Extraction(
            extractor=extraction.extractor,
            extractor_version=extraction.extractor_version,
            pages=len(extraction.pages),
            pages_with_text=extraction.pages_with_text,
            pages_without_text=extraction.pages_without_text,
            characters=extraction.characters,
            output_path=rel_out,
            output_sha256=out_sha,
            preparation_version=PREPARATION_VERSION,
        ).model_dump()
        if extraction.pages_with_text == 0:
            findings.append(
                finding(
                    "extraction.empty",
                    "error",
                    "No page has extractable text (scanned or image-only); OCR is not used",
                    {"pages": len(extraction.pages)},
                )
            )
        elif extraction.pages_without_text:
            findings.append(
                finding(
                    "extraction.no_text_pages",
                    "warning",
                    "Pages without extractable text are never indexed or cited",
                    {"pages": extraction.pages_without_text},
                )
            )
        text_pages = [
            (p.page, p.text)
            for p in extraction.pages
            if p.page not in extraction.pages_without_text
        ]
        screen = screen_pages(text_pages)
        findings += screen
        personal = any(f["code"] == "content.personal_data_suspected" for f in screen)
        data["sensitivity"] = "restricted" if personal else "public"
        data["contains_personal_data"] = personal
        errors = any(f["severity"] == "error" for f in findings)
        status = "extracted" if errors else "validated"
    data["findings"] = findings
    data["status"] = status
    return DocumentManifest.model_validate(data)


def link_documents(
    manifests: list[DocumentManifest], existing: list[DocumentManifest] = ()
) -> list[DocumentManifest]:
    """Record duplicates (``same_bytes_as``) and version chains (``superseded_by``).

    ``existing`` are manifests from other batches, read from disk. The first document with a
    given SHA-256 (``existing`` first, then batch order) keeps it; later ones point to it.
    A ``supersedes`` entry naming an unknown document adds a warning.
    """
    everyone = [*existing, *manifests]
    known = {m.document_id for m in everyone}
    first: dict[str, str] = {}
    for m in existing:
        if m.integrity:
            first.setdefault(m.integrity.sha256, m.document_id)
    out = []
    for m in manifests:
        data = m.model_dump()
        sha = m.integrity.sha256 if m.integrity else None
        if sha:
            owner = first.setdefault(sha, m.document_id)
            data["same_bytes_as"] = owner if owner != m.document_id else None
        data["superseded_by"] = sorted(
            o.document_id for o in everyone if m.document_id in o.supersedes
        )
        unknown = sorted(set(m.supersedes) - known)
        if unknown:
            data["findings"] = [
                *data["findings"],
                finding(
                    "document.unknown_reference",
                    "warning",
                    "'supersedes' names documents that have no manifest",
                    {"documents": unknown},
                ),
            ]
        out.append(DocumentManifest.model_validate(data))
    return out


__all__ = [
    "EXTRACTED_DIR",
    "DocumentIntake",
    "DocumentIntakeFile",
    "build_document_manifest",
    "extraction_path",
    "link_documents",
    "load_intake",
]
