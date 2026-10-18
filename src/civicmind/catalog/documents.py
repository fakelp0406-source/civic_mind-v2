"""Document manifest model (see docs/DOCUMENT_MANIFEST_SPEC.md) and YAML serialisation.

A document manifest (``data/doc_manifests/<document_id>.yaml``) is the single record of where an
official document (a PDF) came from, which exact bytes were received, how its text was
extracted, what screening found, and the person review that decides whether it may become a
retrieval source. It mirrors the dataset ``Manifest`` but is a separate model: documents have
pages, editions and version chains instead of schemas, rows and periods.

Documents live in their own directory because the dataset catalogue reads every
``data/manifests/*.yaml`` file as a dataset manifest.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from civicmind.catalog.manifest import Licence, Retrieval

#: Where document manifests live, relative to the project root.
DOC_MANIFEST_DIR = "data/doc_manifests"
#: Document ids are also used in file paths, so they are restricted to this form.
DOCUMENT_ID_PATTERN = r"^DOC-[A-Z0-9][A-Z0-9-]*$"

DocumentStatus = Literal[
    "planned",  # listed for acquisition; no file yet
    "received",  # file present, nothing checked
    "integrity_passed",  # bytes recorded, opens as a PDF
    "extracted",  # page text extracted, but with errors (not reviewable)
    "validated",  # extraction ran with no errors; ready for person review
    "approved",  # reviewed and promoted to data/docs/<domain>/; a retrieval source
    "quarantined",
    "rejected",
    "withdrawn",  # was approved; removed from use, manifest kept as a tombstone
]
DocumentType = Literal[
    "statistical_report",
    "act",
    "rules",
    "notification",
    "tariff_order",
    "handbook_manual",
    "audit_report",
    "methodology_note",
]
DocumentDomain = Literal["water", "roads"]
DocumentDecision = Literal["approve", "quarantine", "reject", "withdraw"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentIntegrity(_Strict):
    bytes: int
    stated_bytes: int | None = None  # as stated by the publisher or portal, if any
    size_matches_stated: bool | None = None
    sha256: str
    format: Literal["pdf"] = "pdf"
    pdf_header: bool  # file starts with "%PDF-"
    pdf_version: str | None = None
    pages: int | None = None
    encrypted: bool | None = None
    producer: str | None = None  # PDF metadata, as recorded in the file (untrusted text)
    passed: bool


class Extraction(_Strict):
    extractor: str
    extractor_version: str
    pages: int
    pages_with_text: int
    pages_without_text: list[int] = Field(default_factory=list)  # 1-based page numbers
    characters: int
    output_path: str | None = None  # data/processed/rag/extracted/... (git-ignored)
    output_sha256: str | None = None


class DocumentReview(_Strict):
    """A person's decision on one document, bound to the exact bytes it was made for."""

    decision: DocumentDecision
    reviewed_by: str
    reviewed_on: str
    sha256: str
    accepted_caveats: list[str] = Field(default_factory=list)  # warning finding codes
    excluded_pages: list[int] = Field(default_factory=list)  # never indexed or cited
    note: str | None = None


class DocumentManifest(_Strict):
    document_id: str = Field(pattern=DOCUMENT_ID_PATTERN)
    manifest_version: int = 1
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
    retrieval: Retrieval
    integrity: DocumentIntegrity | None = None
    extraction: Extraction | None = None
    relates_to_datasets: list[str] = Field(default_factory=list)  # documentation, never a join
    supersedes: list[str] = Field(default_factory=list)  # recorded by a person
    superseded_by: list[str] = Field(default_factory=list)  # derived from other manifests
    same_bytes_as: str | None = None
    # Until screened, a document is treated as restricted and possibly personal.
    sensitivity: Literal["public", "personal_data", "restricted"] = "restricted"
    contains_personal_data: bool = True
    findings: list[dict[str, Any]] = Field(default_factory=list)
    human_review: Literal["pending", "accepted", "rejected"] = "pending"
    review: DocumentReview | None = None
    status: DocumentStatus
    promoted_to: str | None = None
    known_limitations: list[str] = Field(default_factory=list)

    def to_yaml(self) -> str:
        data = self.model_dump(mode="json")
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)

    def warning_codes(self) -> set[str]:
        return {f["code"] for f in self.findings if f.get("severity") == "warning"}

    def error_codes(self) -> set[str]:
        return {f["code"] for f in self.findings if f.get("severity") == "error"}


#: Windows device names: "CON.pdf" opens the console device, not a file.
WINDOWS_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
     *(f"LPT{i}" for i in range(1, 10))}
)  # fmt: skip


def path_problem(path: str) -> str | None:
    """Why a recorded relative path is unsafe, or ``None``: absolute, a drive, a backslash, a
    ``..`` segment, a control character (e.g. NUL) or a colon (a Windows alternate data stream).
    Such a path could point outside the project root or at something that is not a file."""
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        return f"path {path!r} contains a control character"
    if "\\" in path or PureWindowsPath(path).anchor or PurePosixPath(path).is_absolute():
        return f"path {path!r} is absolute or uses backslashes"
    if ":" in path:
        return f"path {path!r} contains ':'"
    if ".." in PurePosixPath(path).parts:
        return f"path {path!r} contains a '..' segment"
    return None


def filename_problem(name: str) -> str | None:
    """Why a recorded file name is not a plain, portable file name (separators, drives,
    ``.``/``..``, Windows device names, trailing dots or spaces)."""
    if (
        path_problem(name)
        or "/" in name
        or name in {"", ".", ".."}
        or name != name.rstrip(". ")
        or name.split(".")[0].strip().upper() in WINDOWS_DEVICES
    ):
        return f"file name {name!r} is not a plain file name"
    return None


def resolves_within(root: str | Path, rel: str, base: str) -> bool:
    """True when ``root/rel``, with every symlink and junction resolved, lies inside
    ``root/base``. ``base`` itself is not resolved, so a linked directory that points
    elsewhere fails the check. The lexical checks (``path_problem``) are applied first, so this
    is safe to call at any filesystem operation on its own."""
    if path_problem(rel):
        return False
    try:
        target = (Path(root) / rel).resolve()
        limit = Path(root).resolve() / base
    except (OSError, RuntimeError, ValueError):  # ValueError: e.g. an embedded NUL
        return False
    return target.is_relative_to(limit)


def write_document_manifest(manifest: DocumentManifest, directory: str | Path) -> Path:
    path = Path(directory) / f"{manifest.document_id}.yaml"
    path.write_text(manifest.to_yaml(), encoding="utf-8", newline="\n")
    return path


def read_document_manifest(path: str | Path) -> DocumentManifest:
    return DocumentManifest.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def read_document_manifests(root: str | Path) -> list[DocumentManifest]:
    """Every document manifest under ``<root>/data/doc_manifests``, sorted by id."""
    folder = Path(root) / DOC_MANIFEST_DIR
    return [read_document_manifest(p) for p in sorted(folder.glob("*.yaml"))]


__all__ = [
    "DOCUMENT_ID_PATTERN",
    "DOC_MANIFEST_DIR",
    "DocumentDecision",
    "DocumentIntegrity",
    "DocumentManifest",
    "DocumentReview",
    "DocumentStatus",
    "DocumentType",
    "Extraction",
    "filename_problem",
    "path_problem",
    "read_document_manifest",
    "read_document_manifests",
    "resolves_within",
    "write_document_manifest",
]
