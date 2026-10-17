"""Shared types for dataset-specific validators (Stage B, semantic checks).

Validators describe what they find and never modify data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import pandas as pd

Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class Finding:
    """One observation about a dataset.

    ``error`` blocks promotion until a person accepts or resolves it; ``warning`` must be
    recorded as a caveat; ``info`` documents a fact (e.g. a total) for the report.
    """

    code: str
    severity: Severity
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def to_number(series: pd.Series) -> pd.Series:
    """Parse text cells as numbers after trimming whitespace; unparseable cells become NaN."""
    return pd.to_numeric(series.str.strip(), errors="coerce")


def has_errors(findings: list[Finding]) -> bool:
    return any(f.severity == "error" for f in findings)


__all__ = ["Finding", "Severity", "has_errors", "to_number"]
