"""Synthetic PDFs for tests, generated in memory (no binary fixtures, no real documents).

``make_pdf`` writes a minimal valid PDF 1.4 file: one Helvetica text block per page; an empty
string gives a page with no text (like a scanned page). Text must be Latin-1.
"""

from __future__ import annotations

import io


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str]) -> bytes:
    n = len(pages)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        ("<< /Type /Pages /Kids [" + " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
         + f"] /Count {n} >>").encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]  # fmt: skip
    for i, text in enumerate(pages):
        ops = []
        if text:
            ops = ["BT", "/F1 11 Tf", "14 TL", "72 760 Td"]
            ops += [f"({_escape(line)}) Tj T*" for line in text.split("\n")]
            ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>"
            ).encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return out


def encrypt_pdf(data: bytes, user_password: str) -> bytes:
    """The same document encrypted with RC4-128 (needs no extra crypto package)."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    writer.encrypt(user_password=user_password, owner_password="owner", algorithm="RC4-128")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
