"""Build and load the retrieval index: approved chunks, a BM25 index and dense vectors.

Layout (``data/processed/rag/index/<index_id>/``, git-ignored; every file created once through a
verified handle and never overwritten):

* ``chunks.jsonl`` - one chunk per line with its provenance (byte-identical for the same inputs);
* ``bm25.sqlite`` - SQLite FTS5 table (``porter unicode61`` tokenizer), serialised to bytes;
* ``dense.f32`` - float32 little-endian matrix, one L2-normalised row per chunk (optional);
* ``index_manifest.json`` - index version, the corpus documents with both hashes and their
  exclusions, the chunker configuration, the embedding model (id, revision, file hashes,
  runtime versions), counts, and the SHA-256 of each file above.

``index_id`` is derived from the corpus digest, the chunker configuration, the index version and
the model specification, so a different approved corpus or configuration is a different index.

``load_index`` recomputes the corpus from the approved manifests (re-hashing every promoted PDF
and page file), derives the expected ``index_id``, and verifies every index file against the
manifest before use. Missing -> ``IndexUnavailable``; any mismatch -> ``IndexStale``. Nothing is
ever used on trust from disk.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from civicmind.catalog.doc_limits import DEFAULT_LIMITS, PreparationLimits
from civicmind.catalog.safe_fs import UnsafePath, read_verified, write_or_match_verified
from civicmind.rag.chunk import DEFAULT_CHUNKING, Chunk, ChunkConfig, chunk_corpus
from civicmind.rag.corpus import Corpus, load_corpus
from civicmind.rag.embed import MINILM, Encoder, ModelSpec
from civicmind.rag.screen import METHOD as SCREEN_METHOD

INDEX_DIR = "data/processed/rag/index"
INDEX_VERSION = "ragindex@v1"
MAX_INDEX_FILE = 1024 * 1024 * 1024


class IndexUnavailable(RuntimeError):
    """No index exists for the current approved corpus and configuration."""


class IndexStale(RuntimeError):
    """An index file does not match its manifest, or the manifest not the current corpus."""


@dataclass(frozen=True)
class Index:
    index_id: str
    manifest: dict
    chunks: tuple[Chunk, ...]
    bm25: sqlite3.Connection
    vectors: np.ndarray | None  # (n_chunks, dim) float32, rows L2-normalised
    corpus: Corpus

    @property
    def path(self) -> str:
        return f"{INDEX_DIR}/{self.index_id}"


def index_id_for(corpus: Corpus, config: ChunkConfig, spec: ModelSpec | None) -> str:
    basis = {
        "version": INDEX_VERSION,
        "corpus": corpus.digest(),
        "chunker": config.to_dict(),
        "screen": SCREEN_METHOD,  # chunk screening decides which chunks are dropped
        "model": spec.to_dict() if spec else None,
    }
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()[:16]


def _chunks_bytes(chunks: tuple[Chunk, ...]) -> bytes:
    lines = [json.dumps(c.to_dict(), ensure_ascii=False, sort_keys=True) for c in chunks]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _bm25_bytes(chunks: tuple[Chunk, ...]) -> bytes:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE VIRTUAL TABLE chunks USING fts5(text, chunk_row UNINDEXED, "
               "tokenize='porter unicode61')")  # fmt: skip
    db.executemany(
        "INSERT INTO chunks(rowid, text, chunk_row) VALUES (?, ?, ?)",
        [(i + 1, c.text, i) for i, c in enumerate(chunks)],
    )
    db.commit()
    data = db.serialize()
    db.close()
    return data


def build_index(
    root: str | Path,
    encoder: Encoder | None = None,
    config: ChunkConfig = DEFAULT_CHUNKING,
    limits: PreparationLimits = DEFAULT_LIMITS,
) -> Index:
    """Build (or confirm) the index for the current approved corpus. Returns the loaded index."""
    root = Path(root)
    corpus = load_corpus(root, limits)
    if not corpus.documents:
        raise IndexUnavailable("no approved documents; nothing to index")
    report = chunk_corpus(corpus, config)
    spec = encoder.spec if encoder else None
    index_id = index_id_for(corpus, config, spec)
    folder = f"{INDEX_DIR}/{index_id}"
    files = {
        "chunks.jsonl": _chunks_bytes(report.chunks),
        "bm25.sqlite": _bm25_bytes(report.chunks),
    }
    if encoder is not None:
        vectors = encoder.encode([c.text for c in report.chunks]).astype("<f4")
        files["dense.f32"] = vectors.tobytes()
    manifest = {
        "index_id": index_id,
        "index_version": INDEX_VERSION,
        "corpus_digest": corpus.digest(),
        "documents": [
            {
                **d.provenance(),
                "pages_indexed": len(d.pages_indexed),
                "excluded_pages": list(d.excluded_pages),
                "no_text_pages": list(d.no_text_pages),
            }
            for d in corpus.documents
        ],  # fmt: skip
        "skipped_documents": [{"document_id": i, "reason": r} for i, r in corpus.skipped],
        "chunker": config.to_dict(),
        "screen": SCREEN_METHOD,
        "chunks": len(report.chunks),
        "short_pages": len(report.short_pages),
        "dropped_instruction_like": list(report.dropped_instruction_like),
        "bm25": {
            "engine": "sqlite3-fts5",
            "sqlite_version": sqlite3.sqlite_version,
            "tokenizer": "porter unicode61",
        },  # fmt: skip
        "embedding": (
            {**spec.to_dict(), "runtime": getattr(encoder, "versions", {})} if spec else None
        ),
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    # Existing files must hold exactly these bytes (index files are never rewritten). The
    # SQLite serialisation and the vectors can legitimately differ across library versions; if
    # they do, the index id stays the same but the folder is refused rather than overwritten.
    try:
        for name, data in files.items():
            write_or_match_verified(root, f"{folder}/{name}", INDEX_DIR, data)
        body = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        write_or_match_verified(root, f"{folder}/index_manifest.json", INDEX_DIR, body)
    except UnsafePath as exc:
        raise IndexStale(f"index folder {folder} exists with other content ({exc})") from None
    return load_index(root, spec, config, limits)


def load_index(
    root: str | Path,
    spec: ModelSpec | None = MINILM,
    config: ChunkConfig = DEFAULT_CHUNKING,
    limits: PreparationLimits = DEFAULT_LIMITS,
) -> Index:
    """Load and fully verify the index for the *current* approved corpus."""
    root = Path(root)
    corpus = load_corpus(root, limits)
    if not corpus.documents:
        raise IndexUnavailable("no approved documents")
    index_id = index_id_for(corpus, config, spec)
    folder = f"{INDEX_DIR}/{index_id}"
    try:
        raw_manifest = read_verified(root, f"{folder}/index_manifest.json", (INDEX_DIR,), 10**7)
    except FileNotFoundError:
        raise IndexUnavailable(
            f"no index {index_id} for the current approved corpus; run scripts/build_doc_index.py"
        ) from None
    manifest = json.loads(raw_manifest)
    if manifest.get("corpus_digest") != corpus.digest() or manifest.get("index_id") != index_id:
        raise IndexStale("index manifest does not describe the current approved corpus")
    blobs = {}
    for name, expected in manifest["files"].items():
        data = read_verified(root, f"{folder}/{name}", (INDEX_DIR,), MAX_INDEX_FILE)
        if hashlib.sha256(data).hexdigest() != expected:
            raise IndexStale(f"{folder}/{name} does not match the index manifest")
        blobs[name] = data
    chunks = tuple(
        Chunk(**json.loads(line)) for line in blobs["chunks.jsonl"].decode("utf-8").splitlines()
    )
    expected_chunks = chunk_corpus(corpus, config).chunks
    if chunks != expected_chunks:
        raise IndexStale("indexed chunks differ from the chunks of the current approved corpus")
    bm25 = sqlite3.connect(":memory:", check_same_thread=False)
    bm25.deserialize(blobs["bm25.sqlite"])
    vectors = None
    if "dense.f32" in blobs:
        dim = manifest["embedding"]["dim"]
        vectors = np.frombuffer(blobs["dense.f32"], dtype="<f4").reshape(len(chunks), dim)
    return Index(index_id, manifest, chunks, bm25, vectors, corpus)


__all__ = [
    "INDEX_DIR",
    "INDEX_VERSION",
    "Index",
    "IndexStale",
    "IndexUnavailable",
    "build_index",
    "index_id_for",
    "load_index",
]
