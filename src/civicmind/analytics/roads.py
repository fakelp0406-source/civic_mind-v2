"""A4: MoRTH million-plus city traffic-violation tables (Annexure 47), one edition at a time.

* Columns are named verbatim for the dataset's own schema version. The 2019 and 2024
  editions spell columns differently (e.g. ``Greviously`` / ``Grievously``); nothing is
  mapped between them, so an unknown column is refused with the closest verbatim names.
* Cities are matched by their exact published label (surrounding whitespace ignored). There
  is no alias table yet, so ``Bangalore`` does not find ``Bengaluru``.
* The ``Total`` row is never treated as a city; it is the published denominator for shares.
* Publisher rank columns and the serial-number column are not measures.
"""

from __future__ import annotations

import difflib

import pandas as pd

from civicmind.analytics.result import (
    AnalyticsRefused,
    AnalyticsResult,
    evidence,
    hidden_ties,
    require,
)
from civicmind.catalog.ingest import IngestedDataset
from civicmind.catalog.schemas import get_schema

FAMILY = "morth_city_a47"
CITY_CAVEAT = ("MoRTH city boundaries are not established; never combine with ward-level data.",)


def _measure_column(ds: IngestedDataset, column: str) -> str:
    schema = get_schema(ds.schema_version)
    measures = [c for c in schema.numeric_columns if c not in schema.rank_columns]
    if column not in measures:
        close = difflib.get_close_matches(column, measures, n=3, cutoff=0.6)
        raise AnalyticsRefused(
            "column.unknown",
            f"{column!r} is not a count column of {ds.schema_version}",
            {"closest_verbatim": close},
        )
    return column


def _number(value: float) -> int | float:
    value = float(value)
    return int(value) if value.is_integer() else value


def _split(ds: IngestedDataset):
    label = get_schema(ds.schema_version).label_column
    labels = ds.raw[label].str.strip()
    total = labels == "Total"
    if int(total.sum()) != 1:
        raise AnalyticsRefused("total.row", "expected exactly one Total row")
    repeated = sorted(set(labels[~total][labels[~total].duplicated()]))
    if repeated:
        raise AnalyticsRefused("city.ambiguous", "city labels repeat in this table", repeated)
    return label, labels, total


def road_city_value(ds: IngestedDataset, city: str, column: str) -> AnalyticsResult:
    """A4a. One city's published count and its share of the published Total row."""
    require(ds, FAMILY)
    column = _measure_column(ds, column)
    label, labels, total = _split(ds)
    wanted = city.strip()
    match = (labels == wanted) & ~total
    if int(match.sum()) != 1:
        raise AnalyticsRefused(
            "city.not_found",
            f"no row labelled exactly {wanted!r} in {ds.dataset_id} (no alias table)",
            {"closest": difflib.get_close_matches(wanted, labels[~total].tolist(), n=3)},
        )
    value = ds.values.loc[match, column].iloc[0]
    denominator = ds.values.loc[total, column].iloc[0]
    if pd.isna(value) or pd.isna(denominator):
        raise AnalyticsRefused("values.missing", f"{column!r} is not numeric for {wanted!r}/Total")
    share = round(float(value) / float(denominator) * 100, 4) if denominator > 0 else None
    return AnalyticsResult(
        operation="road_city_value",
        value={"value": _number(value), "share_of_total_pct": share},
        unit="count",
        method="published cell; share = city / published Total row x 100",
        evidence=(evidence(ds, [label, column], 2),),
        filters={"city": wanted, "column": column},
        denominator="published Total row (all million-plus cities in this edition)",
        caveats=(
            *CITY_CAVEAT,
            "Share is of the published Total row of this edition (null if that Total is 0).",
            *ds.caveats,
        ),
    )


def road_top_cities(ds: IngestedDataset, column: str, n: int = 10) -> AnalyticsResult:
    """A4b. Top-n cities by a published count (Total excluded; ties share the lowest rank)."""
    require(ds, FAMILY)
    column = _measure_column(ds, column)
    label, labels, total = _split(ds)
    body = ds.values.loc[~total, [column]].assign(city=labels[~total])
    if body[column].isna().any():
        raise AnalyticsRefused("values.missing", f"{column!r} has non-numeric city cells")
    if not 1 <= n <= len(body):
        raise AnalyticsRefused("n.out_of_range", f"n must be 1..{len(body)}")
    body["rank"] = body[column].rank(method="min", ascending=False).astype(int)
    body = body.sort_values(["rank", "city"], kind="mergesort")
    ranked = [
        {"rank": int(r["rank"]), "city": r["city"], "value": _number(r[column])}
        for _, r in body.iterrows()
    ]
    _, tie_caveat = hidden_ties(ranked, n, "city")
    return AnalyticsResult(
        operation="road_top_cities",
        value=ranked[:n],
        unit="count",
        method="rank of the published count, descending; ties share the lowest rank",
        evidence=(evidence(ds, [label, column], len(body)),),
        filters={"column": column, "n": n},
        caveats=(*((tie_caveat,) if tie_caveat else ()), *CITY_CAVEAT, *ds.caveats),
    )


def road_compare_cities(
    ds: IngestedDataset, cities: tuple[str, ...], column: str
) -> AnalyticsResult:
    """A4c. Two cities' published counts in ONE edition, with a derived difference.

    Each value is a published cell, matched by exact label; each share is of the edition's
    published Total row; ``difference`` = first city minus second (derived). Nothing is summed
    across categories and nothing crosses editions.
    """
    require(ds, FAMILY)
    column = _measure_column(ds, column)
    label, labels, total = _split(ds)
    wanted = [c.strip() for c in cities]
    if len(wanted) != 2 or wanted[0] == wanted[1]:
        raise AnalyticsRefused("city.ambiguous", "exactly two different cities are required")
    denominator = ds.values.loc[total, column].iloc[0]
    rows = []
    for city in wanted:
        match = (labels == city) & ~total
        if int(match.sum()) != 1:
            raise AnalyticsRefused(
                "city.not_found",
                f"no row labelled exactly {city!r} in {ds.dataset_id} (no alias table)",
                {"closest": difflib.get_close_matches(city, labels[~total].tolist(), n=3)},
            )
        value = ds.values.loc[match, column].iloc[0]
        if pd.isna(value) or pd.isna(denominator):
            raise AnalyticsRefused(
                "values.missing", f"{column!r} is not numeric for {city!r}/Total"
            )
        share = round(float(value) / float(denominator) * 100, 4) if denominator > 0 else None
        rows.append({"city": city, "value": _number(value), "share_of_total_pct": share})
    difference = _number(float(rows[0]["value"]) - float(rows[1]["value"]))
    return AnalyticsResult(
        operation="road_compare_cities",
        value={"cities": rows, "difference": difference},
        unit="count",
        method=(
            "published cells of one edition; difference = first city minus second (derived); "
            "shares = city / published Total row x 100"
        ),
        evidence=(evidence(ds, [label, column], 3),),
        filters={"cities": wanted, "column": column},
        denominator="published Total row (all million-plus cities in this edition)",
        caveats=(
            *CITY_CAVEAT,
            "Both values come from the same edition and column; no other edition is used.",
            "Shares are of the published Total row of this edition (null if that Total is 0).",
            *ds.caveats,
        ),
    )


__all__ = ["road_city_value", "road_compare_cities", "road_top_cities"]
