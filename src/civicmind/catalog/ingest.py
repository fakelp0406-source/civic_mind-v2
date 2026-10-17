"""Manifest-driven ingestion: the only way other layers read a dataset's values.

``ingest(manifest, root, mode)`` re-verifies the file the manifest describes and returns an
:class:`IngestedDataset`. It fails closed with :class:`IngestionRefused` (a stable ``code``)
at the first failed check:

1. **Status.** ``trusted`` mode needs ``status: promoted``, an ``accept`` review bound to the
   same SHA-256, and ``value_nature`` other than ``modelled``; it reads ``promoted_to``.
   ``exploratory`` mode needs a ``keep_profiled`` review whose ``permitted_uses`` includes
   ``exploratory``; it reads ``retrieval.local_path``. Quarantined, rejected or any other
   status is refused.
2. **File.** Exists inside the repository; size and SHA-256 equal the manifest; encoding,
   BOM, line-ending style and delimiter equal the manifest; not HTML, no NUL bytes.
3. **CSV structure.** Decodes; parses; header present with no duplicate names; every row
   has as many fields as the header.
4. **Schema.** The raw header equals the manifest's schema and exactly one registered
   schema version (``catalog.schemas``), verbatim.
5. **Validation.** The family validator runs. In ``trusted`` mode any error is refused, and
   every warning must be an accepted caveat of the review.

Nothing is modified: source bytes are read once; line endings are interpreted in memory
only; headers keep their exact spelling; duplicate wards, zeros, negatives and ``NA`` cells
stay as published (``raw`` keeps every cell as text). No dataset is joined to another.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import pandas as pd

from civicmind.catalog.fingerprint import fingerprint
from civicmind.catalog.manifest import Manifest
from civicmind.catalog.schemas import detect_schema
from civicmind.catalog.validators import (
    bwssb_monthly,
    census_ward_profile,
    morth_city_table,
    swm_gcp,
)
from civicmind.catalog.validators.base import Finding, to_number

Mode = Literal["trusted", "exploratory"]

VALIDATORS = {
    "bwssb_monthly": bwssb_monthly.validate,
    "census_ward_profile": census_ward_profile.validate,
    "swm_gcp": swm_gcp.validate,
    "morth_city_a47": morth_city_table.validate,
}

#: Uses that analytics must check with :func:`require_use` before relying on a dataset.
USES = (
    "trusted_analytics",
    "measured_performance",
    "ward_efficiency_ranking",
    "ward_ranking",
    "cross_dataset_join",
)


class IngestionRefused(Exception):
    def __init__(self, dataset_id: str, code: str, message: str, details: Any = None):
        self.dataset_id = dataset_id
        self.code = code
        self.details = details
        super().__init__(f"{dataset_id}: {code}: {message}")


class UseNotPermitted(Exception):
    pass


@dataclass(frozen=True)
class IngestedDataset:
    dataset_id: str
    mode: Mode
    family: str
    schema_version: str
    source_path: str  # repo-relative
    sha256: str
    bytes: int
    newline: str | None
    header: tuple[str, ...]
    raw: pd.DataFrame  # every cell as published, as text ("" for empty)
    values: pd.DataFrame  # same columns; numeric_columns parsed, unparseable cells -> NaN
    findings: tuple[Finding, ...]
    caveats: tuple[str, ...]
    restrictions: tuple[str, ...]  # "no_<use>" entries; see require_use
    value_nature: str
    level: str
    period: dict[str, Any]
    ward_scheme: str | None

    def summary(self) -> dict[str, Any]:
        """Deterministic description without the tables (for reports and tests)."""
        return {
            "dataset_id": self.dataset_id,
            "mode": self.mode,
            "family": self.family,
            "schema_version": self.schema_version,
            "source_path": self.source_path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "newline": self.newline,
            "rows": len(self.raw),
            "columns": len(self.header),
            "values_digest": _frame_digest(self.values),
            "findings": [f.to_dict() for f in self.findings],
            "caveats": list(self.caveats),
            "restrictions": list(self.restrictions),
            "value_nature": self.value_nature,
            "level": self.level,
            "period": self.period,
            "ward_scheme": self.ward_scheme,
        }


def require_use(dataset: IngestedDataset, use: str) -> None:
    """Raise UseNotPermitted if ``use`` is restricted for this dataset."""
    if use not in USES:
        raise ValueError(f"unknown use {use!r}")
    if f"no_{use}" in dataset.restrictions:
        raise UseNotPermitted(f"{dataset.dataset_id}: {use} is not permitted ({dataset.mode})")


def _frame_digest(frame: pd.DataFrame) -> str:
    text = frame.to_csv(index=False, lineterminator="\n", float_format="%.10g")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source(m: Manifest, mode: Mode) -> str:
    def refuse(code: str, message: str) -> IngestionRefused:
        return IngestionRefused(m.dataset_id, code, message)

    if m.status in ("quarantined", "rejected"):
        raise refuse(f"status.{m.status}", f"dataset is {m.status}; refused by ingestion")
    sha = m.integrity.sha256 if m.integrity else None
    if m.review is not None and m.review.sha256 != sha:
        raise refuse("review.stale", "review was made for different bytes")
    if mode == "trusted":
        if m.value_nature == "modelled":
            raise refuse("modelled.not_trusted", "modelled values are never ingested as trusted")
        if (
            m.status != "promoted"
            or m.human_review != "accepted"
            or m.review is None
            or m.review.decision != "accept"
            or not m.promoted_to
        ):
            raise refuse(
                "status.not_trusted",
                f"trusted ingestion needs a promoted, accepted dataset (status {m.status!r}, "
                f"human_review {m.human_review!r})",
            )
        return m.promoted_to
    if mode == "exploratory":
        if (
            m.status != "integrity_passed"
            or m.review is None
            or m.review.decision != "keep_profiled"
            or "exploratory" not in m.review.permitted_uses
        ):
            raise refuse(
                "exploratory.not_permitted",
                "exploratory ingestion needs a keep_profiled review that permits 'exploratory'",
            )
        return m.retrieval.local_path or ""
    raise ValueError(f"unknown mode {mode!r}")


def _resolve(m: Manifest, rel: str, root: Path, mode: Mode) -> Path:
    prefix = "data/raw/" if mode == "trusted" else "data/external/"
    pure = PurePosixPath(rel)
    if not rel.startswith(prefix) or ".." in pure.parts or pure.is_absolute():
        raise IngestionRefused(m.dataset_id, "path.unsafe", f"{rel!r} is not under {prefix}")
    path = root / rel
    if not path.is_file():
        raise IngestionRefused(m.dataset_id, "file.missing", f"no file at {rel}")
    return path


def _check_bytes(m: Manifest, path: Path, data: bytes) -> None:
    integ = m.integrity
    if integ is None or not integ.passed or not integ.sha256:
        raise IngestionRefused(m.dataset_id, "integrity.not_recorded", "no passed integrity")
    if len(data) != integ.bytes:
        raise IngestionRefused(
            m.dataset_id,
            "integrity.size_mismatch",
            f"{len(data)} bytes, manifest says {integ.bytes}",
        )
    if hashlib.sha256(data).hexdigest() != integ.sha256:
        raise IngestionRefused(m.dataset_id, "integrity.hash_mismatch", "SHA-256 differs")
    fp = fingerprint(path)
    if fp.looks_like_html or fp.contains_nul:
        raise IngestionRefused(m.dataset_id, "file.not_csv", "HTML or NUL bytes found")
    for field, found, expected in (
        ("encoding", fp.encoding, integ.encoding),
        ("bom", fp.bom, integ.bom),
        ("newline", fp.newline, integ.newline),
        ("delimiter", fp.delimiter, integ.delimiter),
    ):
        if found != expected:
            raise IngestionRefused(
                m.dataset_id,
                f"integrity.{field}_mismatch",
                f"{field} is {found!r}, manifest says {expected!r}",
            )


def parse_rows(dataset_id: str, data: bytes, encoding: str, delimiter: str) -> list[list[str]]:
    """Decode and parse CSV bytes into rows of text. Line endings are handled in memory."""
    try:
        text = data.decode(encoding)
    except (UnicodeDecodeError, LookupError) as exc:
        raise IngestionRefused(dataset_id, "csv.decode_error", str(exc)) from exc
    if text.startswith("﻿"):
        text = text[1:]
    try:
        reader = csv.reader(io.StringIO(text, newline=None), delimiter=delimiter, strict=True)
        rows = [row for row in reader if row]  # blank lines carry no fields
    except csv.Error as exc:
        raise IngestionRefused(dataset_id, "csv.malformed", str(exc)) from exc
    if not rows:
        raise IngestionRefused(dataset_id, "csv.empty", "no header row")
    header = rows[0]
    dupes = sorted({h for h in header if header.count(h) > 1})
    if dupes:
        raise IngestionRefused(dataset_id, "schema.duplicate_columns", "duplicate names", dupes)
    ragged = [i + 1 for i, row in enumerate(rows[1:], start=1) if len(row) != len(header)]
    if ragged:
        raise IngestionRefused(
            dataset_id,
            "csv.ragged_rows",
            f"{len(ragged)} records do not have {len(header)} fields (record numbers, header = 1)",
            ragged[:20],
        )
    return rows


def _restrictions(m: Manifest, mode: Mode) -> tuple[str, ...]:
    out = {"no_cross_dataset_join"}  # no identifier authority or crosswalk is recorded yet
    if mode == "exploratory" or m.value_nature == "modelled":
        out |= {
            "no_trusted_analytics",
            "no_measured_performance",
            "no_ward_efficiency_ranking",
            "no_ward_ranking",
        }
    return tuple(sorted(out))


def ingest(manifest: Manifest, root: str | Path, mode: Mode = "trusted") -> IngestedDataset:
    m = manifest
    root = Path(root)
    rel = _source(m, mode)
    path = _resolve(m, rel, root, mode)
    data = path.read_bytes()
    _check_bytes(m, path, data)
    rows = parse_rows(m.dataset_id, data, m.integrity.encoding, m.integrity.delimiter or ",")
    header = rows[0]
    if header != [c.name for c in m.schema_]:
        raise IngestionRefused(
            m.dataset_id, "schema.manifest_mismatch", "header differs from the manifest schema"
        )
    schema = detect_schema(header)
    if schema is None:
        raise IngestionRefused(
            m.dataset_id, "schema.unknown", "header matches no registered schema version"
        )
    recorded = (m.semantic_checks.get("validator") or "").split("@")[0]
    if recorded and schema.validator and recorded != schema.validator:
        raise IngestionRefused(
            m.dataset_id,
            "schema.family_mismatch",
            f"manifest validator {recorded!r} vs schema {schema.version!r}",
        )
    raw = pd.DataFrame(rows[1:], columns=header, dtype="string").astype(object)
    findings = list(VALIDATORS[schema.family](raw, header))
    errors = [f for f in findings if f.severity == "error"]
    if mode == "trusted":
        if errors:
            raise IngestionRefused(
                m.dataset_id, "validation.errors", "validator errors", [f.code for f in errors]
            )
        accepted = set(m.review.accepted_caveats)
        unaccepted = sorted({f.code for f in findings if f.severity == "warning"} - accepted)
        if unaccepted:
            raise IngestionRefused(
                m.dataset_id,
                "validation.unaccepted_warnings",
                "warnings not accepted in the review",
                unaccepted,
            )
    values = raw.copy()
    unparsed = {}
    for col in schema.numeric_columns:
        parsed = to_number(raw[col].astype("string"))
        blanks = raw[col].str.strip() != ""
        n = int((parsed.isna() & blanks).sum())
        if n:
            unparsed[col] = sorted(set(raw.loc[parsed.isna() & blanks, col]))
        values[col] = parsed.astype("float64")
    if unparsed:
        findings.append(
            Finding(
                "values.unparsed",
                "info",
                "Cells kept as published but not numeric in the typed view (NaN)",
                unparsed,
            )
        )
    caveats = [*m.known_limitations]
    caveats += [f"{f.code}: {f.message}" for f in findings if f.severity == "warning"]
    if mode == "exploratory":
        caveats.insert(0, "EXPLORATORY: modelled or profile-only values; not measurements.")
    return IngestedDataset(
        dataset_id=m.dataset_id,
        mode=mode,
        family=schema.family,
        schema_version=schema.version,
        source_path=rel,
        sha256=m.integrity.sha256,
        bytes=m.integrity.bytes,
        newline=m.integrity.newline,
        header=tuple(header),
        raw=raw,
        values=values,
        findings=tuple(findings),
        caveats=tuple(caveats),
        restrictions=_restrictions(m, mode),
        value_nature=m.value_nature,
        level=schema.level,
        period=m.period.model_dump(),
        ward_scheme=m.ward_scheme,
    )


__all__ = [
    "USES",
    "IngestedDataset",
    "IngestionRefused",
    "Mode",
    "UseNotPermitted",
    "ingest",
    "parse_rows",
    "require_use",
]
