"""Document batch processor: intake -> integrity -> extraction -> screening -> review -> promotion.

Reads ``docs/acquisition/<batch>/DOCUMENT_INTAKE.yaml`` (person-recorded metadata and where each
PDF was saved), builds one document manifest per entry, applies the person's decisions in
``docs/acquisition/<batch>/DOCUMENT_REVIEW_DECISIONS.yaml`` (if the file exists), promotes only
what passes the document gate, and writes manifests to ``data/doc_manifests/`` plus a summary to
``docs/acquisition/<batch>/document_summary.json``.

* Source bytes are never changed. A quarantined document is moved to
  ``data/quarantine/<batch>/docs/``; an approved document is copied byte-identically to
  ``data/docs/<domain>/``. Reads, copies and moves go through ``catalog.safe_fs``: handles are
  verified to lie inside their permitted folders, nothing is overwritten, and a move is checked
  afterwards against the hash of the verified source.
* Limits (``PreparationLimits``, configurable by environment variables) bound file size, pages,
  extracted text, extraction time and the number of documents in a batch.
* The summary lists, for each document, the source ``sha256`` and the ``extraction_sha256`` of
  its page file: an ``approve`` decision must record both.
* ``data/docs/`` holds only approved documents: a promoted copy left by a document of this batch
  that is no longer approved (quarantined, rejected, withdrawn, or its bytes changed so the review
  is stale) is moved to ``data/quarantine/<batch>/docs/promoted/``, unless an approved manifest
  claims that path.
* A ``document_id`` may be recorded in only one batch's intake file.
* Entries without a file stay ``planned``. Tools never download documents.
* Outputs carry no timestamps: re-running on the same inputs gives identical files.

Usage: python scripts/process_doc_batch.py <batch>     (e.g. docs-01)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath

from civicmind.catalog.doc_limits import PreparationLimits
from civicmind.catalog.doc_promote import gate_reasons, promote_document
from civicmind.catalog.doc_review import apply_document_review, load_document_decisions
from civicmind.catalog.documents import (
    DOC_MANIFEST_DIR,
    DocumentManifest,
    filename_problem,
    read_document_manifests,
    resolves_within,
    write_document_manifest,
)
from civicmind.catalog.promote import PromotionRefused
from civicmind.catalog.safe_fs import move_verified
from civicmind.rag.doc_intake import build_document_manifest, finding, link_documents, load_intake
from civicmind.rag.extract import PdfSupportMissing

ROOT = Path(__file__).resolve().parents[1]


def _with(manifest: DocumentManifest, **changes) -> DocumentManifest:
    return DocumentManifest.model_validate({**manifest.model_dump(), **changes})


def locate(root: Path, quarantine: Path, local_path: str | None) -> Path | None:
    """Where the document's bytes are now: its recorded path, or its quarantined copy."""
    if not local_path:
        return None
    for path in (root / local_path, quarantine / PurePosixPath(local_path).name):
        if path.is_file():
            return path
    return None


def other_batch_ids(root: Path, batch: str) -> dict[str, str]:
    """``document_id -> batch`` for every other batch's intake file."""
    owners = {}
    for path in sorted((root / "docs/acquisition").glob("*/DOCUMENT_INTAKE.yaml")):
        if path.parent.name != batch:
            for d in load_intake(path).documents:
                owners[d.document_id] = path.parent.name
    return owners


def promoted_path(manifest: DocumentManifest) -> str | None:
    """Where promotion puts (or put) this document's copy, from its recorded source."""
    local = manifest.retrieval.local_path
    if not local or filename_problem(manifest.retrieval.original_filename):
        return None
    domain = PurePosixPath(local).parent.name
    return f"data/docs/{domain}/{manifest.retrieval.original_filename}"


def quarantine_orphans(
    root: Path,
    quarantine: Path,
    manifests: list[DocumentManifest],
    others: list[DocumentManifest],
    max_bytes: int = PreparationLimits().max_bytes,
) -> list[str]:
    """Move promoted copies of this batch's non-approved documents out of data/docs/.

    A path claimed by an approved manifest (this run's, or ``others``: manifests of other
    batches) is never touched. This batch's manifests on disk are from the previous run and are
    not consulted. Returns the moved paths (relative to the root).
    """
    claimed = {
        m.promoted_to for m in [*others, *manifests] if m.status == "approved" and m.promoted_to
    }
    moved = []
    for m in manifests:
        rel = promoted_path(m)
        if m.status == "approved" or rel is None or rel in claimed:
            continue
        if (root / rel).is_file() and resolves_within(root, rel, "data/docs"):
            target = (quarantine / "promoted" / PurePosixPath(rel).name).relative_to(root)
            move_verified(root, rel, "data/docs", target.as_posix(), "data/quarantine", max_bytes)
            moved.append(rel)
    return moved


