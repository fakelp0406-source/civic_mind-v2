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


class CitationOut(_Strict):
    """One verbatim passage from an approved document (stage 2F). Never a CivicMind value."""

    n: int = Field(description="Citation number used in answer_text, e.g. [1].")
    document_id: str
    title: str
    edition: str | None
    issuing_authority: str
    source_class: str = Field(description="official | secondary_mirror | ... (provenance class)")
    resource_page: str
    download_url: str | None
    publication_date: str | None = Field(description="null when the date is unverified.")
    page: int = Field(description="1-based PDF page; excluded and textless pages never appear.")
    chunk_id: str
    chunk_sha256: str
    document_sha256: str
    extraction_sha256: str
    score: float = Field(description="BM25 relevance score (topical relevance, not truth).")
    quote: str = Field(description="Verbatim excerpt of the indexed page text.")


class RoutePartOut(_Strict):
    """One clause of a combined question, routed on its own."""

    kind: Literal["analytics", "documents", "refused"]
    status: Literal["answered", "refused"]
    question: str
    answer_text: str
    code: str | None = Field(description="This part's refusal code (null when answered).")
    result: ResultOut | None = None
    evidence: list[EvidenceOut] = Field(default_factory=list)
    citations: list[CitationOut] = Field(default_factory=list)


class RouteOut(_Strict):
    """How the router handled a question the deterministic pipeline refused (stage 2F).

    ``refusal.code`` always stays the deterministic pipeline's code; ``code`` here is the
    router's own outcome (``rag.*`` / ``route.*``), e.g. why documents could not answer either.
    """

    kind: Literal["documents", "mixed", "refused"]
    code: str | None = Field(description="Router outcome code; null when answered.")
    reason: str | None = None
    gate: Literal["bm25"] = "bm25"
    index_id: str | None = Field(description="Verified index the evidence came from.")
    editions: list[str] = Field(
        default_factory=list, description="Editions retrieval was restricted to."
    )
    parts: list[RoutePartOut] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)


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
    route: RouteOut | None = Field(
        default=None,
        description="Present only when the question went past the deterministic pipeline "
        "(document retrieval or a combined question). Absent responses are exactly the "
        "deterministic pipeline's.",
    )
    citations: list[CitationOut] | None = Field(
        default=None,
        description="Document passages behind a document or mixed answer (present with route).",
    )


#: Fields added in stage 2F; omitted from a response when the router added nothing.
ROUTE_FIELDS = frozenset({"route", "citations"})


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


class RetrievalReadiness(_Strict):
    """Document retrieval state. Its failure never makes the structured-data API not ready;
    document questions then refuse with ``route.code`` set to ``code``."""

    status: Literal["ready", "unavailable", "disabled"]
    code: str | None = Field(
        default=None,
        description="rag.index_unavailable | rag.index_stale | rag.corpus_integrity (or null).",
    )
    gate: Literal["bm25"] = "bm25"
    index_id: str | None = None
    documents: list[str] = Field(default_factory=list, description="Approved, indexed ids.")
    chunks: int = 0


class ReadinessResponse(_Strict):
    status: Literal["ready", "not_ready"]
    reason: str | None = None
    promoted_datasets: dict[str, int] = Field(
        default_factory=dict, description="Promoted (trusted) datasets per family."
    )
    manifests: int = 0
    retrieval: RetrievalReadiness | None = None


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
    "ROUTE_FIELDS",
    "CitationOut",
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
    "RetrievalReadiness",
    "RouteOut",
    "RoutePartOut",
    "from_answer",
]
