"""Dataset manifest model (see docs/MANIFEST_SPEC.md) and YAML serialisation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Status = Literal[
    "planned",
    "not_retrieved",
    "received",
    "integrity_passed",
    "validated",
    "promoted",
    "quarantined",
    "rejected",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Licence(_Strict):
    name: str
    url: str | None
    evidence: str
    attribution: str
    exemptions_checked: bool


class Retrieval(_Strict):
    retrieved_at: str | None
    retrieved_by: str | None
    method: str
    http_status: int | None = None
    content_type: str | None = None
    original_filename: str
    local_path: str | None
    note: str | None = None


class Integrity(_Strict):
    bytes: int | None
    portal_stated_bytes: int | None
    size_matches_portal: bool | None
    sha256: str | None
    format: str
    encoding: str | None
    bom: bool | None
    newline: str | None
    newline_counts: dict[str, int] | None = None
    delimiter: str | None
    looks_like_html: bool | None = None
    passed: bool


class Period(_Strict):
    start: str | None
    end: str | None
    granularity: str
    as_on: str | None = None


class Geography(_Strict):
    country: str = "India"
    state: str | None = None
    city: str | None = None
    level: str


class SchemaColumn(_Strict):
    name: str
    type: str
    unit: str | None = None
    key: str | None = None


ReviewDecision = Literal["accept", "quarantine", "keep_profiled", "reject"]


class Review(_Strict):
    """A person's decision on one manifest, bound to the exact file bytes it was made for."""

    decision: ReviewDecision
    reviewed_by: str
    reviewed_on: str
    sha256: str
    accepted_caveats: list[str] = Field(default_factory=list)  # warning finding codes
    note: str | None = None


class Manifest(_Strict):
    dataset_id: str
    manifest_version: int = 1
    title: str
    publisher: str
    host_portal: str
    source_class: Literal["official", "secondary_mirror"]
    resource_page: str
    download_url: str
    portal_published: str | None = None
    portal_updated: str | None = None
    licence: Licence
    retrieval: Retrieval
    integrity: Integrity | None = None
    schema_: list[SchemaColumn] = Field(default_factory=list, alias="schema")
    row_count: int | None = None
    period: Period
    geography: Geography
    ward_scheme: str | None = None
    identifier_evidence: str | None = None
    sensitivity: Literal["public", "personal_data", "restricted"]
    contains_personal_data: bool
    semantic_checks: dict[str, Any] = Field(default_factory=dict)
    compatibility: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    value_nature: Literal["measured", "modelled", "unknown"] = "unknown"
    human_review: Literal["pending", "accepted", "rejected"] = "pending"
    review: Review | None = None
    status: Status
    promoted_to: str | None = None
    git_tracked: bool = False
    same_bytes_as: str | None = None
    known_limitations: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def to_yaml(self) -> str:
        data = self.model_dump(by_alias=True, mode="json")
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def write_manifest(manifest: Manifest, directory: str | Path) -> Path:
    path = Path(directory) / f"{manifest.dataset_id}.yaml"
    path.write_text(manifest.to_yaml(), encoding="utf-8", newline="\n")
    return path


def read_manifest(path: str | Path) -> Manifest:
    return Manifest.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


__all__ = ["Manifest", "Review", "read_manifest", "write_manifest"]
