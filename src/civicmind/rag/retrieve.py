"""Retrieval over the verified index, with explicit scores, thresholds and abstention.

Two methods over the same chunks:

* ``bm25`` - SQLite FTS5 ``bm25()``; reported score = ``-bm25`` (higher is better). The query is
  reduced to lower-case alphanumeric terms minus stop words, each quoted, joined with ``OR``,
  so no FTS5 query syntax from the question is ever interpreted.
* ``dense`` - cosine similarity between the MiniLM query vector and the chunk vectors.

Thresholds (``RetrievalConfig``) were calibrated in stage 2E on the 34-item calibration split
of ``eval/questions/rag.v1.yaml`` (balanced accuracy; see ``eval/reports/rag.v1.results.md``).
They are fitted to that small set and to index ``f10ba588d120b144``: BM25 scores grow with query
length, so one global BM25 threshold rejects short questions; dense scores do not detect that an
asked edition is missing. Similarity is evidence of topical relevance, not of factual correctness.
A result is
``answered`` only if at least one hit clears the threshold; otherwise it abstains with a stable
code: ``rag.query_empty`` (no searchable terms), ``rag.no_evidence`` (nothing above threshold).
Index problems surface as ``rag.index_unavailable`` / ``rag.index_stale`` (see ``answer``).
Exact duplicate chunks within one document are collapsed into one hit (``duplicate_pages``).

``answer`` composes an extractive, cited answer: verbatim excerpts from the top hits, each with
document, edition, page, chunk id and content hash. Retrieved text is quoted, never followed: no
model reads it and nothing in it can change the response's codes, citations or caveats. Hits
from different editions are kept apart and labelled, never merged.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np

from civicmind.rag.embed import Encoder
from civicmind.rag.index import Index

Method = Literal["bm25", "dense"]
STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "does",
        "did",
        "do",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "per",
        "the",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "according",
        "report",
        "reports",
        "say",
        "says",
        "said",
        "define",
        "defined",
        "definition",
        "mean",
        "means",
        "meaning",
    ]
)
TERM = re.compile(r"[a-z0-9]+")
RAG_CODES = frozenset(
    {"rag.query_empty", "rag.no_evidence", "rag.index_unavailable", "rag.index_stale"}
)


@dataclass(frozen=True)
class RetrievalConfig:
    k: int = 5
    bm25_min_score: float = 21.775342  # calibrated, rag.v1 calibration split (n=34)
    dense_min_score: float = 0.638919  # calibrated, rag.v1 calibration split (n=34)
    candidate_pool: int = 50

    def threshold(self, method: Method) -> float:
        return self.bm25_min_score if method == "bm25" else self.dense_min_score


DEFAULT_RETRIEVAL = RetrievalConfig()


@dataclass(frozen=True)
class Hit:
    rank: int
    score: float
    chunk_id: str
    document_id: str
    page: int
    text: str
    text_sha256: str
    #: Other pages of the same document with exactly the same chunk text (collapsed into this hit).
    duplicate_pages: tuple[int, ...] = ()


@dataclass(frozen=True)
class Retrieval:
    status: Literal["answered", "abstained"]
    method: Method
    code: str | None
    hits: tuple[Hit, ...]  # above threshold, best first
    candidates: tuple[Hit, ...]  # top-k regardless of threshold (for evaluation)
    threshold: float
    index_id: str


def query_terms(question: str) -> list[str]:
    seen, out = set(), []
    for term in TERM.findall(question.lower()):
        if term not in STOP_WORDS and len(term) > 1 and term not in seen:
            seen.add(term)
            out.append(term)
    return out


def _bm25(index: Index, terms: list[str], pool: int) -> list[tuple[int, float]]:
    match = " OR ".join(f'"{t}"' for t in terms)
    rows = index.bm25.execute(
        "SELECT chunk_row, bm25(chunks) FROM chunks WHERE chunks MATCH ? "
        "ORDER BY bm25(chunks), chunk_row LIMIT ?",
        (match, pool),
    ).fetchall()
    return [(int(row), -float(score)) for row, score in rows]


def _dense(index: Index, encoder: Encoder, question: str, pool: int) -> list[tuple[int, float]]:
    if index.vectors is None:
        raise ValueError("this index has no dense vectors")
    query = encoder.encode([question])[0]
    scores = index.vectors @ query
    order = np.lexsort((np.arange(len(scores)), -scores))[:pool]  # score desc, then row asc
    return [(int(i), float(scores[i])) for i in order]


def retrieve(
    index: Index,
    question: str,
    method: Method = "bm25",
    encoder: Encoder | None = None,
    config: RetrievalConfig = DEFAULT_RETRIEVAL,
    documents: frozenset[str] | None = None,
) -> Retrieval:
    threshold = config.threshold(method)
    terms = query_terms(question)
    if not terms:
        return Retrieval("abstained", method, "rag.query_empty", (), (), threshold, index.index_id)
    if method == "bm25":
        scored = _bm25(index, terms, config.candidate_pool)
    else:
        if encoder is None:
            raise ValueError("dense retrieval needs an encoder")
        scored = _dense(index, encoder, question, config.candidate_pool)
    # Identical text repeated inside one document (some PDFs repeat pages) is collapsed into the
    # best-ranked hit, keeping the other page numbers; identical text in two documents (for example
    # the same form in two editions) stays separate, so neither edition is hidden.
    seen: dict[tuple[str, str], int] = {}
    picked: list[tuple[float, object, list[int]]] = []
    for row, score in scored:
        chunk = index.chunks[row]
        if documents is not None and chunk.document_id not in documents:
            continue
        key = (chunk.document_id, chunk.text_sha256)
        if key in seen:
            duplicates = picked[seen[key]][2]
            if chunk.page != picked[seen[key]][1].page and chunk.page not in duplicates:
                duplicates.append(chunk.page)
            continue
        if len(picked) < config.k:
            seen[key] = len(picked)
            picked.append((score, chunk, []))
    candidates = [
        Hit(i + 1, round(score, 6), c.chunk_id, c.document_id, c.page, c.text, c.text_sha256,
            tuple(sorted(dups)))
        for i, (score, c, dups) in enumerate(picked)
    ]  # fmt: skip
    hits = tuple(h for h in candidates if h.score >= threshold)
    status, code = ("answered", None) if hits else ("abstained", "rag.no_evidence")
    return Retrieval(status, method, code, hits, tuple(candidates), threshold, index.index_id)


SENTENCE = re.compile(r"(?<=[.;:!?])\s+")
MAX_EXCERPT = 320


def best_excerpt(text: str, terms: list[str]) -> str:
    """The sentence (or window) of ``text`` containing the most query terms, verbatim."""
    sentences = [s for s in SENTENCE.split(text) if s.strip()] or [text]

    def overlap(s: str) -> int:
        words = set(TERM.findall(s.lower()))
        return sum(t in words for t in terms)

    best = max(sentences, key=lambda s: (overlap(s), -sentences.index(s)))
    if len(best) <= MAX_EXCERPT:
        return best
    cut = best[:MAX_EXCERPT]
    return cut[: cut.rfind(" ")] if " " in cut else cut


@dataclass(frozen=True)
class Citation:
    n: int
    document_id: str
    title: str
    edition: str | None
    issuing_authority: str
    source_class: str
    resource_page: str
    download_url: str | None
    publication_date: str | None
    page: int
    chunk_id: str
    chunk_sha256: str
    document_sha256: str
    extraction_sha256: str
    score: float
    quote: str


@dataclass(frozen=True)
class DocumentAnswer:
    status: Literal["answered", "abstained"]
    code: str | None
    method: Method
    text: str
    citations: tuple[Citation, ...]
    caveats: tuple[str, ...]
    index_id: str
    threshold: float
    trace: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def answer(
    retrieval: Retrieval, index: Index, question: str, max_citations: int = 3
) -> DocumentAnswer:
    """An extractive, cited answer from a retrieval, or an abstention that says why."""
    trace = {"method": retrieval.method, "index_id": index.index_id,
             "threshold": retrieval.threshold, "candidates": len(retrieval.candidates),
             "above_threshold": len(retrieval.hits)}  # fmt: skip
    if retrieval.status != "answered":
        reason = {
            "rag.query_empty": "The question has no searchable terms.",
            "rag.no_evidence": "No passage in the approved documents is relevant enough to cite.",
        }[retrieval.code]
        return DocumentAnswer("abstained", retrieval.code, retrieval.method,
                              f"Cannot answer ({retrieval.code}): {reason}", (), (),
                              index.index_id, retrieval.threshold, trace)  # fmt: skip
    terms = query_terms(question)
    citations, caveats = [], []
    for n, hit in enumerate(retrieval.hits[:max_citations], start=1):
        doc = index.corpus.document(hit.document_id)
        quote = best_excerpt(hit.text, terms)
        if quote not in hit.text:  # quotes are verbatim, never rewritten (not an assert: -O)
            raise RuntimeError(f"excerpt for {hit.chunk_id} is not verbatim chunk text")
        citations.append(
            Citation(
                n,
                doc.document_id,
                doc.title,
                doc.edition,
                doc.issuing_authority,
                doc.source_class,
                doc.resource_page,
                doc.download_url,
                doc.publication_date,
                hit.page,
                hit.chunk_id,
                hit.text_sha256,
                doc.sha256,
                doc.extraction_sha256,
                hit.score,
                quote,
            )  # fmt: skip
        )
        for limitation in doc.limitations:
            if limitation not in caveats:
                caveats.append(limitation)
    editions = sorted({c.edition or "unknown" for c in citations})
    if len(editions) > 1:
        caveats.insert(
            0,
            f"Passages come from different editions ({', '.join(editions)}); they are quoted "
            "separately and not combined.",
        )
    caveats.insert(0, "Quoted document text, not a CivicMind calculation; check the cited page.")
    lines = [f'[{c.n}] {c.title} ({c.edition}), page {c.page}: "{c.quote}"' for c in citations]
    text = "Relevant passages from approved documents:\n" + "\n".join(lines)
    return DocumentAnswer("answered", None, retrieval.method, text, tuple(citations),
                          tuple(caveats), index.index_id, retrieval.threshold, trace)  # fmt: skip


__all__ = [
    "DEFAULT_RETRIEVAL",
    "RAG_CODES",
    "Citation",
    "DocumentAnswer",
    "Hit",
    "Retrieval",
    "RetrievalConfig",
    "answer",
    "best_excerpt",
    "query_terms",
    "retrieve",
]
