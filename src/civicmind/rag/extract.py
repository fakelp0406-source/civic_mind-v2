"""PDF inspection and page-text extraction with page provenance (pypdf).

``read_pdf`` opens a received document **read-only** and returns:

* a ``PdfInspection``: header, PDF version, page count, encryption, producer metadata, and an
  error code when the file cannot be used (``pdf.not_pdf``, ``pdf.unreadable``,
  ``pdf.encrypted``);
* an ``ExtractionResult``: the text of every page as the extractor returned it (only line
  endings are normalised to ``\\n``), 1-based page numbers, and the pages with no usable text.

No OCR is attempted: a page with fewer than ``MIN_PAGE_CHARS`` non-space characters is listed
in ``pages_without_text`` and is never indexed or cited. Extracted text is untrusted data.

``pypdf`` is an optional dependency (extra ``rag``) and is imported only when a PDF is read,
so importing ``civicmind.rag`` stays lightweight. Without it, reading a PDF raises
``PdfSupportMissing`` (an ``ImportError``) with installation instructions; nothing is guessed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

EXTRACTOR = "pypdf"
#: Pages with fewer non-whitespace characters than this count as having no text.
MIN_PAGE_CHARS = 20
PDF_ERRORS = frozenset({"pdf.not_pdf", "pdf.unreadable", "pdf.encrypted"})


class PdfSupportMissing(ImportError):
    """PDF extraction was requested but the optional ``rag`` extra (pypdf) is not installed."""

    def __init__(self) -> None:
        super().__init__(
            "PDF extraction needs the optional 'rag' extra (pypdf), which is not installed: "
            'pip install -e ".[rag]" -c constraints-py313.txt'
        )


@dataclass(frozen=True)
class PageText:
    page: int  # 1-based
    text: str
    chars: int  # non-whitespace characters


@dataclass(frozen=True)
class PdfInspection:
    pdf_header: bool
    pdf_version: str | None = None
    pages: int | None = None
    encrypted: bool | None = None
    producer: str | None = None
    error: str | None = None  # one of PDF_ERRORS, or None


@dataclass(frozen=True)
class ExtractionResult:
    extractor: str
    extractor_version: str
    pages: tuple[PageText, ...] = field(default_factory=tuple)

    @property
    def pages_without_text(self) -> list[int]:
        return [p.page for p in self.pages if p.chars < MIN_PAGE_CHARS]

    @property
    def pages_with_text(self) -> int:
        return sum(p.chars >= MIN_PAGE_CHARS for p in self.pages)

    @property
    def characters(self) -> int:
        return sum(p.chars for p in self.pages)


def _visible_chars(text: str) -> int:
    return sum(not c.isspace() for c in text)


def read_pdf(path: str | Path) -> tuple[PdfInspection, ExtractionResult | None]:
    """Inspect a PDF and extract page text. Never modifies the file."""
    path = Path(path)
    with open(path, "rb") as handle:
        head = handle.read(1024)
    if not head.startswith(b"%PDF-"):
        return PdfInspection(pdf_header=False, error="pdf.not_pdf"), None

    try:
        import pypdf  # optional dependency, imported on use
    except ImportError as exc:
        raise PdfSupportMissing() from exc

    version = head[5:8].decode("ascii", errors="replace")
    try:
        reader = pypdf.PdfReader(str(path))
        encrypted = bool(reader.is_encrypted)
        if encrypted and reader.decrypt("") == 0:  # PasswordType.NOT_DECRYPTED
            return PdfInspection(True, version, None, True, None, "pdf.encrypted"), None
        meta = reader.metadata
        producer = str(meta.producer) if meta is not None and meta.producer else None
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").replace("\r\n", "\n").replace("\r", "\n")
            pages.append(PageText(number, text, _visible_chars(text)))
    except Exception:  # noqa: BLE001 - malformed PDFs raise many types; fail closed
        # The exception text can contain file paths or document text; it is not kept.
        return PdfInspection(True, version, error="pdf.unreadable"), None
    inspection = PdfInspection(True, version, len(pages), encrypted, producer)
    return inspection, ExtractionResult(EXTRACTOR, pypdf.__version__, tuple(pages))


def write_pages(result: ExtractionResult, document_id: str, sha256: str, path: str | Path) -> str:
    """Write one JSON record per page (deterministic bytes) and return the file's SHA-256."""
    lines = [
        json.dumps(
            {
                "document_id": document_id,
                "sha256": sha256,
                "page": p.page,
                "chars": p.chars,
                "text": p.text,
                "extractor": result.extractor,
                "extractor_version": result.extractor_version,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for p in result.pages
    ]
    data = ("\n".join(lines) + "\n").encode("utf-8")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def read_pages(path: str | Path) -> list[dict]:
    """Read a page file written by ``write_pages``."""
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


__all__ = [
    "EXTRACTOR",
    "MIN_PAGE_CHARS",
    "PDF_ERRORS",
    "ExtractionResult",
    "PageText",
    "PdfSupportMissing",
    "PdfInspection",
    "read_pages",
    "read_pdf",
    "write_pages",
]
