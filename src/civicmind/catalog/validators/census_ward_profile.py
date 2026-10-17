"""Validator for the Smart Cities "Demographic Profile: Bengaluru as on 01-03-2011" ward table.

Written against the real batch-01 schema (``census_ward_profile/v1``). It reports what makes
the file unusable as a ward reference and changes nothing:

* ward names reused under several ward numbers (the 67-name cycle) is an **error**;
* population columns labelled "in thousands" whose values look like persons is a warning;
* columns that are entirely ``NA`` or empty are a warning;
* male + female differing from the total is a warning.
"""

from __future__ import annotations

import pandas as pd

from civicmind.catalog.identifiers import names_shared_by_multiple_ids
from civicmind.catalog.validators.base import Finding, to_number

WARD_ID = "Ward No."
WARD_NAME = "Ward Name"
TOTAL = "Total Population (in thousands)"
MALE = "Population - Male (in thousands)"
FEMALE = "Population - female (in thousands)"
#: A ward of more than 10,000 thousand (10 million) people is implausible.
THOUSANDS_CEILING = 10_000


def validate(frame: pd.DataFrame, raw_header: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    ward = to_number(frame[WARD_ID])
    bad = int((ward.isna() | (ward % 1 != 0)).sum())
    if bad:
        findings.append(
            Finding("ward.non_integer", "error", f"{bad} missing or non-integer ward numbers")
        )
    dup = ward[ward.duplicated(keep=False) & ward.notna()].astype(int).unique().tolist()
    if dup:
        findings.append(
            Finding("ward.duplicated", "warning", "Repeated ward numbers", {"wards": dup})
        )
    reused = names_shared_by_multiple_ids(frame, WARD_ID, WARD_NAME)
    if reused:
        findings.append(
            Finding(
                "ward_name.reused",
                "error",
                f"{len(reused)} ward names appear under more than one ward number",
                {
                    "distinct_names": int(frame[WARD_NAME].nunique()),
                    "examples": dict(list(reused.items())[:5]),
                },
            )
        )
    for col in frame.columns[4:]:
        text = frame[col].fillna("").str.strip()
        if text.isin(["", "NA"]).all():
            findings.append(
                Finding("column.all_missing", "warning", f"Column has no values: {col!r}")
            )
            continue
        values = to_number(frame[col])
        if (values < 0).any():
            findings.append(Finding("cells.negative", "error", f"Negative values in {col!r}"))
    total = to_number(frame[TOTAL])
    if total.max() > THOUSANDS_CEILING:
        findings.append(
            Finding(
                "unit.label_implausible",
                "warning",
                "Values labelled 'in thousands' look like persons",
                {"column": TOTAL, "min": float(total.min()), "max": float(total.max())},
            )
        )
    gap = (to_number(frame[MALE]) + to_number(frame[FEMALE]) - total).abs()
    off = int((gap > 1).sum())
    if off:
        findings.append(
            Finding("population.sex_sum", "warning", f"{off} wards where male + female != total")
        )
    return findings


__all__ = ["validate"]
