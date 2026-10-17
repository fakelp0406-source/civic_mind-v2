"""Validator for "Solid Waste Generated, Collected, Processed Data Bengaluru 2015-16 to 2017-18".

Written against the real batch-01 schema (``swm_gcp/v1``). It detects the signature of
modelled values (one base series scaled by the same factor in every ward) and the internal
inconsistencies recorded in the review. It never corrects or re-derives any value.
"""

from __future__ import annotations

import pandas as pd

from civicmind.catalog.validators.base import Finding, to_number

WARD_ID = "Ward_No."
YEARS = ("2015-16", "2016-17", "2017-18")
#: Relative spread below which a ratio is treated as the same constant in every ward.
CONSTANT_RATIO_TOLERANCE = 1e-4


def _column(frame: pd.DataFrame, kind: str, year: str) -> str:
    return next(c for c in frame.columns if kind in c and c.endswith(year))


def _constant_ratio(num: pd.Series, den: pd.Series) -> float | None:
    mask = den > 0
    if not mask.any():
        return None
    ratio = num[mask] / den[mask]
    centre = float(ratio.median())
    if centre and float((ratio - centre).abs().max()) / abs(centre) < CONSTANT_RATIO_TOLERANCE:
        return round(centre, 6)
    return None


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
    series = {}
    for kind in ("generated", "collected", "processed"):
        for year in YEARS:
            col = _column(frame, kind, year)
            values = to_number(frame[col])
            if values.isna().any():
                findings.append(
                    Finding("cells.non_numeric", "error", f"Non-numeric cells in {col!r}")
                )
            if (values < 0).any():
                findings.append(Finding("cells.negative", "error", f"Negative values in {col!r}"))
            series[kind, year] = values
    constant = {}
    for a, b in (
        (("generated", "2016-17"), ("generated", "2015-16")),
        (("collected", "2017-18"), ("collected", "2016-17")),
        (("processed", "2015-16"), ("generated", "2015-16")),
        (("processed", "2016-17"), ("generated", "2016-17")),
        (("processed", "2017-18"), ("collected", "2017-18")),
    ):
        ratio = _constant_ratio(series[a], series[b])
        if ratio is not None:
            constant[f"{a[0]} {a[1]} / {b[0]} {b[1]}"] = ratio
    if constant:
        findings.append(
            Finding(
                "values.modelled_signature",
                "warning",
                f"{len(constant)} ratios are the same constant in every ward (modelled values)",
                {"constant_ratios": constant},
            )
        )
    for year in YEARS:
        gen, col = series["generated", year], series["collected", year]
        over = int((col > gen + 1e-9).sum())
        if over:
            findings.append(
                Finding(
                    "collected.exceeds_generated",
                    "warning",
                    f"{year}: collected exceeds generated in {over} wards",
                    {"year": year, "wards": over},
                )
            )
        if ((col - gen).abs() <= 1e-9).all():
            findings.append(
                Finding(
                    "collected.equals_generated",
                    "warning",
                    f"{year}: collected equals generated in every ward",
                    {"year": year},
                )
            )
    return findings


__all__ = ["validate"]
