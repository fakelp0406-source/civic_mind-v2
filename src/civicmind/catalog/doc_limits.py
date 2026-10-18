"""Resource limits for document preparation (configurable; fail closed on bad values).

Defaults suit official reports of a few hundred pages. Each can be overridden with an
environment variable; a value that is not a positive integer raises ``ValueError`` instead of
silently falling back.

| Limit | Default | Environment variable |
|---|---|---|
| file size | 50 MiB | ``CIVICMIND_DOC_MAX_BYTES`` |
| pages | 2,000 | ``CIVICMIND_DOC_MAX_PAGES`` |
| extracted characters per document | 20,000,000 | ``CIVICMIND_DOC_MAX_TEXT_CHARS`` |
| extraction time per document (seconds) | 300 | ``CIVICMIND_DOC_EXTRACT_SECONDS`` |
| documents per batch | 50 | ``CIVICMIND_DOC_MAX_BATCH`` |

The time limit is checked between pages (cooperative): a single pathological page can exceed it,
and extraction then stops at the next page boundary. It is not a hard kill.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass

ENV = {
    "max_bytes": "CIVICMIND_DOC_MAX_BYTES",
    "max_pages": "CIVICMIND_DOC_MAX_PAGES",
    "max_text_chars": "CIVICMIND_DOC_MAX_TEXT_CHARS",
    "extract_seconds": "CIVICMIND_DOC_EXTRACT_SECONDS",
    "max_batch": "CIVICMIND_DOC_MAX_BATCH",
}


@dataclass(frozen=True)
class PreparationLimits:
    max_bytes: int = 50 * 1024 * 1024
    max_pages: int = 2000
    max_text_chars: int = 20_000_000
    extract_seconds: int = 300
    max_batch: int = 50

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"limit {name} must be a positive integer, got {value!r}")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> PreparationLimits:
        env = os.environ if environ is None else environ
        values = {}
        for field, var in ENV.items():
            raw = env.get(var)
            if raw is None or raw == "":
                continue
            try:
                values[field] = int(raw)
            except ValueError:
                raise ValueError(f"{var} must be a positive integer, got {raw!r}") from None
        return cls(**values)

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


DEFAULT_LIMITS = PreparationLimits()

__all__ = ["DEFAULT_LIMITS", "ENV", "PreparationLimits"]
