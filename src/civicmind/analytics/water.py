"""A1-A3: BWSSB monthly ward water consumption (``bwssb_monthly/v1``), one month per dataset.

Rules shared by every operation here:

* Rows are used exactly as published. Repeated ward numbers (e.g. 14, 85, 153, 191) are
  neither merged nor dropped; totals include every row and say so.
* ``Consumption in ML`` is megalitres recorded in the month; ``Number of Connections`` is a
  count. The derived intensity is litres per connection per day:
  ``ML x 1,000,000 / connections / days in the period`` (period from the manifest).
* Rankings are of **published rows**. A claim about unique wards needs unique ward numbers:
  ``water_rank_wards`` refuses (``ward.identifiers_not_unique``) when any number repeats.
* Months are compared only as city totals. Rows are never matched across files to combine
  values (no identifier authority is recorded, so that would be a join).
* One narrow, explicit exception (T10, approved 2026-10-17, ``water_intensity_flags@v1``):
  ``water_rank_rows`` may look up the *same published row* in other trusted months of this
  series, by the exact (ward number, published name) pair, **only** to attach descriptive
  flags to intensity rankings. Reference values are shown next to the row but never added,
  averaged or used to rank, and no row is excluded. This does not authorise any other
  cross-dataset matching: every dataset keeps its ``no_cross_dataset_join`` restriction, and
  no other function performs this lookup.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import pandas as pd

from civicmind.analytics.result import (
    AnalyticsRefused,
    AnalyticsResult,
    evidence,
    hidden_ties,
    require,
)
from civicmind.catalog.ingest import IngestedDataset

FAMILY = "bwssb_monthly"
WARD = "Ward number "
NAME = "Ward Name"
CONNECTIONS = "Number of Connections"
ML = "Consumption in ML"

Measure = Literal["connections", "consumption_ml"]
RankMeasure = Literal["connections", "consumption_ml", "litres_per_connection_per_day"]
MEASURES = {"connections": (CONNECTIONS, "connections"), "consumption_ml": (ML, "ML")}
RANK_MEASURES = (*MEASURES, "litres_per_connection_per_day")
DUPLICATE_NOTE = "Totals include every published row; repeated ward numbers are not merged."
#: T10 flag policy (approved 2026-10-17): flags annotate, they never exclude or re-rank.
FLAG_POLICY = "water_intensity_flags@v1"
VOLATILITY_RATIO = 2.0  # >= 2x or <= 0.5x the same row's intensity in a reference month
MIN_CONNECTIONS = 100  # provisional operational threshold, not a statistical standard
FLAG_DEFINITIONS = {
    "small_connection_base": (
        f"Fewer than {MIN_CONNECTIONS} connections on the row. A provisional operational "
        "threshold chosen for this project on 2026-10-17, not a universal statistical standard: "
        "intensity on a small base can swing on very little consumption."
    ),
    "volatile_vs_reference": (
        f"Descriptive only: the row's intensity is >= {VOLATILITY_RATIO:g}x or <= "
        f"{1 / VOLATILITY_RATIO:g}x the same row's intensity in a reference month (zero "
        "consumption against positive consumption also counts). It describes a difference "
        "between two months; it is not evidence of an anomaly, a data error or a cause."
    ),
    "not_comparable": (
        "Volatility could NOT be assessed against a reference month (no row with exactly this "
        "ward number and name, more than one, or 0 connections there so intensity is "
        "undefined). This is not a pass."
    ),
}
#: Per-row result of the volatility check, always present on intensity rankings.
VOLATILITY_STATUSES = ("volatile", "not_comparable", "within_threshold", "not_assessed")
#: Ranked values are rounded to this many decimals BEFORE ranking, so ties are decided on the
#: same numbers that are reported.
DECIMALS = 6


def _days(ds: IngestedDataset) -> int:
    start, end = ds.period.get("start"), ds.period.get("end")
    if not start or not end:
        raise AnalyticsRefused("period.missing", f"{ds.dataset_id} has no start/end period")
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    if days <= 0:
        raise AnalyticsRefused("period.invalid", f"{ds.dataset_id}: end is before start")
    return days


def _measure(measure: str) -> tuple[str, str]:
    if measure not in MEASURES:
        raise AnalyticsRefused("measure.unknown", f"unknown measure {measure!r}", list(MEASURES))
    return MEASURES[measure]


def _number(value: float) -> int | float:
    value = round(float(value), DECIMALS)
    return int(value) if value.is_integer() else value


def duplicated_ward_numbers(ds: IngestedDataset) -> dict[int, list[str]]:
    """Ward numbers on more than one published row, with every name as published."""
    ward = ds.values[WARD]
    names = ds.raw[NAME].str.strip()
    mask = ward.duplicated(keep=False) & ward.notna()
    out: dict[int, list[str]] = {}
    for w, n in zip(ward[mask].astype(int), names[mask], strict=True):
        out.setdefault(int(w), []).append(n)
    return dict(sorted(out.items()))


def _require_numeric(ds: IngestedDataset, *columns: str) -> None:
    for column in columns:
        if ds.values[column].isna().any():
            raise AnalyticsRefused("values.missing", f"{column!r} has non-numeric cells")


def water_total(ds: IngestedDataset, measure: Measure) -> AnalyticsResult:
    """A1. City total of one measure for one month (all published rows)."""
    require(ds, FAMILY)
    column, unit = _measure(measure)
    _require_numeric(ds, column)
    values = ds.values[column]
    dup = duplicated_ward_numbers(ds)
    caveats = [DUPLICATE_NOTE]
    if dup:
        caveats.append(
            f"{len(dup)} ward numbers appear on more than one row ({sorted(dup)}); "
            "their rows are all included."
        )
    return AnalyticsResult(
        operation="water_total",
        value=_number(values.sum()),
        unit=unit,
        method=f"sum of {column!r} over all {len(values)} published rows (no deduplication)",
        evidence=(evidence(ds, [column], len(values)),),
        filters={"measure": measure},
        caveats=(*caveats, *ds.caveats),
    )


def _rank(
    ds: IngestedDataset, measure: str, n: int, order: str
) -> tuple[list[dict], str, str | None, list[str], list[str], int]:
    if measure not in RANK_MEASURES:
        raise AnalyticsRefused("measure.unknown", f"unknown measure {measure!r}", RANK_MEASURES)
    if order not in ("desc", "asc"):
        raise AnalyticsRefused("order.unknown", f"order must be 'desc' or 'asc', not {order!r}")
    if not 1 <= n <= len(ds.values):
        raise AnalyticsRefused("n.out_of_range", f"n must be 1..{len(ds.values)}")
    _require_numeric(ds, WARD, CONNECTIONS, ML)
    frame = pd.DataFrame(
        {
            "source_record": range(2, len(ds.values) + 2),  # header is record 1
            "ward_number": ds.values[WARD].astype(int),
            "ward_name": ds.raw[NAME].str.strip(),
            "connections": ds.values[CONNECTIONS],
            "consumption_ml": ds.values[ML],
        }
    )
    excluded: list[str] = []
    denominator = None
    if measure == "litres_per_connection_per_day":
        days = _days(ds)
        zero = frame["connections"] <= 0
        excluded = [
            f"record {r} (ward {w} {name})"
            for r, w, name in frame.loc[zero, ["source_record", "ward_number", "ward_name"]].values
        ]
        frame = frame[~zero].copy()
        frame["value"] = frame["consumption_ml"] * 1_000_000 / frame["connections"] / days
        unit = "litres per connection per day"
        denominator = f"connections on the same row x {days} days in the period"
        columns = [WARD, NAME, CONNECTIONS, ML]
    else:
        column, unit = _measure(measure)
        frame["value"] = frame[measure]
        columns = [WARD, NAME, column]
    frame["value"] = frame["value"].round(DECIMALS)
    frame["rank"] = frame["value"].rank(method="min", ascending=(order == "asc")).astype(int)
    frame = frame.sort_values(["rank", "ward_number", "source_record"], kind="mergesort")
    dup = duplicated_ward_numbers(ds)
    rows = [
        {
            "rank": int(r.rank),
            "source_record": int(r.source_record),
            "ward_number": int(r.ward_number),
            "ward_name": r.ward_name,
            "value": _number(r.value),
            "ward_number_repeated": int(r.ward_number) in dup,
        }
        for r in frame.head(n).itertuples()
    ]
    return rows, unit, denominator, columns, excluded, len(frame)


NO_UNIQUE_MATCH = "no row with exactly this ward number and name, or more than one"
ZERO_CONNECTIONS = "0 connections in the reference month (intensity undefined)"


def _row_intensities(ds: IngestedDataset) -> dict[tuple[int, str], int | float | str]:
    """Intensity per exact (ward number, published name), or the reason it is unusable.

    Zero *consumption* with connections gives intensity 0, which is comparable. Zero
    *connections* gives no intensity at all, which is not comparable.
    """
    days = _days(ds)
    keys = list(zip(ds.values[WARD].astype(int), ds.raw[NAME].str.strip(), strict=True))
    counts: dict[tuple[int, str], int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    out: dict[tuple[int, str], int | float | str] = {}
    for key, conn, ml in zip(keys, ds.values[CONNECTIONS], ds.values[ML], strict=True):
        if counts[key] != 1:
            out[key] = NO_UNIQUE_MATCH
        elif conn <= 0:
            out[key] = ZERO_CONNECTIONS
        else:
            out[key] = _number(float(ml) * 1_000_000 / float(conn) / days)
    return out


def _compare(value: float, reference: float) -> str:
    """'volatile' or 'within_threshold' for two defined intensities (either may be 0)."""
    low, high = sorted((value, reference))
    if low == 0:
        return "volatile" if high > 0 else "within_threshold"  # 0 vs 0 is no change
    return "volatile" if high / low >= VOLATILITY_RATIO else "within_threshold"


def _check_references(ds: IngestedDataset, references: tuple[IngestedDataset, ...]) -> None:
    seen = {ds.dataset_id}
    for ref in references:
        require(ref, FAMILY)
        if ref.schema_version != ds.schema_version:
            raise AnalyticsRefused("schema.different_versions", "reference uses another schema")
        if ref.dataset_id in seen:
            raise AnalyticsRefused("period.same", f"{ref.dataset_id} given twice or as itself")
        seen.add(ref.dataset_id)
        _days(ref)


def _annotate(row: dict, connections: float, ref_maps: dict[str, dict]) -> None:
    """Attach T10 fields to one ranked row (in place). Never changes rank or value."""
    key = (row["ward_number"], row["ward_name"])
    values, statuses, notes = {}, {}, {}
    for rid, intensities in ref_maps.items():
        found = intensities.get(key, NO_UNIQUE_MATCH)
        if isinstance(found, str):
            values[rid], statuses[rid], notes[rid] = None, "not_comparable", found
        else:
            values[rid], statuses[rid] = found, _compare(row["value"], found)
    if not statuses:
        overall = "not_assessed"
    elif "volatile" in statuses.values():
        overall = "volatile"
    elif "not_comparable" in statuses.values():
        overall = "not_comparable"
    else:
        overall = "within_threshold"
    flags = []
    if connections < MIN_CONNECTIONS:
        flags.append("small_connection_base")
    if "volatile" in statuses.values():
        flags.append("volatile_vs_reference")
    if "not_comparable" in statuses.values():
        flags.append("not_comparable")
    row.update(
        connections=_number(connections),
        reference_values=values,
        reference_status=statuses,
        reference_notes=notes,
        volatility_status=overall,
        flags=flags,
    )


def _flag_counts(rows: list[dict]) -> dict[str, int]:
    counts = dict.fromkeys(VOLATILITY_STATUSES, 0)
    for row in rows:
        counts[row["volatility_status"]] += 1
    counts["small_connection_base"] = sum("small_connection_base" in r["flags"] for r in rows)
    return counts


def water_rank_rows(
    ds: IngestedDataset,
    measure: RankMeasure,
    n: int = 10,
    order: Literal["desc", "asc"] = "desc",
    references: tuple[IngestedDataset, ...] = (),
) -> AnalyticsResult:
    """A2. Top-n **published rows** by a measure. Not a ranking of unique wards.

    Ties share the lowest rank ("min" method, on values rounded to 6 decimals); display order
    breaks ties by ward number, then source record. Rows whose intensity cannot be computed
    (0 connections) are excluded and listed in the caveats. The value states the ranked unit
    and lists every repeated ward number in the file, whether or not it is in the top n.

    For ``litres_per_connection_per_day`` every ranked row carries ``water_intensity_flags@v1``
    fields (see ``FLAG_DEFINITIONS``): ``volatility_status`` (one of ``VOLATILITY_STATUSES``;
    ``not_assessed`` without references), per-reference ``reference_status`` /
    ``reference_values`` / ``reference_notes``, and ``flags``. ``flag_summary`` counts every
    status over all ranked rows and over the returned rows, so ``not_comparable`` rows can
    never be read as passes. Flags never change ranks or exclude rows.
    """
    require(ds, FAMILY, "ward_ranking")
    references = tuple(references)
    if references and measure != "litres_per_connection_per_day":
        raise AnalyticsRefused(
            "measure.unknown", "reference months are only used for intensity flags", measure
        )
    _check_references(ds, references)
    _rank(ds, measure, n, order)  # validates the arguments before the full ranking
    all_rows, unit, denominator, columns, excluded, used = _rank(
        ds, measure, len(ds.values), order
    )
    rows = all_rows[:n]
    dup = duplicated_ward_numbers(ds)
    flag_policy = None
    if measure == "litres_per_connection_per_day":
        ref_maps = {ref.dataset_id: _row_intensities(ref) for ref in references}
        connections = dict(zip(range(2, len(ds.values) + 2), ds.values[CONNECTIONS], strict=True))
        for row in all_rows:
            _annotate(row, float(connections[row["source_record"]]), ref_maps)
        flag_policy = {
            "id": FLAG_POLICY,
            "volatility_ratio": VOLATILITY_RATIO,
            "min_connections": MIN_CONNECTIONS,
            "min_connections_basis": "provisional operational threshold, not a statistical rule",
            "match_key": "exact (ward number, published ward name)",
            "references": [ref.dataset_id for ref in references],
            "definitions": dict(FLAG_DEFINITIONS),
            "scope": (
                "Narrow exception for these flags only; no values are combined across months "
                "and no other cross-dataset matching is authorised."
            ),
        }
    caveats = [
        "PUBLISHED ROWS, NOT UNIQUE WARDS: each row is ranked separately"
        + (
            f"; ward numbers {sorted(dup)} appear on more than one row and are not merged."
            if dup
            else "."
        )
    ]
    if excluded:
        caveats.append(f"Excluded (0 connections, intensity undefined): {'; '.join(excluded)}")
    tie_count, tie_caveat = hidden_ties(all_rows, n, "ward_name")
    if tie_caveat:
        caveats.insert(0, tie_caveat)
    value = {
        "ranked_unit": "published_row",
        "duplicated_ward_numbers": {str(k): v for k, v in dup.items()},
        "rows": rows,
        "ties_beyond_cutoff": tie_count,
    }
    ref_evidence = ()
    if flag_policy is not None:
        value["flag_policy"] = flag_policy
        totals = _flag_counts(all_rows)
        value["flag_summary"] = {"all_ranked_rows": totals, "returned_rows": _flag_counts(rows)}
        if references:
            months = len(references) + 1
            assessed = (
                f"Volatility compares {months} months ({ds.dataset_id} with "
                f"{', '.join(r.dataset_id for r in references)}): of {len(all_rows)} ranked rows, "
                f"{totals['volatile']} volatile, {totals['not_comparable']} NOT COMPARABLE "
                f"(not assessed, not passed), {totals['within_threshold']} within threshold. "
                "volatile_vs_reference is a descriptive difference between these months only, "
                "not evidence of an anomaly, an error or a cause. Rows are matched by exact ward "
                "number and name and never combined with this month's values."
            )
        else:
            assessed = "Volatility not assessed: no reference month given."
        caveats.append(
            f"{FLAG_POLICY}: flags annotate only; no row is excluded and ranks are unchanged. "
            f"{assessed} {totals['small_connection_base']} rows have fewer than "
            f"{MIN_CONNECTIONS} connections (a provisional operational threshold)."
        )
        ref_evidence = tuple(
            evidence(ref, [WARD, NAME, CONNECTIONS, ML], len(ref.values)) for ref in references
        )
    return AnalyticsResult(
        operation="water_rank_rows",
        value=value,
        unit=unit,
        method=(
            f"rank of {measure} ({order}) over {used} published rows; values rounded to "
            f"{DECIMALS} decimals; ties share the lowest rank"
        ),
        evidence=(evidence(ds, columns, used), *ref_evidence),
        filters={
            "measure": measure,
            "n": n,
            "order": order,
            "references": [ref.dataset_id for ref in references],
        },
        denominator=denominator,
        caveats=(*caveats, *ds.caveats),
    )


def water_rank_wards(
    ds: IngestedDataset,
    measure: RankMeasure,
    n: int = 10,
    order: Literal["desc", "asc"] = "desc",
) -> AnalyticsResult:
    """A2 (ward claim). Top-n **unique wards**; refuses if any ward number repeats.

    There is no approved rule for combining repeated ward numbers (sum? the first row? a
    typo?), so a unique-ward ranking is answered only when every ward number occurs once.
    """
    require(ds, FAMILY, "ward_ranking")
    dup = duplicated_ward_numbers(ds)
    if dup:
        raise AnalyticsRefused(
            "ward.identifiers_not_unique",
            f"{len(dup)} ward numbers repeat in {ds.dataset_id}; a unique-ward ranking would "
            "require merging or dropping rows (use water_rank_rows for published rows)",
            {str(k): v for k, v in dup.items()},
        )
    _rank(ds, measure, n, order)  # validates the arguments before the full ranking
    all_rows, unit, denominator, columns, excluded, used = _rank(
        ds, measure, len(ds.values), order
    )
    rows = all_rows[:n]
    caveats = ["Every ward number occurs exactly once in this file."]
    if excluded:
        caveats.append(f"Excluded (0 connections, intensity undefined): {'; '.join(excluded)}")
    tie_count, tie_caveat = hidden_ties(all_rows, n, "ward_name")
    if tie_caveat:
        caveats.insert(0, tie_caveat)
    return AnalyticsResult(
        operation="water_rank_wards",
        value={
            "ranked_unit": "ward",
            "duplicated_ward_numbers": {},
            "rows": rows,
            "ties_beyond_cutoff": tie_count,
        },
        unit=unit,
        method=f"rank of {measure} ({order}) over {used} wards; ties share the lowest rank",
        evidence=(evidence(ds, columns, used),),
        filters={"measure": measure, "n": n, "order": order},
        denominator=denominator,
        caveats=(*caveats, *ds.caveats),
    )


def water_month_change(
    earlier: IngestedDataset, later: IngestedDataset, measure: Measure
) -> AnalyticsResult:
    """A3. Change in the city total between two months of the same series (totals only).

    Reports both months' day counts. When they differ, the raw change mixes a calendar
    effect into the result, so a per-day change is also given and the caveat says so.
    """
    for ds in (earlier, later):
        require(ds, FAMILY)
    if earlier.schema_version != later.schema_version:
        raise AnalyticsRefused("schema.different_versions", "months use different schemas")
    if earlier.dataset_id == later.dataset_id:
        raise AnalyticsRefused("period.same", "both inputs are the same dataset")
    d_a, d_b = _days(earlier), _days(later)
    if earlier.period["end"] >= later.period["start"]:
        raise AnalyticsRefused("period.order", "'earlier' must end before 'later' starts")
    a, b = water_total(earlier, measure), water_total(later, measure)
    change = _number(b.value - a.value)
    pct = round(change / a.value * 100, 4) if a.value else None
    value = {
        "earlier": a.value,
        "later": b.value,
        "change": change,
        "pct_change": pct,
        "earlier_days": d_a,
        "later_days": d_b,
    }
    caveats = [
        "City totals only; wards are not matched between months.",
        "Each total includes every published row of its month; row sets may differ.",
    ]
    if measure == "consumption_ml" and d_a != d_b:
        per_day = _number(b.value / d_b - a.value / d_a)
        value["change_per_day"] = per_day
        caveats.append(f"Months differ in length ({d_a} vs {d_b} days); see change_per_day.")
    if measure == "connections":
        caveats.append("Connections are a count at the time of the file, not a monthly flow.")
    return AnalyticsResult(
        operation="water_month_change",
        value=value,
        unit=a.unit,
        method=("later city total minus earlier city total; pct_change = change / earlier x 100"),
        evidence=a.evidence + b.evidence,
        filters={"measure": measure},
        denominator="earlier month's city total",
        caveats=(
            *caveats,
            *(f"[{earlier.dataset_id}] {c}" for c in earlier.caveats),
            *(f"[{later.dataset_id}] {c}" for c in later.caveats),
        ),
    )


__all__ = [
    "duplicated_ward_numbers",
    "water_month_change",
    "water_rank_rows",
    "water_rank_wards",
    "water_total",
]
