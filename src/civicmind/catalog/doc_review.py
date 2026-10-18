"""Apply a person's recorded document review decisions to generated document manifests.

Decisions live in a reviewed YAML file per acquisition batch
(``docs/acquisition/<batch>/DOCUMENT_REVIEW_DECISIONS.yaml``) so that regenerating manifests
never erases them. Each decision is bound to the SHA-256 it was made for. Fails closed: changed
bytes (``review.stale``), an ``approve`` that leaves a warning uncovered
(``review.incomplete``), an approval of a document that did not validate
(``review.not_applicable``) or impossible page exclusions (``review.invalid_pages``) leave
``human_review: pending`` and add a finding.

A warning is covered when its code is listed in ``accepted_caveats``, or when every page it
names is in ``excluded_pages`` (excluded pages are never indexed or cited).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from civicmind.catalog.documents import DocumentDecision, DocumentManifest, DocumentReview

HUMAN_REVIEW = {
    "approve": "accepted",
    "quarantine": "rejected",
    "reject": "rejected",
    "withdraw": "rejected",
}
STATUS = {"quarantine": "quarantined", "reject": "rejected", "withdraw": "withdrawn"}
PERSONAL = "content.personal_data_suspected"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentDecisionEntry(_Strict):
    decision: DocumentDecision
    sha256: str
    accepted_caveats: list[str] = Field(default_factory=list)
    excluded_pages: list[int] = Field(default_factory=list)
    add_limitations: list[str] = Field(default_factory=list)
    note: str | None = None


class DocumentDecisionsFile(_Strict):
    reviewed_by: str
    reviewed_on: str
    decisions: dict[str, DocumentDecisionEntry]


def load_document_decisions(path: str | Path) -> DocumentDecisionsFile | None:
    """The decisions file, or ``None`` when it does not exist yet."""
    path = Path(path)
    if not path.is_file():
        return None
    return DocumentDecisionsFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _covered(finding: dict, accepted: set[str], excluded: set[int]) -> bool:
    if finding["code"] in accepted:
        return True
    pages = set((finding.get("details") or {}).get("pages") or ())
    return bool(pages) and pages <= excluded


def uncovered_warnings(
    manifest: DocumentManifest, accepted: list[str], excluded: list[int]
) -> list[str]:
    """Warning codes neither accepted as caveats nor confined to excluded pages."""
    acc, exc = set(accepted), set(excluded)
    return sorted(
        {
            f["code"]
            for f in manifest.findings
            if f.get("severity") == "warning" and not _covered(f, acc, exc)
        }
    )


def _with_finding(manifest: DocumentManifest, code: str, message: str, details: dict):
    data = manifest.model_dump()
    data["findings"] = [
        *data["findings"],
        {"code": code, "severity": "warning", "message": message, "details": details},
    ]
    data["human_review"] = "pending"
    data["review"] = None
    return DocumentManifest.model_validate(data)


def _page_problems(manifest: DocumentManifest, excluded: list[int]) -> list[str]:
    problems = []
    total = manifest.integrity.pages if manifest.integrity else None
    bad = sorted(p for p in excluded if p < 1 or (total is not None and p > total))
    if bad:
        problems.append(f"pages outside 1..{total}: {bad}")
    if manifest.extraction is not None:
        text_pages = set(range(1, manifest.extraction.pages + 1)) - set(
            manifest.extraction.pages_without_text
        )
        if text_pages and text_pages <= set(excluded):
            problems.append("every page with text is excluded; nothing would remain")
    return problems


def apply_document_review(
    manifest: DocumentManifest, decisions: DocumentDecisionsFile | None
) -> DocumentManifest:
    """Return a copy of ``manifest`` with the recorded decision applied (no file changes)."""
    if decisions is None or manifest.document_id not in decisions.decisions:
        return manifest
    d = decisions.decisions[manifest.document_id]
    current = manifest.integrity.sha256 if manifest.integrity else None
    if d.sha256 != current:
        return _with_finding(
            manifest,
            "review.stale",
            "Recorded review was made for different file bytes; not applied",
            {"reviewed_sha256": d.sha256, "current_sha256": current},
        )
    if d.decision == "approve":
        if manifest.status != "validated":
            return _with_finding(
                manifest,
                "review.not_applicable",
                f"'approve' recorded but status is {manifest.status!r}; not applied",
                {"status": manifest.status},
            )
        problems = _page_problems(manifest, d.excluded_pages)
        if problems:
            return _with_finding(
                manifest,
                "review.invalid_pages",
                "Excluded pages are not valid for this document; not applied",
                {"problems": problems},
            )
        uncovered = uncovered_warnings(manifest, d.accepted_caveats, d.excluded_pages)
        if uncovered:
            return _with_finding(
                manifest,
                "review.incomplete",
                "Warnings neither accepted as caveats nor confined to excluded pages; not applied",
                {"uncovered": uncovered},
            )
    if d.decision == "withdraw" and manifest.status not in ("validated", "approved"):
        return _with_finding(
            manifest,
            "review.not_applicable",
            f"'withdraw' recorded but status is {manifest.status!r}; not applied",
            {"status": manifest.status},
        )
    data = manifest.model_dump()
    data["review"] = DocumentReview(
        decision=d.decision,
        reviewed_by=decisions.reviewed_by,
        reviewed_on=decisions.reviewed_on,
        sha256=d.sha256,
        accepted_caveats=d.accepted_caveats,
        excluded_pages=sorted(d.excluded_pages),
        note=d.note,
    ).model_dump()
    data["human_review"] = HUMAN_REVIEW[d.decision]
    data["known_limitations"] = [*data["known_limitations"], *d.add_limitations]
    if d.decision in STATUS:
        data["status"] = STATUS[d.decision]
    screened = any(f["code"] == "content.screen" for f in manifest.findings)
    if d.decision == "approve" and screened:
        # The reviewer has judged every personal-data match (accepted or excluded pages).
        personal = [f for f in manifest.findings if f["code"] == PERSONAL]
        if all(_covered(f, set(d.accepted_caveats), set(d.excluded_pages)) for f in personal):
            data["sensitivity"] = "public"
            data["contains_personal_data"] = False
    return DocumentManifest.model_validate(data)


__all__ = [
    "DocumentDecisionEntry",
    "DocumentDecisionsFile",
    "apply_document_review",
    "load_document_decisions",
    "uncovered_warnings",
]
