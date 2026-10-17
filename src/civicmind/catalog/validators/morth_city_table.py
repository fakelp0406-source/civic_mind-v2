"""Validator for MoRTH "Road Accidents in India" million-plus city tables (e.g. Annexure 47).

Checks the published ``Total`` row against the sum of the city rows for every count column,
reports negatives and non-numeric cells, casualties recorded against a category with zero
accidents, and lists the cities. Rank columns and serial numbers are excluded from the total
check. Nothing is corrected; every finding is reported for a person to review.
"""

from __future__ import annotations

import re

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
    findings.extend(_injury_identity(frame, label))
    findings.extend(_zero_accident_casualties(body, label))
    return findings


_INJURED = re.compile(r"^(?P<cat>.+?)\s*-\s*Persons Injured\s*-\s*(?P<part>.+?)\s*$")


def _injury_identity(frame: pd.DataFrame, label: str) -> list[Finding]:
    """Grievous + minor injured must equal total injured, per category and row.

    Only reported when violated (a published inconsistency, kept as-is). Column spellings
    differ by edition ("Greviously"/"Grievously"), so parts are matched per header.
    """
    groups: dict[str, dict[str, str]] = {}
    for col in frame.columns:
        m = _INJURED.match(col)
        if m:
            part = m.group("part").lower()
            key = "grievous" if part.startswith(("grev", "griev")) else part
            groups.setdefault(m.group("cat").strip(), {})[key] = col
    bad = []
    for cat, cols in groups.items():
        if not {"grievous", "minor injury", "total injured"} <= set(cols):
            continue
        g, mi, t = (
            to_number(frame[cols[k]]) for k in ("grievous", "minor injury", "total injured")
        )
        off = (g + mi - t).abs() > 1e-9
        for name in frame.loc[off, label].str.strip():
            bad.append({"category": cat, "row": name})
    if not bad:
        return []
    return [
        Finding(
            "injured.sum_mismatch",
            "warning",
            f"{len(bad)} rows where grievous + minor injured != total injured (published as-is)",
            {"rows": bad[:20]},
        )
    ]


_ACCIDENTS = re.compile(
    r"^(?P<cat>.+?)\s*-\s*(?:Total )?Number of Accidents(?:\s*-\s*Number)?\s*$"
)


def _zero_accident_casualties(body: pd.DataFrame, label: str) -> list[Finding]:
    """Persons killed or injured in a category whose accident count is 0, per row.

    A published inconsistency (e.g. Pune, Over-Speeding, 2021 edition). Reported as a
    warning only; no value is changed and the row is kept.
    """
    columns = list(body.columns)
    rows = []
    for col in columns:
        m = _ACCIDENTS.match(col)
        if not m:
            continue
        prefix = m.group("cat").strip()
        killed = [
            c
            for c in columns
            if c.startswith(prefix) and "Persons Killed" in c and "rank" not in c.lower()
        ]
        injured = [c for c in columns if c.startswith(prefix) and c.endswith("Total Injured")]
        accidents = to_number(body[col])
        k = to_number(body[killed[0]]) if killed else None
        i = to_number(body[injured[0]]) if injured else None
        for idx in body.index[accidents == 0]:
            dead = 0.0 if k is None or pd.isna(k[idx]) else float(k[idx])
            hurt = 0.0 if i is None or pd.isna(i[idx]) else float(i[idx])
            if dead > 0 or hurt > 0:
                rows.append(
                    {
                        "row": str(body.at[idx, label]).strip(),
                        "category": prefix,
                        "killed": dead,
                        "injured": hurt,
                    }
                )
    if not rows:
        return []
    return [
        Finding(
            "casualties.zero_accidents",
            "warning",
            f"{len(rows)} rows report persons killed or injured in a category with 0 accidents "
            "(published as-is; not corrected)",
            {"rows": rows},
        )
    ]


def schema_drift(old_header: list[str], new_header: list[str]) -> dict[str, list[str]]:
    """Compare two editions' headers verbatim; no columns are mapped automatically."""
    old, new = set(old_header), set(new_header)
    return {
        "only_in_old": sorted(old - new),
        "only_in_new": sorted(new - old),
        "common": sorted(old & new),
    }


__all__ = ["find_label_column", "schema_drift", "validate"]
