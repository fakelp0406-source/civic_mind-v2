"""Deterministic answer composer. Depends only on ``civicmind.evidence``.

An answer is a fixed template filled from a validated ``EvidencePackage``. The composer never
computes a new number: it only formats values that are already in the package, and a final
check refuses to emit text containing any number not found in the package (value, filters,
periods, dataset ids). Refusals carry the stable code, the stage and the reason.

``value_basis`` says what kind of value an answer gives: ``published`` (cells as published),
``derived`` (computed by a tested formula), ``published_and_derived`` (a published count with a
derived share or difference) or ``catalogue`` (manifest metadata; no data value). ``coverage``
(optional) is the catalogue's description of trusted and non-trusted periods for the question's
domain; it is passed through unchanged and never used to compute anything.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from civicmind.evidence.model import EvidencePackage, Refusal, ValidationReport, package_digest

NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
MEASURE_LABEL = {
    "connections": "Water connections",
    "consumption_ml": "Water consumption",
    "litres_per_connection_per_day": "Water consumption per connection per day",
}


@dataclass(frozen=True)
class Answer:
    status: str  # "answered" | "refused"
    question: str
    text: str
    code: str | None = None
    stage: str | None = None
    reason: str | None = None
    operation: str | None = None
    value: Any = None
    unit: str | None = None
    metric: str | None = None
    periods: tuple[str, ...] = ()
    method: str | None = None
    denominator: str | None = None
    caveats: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    trace: tuple[str, ...] = field(default_factory=tuple)
    value_basis: str | None = None  # published | derived | published_and_derived | catalogue
    coverage: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fmt(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        text = f"{value:,.6f}".rstrip("0").rstrip(".")
        return text if text not in ("", "-") else "0"
    return str(value)


def period_label(start: str | None, end: str | None) -> str:
    if not start:
        return "an unstated period"
    s, e = date.fromisoformat(start), date.fromisoformat(end or start)
    if (s.year, s.month) == (e.year, e.month):
        return s.strftime("%B %Y")
    if s.month == 1 and s.day == 1 and e.month == 12 and e.day == 31 and s.year == e.year:
        return str(s.year)
    return f"{start} to {end}"


def month_label(period_key: str) -> str:
    """'2025-07' -> 'July 2025'; a bare year is returned unchanged."""
    if len(period_key) == 7:
        return date.fromisoformat(f"{period_key}-01").strftime("%B %Y")
    return period_key


def value_basis(package: EvidencePackage) -> str:
    op, measure = package.operation, package.filters.get("measure")
    if op == "data_coverage":
        return "catalogue"
    if op in ("road_city_value", "road_compare_cities"):
        return "published_and_derived"
    if op == "road_top_cities":
        return "published"
    if op in ("water_rank_rows", "water_rank_wards"):
        return "derived" if measure == "litres_per_connection_per_day" else "published"
    return "derived"  # water_total (sum of rows), water_month_change (difference of totals)


def _numbers(obj: Any) -> list[float]:
    out: list[float] = []
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, int | float):
        out.append(float(obj))
    elif isinstance(obj, str):
        out += [float(m.replace(",", "")) for m in NUMBER.findall(obj)]
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out += _numbers(k) + _numbers(v)
    elif isinstance(obj, list | tuple):
        for v in obj:
            out += _numbers(v)
    return out


def check_numbers(text: str, package: EvidencePackage) -> list[str]:
    """Numbers in ``text`` that do not occur in the package (should be empty)."""
    allowed = _numbers(package.value) + _numbers(package.filters)
    for item in package.items:
        allowed += (
            _numbers(item.dataset_id) + _numbers(item.period_start) + _numbers(item.period_end)
        )
        allowed += _numbers(period_label(item.period_start, item.period_end))
    stripped = re.sub(r"sha256 [0-9a-f]+", "", text)
    missing = []
    for token in NUMBER.findall(stripped):
        number = float(token.replace(",", ""))
        if not any(abs(number - a) <= 1e-9 * max(1.0, abs(a)) for a in allowed):
            missing.append(token)
    return missing


def _source_note(package: EvidencePackage) -> str:
    return "; ".join(f"{i.dataset_id}, sha256 {i.sha256[:12]}" for i in package.items)


def _text(p: EvidencePackage) -> str:
    v, f = p.value, p.filters
    primary = [i for i in p.items if i.role == "primary"]
    when = period_label(primary[0].period_start, primary[0].period_end) if primary else ""
    if p.operation == "water_total":
        return (
            f"{MEASURE_LABEL[f['measure']]} recorded by BWSSB in {when}: {fmt(v)} {p.unit} "
            f"(city total of all published rows)."
        )
    if p.operation == "water_month_change":
        later = period_label(primary[1].period_start, primary[1].period_end)
        pct = "n/a" if v["pct_change"] is None else f"{fmt(v['pct_change'])}%"
        return (
            f"{MEASURE_LABEL[f['measure']]}: {fmt(v['earlier'])} {p.unit} in {when} and "
            f"{fmt(v['later'])} {p.unit} in {later}; change {fmt(v['change'])} {p.unit} "
            f"({pct}). City totals only; wards are not matched between months."
        )
    if p.operation in ("water_rank_rows", "water_rank_wards"):
        noun = "published row" if v["ranked_unit"] == "published_row" else "ward"
        unit_word = noun if len(v["rows"]) == 1 else f"{noun}s"
        parts = []
        for r in v["rows"]:
            flags = f" [{', '.join(r['flags'])}]" if r.get("flags") else ""
            parts.append(
                f"#{r['rank']} ward {r['ward_number']} {r['ward_name']}: {fmt(r['value'])}{flags}"
            )
        order = "highest" if f["order"] == "desc" else "lowest"
        return (
            f"{len(v['rows'])} {unit_word} with the {order} "
            f"{MEASURE_LABEL[f['measure']].lower()} ({p.unit}) in {when}: "
            + "; ".join(parts)
            + "."
        )
    if p.operation == "road_city_value":
        share = v["share_of_total_pct"]
        share_text = "" if share is None else f", {fmt(share)}% of the published Total row"
        return f"{f['city']}, {when}, '{f['column']}': {fmt(v['value'])}{share_text}."
    if p.operation == "road_compare_cities":
        (a, b), diff = v["cities"], v["difference"]

        def share(row: dict) -> str:
            pct = row["share_of_total_pct"]
            return "share n/a" if pct is None else f"{fmt(pct)}% of the published Total row"

        return (
            f"{a['city']} and {b['city']}, {when}, '{f['column']}': {fmt(a['value'])} "
            f"({share(a)}) and {fmt(b['value'])} ({share(b)}); difference {fmt(diff)} "
            f"({a['city']} minus {b['city']}, derived)."
        )
    if p.operation == "data_coverage":
        unit = v["period_unit"]
        trusted = [month_label(k) for k in v["trusted_periods"]]
        parts = [
            f"{v['series']}: {v['trusted_count']} trusted {unit}"
            f"{'s' if v['trusted_count'] != 1 else ''}"
            + (f" ({', '.join(trusted)})." if trusted else ".")
        ]
        if v["latest_trusted_period"]:
            published = v["latest_trusted_portal_published"]
            parts.append(
                f"Latest trusted {unit}: {month_label(v['latest_trusted_period'])} "
                f"({v['latest_trusted_dataset']}"
                + (f"; portal published {published}" if published else "")
                + ")."
            )
        if v["not_trusted"]:
            parts.append(
                "Not used for answers: "
                + ", ".join(
                    f"{month_label(n['period'])} ({n['trust'].replace('_', ' ')})"
                    for n in v["not_trusted"]
                )
                + "."
            )
        if v["other_tables"]:
            parts.append(
                "Other tables catalogued but never used for these questions: "
                + ", ".join(
                    f"{o['dataset_id']} ({o['trust'].replace('_', ' ')})"
                    for o in v["other_tables"]
                )  # fmt: skip
                + "."
            )
        return " ".join(parts)
    if p.operation == "road_top_cities":
        parts = [f"#{r['rank']} {r['city']}: {fmt(r['value'])}" for r in v]
        return (
            f"Top {len(v)} million-plus cities by '{f['column']}' in {when}: "
            + "; ".join(parts)
            + "."
        )
    raise ValueError(f"no template for {p.operation!r}")


TIE_PREFIX = "TIES BEYOND CUT-OFF"  # caveat prefix set by analytics rankings


def compose_answer(
    package: EvidencePackage,
    validation: ValidationReport,
    trace: tuple[str, ...] = (),
    coverage: dict[str, Any] | None = None,
) -> Answer:
    """Compose an answer; only for a package that passed ``validate_package`` unchanged."""
    if not validation.ok or validation.package_digest != package_digest(package):
        raise ValueError("evidence package was not validated (or changed after validation)")
    body = _text(package)
    if any(c.startswith(TIE_PREFIX) for c in package.caveats):
        body += " Further items tie at the last rank shown and are not listed (see caveats)."
    source = _source_note(package) or "dataset manifests (catalogue metadata only)"
    text = f"{body} Source: {source}."
    missing = check_numbers(text, package)
    if missing:  # a template bug must never reach a user
        raise ValueError(f"numbers not in evidence: {missing}")
    f = package.filters
    return Answer(
        status="answered",
        question=package.question,
        text=text,
        operation=package.operation,
        value=package.value,
        unit=package.unit,
        metric=f.get("column") or f.get("measure"),
        periods=tuple(
            period_label(i.period_start, i.period_end)
            for i in package.items
            if i.role == "primary"
        ),
        method=package.method,
        denominator=package.denominator,
        caveats=package.caveats,
        assumptions=package.assumptions,
        evidence=tuple(asdict(i) for i in package.items),
        trace=trace,
        value_basis=value_basis(package),
        coverage=coverage,
    )


def compose_refusal(
    question: str,
    refusal: Refusal,
    trace: tuple[str, ...] = (),
    coverage: dict[str, Any] | None = None,
) -> Answer:
    return Answer(
        status="refused",
        question=question,
        text=f"Cannot answer ({refusal.code}): {refusal.reason}",
        code=refusal.code,
        stage=refusal.stage,
        reason=refusal.reason,
        trace=trace,
        coverage=coverage,
    )


__all__ = [
    "Answer",
    "check_numbers",
    "compose_answer",
    "compose_refusal",
    "fmt",
    "month_label",
    "period_label",
    "value_basis",
]
