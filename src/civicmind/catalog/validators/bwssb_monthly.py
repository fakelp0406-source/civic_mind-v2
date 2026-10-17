"""Validator for BWSSB monthly ward-wise water consumption files (Karnataka OGD).

Expected columns, verbatim (note the trailing space in the first name):
``"Ward number "``, ``"Ward Name"``, ``"Number of Connections"``, ``"Consumption in ML"``.

The ward scheme behind ``Ward number`` is NOT established by the file; this validator only
checks internal consistency and reports duplicates, it never resolves them.
"""

from __future__ import annotations

import pandas as pd

from civicmind.catalog.validators.base import Finding, to_number

EXPECTED_COLUMNS = ["Ward number ", "Ward Name", "Number of Connections", "Consumption in ML"]


def validate(frame: pd.DataFrame, raw_header: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    if raw_header != EXPECTED_COLUMNS:
        stripped_equal = [h.strip() for h in raw_header] == [c.strip() for c in EXPECTED_COLUMNS]
        findings.append(
            Finding(
                "schema.columns",
                "warning" if stripped_equal else "error",
                "Header differs from the expected BWSSB monthly schema"
                + (" (whitespace only)" if stripped_equal else ""),
                {"expected": EXPECTED_COLUMNS, "found": raw_header},
            )
        )
        if len(raw_header) != len(EXPECTED_COLUMNS):
            return findings
        # Same column count: keep checking positionally so the report shows every problem;
        # the header error above still blocks promotion until a person decides.
    ward_col, name_col, conn_col, ml_col = frame.columns[:4]

    ward = to_number(frame[ward_col])
    bad_ward = frame[ward.isna() | (ward % 1 != 0)]
    if len(bad_ward):
        findings.append(
            Finding(
                "ward.non_integer",
                "error",
                f"{len(bad_ward)} rows have a missing or non-integer ward number",
                {"rows": bad_ward[[ward_col, name_col]].fillna("").values.tolist()[:20]},
            )
        )
    valid = ward.dropna()
    findings.append(
        Finding(
            "ward.range",
            "info",
            "Ward number range and count",
            {
                "min": int(valid.min()) if len(valid) else None,
                "max": int(valid.max()) if len(valid) else None,
                "distinct": int(valid.nunique()),
                "rows": int(len(frame)),
            },
        )
    )
    missing = (
        sorted(set(range(1, int(valid.max()) + 1)) - set(valid.astype(int))) if len(valid) else []
    )
    if missing:
        findings.append(
            Finding(
                "ward.gaps", "warning", "Ward numbers missing from 1..max", {"missing": missing}
            )
        )
    dup_mask = ward.duplicated(keep=False) & ward.notna()
    if dup_mask.any():
        groups = (
            frame[dup_mask]
            .assign(_w=ward[dup_mask].astype(int))
            .groupby("_w")[name_col]
            .apply(lambda s: [str(v).strip() for v in s])
            .to_dict()
        )
        findings.append(
            Finding(
                "ward.duplicated",
                "warning",
                f"{len(groups)} ward numbers appear on more than one row (left unresolved)",
                {"ward_numbers": {str(k): v for k, v in sorted(groups.items())}},
            )
        )

    for col, label, integer in (
        (conn_col, "connections", True),
        (ml_col, "consumption_ml", False),
    ):
        values = to_number(frame[col])
        if values.isna().any():
            findings.append(
                Finding(
                    f"{label}.non_numeric",
                    "error",
                    f"{int(values.isna().sum())} non-numeric or empty {label} values",
                    {"wards": frame.loc[values.isna(), name_col].fillna("").tolist()[:20]},
                )
            )
        if (values < 0).any():
            findings.append(
                Finding(
                    f"{label}.negative",
                    "error",
                    f"{int((values < 0).sum())} negative {label} values",
                    {"wards": frame.loc[values < 0, name_col].tolist()},
                )
            )
        if integer and (values.dropna() % 1 != 0).any():
            findings.append(Finding(f"{label}.non_integer", "warning", f"Fractional {label}"))
        zeros = frame.loc[values == 0, name_col].tolist()
        if zeros:
            findings.append(
                Finding(
                    f"{label}.zero",
                    "warning",
                    f"{len(zeros)} rows with zero {label}",
                    {"wards": zeros},
                )
            )
        findings.append(
            Finding(
                f"{label}.total",
                "info",
                f"Column total of {label} (all rows, duplicates included)",
                {"total": round(float(values.sum()), 3)},
            )
        )
    return findings


__all__ = ["EXPECTED_COLUMNS", "validate"]
