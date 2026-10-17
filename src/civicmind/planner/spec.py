"""Typed query specification and planner refusals.

A ``QuerySpec`` is the only thing the orchestrator executes: an allowlisted ``intent``, the
periods it needs, and keyword parameters for exactly one analytics function. It never holds
free text that is later interpreted (the original question is kept only for the record).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Intent = Literal[
    "water_total",
    "water_rank_rows",
    "water_rank_wards",
    "water_month_change",
    "road_city_value",
    "road_top_cities",
    "dataset_family",  # a question about a family with no trusted data (waste, census)
]
INTENTS: tuple[str, ...] = Intent.__args__  # type: ignore[attr-defined]

Stage = Literal["planner", "feasibility", "ingest", "analytics", "evidence"]

#: Stable planner and feasibility refusal codes. Add deliberately; never rename.
PLANNER_CODES = frozenset(
    {
        "query.empty",
        "query.too_long",
        "query.prompt_injection",
        "query.causal",
        "query.predictive",
        "query.out_of_scope",
        "query.cross_domain",
        "query.unsupported_operation",
        "query.unit_unsupported",
        "query.metric_missing",
        "query.metric_ambiguous",
        "query.period_missing",
        "query.period_ambiguous",
        "query.entity_missing",
        "query.entity_ambiguous",
        "query.unrecognised_terms",
        "query.cross_edition",
    }
)
FEASIBILITY_CODES = frozenset(
    {
        "period.unavailable",
        "status.quarantined",
        "status.rejected",
        "dataset.not_trusted",
        "modelled.not_trusted",
    }
)


@dataclass(frozen=True)
class QuerySpec:
    intent: str
    domain: str  # water | roads | waste | census
    periods: tuple[str, ...]  # water: "YYYY-MM"; roads: "YYYY"; in the order asked
    params: dict[str, Any] = field(default_factory=dict)  # keyword args for the analytics call
    reference_periods: tuple[str, ...] = ()  # water intensity flags only
    assumptions: tuple[str, ...] = ()  # every default the parser applied, stated
    question: str = ""

    def __post_init__(self) -> None:
        if self.intent not in INTENTS:
            raise ValueError(f"intent {self.intent!r} is not allowlisted")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlanRefusal:
    code: str
    reason: str
    stage: Stage = "planner"
    details: Any = None

    def __post_init__(self) -> None:
        if self.code not in PLANNER_CODES | FEASIBILITY_CODES:
            raise ValueError(f"undeclared planner code {self.code!r}")


__all__ = [
    "FEASIBILITY_CODES",
    "INTENTS",
    "PLANNER_CODES",
    "PlanRefusal",
    "QuerySpec",
]
