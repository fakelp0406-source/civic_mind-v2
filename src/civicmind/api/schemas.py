"""Typed request and response models of the HTTP API (version 1).

Responses mirror :class:`civicmind.respond.compose.Answer` field by field; nothing is computed
here. Two things are deliberately left out: the evidence ``source_path`` (internal storage
location; the dataset id and SHA-256 identify the source) and refusal ``details`` (which the
pipeline never puts on an ``Answer`` either).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Transport bound only. The parser's own limit (``query.too_long``, 400 characters) stays
#: authoritative and is reported as a normal refusal.
MAX_QUESTION_CHARS = 1000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryRequest(_Strict):
    """A natural-language question. No other field is accepted (no dataset ids or paths)."""

    question: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_CHARS,
        description="The question. Leading and trailing whitespace is removed.",
        examples=["How many over-speeding accidents did Bengaluru record in 2021?"],
    )

    @field_validator("question", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class RefusalOut(_Strict):
    code: str = Field(description="Stable refusal code from the pipeline.")
    stage: str = Field(
        description="planner | feasibility | ingest | analytics | evidence | pipeline"
    )
    reason: str


class ResultOut(_Strict):
    operation: str
    value: Any = Field(description="Deterministic analytics output, exactly as computed.")
    value_basis: Literal["published", "derived", "published_and_derived", "catalogue"] | None = (
        Field(
            default=None,
            description="published cells, a derived calculation, a published count with a "
            "derived share/difference, or catalogue metadata (no data value).",
        )
    )
    unit: str | None
    metric: str | None
    periods: list[str]
    method: str | None
    denominator: str | None


class EvidenceOut(_Strict):
    dataset_id: str
    role: Literal["primary", "reference"]
    schema_version: str
    sha256: str
    mode: str
    period_start: str | None
    period_end: str | None
    columns: list[str]
    rows_used: int


class PeriodTrustOut(_Strict):
    period: str
    dataset_id: str
    trust: str = Field(description="quarantined | exploratory_only | profile_only | ...")


class OtherTableOut(_Strict):
    edition: str | None
    table: str | None
    dataset_id: str
    trust: str


class CoverageOut(_Strict):
    """Catalogue coverage for the question's domain (manifest metadata; not live data)."""

    domain: str
    series: str
    period_unit: str
    trusted_periods: list[str]
    latest_trusted_period: str | None
    latest_trusted_dataset: str | None
    latest_trusted_portal_published: str | None
    not_trusted: list[PeriodTrustOut]
    other_tables: list[OtherTableOut]
    freshness_note: str


class QueryResponse(_Strict):
    request_id: str
    status: Literal["answered", "refused"]
    question: str
    answer_text: str = Field(description="Templated answer, or 'Cannot answer (code): reason'.")
    refusal: RefusalOut | None = None
    result: ResultOut | None = None
    caveats: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    evidence: list[EvidenceOut] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    coverage: CoverageOut | None = Field(
        default=None,
        description="Trusted and non-trusted periods for water or road questions (null "
        "otherwise). Static catalogue metadata, not a freshness guarantee.",
    )


class ErrorBody(_Strict):
    code: str
    message: str
    request_id: str
    fields: list[str] | None = Field(
        default=None, description="Locations of invalid request fields (never their values)."
    )


class ErrorResponse(_Strict):
    error: ErrorBody


class HealthResponse(_Strict):
    status: Literal["ok"]


class ReadinessResponse(_Strict):
    status: Literal["ready", "not_ready"]
    reason: str | None = None
    promoted_datasets: dict[str, int] = Field(
        default_factory=dict, description="Promoted (trusted) datasets per family."
    )
    manifests: int = 0


def from_answer(answer: Any, request_id: str) -> QueryResponse:
    """Map a pipeline ``Answer`` onto the response model without changing any value."""
    answered = answer.status == "answered"
    return QueryResponse(
        request_id=request_id,
        status=answer.status,
        question=answer.question,
        answer_text=answer.text,
        refusal=None
        if answered
        else RefusalOut(code=answer.code, stage=answer.stage, reason=answer.reason),
        result=ResultOut(
            operation=answer.operation,
            value=answer.value,
            value_basis=answer.value_basis,
            unit=answer.unit,
            metric=answer.metric,
            periods=list(answer.periods),
            method=answer.method,
            denominator=answer.denominator,
        )
        if answered
        else None,
        caveats=list(answer.caveats),
        assumptions=list(answer.assumptions),
        evidence=[
            EvidenceOut(**{k: v for k, v in item.items() if k != "source_path"})
            for item in answer.evidence
        ],
        trace=list(answer.trace),
        coverage=CoverageOut(**answer.coverage) if answer.coverage else None,
    )


__all__ = [
    "MAX_QUESTION_CHARS",
    "ErrorBody",
    "CoverageOut",
    "ErrorResponse",
    "EvidenceOut",
    "HealthResponse",
    "QueryRequest",
    "QueryResponse",
    "ReadinessResponse",
    "RefusalOut",
    "ResultOut",
    "from_answer",
]
