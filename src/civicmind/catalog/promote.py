"""Promotion gate: copy a reviewed, validated file byte-identically into ``data/raw/<domain>/``.

See docs/MANIFEST_SPEC.md section 3. ``promote`` never edits the source file, never
overwrites a different file, and never changes Git tracking (``git_tracked`` stays as it is;
tracking needs a separate allowlist line in ``.gitignore``).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath

from civicmind.catalog.manifest import Manifest

DOMAINS = frozenset({"water", "roads", "waste", "demographics"})
SOURCE_PREFIX = "data/external/"
RAW_DIR = "data/raw"


class PromotionRefused(Exception):
    def __init__(self, dataset_id: str, reasons: list[str]):
        self.dataset_id = dataset_id
        self.reasons = reasons
        super().__init__(f"{dataset_id}: promotion refused: " + "; ".join(reasons))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_verified(source: Path, root: Path, rel_target: str, expected: str, ident: str) -> None:
    """Copy ``source`` to ``root/rel_target`` byte-identically, never overwriting.

    An existing target with the same bytes is left alone (idempotent); one with different
    bytes raises ``PromotionRefused``. The copy goes to a ``.partial`` file, is hash-checked,
    then renamed into place.
    """
    target = root / rel_target
    if target.exists():
        if _sha256(target) != expected:
            raise PromotionRefused(ident, [f"{rel_target} exists with different bytes"])
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    try:
        with open(source, "rb") as src, open(partial, "xb") as dst:
            for chunk in iter(lambda: src.read(1 << 16), b""):
                dst.write(chunk)
        if _sha256(partial) != expected:
            raise PromotionRefused(ident, ["copy hash mismatch"])
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def gate_reasons(manifest: Manifest) -> list[str]:
    """Every manifest-level reason promotion is not allowed (empty list = gate open)."""
    m = manifest
    reasons = []
    if m.status != "validated":
        reasons.append(f"status is {m.status!r}, not 'validated'")
    if m.human_review != "accepted" or m.review is None or m.review.decision != "accept":
        reasons.append("no accepted person review")
    if m.integrity is None or not m.integrity.passed or not m.integrity.sha256:
        reasons.append("integrity not passed or hash missing")
    elif m.review is not None and m.review.sha256 != m.integrity.sha256:
        reasons.append("review was made for different bytes")
    if not m.semantic_checks.get("validator") or m.semantic_checks.get("errors") != 0:
        reasons.append("no validator run with 0 errors")
    if not m.licence.name or m.licence.name.strip().upper() == "UNKNOWN":
        reasons.append("licence unknown")
    if m.value_nature == "modelled":
        reasons.append("modelled values are never promoted to trusted raw data")
    if m.sensitivity != "public" or m.contains_personal_data:
        reasons.append("not public, or contains personal data")
    local = m.retrieval.local_path or ""
    if not local.startswith(SOURCE_PREFIX):
        reasons.append(f"source is not under {SOURCE_PREFIX}: {local!r}")
    elif PurePosixPath(local).parent.name not in DOMAINS:
        reasons.append(f"unknown domain folder {PurePosixPath(local).parent.name!r}")
    name = m.retrieval.original_filename
    if not name or name != PurePosixPath(name).name or "\\" in name or name in {".", ".."}:
        reasons.append(f"unsafe original_filename {name!r}")
    return reasons


def promote(manifest: Manifest, root: str | Path) -> Manifest:
    """Copy the manifest's source into data/raw/<domain>/ and return the promoted manifest.

    Idempotent: if the target already holds identical bytes, nothing is written.
    Raises PromotionRefused if any gate condition fails or bytes differ anywhere.
    """
    root = Path(root)
    reasons = gate_reasons(manifest)
    if reasons:
        raise PromotionRefused(manifest.dataset_id, reasons)
    expected = manifest.integrity.sha256
    source = root / manifest.retrieval.local_path
    if not source.is_file():
        raise PromotionRefused(manifest.dataset_id, [f"source file missing: {source}"])
    if source.stat().st_size != manifest.integrity.bytes or _sha256(source) != expected:
        raise PromotionRefused(manifest.dataset_id, ["source bytes differ from manifest"])
    domain = PurePosixPath(manifest.retrieval.local_path).parent.name
    rel_target = f"{RAW_DIR}/{domain}/{manifest.retrieval.original_filename}"
    copy_verified(source, root, rel_target, expected, manifest.dataset_id)
    data = manifest.model_dump(by_alias=True)
    data.update(status="promoted", promoted_to=rel_target)
    return Manifest.model_validate(data)


__all__ = ["DOMAINS", "PromotionRefused", "copy_verified", "gate_reasons", "promote"]
