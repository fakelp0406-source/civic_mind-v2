"""Feasibility: can a ``QuerySpec`` be answered from trusted, available data? -> ``Plan``.

Uses catalogue metadata only (manifest periods, status, review notes, recorded headers and
the registered schema versions). It never reads data values. Ingestion re-checks everything
again before any number is computed (defence in depth).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from civicmind.catalog.schemas import detect_schema
from civicmind.planner.catalog_index import DatasetEntry
from civicmind.planner.spec import PlanRefusal, QuerySpec

ROAD_CATEGORY_PREFIX = {
    "over_speeding": "overspeeding",
    "drunken_driving": "drunkendriving",
    "wrong_side": "drivingonwrongside",
    "red_light": "jumpingredlight",
    "mobile_phone": "useofmobilephone",
    "others": "others",
}
ROAD_METRIC_PARTS = {
    "accidents": ("numberofaccidents",),
    "killed": ("personskilled",),
    "grievous": ("greviouslyinjured", "grievouslyinjured"),  # spelling differs by edition
    "minor": ("minorinjury",),
    "total_injured": ("totalinjured",),
}


@dataclass(frozen=True)
class Plan:
    spec: QuerySpec
    function: str  # an allowlisted intent; the orchestrator maps it to one analytics function
    dataset_ids: tuple[str, ...]
    reference_ids: tuple[str, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _refuse(code: str, reason: str, details=None) -> PlanRefusal:
    return PlanRefusal(code=code, reason=reason, stage="feasibility", details=details)


def _trusted(entry: DatasetEntry) -> PlanRefusal | None:
    note = f" Review note: {entry.review_note}" if entry.review_note else ""
    if entry.status == "quarantined":
        return _refuse(
            "status.quarantined",
            f"{entry.dataset_id} ({entry.title}) is quarantined and cannot be used.{note}",
        )
    if entry.status == "rejected":
        return _refuse("status.rejected", f"{entry.dataset_id} was rejected.{note}")
    if entry.value_nature == "modelled":
        return _refuse(
            "modelled.not_trusted",
            f"{entry.dataset_id} holds modelled estimates, not measurements; no review decision "
            f"permits analytics on it.{note}",
        )
    if entry.status != "promoted" or entry.human_review != "accepted":
        return _refuse(
            "dataset.not_trusted",
            f"{entry.dataset_id} is not promoted with an accepted review (status "
            f"{entry.status!r}).",
        )
    return None


def _resolve(family: str, period: str, index) -> DatasetEntry | PlanRefusal:
    matches = [e for e in index if e.family == family and e.period_key == period]
    if not matches:
        available = sorted(f"{e.period_key} ({e.status})" for e in index if e.family == family)
        return _refuse(
            "period.unavailable",
            f"No {family} dataset covers {period}. Catalogued: {', '.join(available)}.",
            available,
        )
    if len(matches) > 1:  # never pick one silently
        return _refuse(
            "period.unavailable",
            f"More than one {family} dataset claims {period}; none is chosen.",
            [e.dataset_id for e in matches],
        )
    return matches[0]


def _road_column(entry: DatasetEntry, category: str, metric: str) -> str | PlanRefusal:
    schema = detect_schema(entry.columns)
    if schema is None:
        return _refuse("dataset.not_trusted", f"{entry.dataset_id} has no registered schema.")
    measures = [c for c in schema.numeric_columns if c not in schema.rank_columns]
    prefix = ROAD_CATEGORY_PREFIX[category]
    parts = ROAD_METRIC_PARTS[metric]
    found = []
    for column in measures:
        norm = re.sub(r"[^a-z0-9]", "", column.lower())
        if norm.startswith(prefix) and any(p in norm for p in parts):
            found.append(column)
    if len(found) != 1:
        return PlanRefusal(
            code="query.metric_ambiguous",
            reason=f"{category}/{metric} does not identify exactly one column of "
            f"{schema.version}.",
            stage="feasibility",
            details=found,
        )
    return found[0]


def check(spec: QuerySpec, index) -> Plan | PlanRefusal:
    if spec.intent == "dataset_family":
        entries = [e for e in index if e.family == spec.domain]
        if not entries:
            return _refuse("dataset.not_trusted", f"No {spec.domain} dataset is catalogued.")
        for entry in entries:
            refusal = _trusted(entry)
            if refusal:
                return refusal
        return PlanRefusal(
            code="query.unsupported_operation",
            reason=f"No analytics operation exists for {spec.domain} data.",
            stage="feasibility",
        )
    family = spec.domain
    resolved = []
    for period in (*spec.periods, *spec.reference_periods):
        entry = _resolve(family, period, index)
        if isinstance(entry, PlanRefusal):
            return entry
        refusal = _trusted(entry)
        if refusal:
            return refusal
        resolved.append(entry)
    datasets = tuple(e.dataset_id for e in resolved[: len(spec.periods)])
    references = tuple(e.dataset_id for e in resolved[len(spec.periods) :])
    p = spec.params
    if spec.intent in ("water_total", "water_month_change"):
        kwargs = {"measure": p["measure"]}
    elif spec.intent in ("water_rank_rows", "water_rank_wards"):
        kwargs = {"measure": p["measure"], "n": p["n"], "order": p["order"]}
    else:
        column = _road_column(resolved[0], p["category"], p["metric"])
        if isinstance(column, PlanRefusal):
            return column
        if spec.intent == "road_city_value":
            kwargs = {"city": p["city"], "column": column}
        else:
            kwargs = {"column": column, "n": p["n"]}
    return Plan(
        spec=spec,
        function=spec.intent,
        dataset_ids=datasets,
        reference_ids=references,
        kwargs=kwargs,
    )


__all__ = ["Plan", "check"]
