"""Evidence package, source records, refusals and validation. Pure data; no other layer imported.

``validate_package`` checks a computed result against the facts recorded for its sources
(supplied by the caller from the manifests): every item must name a known dataset whose
SHA-256, status, file path, period and columns match, in trusted mode. Any mismatch blocks
the answer (``evidence.invalid``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

SHA256 = re.compile(r"[0-9a-f]{64}")
EVIDENCE_CODES = frozenset({"evidence.invalid"})


@dataclass(frozen=True)
class SourceRecord:
    """What the catalogue says about one dataset (built from its manifest)."""

    dataset_id: str
    sha256: str
    status: str
    source_path: str | None  # promoted_to
    columns: tuple[str, ...]
    period_start: str | None
    period_end: str | None
    title: str = ""


@dataclass(frozen=True)
class EvidenceItem:
    dataset_id: str
    role: str  # "primary" or "reference"
    schema_version: str
    sha256: str
    source_path: str
    mode: str
    period_start: str | None
    period_end: str | None
    columns: tuple[str, ...]
    rows_used: int


@dataclass(frozen=True)
class EvidencePackage:
    question: str
    intent: str
    operation: str
    value: Any
    unit: str
    method: str
    denominator: str | None
    caveats: tuple[str, ...]
    filters: dict[str, Any]
    assumptions: tuple[str, ...]
    items: tuple[EvidenceItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Refusal:
    code: str
    stage: str  # planner | feasibility | ingest | analytics | evidence | pipeline
    reason: str
    details: Any = None


@dataclass(frozen=True)
class ValidationReport:
    """Outcome of ``validate_package``, bound to the exact package it checked."""

    problems: tuple[str, ...] = field(default_factory=tuple)
    package_digest: str = ""

    @property
    def ok(self) -> bool:
        return not self.problems and bool(self.package_digest)


def package_digest(package: EvidencePackage) -> str:
    """SHA-256 of the package's canonical JSON; any change to a value or item changes it."""
    text = json.dumps(asdict(package), sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_package(
    package: EvidencePackage,
    sources: Mapping[str, SourceRecord],
    primary_ids: Sequence[str],
    reference_ids: Sequence[str] = (),
) -> ValidationReport:
    problems: list[str] = []
    if package.value is None:
        problems.append("no value")
    if not package.unit or not package.method or not package.caveats:
        problems.append("unit, method and caveats are required")
    expected = [*primary_ids, *reference_ids]
    if [item.dataset_id for item in package.items] != expected:
        problems.append(f"evidence datasets {[i.dataset_id for i in package.items]} != {expected}")
    for item in package.items:
        src = sources.get(item.dataset_id)
        if src is None:
            problems.append(f"{item.dataset_id}: not in the catalogue")
            continue
        if not SHA256.fullmatch(item.sha256) or item.sha256 != src.sha256:
            problems.append(f"{item.dataset_id}: SHA-256 does not match the manifest")
        if src.status != "promoted" or item.mode != "trusted":
            problems.append(f"{item.dataset_id}: not a promoted dataset used in trusted mode")
        if item.source_path != src.source_path:
            problems.append(f"{item.dataset_id}: source path differs from the manifest")
        if not item.columns or not set(item.columns) <= set(src.columns):
            problems.append(f"{item.dataset_id}: columns are not in the manifest schema")
        if (item.period_start, item.period_end) != (src.period_start, src.period_end):
            problems.append(f"{item.dataset_id}: period differs from the manifest")
        if item.rows_used <= 0:
            problems.append(f"{item.dataset_id}: no rows used")
    return ValidationReport(tuple(problems), package_digest(package))


__all__ = [
    "EVIDENCE_CODES",
    "EvidenceItem",
    "EvidencePackage",
    "Refusal",
    "SourceRecord",
    "ValidationReport",
    "package_digest",
    "validate_package",
]