def process(batch: str, root: Path = ROOT, limits: PreparationLimits | None = None) -> list[dict]:
    limits = limits or PreparationLimits.from_env()
    reports = root / "docs/acquisition" / batch
    quarantine = root / "data/quarantine" / batch / "docs"
    intake = load_intake(reports / "DOCUMENT_INTAKE.yaml")
    if intake.batch != batch:
        raise SystemExit(f"intake file is for batch {intake.batch!r}, not {batch!r}")
    decisions = load_document_decisions(reports / "DOCUMENT_REVIEW_DECISIONS.yaml")
    ids = {d.document_id for d in intake.documents}
    if len(ids) != len(intake.documents):
        raise SystemExit("duplicate document_id in the intake file")
    if len(intake.documents) > limits.max_batch:
        raise SystemExit(
            f"the batch has {len(intake.documents)} documents; the limit is {limits.max_batch}"
        )
    owners = other_batch_ids(root, batch)
    clashes = sorted(f"{i} (batch {owners[i]})" for i in ids if i in owners)
    if clashes:
        raise SystemExit(f"document_id already recorded in another batch: {', '.join(clashes)}")
    existing = [m for m in read_document_manifests(root) if m.document_id not in ids]

    built = [
        build_document_manifest(d, root, locate(root, quarantine, d.local_path), limits)
        for d in intake.documents
    ]
    out_dir = root / DOC_MANIFEST_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    final = []
    for manifest in link_documents(built, existing):
        manifest = apply_document_review(manifest, decisions)
        source = locate(root, quarantine, manifest.retrieval.local_path)
        if manifest.status == "quarantined" and source is not None:
            if not source.is_relative_to(quarantine):  # not yet moved
                target = (quarantine / source.name).relative_to(root).as_posix()
                move_verified(
                    root,
                    manifest.retrieval.local_path,
                    "data/external",
                    target,
                    "data/quarantine",
                    limits.max_bytes,
                )
        elif manifest.human_review == "accepted" and manifest.status == "validated":
            try:
                manifest = promote_document(manifest, root, limits)
            except PromotionRefused as exc:
                manifest = _with(
                    manifest,
                    findings=[
                        *manifest.findings,
                        finding(
                            "promotion.refused",
                            "warning",
                            "Gate refused",
                            {"reasons": exc.reasons},
                        ),
                    ],
                )
        final.append(manifest)
    for rel in quarantine_orphans(root, quarantine, final, existing, limits.max_bytes):
        print(f"moved {rel} to {(quarantine / 'promoted').relative_to(root).as_posix()}/")
    summary = []
    for manifest in final:
        write_document_manifest(manifest, out_dir)
        summary.append(
            {
                "document_id": manifest.document_id,
                "status": manifest.status,
                "human_review": manifest.human_review,
                "sha256": manifest.integrity.sha256 if manifest.integrity else None,
                "extraction_sha256": manifest.extraction.output_sha256
                if manifest.extraction
                else None,
                "pages": manifest.integrity.pages if manifest.integrity else None,
                "pages_with_text": manifest.extraction.pages_with_text
                if manifest.extraction
                else None,
                "errors": sorted(manifest.error_codes()),
                "warnings": sorted(manifest.warning_codes()),
                "gate": gate_reasons(manifest) if manifest.status != "approved" else [],
                "promoted_to": manifest.promoted_to,
            }
        )
    (reports / "document_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batch", help="acquisition batch folder under docs/acquisition/")
    args = parser.parse_args()
    try:
        rows = process(args.batch)
    except PdfSupportMissing as exc:  # raised while building: no manifest or summary written
        raise SystemExit(f"error: {exc}") from None
    for row in rows:
        extra = f" errors={row['errors']}" if row["errors"] else ""
        extra += f" warnings={row['warnings']}" if row["warnings"] else ""
        print(f"{row['document_id']:<24} {row['status']:<17} review={row['human_review']}{extra}")


if __name__ == "__main__":
    main()
