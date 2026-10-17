"""Structured results and refusals shared by every analytics operation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from civicmind.catalog.ingest import IngestedDataset, UseNotPermitted, require_use

_SHA256 = re.compile(r"[0-9a-f]{64}")

#: Every refusal code analytics may raise. Codes are part of the evaluation contract: add new
#: ones here deliberately; never rename existing ones.
REFUSAL_CODES = frozenset(
    {
        "dataset.wrong_family",
        "dataset.not_trusted",
        "use.not_permitted",
        "measure.unknown",
        "order.unknown",
        "n.out_of_range",
        "values.missing",
        "period.missing",
        "period.invalid",
        "period.same",
        "period.order",
        "schema.different_versions",
        "ward.identifiers_not_unique",
        "column.unknown",
        "total.row",
        "city.not_found",
        "city.ambiguous",
    }
)


class AnalyticsRefused(Exception):
    """The question cannot be answered from the given data; ``code`` is stable."""

    def __init__(self, code: str, message: str, details: Any = None):
        if code not in REFUSAL_CODES:
            raise ValueError(f"undeclared refusal code {code!r}")
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class Evidence:
    dataset_id: str
    schema_version: str
    sha256: str
    source_path: str
    mode: str
    period: dict[str, Any]
    columns: tuple[str, ...]  # verbatim source columns the number was computed from
    rows_used: int


@dataclass(frozen=True)
class AnalyticsResult:
    operation: str
    value: Any
    unit: str
    method: str
    evidence: tuple[Evidence, ...]
    filters: dict[str, Any] = field(default_factory=dict)
    denominator: str | None = None
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Every number must be traceable: fail at construction, not when it is cited.
        if not self.unit or not self.method or not self.caveats or not self.evidence:
            raise ValueError(f"{self.operation}: unit, method, caveats and evidence are required")
        for ev in self.evidence:
            if not _SHA256.fullmatch(ev.sha256 or "") or not ev.dataset_id or not ev.columns:
                raise ValueError(f"{self.operation}: incomplete evidence for {ev.dataset_id!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evidence(ds: IngestedDataset, columns: list[str], rows_used: int) -> Evidence:
    return Evidence(
        dataset_id=ds.dataset_id,
        schema_version=ds.schema_version,
        sha256=ds.sha256,
        source_path=ds.source_path,
        mode=ds.mode,
        period=dict(ds.period),
        columns=tuple(columns),
        rows_used=rows_used,
    )


TIE_PREFIX = "TIES BEYOND CUT-OFF"


def hidden_ties(ranked: list[dict], n: int, label: str) -> tuple[int, str | None]:
    """How many rows beyond the first ``n`` share the last shown rank, and a caveat saying so.

    A top-n list must not silently drop an item that ranks equal to one it shows.
    """
    if not ranked or n >= len(ranked):
        return 0, None
    last = ranked[n - 1]["rank"]
    tied = [r for r in ranked[n:] if r["rank"] == last]
    if not tied:
        return 0, None
    names = ", ".join(str(r[label]) for r in tied[:5]) + (" ..." if len(tied) > 5 else "")
    return len(tied), (
        f"{TIE_PREFIX}: {len(tied)} more item(s) share rank {last} with the last item shown "
        f"and are not listed ({names}); increase n to include them."
    )


def require(ds: IngestedDataset, family: str, *uses: str) -> None:
    """Refuse unless ``ds`` was ingested as trusted, is of ``family``, and every use is permitted.

    The mode is checked directly as well as through ``restrictions``, so a dataset whose
    restrictions were lost or altered still cannot reach trusted analytics.
    """
    if ds.mode != "trusted":
        raise AnalyticsRefused(
            "dataset.not_trusted", f"{ds.dataset_id} was ingested in {ds.mode!r} mode"
        )
    if ds.family != family:
        raise AnalyticsRefused(
            "dataset.wrong_family", f"{ds.dataset_id} is {ds.family!r}, need {family!r}"
        )
    for use in ("trusted_analytics", *uses):
        try:
            require_use(ds, use)
        except UseNotPermitted as exc:
            raise AnalyticsRefused("use.not_permitted", str(exc)) from exc


__all__ = [
    "REFUSAL_CODES",
    "TIE_PREFIX",
    "hidden_ties",
    "AnalyticsRefused",
    "AnalyticsResult",
    "Evidence",
    "evidence",
    "require",
]
