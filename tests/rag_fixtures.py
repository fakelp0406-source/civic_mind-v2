"""Synthetic approved-document corpora for retrieval tests (no real documents)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np

from civicmind.catalog.doc_promote import promote_document
from civicmind.catalog.doc_review import DocumentDecisionsFile, apply_document_review
from civicmind.catalog.documents import DocumentManifest, write_document_manifest
from civicmind.rag.doc_intake import DocumentIntake, build_document_manifest
from civicmind.rag.embed import ModelSpec
from pdf_synth import make_pdf

LICENCE = {
    "name": "L",
    "url": None,
    "evidence": "t",
    "attribution": "t",
    "exemptions_checked": True,
}


def intake(doc_id: str, edition: str, filename: str) -> DocumentIntake:
    return DocumentIntake.model_validate(
        {
            "document_id": doc_id,
            "title": f"Synthetic Report {edition}",
            "issuing_authority": "A",
            "publisher": "P",
            "document_type": "statistical_report",
            "domains": ["roads"],
            "source_class": "official",
            "resource_page": f"https://example.invalid/{doc_id}",
            "download_url": f"https://example.invalid/{filename}",
            "edition": edition,
            "licence": LICENCE,
            "original_filename": filename,
            "local_path": f"data/external/v/docs/roads/{filename}",
        }  # fmt: skip
    )


def add_document(
    root: Path,
    doc_id: str,
    pages: list[str],
    edition: str = "2023",
    decision: str | None = "approve",
    excluded_pages: list[int] | None = None,
    promote: bool = True,
) -> DocumentManifest:
    """Prepare a synthetic PDF; optionally review and promote it; write its manifest."""
    filename = f"{doc_id.lower()}.pdf"
    path = root / f"data/external/v/docs/roads/{filename}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_pdf(pages))
    m = build_document_manifest(intake(doc_id, edition, filename), root)
    if decision is not None:
        entry = {"decision": decision, "sha256": m.integrity.sha256,
                 "extraction_sha256": m.extraction.output_sha256,
                 "accepted_caveats": sorted(m.warning_codes()),
                 "excluded_pages": excluded_pages or []}  # fmt: skip
        m = apply_document_review(
            m,
            DocumentDecisionsFile.model_validate(
                {
                    "reviewed_by": "tester",
                    "reviewed_on": "2026-10-18",
                    "decisions": {doc_id: entry},
                }  # fmt: skip
            ),
        )
        if decision == "approve" and promote:
            m = promote_document(m, root)
    (root / "data/doc_manifests").mkdir(parents=True, exist_ok=True)
    write_document_manifest(m, root / "data/doc_manifests")
    return m


FAKE_SPEC = ModelSpec("test/fake-bow", "rev0", "none", {}, dim=64, max_tokens=512)


class FakeEncoder:
    """Deterministic hashed bag-of-words vectors (L2-normalised); stands in for MiniLM."""

    spec = FAKE_SPEC

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.spec.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.spec.dim
                out[i, bucket] += 1.0
            norm = np.linalg.norm(out[i])
            if norm:
                out[i] /= norm
        return out
