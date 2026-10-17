"""Move a file into a quarantine folder without ever overwriting another file.

Quarantine keeps the exact published bytes as evidence, so a name collision must stop the
run instead of replacing (and destroying) the file already there, even if the bytes happen
to be identical: a person decides which copy to keep.
"""

from __future__ import annotations

import os
from pathlib import Path


class QuarantineConflict(Exception):
    pass


def move_to_quarantine(path: str | Path, directory: str | Path) -> Path:
    """Move ``path`` into ``directory`` (same file name) and return the new path.

    Already inside ``directory``: returned unchanged. A different file already holding that
    name: ``QuarantineConflict`` and nothing is moved. ``os.rename`` is used, never a copy,
    so the bytes are not rewritten; on any error the source stays where it was.
    """
    source = Path(path)
    folder = Path(directory)
    target = folder / source.name
    if source.resolve() == target.resolve():
        return target
    if not source.is_file():
        raise FileNotFoundError(f"cannot quarantine missing file: {source.name}")
    if target.exists():
        raise QuarantineConflict(
            f"{target.name} already exists in {folder.name}/; not overwritten. Resolve the "
            "duplicate by hand (compare SHA-256) before re-running."
        )
    folder.mkdir(parents=True, exist_ok=True)
    os.rename(source, target)  # same volume: atomic; fails instead of replacing on Windows
    if source.exists() or not target.is_file():
        raise QuarantineConflict(f"move of {source.name} did not complete")
    return target


__all__ = ["QuarantineConflict", "move_to_quarantine"]
