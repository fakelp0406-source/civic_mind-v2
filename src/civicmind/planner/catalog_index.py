"""Catalogue metadata the planner may use: which datasets exist, their periods and status.

Built only from manifests (``data/manifests/*.yaml``); never from data values. A dataset's
family comes from its id prefix (documented below), not from its contents.

A family can hold several source tables with different meanings (MoRTH publishes Annexures
1, 2, 47, 49, ... in the same yearly edition), so each entry also records its source
``table``, parsed from the id (``ROAD-RA<edition>-<annexure>``). Feasibility matches on
family, table and period; a road id that does not parse has no table and never matches.
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
            )
        )
    return tuple(entries)


__all__ = ["FAMILY_BY_PREFIX", "ROAD_ID", "DatasetEntry", "load_index", "source_table"]
