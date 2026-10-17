"""Stage A - source-file integrity fingerprint.

Describes the exact bytes received from a publisher: size, SHA-256, text encoding, BOM,
line-ending style and delimiter. It never modifies the file, and it makes no claim about
whether the contents are semantically valid.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

#: Encodings tried in order when no BOM is present.
CANDIDATE_ENCODINGS = ("utf-8", "cp1252")
_SNIFF_BYTES = 8192


@dataclass(frozen=True)
class FileFingerprint:
    """Byte-level description of one received file."""

    path: str
    bytes: int
    sha256: str
    encoding: str | None
    bom: bool
    newline: str
    newline_counts: dict[str, int]
    delimiter: str | None
    looks_like_html: bool
    contains_nul: bool

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_of(path: str | Path) -> str:
    """Return the hex SHA-256 of a file, streaming in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_encoding(raw: bytes) -> tuple[str | None, bool]:
    """Return ``(encoding, has_utf8_bom)``; ``None`` when no candidate decodes cleanly."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", True
    for encoding in CANDIDATE_ENCODINGS:
        try:
            raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding, False
    return None, False


def classify_newlines(raw: bytes) -> tuple[str, dict[str, int]]:
    """Count CRLF, bare LF and bare CR line breaks and name the dominant style.

    Returns ``"CRLF"``, ``"LF"`` or ``"CR"`` when only one style occurs, ``"mixed"``
    otherwise, and ``"none"`` for a single-line file.
    """
    crlf = raw.count(b"\r\n")
    counts = {"CRLF": crlf, "LF": raw.count(b"\n") - crlf, "CR": raw.count(b"\r") - crlf}
    present = [style for style, count in counts.items() if count]
    if not present:
        return "none", counts
    return (present[0] if len(present) == 1 else "mixed"), counts


def sniff_delimiter(text: str) -> str | None:
    """Best-effort delimiter detection over a text sample; ``None`` if undetermined."""
    try:
        return csv.Sniffer().sniff(text, delimiters=",;\t|").delimiter
    except csv.Error:
        return None


def fingerprint(path: str | Path) -> FileFingerprint:
    """Fingerprint a received file without changing it."""
    path = Path(path)
    raw = path.read_bytes()
    encoding, bom = detect_encoding(raw)
    newline, counts = classify_newlines(raw)
    sample = raw[:_SNIFF_BYTES]
    head = sample.lstrip()[:1024].lower()
    text_sample = sample.decode(encoding, errors="replace") if encoding else ""
    return FileFingerprint(
        path=path.as_posix(),
        bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        encoding=encoding,
        bom=bom,
        newline=newline,
        newline_counts=counts,
        delimiter=sniff_delimiter(text_sample) if text_sample else None,
        looks_like_html=head.startswith(b"<") and (b"<html" in head or b"<!doctype" in head),
        contains_nul=b"\x00" in raw,
    )


__all__ = [
    "FileFingerprint",
    "classify_newlines",
    "detect_encoding",
    "fingerprint",
    "sha256_of",
    "sniff_delimiter",
]
