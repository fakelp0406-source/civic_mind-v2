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
import io
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from civicmind.catalog.doc_limits import DEFAULT_LIMITS, PreparationLimits

EXTRACTOR = "pypdf"
#: Pages with fewer non-whitespace characters than this count as having no text.
MIN_PAGE_CHARS = 20
#: Bumped whenever extraction or the page-file format changes; recorded in every page record,
#: so a change invalidates the extraction hash and therefore every review bound to it.
PREPARATION_VERSION = "docprep@v2"
PDF_ERRORS = frozenset(
    {
        "document.too_large",
        "pdf.not_pdf",
        "pdf.unreadable",
        "pdf.encrypted",
        "pdf.too_many_pages",
        "extraction.too_large",
        "extraction.timeout",
    }
)


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


def read_pdf_bytes(
    data: bytes, limits: PreparationLimits = DEFAULT_LIMITS
) -> tuple[PdfInspection, ExtractionResult | None]:
    """Inspect and extract a PDF held in memory. The caller hashes the same ``data`` object, so
    the recorded SHA-256 and the extracted text always describe identical bytes.

    Limits (``PreparationLimits``): more than ``max_bytes`` bytes is ``document.too_large``;
    more than ``max_pages`` pages is ``pdf.too_many_pages`` (checked before any page is
    extracted); more than ``max_text_chars`` extracted characters is ``extraction.too_large``;
    more than ``extract_seconds`` (checked between pages) is ``extraction.timeout``. Any failure
    returns no extraction at all, never a partial one.
    """
    if len(data) > limits.max_bytes:
        header = data.startswith(b"%PDF-")
        return PdfInspection(pdf_header=header, error="document.too_large"), None
    if not data.startswith(b"%PDF-"):
        return PdfInspection(pdf_header=False, error="pdf.not_pdf"), None

    try:
        import pypdf  # optional dependency, imported on use
    except ImportError as exc:
        raise PdfSupportMissing() from exc

    version = data[5:8].decode("ascii", errors="replace")
    started = time.monotonic()
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        encrypted = bool(reader.is_encrypted)
        if encrypted and reader.decrypt("") == 0:  # PasswordType.NOT_DECRYPTED
            return PdfInspection(True, version, None, True, None, "pdf.encrypted"), None
        count = len(reader.pages)
        if count > limits.max_pages:
            return PdfInspection(True, version, count, encrypted, None, "pdf.too_many_pages"), None
        meta = reader.metadata
        producer = str(meta.producer) if meta is not None and meta.producer else None
        pages, total = [], 0
        for number, page in enumerate(reader.pages, start=1):
            if time.monotonic() - started > limits.extract_seconds:
                failed = PdfInspection(
                    True, version, count, encrypted, producer, "extraction.timeout"
                )
                return failed, None
            text = (page.extract_text() or "").replace("\r\n", "\n").replace("\r", "\n")
            total += len(text)
            if total > limits.max_text_chars:
                failed = PdfInspection(
                    True, version, count, encrypted, producer, "extraction.too_large"
                )
                return failed, None
            pages.append(PageText(number, text, _visible_chars(text)))
    except Exception:  # noqa: BLE001 - malformed PDFs raise many types; fail closed
        # The exception text can contain file paths or document text; it is not kept.
        return PdfInspection(True, version, error="pdf.unreadable"), None
    inspection = PdfInspection(True, version, len(pages), encrypted, producer)
    return inspection, ExtractionResult(EXTRACTOR, pypdf.__version__, tuple(pages))


def read_pdf(
    path: str | Path, limits: PreparationLimits = DEFAULT_LIMITS
) -> tuple[PdfInspection, ExtractionResult | None]:
    """Convenience for tools and tests: read the file once, then ``read_pdf_bytes``. The
    document catalogue itself reads through ``catalog.safe_fs.read_verified`` instead."""
    return read_pdf_bytes(Path(path).read_bytes(), limits)


def pages_bytes(result: ExtractionResult, document_id: str, sha256: str) -> bytes:
    """The page file: one JSON record per page, deterministic bytes. Each record names the
    document, the SHA-256 of the exact source bytes, the extractor and the preparation version,
    so the file's own hash identifies the reviewed text artifact."""
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
                "preparation_version": PREPARATION_VERSION,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for p in result.pages
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_pages(result: ExtractionResult, document_id: str, sha256: str, path: str | Path) -> str:
    """Write ``pages_bytes`` to ``path`` and return its SHA-256 (tools and tests; the catalogue
    writes through ``catalog.safe_fs``)."""
    data = pages_bytes(result, document_id, sha256)
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
    "PREPARATION_VERSION",
    "ExtractionResult",
    "PageText",
    "PdfSupportMissing",
    "PdfInspection",
    "pages_bytes",
    "read_pages",
    "read_pdf",
    "read_pdf_bytes",
    "write_pages",
]
