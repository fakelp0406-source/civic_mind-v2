"""Personal-data screening of a dataset's header (Stage D evidence, not a guarantee).

``scan_header`` flags column names that usually hold personal information (names of people,
phone numbers, e-mail, addresses, identity numbers, free-text remarks). It looks at **column
names only**; it does not read cell values, so a sensitive column with an innocuous name is
not caught. Its result is recorded in the manifest as evidence for the sensitivity fields,
and any hit blocks trusted use until a person reviews it.

Patterns avoid known false positives in batch-01 headers: "Ward Name", "City Name", "Zone
Name" (places, not people) and MoRTH's "Use of Mobile Phone" (a violation category).
"""

from __future__ import annotations

import re

METHOD = "header-name scan sensitivity@v1 (column names only; cell values not inspected)"

PATTERNS = (
    ("person_name", r"\b(staff|officer|employee|complainant|citizen|applicant|person|owner|"
                    r"consumer|customer|user|resident|patient|driver)\s*'?s?\s*name\b"),
    ("person_name", r"\bname of (the )?(staff|officer|complainant|applicant|person|owner|"
                    r"consumer|customer|resident|driver)\b"),
    ("person_name", r"^\s*(full |first |last )?name\s*$"),
    ("phone", r"\b(phone|mobile|contact|cell)\s*(no|number|num|#)\b"),
    ("email", r"\be-?mail\b"),
    ("address", r"\b(address|house no|door no)\b"),
    ("identity_number", r"\b(aadhaa?r|pan( no| number)?|voter id|passport|vehicle (no|number)|"
                        r"registration (no|number))\b"),
    ("free_text", r"\b(remarks?|comments?|description|grievance text|complaint text)\b"),
    ("birth_date", r"\b(date of birth|dob)\b"),
)  # fmt: skip


def scan_header(columns: list[str] | tuple[str, ...]) -> list[dict[str, str]]:
    """Columns whose names suggest personal data, with the kind of data suspected."""
    hits = []
    for column in columns:
        lower = column.lower()
        for kind, pattern in PATTERNS:
            if re.search(pattern, lower):
                hits.append({"column": column, "kind": kind})
                break
    return hits


__all__ = ["METHOD", "PATTERNS", "scan_header"]
