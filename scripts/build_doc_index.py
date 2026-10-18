"""Build the retrieval index over approved documents only (BM25 + optional MiniLM vectors).

Loads the approved corpus (re-verifying every promoted PDF and reviewed page file), chunks it,
builds the SQLite FTS5 index and, unless ``--bm25-only``, the dense vectors with the pinned
MiniLM model, then verifies the result by loading it back. Index files are created once and never
overwritten; re-running on the same inputs confirms the existing index.

Usage: python scripts/build_doc_index.py [--bm25-only]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from civicmind.rag.embed import MiniLMEncoder
from civicmind.rag.index import build_index

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bm25-only", action="store_true", help="skip dense vectors")
    args = parser.parse_args()
    started = time.perf_counter()
    encoder = None if args.bm25_only else MiniLMEncoder(ROOT)
    index = build_index(ROOT, encoder)
    m = index.manifest
    print(f"index {index.index_id} at {index.path} ({time.perf_counter() - started:.1f} s)")
    for d in m["documents"]:
        excluded = d["excluded_pages"] or "none"
        print(
            f"  {d['document_id']}: {d['pages_indexed']} pages indexed, excluded {excluded}, "
            f"sha256 {d['document_sha256'][:12]}"
        )
    for s in m["skipped_documents"]:
        print(f"  not indexed: {s['document_id']} ({s['reason']})")
    dropped = len(m["dropped_instruction_like"])
    print(
        f"  chunks {m['chunks']}, short pages {m['short_pages']}, "
        f"instruction-like dropped {dropped}"
    )
    e = m["embedding"]
    print(f"  dense: {e['model_id'] + '@' + e['revision'][:8] if e else 'none'}")


if __name__ == "__main__":
    main()
