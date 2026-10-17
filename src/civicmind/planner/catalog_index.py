"""Catalogue metadata the planner may use: which datasets exist, their periods and status.

Built only from manifests (``data/manifests/*.yaml``); never from data values. A dataset's
family comes from its id prefix (documented below), not from its contents.

A family can hold several source tables with different meanings (MoRTH publishes Annexures
1, 2, 47, 49, ... in the same yearly edition), so each entry also records its source
``table``, parsed from the id (``ROAD-RA<edition>-<annexure>``). Feasibility matches on
family, table and period; a road id that does not parse has no table and never matches.

``coverage`` summarises, for one family, which periods are trusted and why the others are not
(quarantined, exploratory only, ...). It reads manifests only. "Latest" there means the latest
trusted file in this catalogue - a static copy as published - never "current conditions".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from civicmind.catalog.manifest import read_manifest

#: Dataset-id prefix -> planner family. Only these families exist for the planner.
FAMILY_BY_PREFIX = (
    ("WATER-BWSSB-", "water"),
    ("ROAD-RA", "roads"),
    ("WASTE-", "waste"),
    ("DEMO-", "census"),
)

#: ``ROAD-RA2024-A47`` -> edition 2024, table "A47" (the MoRTH annexure number).
ROAD_ID = re.compile(r"^ROAD-RA(?P<edition>\d{4})-(?P<table>A\d+)$")


@dataclass(frozen=True)
class DatasetEntry:
    dataset_id: str
    family: str
    period_key: str  # water "YYYY-MM"; roads "YYYY"; others the start date
    period_start: str | None
    period_end: str | None
    status: str
    human_review: str
    value_nature: str
    review_note: str | None
    title: str
    columns: tuple[str, ...]  # verbatim header recorded in the manifest (metadata)
    table: str | None = None  # source table within the family (roads: "A47"); None otherwise
    review_decision: str | None = None  # accept | quarantine | keep_profiled | reject
    permitted_uses: tuple[str, ...] = ()  # e.g. ("exploratory",) from a keep_profiled review
    portal_published: str | None = None  # publisher's date for this file (manifest metadata)


def _family(dataset_id: str) -> str | None:
    return next((fam for prefix, fam in FAMILY_BY_PREFIX if dataset_id.startswith(prefix)), None)


def source_table(dataset_id: str) -> str | None:
    """The source table a dataset id names: the annexure for MoRTH ids, else ``None``."""
    match = ROAD_ID.match(dataset_id)
    return match.group("table") if match else None


def load_index(root: str | Path) -> tuple[DatasetEntry, ...]:
    entries = []
    for path in sorted((Path(root) / "data/manifests").glob("*.yaml")):
        m = read_manifest(path)
        family = _family(m.dataset_id)
        if family is None:
            continue
        start = m.period.start or m.period.as_on
        if family == "water":
            key = (start or "")[:7]
        elif family == "roads":
            key = (start or "")[:4]
        else:
            key = start or ""
        entries.append(
            DatasetEntry(
                dataset_id=m.dataset_id,
                family=family,
                period_key=key,
                period_start=m.period.start,
                period_end=m.period.end,
                status=m.status,
                human_review=m.human_review,
                value_nature=m.value_nature,
                review_note=m.review.note if m.review else None,
                title=m.title,
                columns=tuple(c.name for c in m.schema_),
                table=source_table(m.dataset_id),
                review_decision=m.review.decision if m.review else None,
                permitted_uses=tuple(m.review.permitted_uses) if m.review else (),
                portal_published=m.portal_published,
            )
        )
    return tuple(entries)


def trust_label(entry: DatasetEntry) -> str:
    """One word for how an entry may be used: trusted, exploratory_only, quarantined, ..."""
    if entry.status == "promoted" and entry.human_review == "accepted":
        return "trusted"
    if entry.status in ("quarantined", "rejected"):
        return entry.status
    if entry.value_nature == "modelled":
        return "modelled"
    if entry.review_decision == "keep_profiled":
        return "exploratory_only" if "exploratory" in entry.permitted_uses else "profile_only"
    return "not_reviewed"


#: The series each answerable family is about, and the table its analytics read.
SERIES = {
    "water": ("BWSSB monthly ward water consumption", None, "month"),
    "roads": ("MoRTH million-plus city traffic-rule violations (Annexure 47)", "A47", "edition"),
}
FRESHNESS_NOTE = (
    "Static files as published by the portal and copied into this catalogue; there is no live "
    "data connection. 'Latest' is the latest trusted file here, not current conditions."
)


def coverage(
    index: tuple[DatasetEntry, ...], family: str, *, other_tables: bool = False
) -> dict | None:
    """Trusted and non-trusted periods of one answerable family (metadata only), or None.

    ``other_tables`` lists same-family tables that are never used for this series (e.g. MoRTH
    Annexures 1, 2, 49). It is off by default so that ordinary answers about Annexure 47 never
    mention another annexure; availability questions ask for it explicitly.
    """
    if family not in SERIES:
        return None
    series, table, unit = SERIES[family]
    members = [e for e in index if e.family == family]
    in_series = sorted(
        (e for e in members if table is None or e.table == table), key=lambda e: e.period_key
    )
    trusted = [e for e in in_series if trust_label(e) == "trusted"]
    latest = trusted[-1] if trusted else None
    return {
        "domain": family,
        "series": series,
        "period_unit": unit,
        "trusted_periods": [e.period_key for e in trusted],
        "latest_trusted_period": latest.period_key if latest else None,
        "latest_trusted_dataset": latest.dataset_id if latest else None,
        "latest_trusted_portal_published": latest.portal_published if latest else None,
        "not_trusted": [
            {"period": e.period_key, "dataset_id": e.dataset_id, "trust": trust_label(e)}
            for e in in_series
            if trust_label(e) != "trusted"
        ],
        "other_tables": [  # same family, different table: never used for this series
            {
                "edition": m.group("edition") if (m := ROAD_ID.match(e.dataset_id)) else None,
                "table": e.table,
                "dataset_id": e.dataset_id,
                "trust": trust_label(e),
            }
            for e in sorted(members, key=lambda e: e.dataset_id)
            if other_tables and table is not None and e.table != table
        ],
        "freshness_note": FRESHNESS_NOTE,
    }


__all__ = [
    "FAMILY_BY_PREFIX",
    "FRESHNESS_NOTE",
    "ROAD_ID",
    "SERIES",
    "DatasetEntry",
    "coverage",
    "load_index",
    "source_table",
    "trust_label",
]
