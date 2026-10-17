"""Validator for MoRTH "Road Accidents in India" million-plus city tables (e.g. Annexure 47).

Checks the published ``Total`` row against the sum of the city rows for every count column,
reports negatives and non-numeric cells, and lists the cities. Rank columns and serial
numbers are excluded from the total check. Nothing is corrected.
"""

from __future__ import annotations

import pandas as pd

from civicmind.catalog.validators.base import Finding, to_number

LABEL_HINTS = ("million plus cities", "cities", "states/uts")
SERIAL_HINTS = ("sl. no", "sl.no", "s. no", "s.no")


def find_label_column(columns: list[str]) -> str | None:
    lowered = {c: c.strip().lower() for c in columns}
    for hint in LABEL_HINTS:
        for col, low in lowered.items():
            if low == hint:
                return col
    return None


def _is_serial(name: str) -> bool:
    return name.strip().lower().rstrip(".") in {h.rstrip(".") for h in SERIAL_HINTS}


def validate(frame: pd.DataFrame, raw_header: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    label = find_label_column(list(frame.columns))
    if label is None:
        return [
            Finding(
                "schema.label_column",
                "error",
                "No city/state label column found",
                {"columns": raw_header},
            )
        ]
    labels = frame[label].fillna("").str.strip()
    total_mask = labels.str.lower() == "total"
    if total_mask.sum() != 1:
        findings.append(
            Finding(
                "total.row",
                "error",
                f"Expected exactly one Total row, found {int(total_mask.sum())}",
            )
        )
    body = frame[~total_mask]
    findings.append(
        Finding(
            "entities.count",
            "info",
            f"{len(body)} entity rows (excluding Total)",
            {"label_column": label, "entities": labels[~total_mask].tolist()},
        )
    )
    dup = labels[~total_mask][labels[~total_mask].duplicated()].tolist()
    if dup:
        findings.append(
            Finding("entities.duplicated", "error", "Duplicated entity labels", {"labels": dup})
        )

    mismatches, non_numeric, negatives = [], {}, {}
    for col in frame.columns:
        if col == label or _is_serial(col):
            continue
        values = to_number(body[col])
        bad = body.loc[values.isna(), label].tolist()
        if bad:
            non_numeric[col] = bad
        neg = body.loc[values < 0, label].tolist()
        if neg:
            negatives[col] = neg
        if "rank" in col.lower() or total_mask.sum() != 1:
            continue
        published = to_number(frame.loc[total_mask, col]).iloc[0]
        computed = values.sum()
        if pd.isna(published) or abs(published - computed) > 1e-6:
            mismatches.append(
                {
                    "column": col,
                    "published_total": None if pd.isna(published) else float(published),
                    "sum_of_rows": float(computed),
                }
            )
    if non_numeric:
        findings.append(
            Finding(
                "cells.non_numeric",
                "error",
                "Non-numeric cells in count/rank columns",
                non_numeric,
            )
        )
    if negatives:
        findings.append(
            Finding("cells.negative", "warning", "Negative counts (published as-is)", negatives)
        )
    if mismatches:
        findings.append(
            Finding(
                "total.mismatch",
                "warning",
                f"{len(mismatches)} columns where Total != sum of rows",
                {"columns": mismatches},
            )
        )
    elif total_mask.sum() == 1:
        findings.append(
            Finding(
                "total.consistent",
                "info",
                "Total row equals the sum of entity rows for every count column",
            )
        )
    return findings


def schema_drift(old_header: list[str], new_header: list[str]) -> dict[str, list[str]]:
    """Compare two editions' headers verbatim; no columns are mapped automatically."""
    old, new = set(old_header), set(new_header)
    return {
        "only_in_old": sorted(old - new),
        "only_in_new": sorted(new - old),
        "common": sorted(old & new),
    }


__all__ = ["find_label_column", "schema_drift", "validate"]
