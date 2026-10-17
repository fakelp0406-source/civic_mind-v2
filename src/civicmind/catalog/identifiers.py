"""Stage C - identifier assessment between two datasets. It never joins them.

The report separates four outcomes, as required before any join can be considered:

* ``matched``: the identifier occurs once on each side and the normalised names agree;
* ``name_conflict``: the identifier occurs once on each side but the names differ;
* ``unmatched_left`` / ``unmatched_right``: identifiers present on one side only;
* ``ambiguous_left`` / ``ambiguous_right``: an identifier that maps to several distinct names
  within one dataset;
* ``duplicated_left`` / ``duplicated_right``: identifiers repeated within one dataset.

A high match rate does **not** authorise a join. That requires a documented identifier
definition or a version-aware crosswalk (see docs/MANIFEST_SPEC.md, Stage C).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import pandas as pd


def normalise_name(name: object) -> str:
    """Lower-case, strip punctuation and collapse spaces. Used only for comparison."""
    text = re.sub(r"[^a-z0-9 ]+", " ", str(name).lower())
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class IdentifierAssessment:
    left_label: str
    right_label: str
    matched: list[str]
    name_conflict: list[dict]
    unmatched_left: list[str]
    unmatched_right: list[str]
    ambiguous_left: dict[str, list[str]]
    ambiguous_right: dict[str, list[str]]
    duplicated_left: dict[str, int]
    duplicated_right: dict[str, int]
    join_authorised: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def counts(self) -> dict[str, int]:
        return {
            "matched": len(self.matched),
            "name_conflict": len(self.name_conflict),
            "unmatched_left": len(self.unmatched_left),
            "unmatched_right": len(self.unmatched_right),
            "ambiguous_left": len(self.ambiguous_left),
            "ambiguous_right": len(self.ambiguous_right),
            "duplicated_left": len(self.duplicated_left),
            "duplicated_right": len(self.duplicated_right),
        }


def _side(frame: pd.DataFrame, id_col: str, name_col: str) -> tuple[dict, dict, dict]:
    ids = frame[id_col].astype(str).str.strip()
    names = frame[name_col].astype(str).str.strip()
    by_id: dict[str, list[str]] = {}
    for i, n in zip(ids, names, strict=True):
        by_id.setdefault(i, []).append(n)
    duplicated = {i: len(v) for i, v in by_id.items() if len(v) > 1}
    ambiguous = {
        i: sorted(set(v)) for i, v in by_id.items() if len({normalise_name(x) for x in v}) > 1
    }
    return by_id, duplicated, ambiguous


def assess_identifiers(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    left_id: str,
    left_name: str,
    right_id: str,
    right_name: str,
    left_label: str = "left",
    right_label: str = "right",
) -> IdentifierAssessment:
    l_ids, l_dup, l_amb = _side(left, left_id, left_name)
    r_ids, r_dup, r_amb = _side(right, right_id, right_name)
    matched, conflicts = [], []
    for key in sorted(set(l_ids) & set(r_ids), key=_sort_key):
        if key in l_dup or key in r_dup:
            continue  # reported under duplicated/ambiguous instead
        ln, rn = l_ids[key][0], r_ids[key][0]
        if normalise_name(ln) == normalise_name(rn):
            matched.append(key)
        else:
            conflicts.append({"id": key, left_label: ln, right_label: rn})
    return IdentifierAssessment(
        left_label=left_label,
        right_label=right_label,
        matched=matched,
        name_conflict=conflicts,
        unmatched_left=sorted(set(l_ids) - set(r_ids), key=_sort_key),
        unmatched_right=sorted(set(r_ids) - set(l_ids), key=_sort_key),
        ambiguous_left=l_amb,
        ambiguous_right=r_amb,
        duplicated_left=l_dup,
        duplicated_right=r_dup,
    )


def names_shared_by_multiple_ids(frame: pd.DataFrame, id_col: str, name_col: str) -> dict:
    """Normalised names that appear under more than one identifier within ONE dataset.

    A long list here means the name column cannot be trusted as a label for the identifier
    (for example, a block of names repeated against different ward numbers).
    """
    ids = frame[id_col].astype(str).str.strip()
    names = frame[name_col].astype(str).map(normalise_name)
    grouped: dict[str, set[str]] = {}
    for i, n in zip(ids, names, strict=True):
        grouped.setdefault(n, set()).add(i)
    return {n: sorted(v, key=_sort_key) for n, v in sorted(grouped.items()) if len(v) > 1}


def _sort_key(value: str):
    return (0, int(value)) if value.isdigit() else (1, value)


__all__ = [
    "IdentifierAssessment",
    "assess_identifiers",
    "names_shared_by_multiple_ids",
    "normalise_name",
]
