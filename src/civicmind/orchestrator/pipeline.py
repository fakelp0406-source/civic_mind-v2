"""End-to-end question pipeline: parse -> feasibility -> ingest -> analytics -> evidence -> answer.

Bounded and read-only:

* **Allowlisted dispatch.** ``DISPATCH`` maps each intent to exactly one tested analytics
  function. There is no fallback or "nearest intent"; question text never reaches a function
  except as the already-parsed keyword values in the plan.
* **Step limit.** At most ``MAX_STEPS`` steps; exceeding it refuses (``pipeline.step_limit``).
* **Fail closed.** Every stage can refuse with a stable code; an unexpected error is reported
  as ``pipeline.internal_error``, never as an answer.
* **Evidence first.** A result is composed only after ``validate_package`` confirms every
  evidence item against the manifests (hash, status, path, period, columns).

Nothing is written except by the caller; no network, no language model.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from civicmind.analytics import roads, water
from civicmind.analytics.result import AnalyticsRefused, AnalyticsResult
from civicmind.catalog.ingest import IngestionRefused, ingest
from civicmind.catalog.manifest import read_manifest
from civicmind.evidence.model import (
    EvidenceItem,
    EvidencePackage,
    Refusal,
    SourceRecord,
    validate_package,
)
from civicmind.planner.catalog_index import load_index
from civicmind.planner.feasibility import Plan, check
from civicmind.planner.parser import parse
from civicmind.planner.spec import PlanRefusal
from civicmind.respond.compose import Answer, compose_answer, compose_refusal

ROOT = Path(__file__).resolve().parents[3]
MAX_STEPS = 10
PIPELINE_CODES = frozenset({"pipeline.step_limit", "pipeline.internal_error"})

DISPATCH: dict[str, Callable[..., AnalyticsResult]] = {
    "water_total": water.water_total,
    "water_rank_rows": water.water_rank_rows,
    "water_rank_wards": water.water_rank_wards,
    "water_month_change": water.water_month_change,
    "road_city_value": roads.road_city_value,
    "road_top_cities": roads.road_top_cities,
}
#: Only this intent may receive reference months (T10 intensity flags).
ACCEPTS_REFERENCES = frozenset({"water_rank_rows"})


class _Stop(Exception):
    def __init__(self, refusal: Refusal):
        self.refusal = refusal


class _Trace:
    def __init__(self, limit: int):
        self.steps: list[str] = []
        self.limit = limit

    def step(self, name: str) -> None:
        if len(self.steps) >= self.limit:
            raise _Stop(
                Refusal("pipeline.step_limit", "pipeline", f"more than {self.limit} steps")
            )
        self.steps.append(name)


def sources(root: Path) -> dict[str, SourceRecord]:
    out = {}
    for path in sorted((root / "data/manifests").glob("*.yaml")):
        m = read_manifest(path)
        out[m.dataset_id] = SourceRecord(
            dataset_id=m.dataset_id,
            sha256=m.integrity.sha256 if m.integrity else "",
            status=m.status,
            source_path=m.promoted_to,
            columns=tuple(c.name for c in m.schema_),
            period_start=m.period.start,
            period_end=m.period.end,
            title=m.title,
        )
    return out


def _reason(exc: Exception, code: str) -> str:
    """The exception message without its '<dataset>: <code>: ' / '<code>: ' prefix."""
    text = str(exc)
    marker = f"{code}: "
    return text.split(marker, 1)[1] if marker in text else text


def _from_plan_refusal(r: PlanRefusal) -> Refusal:
    return Refusal(code=r.code, stage=r.stage, reason=r.reason, details=r.details)


def _package(question: str, plan: Plan, result: AnalyticsResult) -> EvidencePackage:
    primary = len(plan.dataset_ids)
    items = tuple(
        EvidenceItem(
            dataset_id=e.dataset_id,
            role="primary" if i < primary else "reference",
            schema_version=e.schema_version,
            sha256=e.sha256,
            source_path=e.source_path,
            mode=e.mode,
            period_start=e.period.get("start"),
            period_end=e.period.get("end"),
            columns=tuple(e.columns),
            rows_used=e.rows_used,
        )
        for i, e in enumerate(result.evidence)
    )
    return EvidencePackage(
        question=question,
        intent=plan.function,
        operation=result.operation,
        value=result.value,
        unit=result.unit,
        method=result.method,
        denominator=result.denominator,
        caveats=tuple(result.caveats),
        filters=dict(result.filters),
        assumptions=tuple(plan.spec.assumptions),
        items=items,
    )


def _run(question: str, root: Path, trace: _Trace) -> Answer:
    trace.step("parse")
    spec = parse(question)
    if isinstance(spec, PlanRefusal):
        raise _Stop(_from_plan_refusal(spec))
    trace.step("feasibility")
    plan = check(spec, load_index(root))
    if isinstance(plan, PlanRefusal):
        raise _Stop(_from_plan_refusal(plan))
    if plan.function not in DISPATCH:
        raise _Stop(Refusal("query.unsupported_operation", "pipeline", "intent not allowlisted"))
    if plan.reference_ids and plan.function not in ACCEPTS_REFERENCES:
        raise _Stop(
            Refusal(
                "query.unsupported_operation",
                "feasibility",
                "Reference months are only used to flag rankings of published rows.",
            )
        )
    loaded = []
    for dataset_id in (*plan.dataset_ids, *plan.reference_ids):
        trace.step(f"ingest:{dataset_id}")
        manifest = read_manifest(root / "data/manifests" / f"{dataset_id}.yaml")
        try:
            loaded.append(ingest(manifest, root, "trusted"))
        except IngestionRefused as exc:
            raise _Stop(Refusal(exc.code, "ingest", _reason(exc, exc.code), exc.details)) from exc
    datasets = loaded[: len(plan.dataset_ids)]
    references = tuple(loaded[len(plan.dataset_ids) :])
    trace.step(f"analytics:{plan.function}")
    kwargs = dict(plan.kwargs)
    if references:
        kwargs["references"] = references
    try:
        result = DISPATCH[plan.function](*datasets, **kwargs)
    except AnalyticsRefused as exc:
        raise _Stop(Refusal(exc.code, "analytics", _reason(exc, exc.code), exc.details)) from exc
    trace.step("evidence")
    package = _package(question, plan, result)
    report = validate_package(package, sources(root), plan.dataset_ids, plan.reference_ids)
    if not report.ok:
        raise _Stop(
            Refusal("evidence.invalid", "evidence", "; ".join(report.problems), report.problems)
        )
    trace.step("compose")
    return compose_answer(package, report, tuple(trace.steps))


def answer_question(question: str, root: str | Path = ROOT, max_steps: int = MAX_STEPS) -> Answer:
    trace = _Trace(max_steps)
    try:
        return _run(question, Path(root), trace)
    except _Stop as stop:
        return compose_refusal(question, stop.refusal, tuple(trace.steps))
    except Exception as exc:  # noqa: BLE001 - fail closed: an error is never an answer
        # The exception text can contain local paths or data; it is not shown to the user.
        refusal = Refusal(
            "pipeline.internal_error",
            "pipeline",
            f"An unexpected internal error ({type(exc).__name__}) occurred; no answer is given.",
        )
        return compose_refusal(question, refusal, tuple(trace.steps))


__all__ = ["DISPATCH", "MAX_STEPS", "PIPELINE_CODES", "answer_question", "sources"]
