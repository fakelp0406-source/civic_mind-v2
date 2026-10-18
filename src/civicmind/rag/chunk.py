"""Deterministic, page-aware chunking.

Each corpus page is split on its own: a chunk never spans two pages, so every chunk has exactly
one page number and its citation is exact. Within a page, text is whitespace-normalised and cut
into windows of ``max_words`` words that overlap by ``overlap_words``. A page with fewer than
``min_words`` words yields no chunk (recorded as ``short_pages``).

Chunks whose text the screen flags as addressed to an AI system (``content.instruction_like``)
are dropped and counted: retrieved text is data, and such text has no place in evidence.

``chunk_id`` is ``<document_id>:p<page>:c<n>``; ``text_sha256`` is the SHA-256 of the chunk text.
The same pages and configuration always give byte-identical chunks.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

from civicmind.rag.corpus import Corpus
from civicmind.rag.screen import screen_pages


@dataclass(frozen=True)
class ChunkConfig:
    version: str = "chunk@v1"
    max_words: int = 160
    overlap_words: int = 40
    min_words: int = 12

    def __post_init__(self) -> None:
        if not 0 <= self.overlap_words < self.max_words or self.min_words < 1:
            raise ValueError("need 0 <= overlap_words < max_words and min_words >= 1")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    page: int
    text: str
    text_sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ChunkReport:
    chunks: tuple[Chunk, ...]
    short_pages: tuple[tuple[str, int], ...]
    dropped_instruction_like: tuple[str, ...]


DEFAULT_CHUNKING = ChunkConfig()


def chunk_corpus(corpus: Corpus, config: ChunkConfig = DEFAULT_CHUNKING) -> ChunkReport:
    chunks, short, dropped = [], [], []
    step = config.max_words - config.overlap_words
    for page in corpus.pages:
        words = page.text.split()
        if len(words) < config.min_words:
            short.append((page.document_id, page.page))
            continue
        starts = list(range(0, max(len(words) - config.overlap_words, 1), step))
        for n, start in enumerate(starts):
            text = " ".join(words[start : start + config.max_words])
            chunk_id = f"{page.document_id}:p{page.page}:c{n}"
            if any(f["code"] == "content.instruction_like" for f in screen_pages([(0, text)])):
                dropped.append(chunk_id)
                continue
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunks.append(Chunk(chunk_id, page.document_id, page.page, text, digest))
    return ChunkReport(tuple(chunks), tuple(short), tuple(dropped))


__all__ = ["DEFAULT_CHUNKING", "Chunk", "ChunkConfig", "ChunkReport", "chunk_corpus"]
