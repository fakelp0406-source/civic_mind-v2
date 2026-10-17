"""Schema profile of a delimited text file, read without type coercion.

Every cell is read as text, so nothing is silently converted (for example ``"NA"`` stays
``"NA"`` and ``"0012"`` keeps its zeros). Numeric facts are reported separately for the
values that parse cleanly. Column names are kept verbatim, including stray whitespace.
"""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

_SAMPLE_VALUES = 3


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    non_empty: int
    empty: int
    distinct: int
    numeric: int
    non_numeric_values: list[str]
    minimum: float | None
    maximum: float | None
    negatives: int
    samples: list[str]


@dataclass(frozen=True)
class TableProfile:
    rows: int
    columns: int
    column_names: list[str]
    duplicate_rows: int
    duplicate_column_names: list[str]
    names_with_outer_whitespace: list[str]
    header_rows_repeated_in_body: int
    columns_detail: list[ColumnProfile] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _decoded(path: str | Path, encoding: str) -> io.StringIO:
    # Universal newlines in memory, so bare-CR files parse; the file on disk is untouched.
    return io.StringIO(Path(path).read_bytes().decode(encoding), newline=None)


def read_raw_header(path: str | Path, encoding: str, delimiter: str = ",") -> list[str]:
    """Return the first row exactly as written (pandas would rename duplicate names)."""
    return next(csv.reader(_decoded(path, encoding), delimiter=delimiter), [])


def read_text_table(path: str | Path, encoding: str, delimiter: str = ",") -> pd.DataFrame:
    """Read a delimited file as all-text cells; only empty cells become missing."""
    return pd.read_csv(
        _decoded(path, encoding),
        sep=delimiter,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )


def _profile_column(name: str, series: pd.Series) -> ColumnProfile:
    stripped = series.dropna().str.strip()
    as_number = pd.to_numeric(stripped, errors="coerce")
    numeric = as_number.dropna()
    non_numeric = sorted(set(stripped[as_number.isna()]))
    return ColumnProfile(
        name=name,
        non_empty=int(series.notna().sum()),
        empty=int(series.isna().sum()),
        distinct=int(stripped.nunique()),
        numeric=int(numeric.size),
        non_numeric_values=non_numeric[:10],
        minimum=float(numeric.min()) if numeric.size else None,
        maximum=float(numeric.max()) if numeric.size else None,
        negatives=int((numeric < 0).sum()),
        samples=list(dict.fromkeys(stripped.head(20)))[:_SAMPLE_VALUES],
    )


def profile_frame(frame: pd.DataFrame, raw_header: list[str] | None = None) -> TableProfile:
    """Profile an all-text frame produced by :func:`read_text_table`.

    ``raw_header`` (from :func:`read_raw_header`) is used for name checks, because pandas
    renames duplicate column names on read.
    """
    names = list(raw_header) if raw_header is not None else [str(c) for c in frame.columns]
    header = [n.strip() for n in names]
    repeated = int(
        sum(
            1
            for row in frame.itertuples(index=False)
            if [("" if pd.isna(v) else str(v).strip()) for v in row] == header
        )
    )
    return TableProfile(
        rows=int(len(frame)),
        columns=len(names),
        column_names=names,
        duplicate_rows=int(frame.duplicated().sum()),
        duplicate_column_names=sorted({n for n in names if names.count(n) > 1}),
        names_with_outer_whitespace=[n for n in names if n != n.strip()],
        header_rows_repeated_in_body=repeated,
        columns_detail=[_profile_column(n, frame[n]) for n in frame.columns],
    )


__all__ = ["ColumnProfile", "TableProfile", "profile_frame", "read_raw_header", "read_text_table"]
