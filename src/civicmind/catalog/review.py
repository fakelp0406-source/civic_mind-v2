"""Apply a person's recorded review decisions to generated manifests.

Decisions live in a reviewed YAML file (e.g. ``docs/acquisition/batch-01/REVIEW_DECISIONS.yaml``)
so that regenerating manifests never erases them. Each decision is bound to the SHA-256 it
was made for. The function fails closed: if the bytes changed, or an ``accept`` does not
cover every warning finding, the manifest stays ``human_review: pending``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from civicmind.catalog.manifest import Manifest, Review, ReviewDecision

HUMAN_REVIEW = {
    "accept": "accepted",
    "quarantine": "rejected",
    "reject": "rejected",
    "keep_profiled": "pending",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Decision(_Strict):
    decision: ReviewDecision
    sha256: str
    accepted_caveats: list[str] = Field(default_factory=list)
    value_nature: Literal["measured", "modelled", "unknown"] | None = None
    add_limitations: list[str] = Field(default_factory=list)
    permitted_uses: list[Literal["exploratory"]] = Field(default_factory=list)
    note: str | None = None


class DecisionsFile(_Strict):
    reviewed_by: str
    reviewed_on: str
    decisions: dict[str, Decision]


def load_decisions(path: str | Path) -> DecisionsFile:
    return DecisionsFile.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _with_finding(manifest: Manifest, code: str, message: str, details: dict) -> Manifest:
    data = manifest.model_dump(by_alias=True)
    data["findings"] = [
        *data["findings"],
        {"code": code, "severity": "warning", "message": message, "details": details},
    ]
    data["human_review"] = "pending"
    data["review"] = None
    return Manifest.model_validate(data)


def apply_review(manifest: Manifest, decisions: DecisionsFile | None) -> Manifest:
    """Return a copy of ``manifest`` with the recorded decision applied (no file changes)."""
    if decisions is None or manifest.dataset_id not in decisions.decisions:
        return manifest
    d = decisions.decisions[manifest.dataset_id]
    current = manifest.integrity.sha256 if manifest.integrity else None
    if d.sha256 != current:
        return _with_finding(
            manifest,
            "review.stale",
            "Recorded review was made for different file bytes; not applied",
            {"reviewed_sha256": d.sha256, "current_sha256": current},
        )
    if d.decision == "accept":
        if manifest.status != "validated":
            return _with_finding(
                manifest,
                "review.not_applicable",
                f"'accept' recorded but status is {manifest.status!r}; not applied",
                {"status": manifest.status},
            )
        warnings = {f["code"] for f in manifest.findings if f.get("severity") == "warning"}
        uncovered = sorted(warnings - set(d.accepted_caveats))
        if uncovered:
            return _with_finding(
                manifest,
                "review.incomplete",
                "Warnings not accepted as caveats by the reviewer; not applied",
                {"uncovered": uncovered},
            )
    data = manifest.model_dump(by_alias=True)
    data["review"] = Review(
        decision=d.decision,
        reviewed_by=decisions.reviewed_by,
        reviewed_on=decisions.reviewed_on,
        sha256=d.sha256,
        accepted_caveats=d.accepted_caveats,
        permitted_uses=d.permitted_uses,
        note=d.note,
    ).model_dump()
    data["human_review"] = HUMAN_REVIEW[d.decision]
    if d.value_nature is not None:
        data["value_nature"] = d.value_nature
    data["known_limitations"] = [*data["known_limitations"], *d.add_limitations]
    if d.decision == "quarantine":
        data["status"] = "quarantined"
    elif d.decision == "reject":
        data["status"] = "rejected"
    return Manifest.model_validate(data)


__all__ = ["Decision", "DecisionsFile", "apply_review", "load_decisions"]
