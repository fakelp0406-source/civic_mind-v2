"""Bounded routing between deterministic analytics and approved-document retrieval (stage 2D).

Served by the HTTP API through ``civicmind.api.retrieval`` (stage 2F; BM25 gate only).
``Router.route(question)`` returns a ``RoutedAnswer`` and never
fabricates: every outcome is a deterministic answer, a cited document answer, a mixed answer whose
parts are each independently supported, or a refusal with a stable code.

Order of decisions (the first that applies wins):

1. **Deterministic first.** The existing pipeline (``answer_question``) runs on the whole
   question. If it answers, that answer is returned unchanged (route ``analytics``).
2. **Protected refusals stand.** If it refuses for a reason documents must never override (input
   safety, prediction, cross-domain or cross-edition mixing, trust state, evidence validation,
   and every ingest failure of server-side data: ``INGEST_FAILURE_CODES``), the refusal is
   returned unchanged.
3. **Mixed questions.** A question made of two clauses joined by "and <question word>" is split.
   Each part is routed on its own; the parts are combined only if both are answered with their own
   evidence. Otherwise ``route.mixed_unsupported``, with each part's code. A year named anywhere
   applies to both parts.
4. **Document eligibility** (closed patterns, no model): the question must be a definition or
   methodology question, or explicitly attribute the content to the report or ministry. Numeric
   questions ("how many", "what share", …) and causal questions ("why …") go to documents **only**
   with explicit attribution ("according to the report", "does the report …"); otherwise the
   deterministic refusal stands. Documents are never a numeric fallback.
5. **Edition and currency guards.** "Latest", "current", "recent" and similar refuse with
   ``rag.currency_unverifiable``: the newest approved document is not assumed to be current. A
   named year with an approved edition restricts retrieval to that edition. A year newer than
   every approved edition refuses with ``rag.edition_unavailable`` (a 2024 question is never
   answered from 2023 or 2019). An older year without its own edition may be answered only from
   later editions, which report earlier years.
6. **Domain guard.** A question about a domain with no approved document (water, waste, census)
   refuses with ``rag.no_eligible_documents``.
7. **Retrieval with a gate** (``RouterConfig.gate``: ``bm25`` or ``dense``, calibrated thresholds
   from stage 2E), restricted to eligible documents. Every cited hit is re-checked: approved corpus
   document, allowed edition, page neither excluded nor textless. A violation fails closed
   (``rag.ineligible_evidence``).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from civicmind.orchestrator.pipeline import ROOT, answer_question
from civicmind.planner.parser import detect_domain
from civicmind.rag.corpus import CorpusIntegrityError, approved_digest
from civicmind.rag.embed import MINILM, Encoder, ModelSpec
from civicmind.rag.index import Index, IndexStale, IndexUnavailable, load_index
from civicmind.rag.retrieve import (
    DEFAULT_RETRIEVAL,
    RAG_CODES,
    DocumentAnswer,
    RetrievalConfig,
    answer,
    retrieve,
)
from civicmind.respond.compose import Answer

log = logging.getLogger("civicmind.router")

Route = Literal["analytics", "documents", "mixed", "refused"]

#: Ingest refusals that mean server-side dataset bytes or their validation failed (HTTP 503):
#: integrity (hash, size, missing record), missing or non-CSV files, unparseable CSV, unsafe
#: paths, schema and validation failures, and a review bound to other bytes. Listed explicitly
#: (no ``ingest`` wildcard): trust-state ingest refusals are protected separately below, and
#: ``tests/test_router.py`` checks this list against every code ``catalog/ingest.py`` raises.
#: A document answer must never stand in for damaged data: it would hide the failure.
INGEST_FAILURE_CODES = frozenset(
    {
        "integrity.hash_mismatch",
        "integrity.size_mismatch",
        "integrity.not_recorded",
        "file.missing",
        "file.not_csv",
        "path.unsafe",
        "csv.decode_error",
        "csv.empty",
        "csv.malformed",
        "csv.ragged_rows",
        "schema.duplicate_columns",
        "schema.family_mismatch",
        "schema.manifest_mismatch",
        "schema.unknown",
        "validation.errors",
        "validation.unaccepted_warnings",
        "review.stale",
    }
)

#: Deterministic refusals that documents must never override.
PROTECTED_CODES = frozenset(
    {
        *INGEST_FAILURE_CODES,
        "query.empty",
        "query.too_long",
        "query.prompt_injection",
        "query.predictive",
        "query.cross_domain",
        "query.cross_edition",
        "query.unit_unsupported",
        "period.unavailable",
        "status.quarantined",
        "status.rejected",
        "status.not_trusted",
        "dataset.not_trusted",
        "modelled.not_trusted",
        "exploratory.not_permitted",
        "evidence.invalid",
        "pipeline.internal_error",
        "pipeline.step_limit",
    }
)
ROUTE_CODES = frozenset(
    {
        "route.mixed_unsupported",
        "rag.currency_unverifiable",
        "rag.edition_unavailable",
        "rag.no_eligible_documents",
        "rag.ineligible_evidence",
        "rag.corpus_integrity",
        *RAG_CODES,
    }
)

DEFINITION = re.compile(
    r"\b(defin(e|ed|es|ition|itions)|meaning|what\s+(is|are)\s+(an?|the)\b|what\s+counts\s+as|"
    r"what\s+are\b|methodolog\w*|formats?\b|project\b|strategy\b|scheme\b|meant\s+to\b|purpose\b|"
    r"under\s+which\b)",
    re.IGNORECASE,
)
ATTRIBUTION = re.compile(
    r"\b(according\s+to\s+the\s+(\d{4}\s+)?(report|ministry)|as\s+per\s+the\s+(\d{4}\s+)?report|"
    r"(the|this)\s+(\d{4}\s+)?report\b|(the|this)\s+ministry\b|morth\b|transport\s+research\s+wing|"
    r"\btrw\b)",
    re.IGNORECASE,
)
NUMERIC = re.compile(
    r"\b(how\s+many|how\s+much|what\s+(share|percentage|proportion|fraction|number)|number\s+of|"
    r"total|count|rank\w*|top\s+\d+|highest|lowest|compare\w*)\b",
    re.IGNORECASE,
)
CAUSAL = re.compile(r"\b(why|cause[sd]?|because|due\s+to|led\s+to)\b", re.IGNORECASE)
CURRENCY = re.compile(
    r"\b(latest|current|currently|newest|most\s+recent|recent|up[\s-]to[\s-]date|this\s+year|"
    r"now|today|so\s+far)\b",
    re.IGNORECASE,
)
YEAR = re.compile(r"(?<!\d)(19\d\d|20\d\d)(?!\d)")
SPLIT = re.compile(r",?\s+and\s+(?=(why|how|what|which|who|where|when|does|do|is|are)\b)", re.I)
DOCUMENT_DOMAINS = frozenset({"roads"})


@dataclass(frozen=True)
class RouterConfig:
    gate: Literal["bm25", "dense"] = "bm25"
    retrieval: RetrievalConfig = DEFAULT_RETRIEVAL


DEFAULT_ROUTER = RouterConfig()


@dataclass(frozen=True)
class RoutedAnswer:
    route: Route
    status: Literal["answered", "refused"]
    question: str
    text: str
    code: str | None = None
    stage: str | None = None
    reason: str | None = None
    analytics: dict | None = None  # the deterministic Answer, unchanged (as a dict)
    document: dict | None = None  # the extractive DocumentAnswer (as a dict)
    citations: tuple[dict, ...] = ()
    caveats: tuple[str, ...] = ()
    editions: tuple[str, ...] = ()  # editions retrieval was restricted to
    parts: tuple[RoutedAnswer, ...] = ()
    trace: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return asdict(self)


def _refuse(question: str, code: str, reason: str, stage: str = "router", **extra) -> RoutedAnswer:
    return RoutedAnswer(
        "refused",
        "refused",
        question,
        f"Cannot answer ({code}): {reason}",
        code=code,
        stage=stage,
        reason=reason,
        **extra,
    )


def _from_analytics(question: str, a: Answer, trace: tuple[str, ...]) -> RoutedAnswer:
    route: Route = "analytics" if a.status == "answered" else "refused"
    return RoutedAnswer(
        route,
        a.status,
        question,
        a.text,
        code=a.code,
        stage=a.stage,
        reason=a.reason,
        analytics=a.to_dict(),
        caveats=tuple(a.caveats),
        trace=(*trace, "analytics"),
    )


def document_eligible(question: str, deterministic_code: str | None) -> bool:
    """Whether a question the pipeline refused may be tried against documents."""
    attributed = bool(ATTRIBUTION.search(question))
    if NUMERIC.search(question) and not attributed:
        return False  # numbers come from analytics; documents are not a numeric fallback
    if (deterministic_code == "query.causal" or CAUSAL.search(question)) and not attributed:
        return False  # causal claims only as the report's own stated reasons
    return attributed or bool(DEFINITION.search(question))


class Router:
    """Load the verified index once; route questions. ``reload()`` re-verifies from disk."""

    def __init__(
        self,
        root: str | Path = ROOT,
        config: RouterConfig = DEFAULT_ROUTER,
        encoder: Encoder | None = None,
        answer_fn: Callable[[str, Path], Answer] = answer_question,
        index_spec: ModelSpec | None = MINILM,
    ):
        self.root, self.config, self.answer_fn = Path(root), config, answer_fn
        self.index_spec = index_spec  # the spec the index was built with (part of its id)
        if config.gate == "dense" and encoder is None:
            raise ValueError("the dense gate needs an encoder")
        self.encoder = encoder
        self.index: Index | None = None
        self.index_error: str | None = None
        self.reload()

    def reload(self) -> None:
        try:
            self.index = load_index(self.root, self.index_spec)
            self.index_error = None
        except IndexUnavailable:
            self.index, self.index_error = None, "rag.index_unavailable"
        except IndexStale:
            self.index, self.index_error = None, "rag.index_stale"
        except CorpusIntegrityError:
            self.index, self.index_error = None, "rag.corpus_integrity"
        except Exception:  # noqa: BLE001 - fail closed: an unreadable index is never used
            # e.g. a corrupt index_manifest.json or document manifest: it cannot be shown to
            # match the approved corpus, so it is treated as stale. Details are logged only.
            log.exception("document index could not be loaded")
            self.index, self.index_error = None, "rag.index_stale"

    def index_is_current(self, index: Index | None = None) -> bool:
        """The loaded index (or ``index``) still describes exactly what the manifests approve.

        Metadata only (``approved_digest``): cheap enough before every document answer. A
        document withdrawn, quarantined or re-reviewed since loading makes this false. Bytes
        are re-verified only by ``reload()``. Unreadable manifests count as not current.
        """
        index = index if index is not None else self.index
        if index is None:
            return False
        try:
            return approved_digest(self.root) == index.corpus.digest()
        except Exception:  # noqa: BLE001 - unreadable manifests cannot confirm the approval
            log.exception("approved corpus could not be re-derived from the manifests")
            return False

    # --- routing ----------------------------------------------------------------------------

    def route(self, question: str, deterministic: Answer | None = None) -> RoutedAnswer:
        """Route one question. ``deterministic`` is the pipeline's answer to this exact
        (whitespace-normalised) question when the caller already has it; it is used as is."""
        q = " ".join((question or "").split())
        det = deterministic if deterministic is not None else self.answer_fn(q, self.root)
        if det.status == "answered":
            return _from_analytics(q, det, ("deterministic",))
        if det.code in PROTECTED_CODES:
            return _from_analytics(q, det, ("deterministic", "protected_refusal"))
        parts = [p.strip(" ?.,") for p in SPLIT.split(q)[::2] if p and p.strip(" ?.,")]
        if len(parts) == 2:
            return self._mixed(q, parts)
        if not document_eligible(q, det.code):
            return _from_analytics(q, det, ("deterministic", "not_document_question"))
        return self._documents(q, YEAR.findall(q))

    def _mixed(self, question: str, parts: list[str]) -> RoutedAnswer:
        years = YEAR.findall(question)
        routed = []
        for part in parts:
            det = self.answer_fn(part, self.root)
            if (
                det.status == "answered"
                or det.code in PROTECTED_CODES
                or not document_eligible(part, det.code)
            ):
                routed.append(_from_analytics(part, det, ("mixed_part",)))
            else:
                routed.append(self._documents(part, YEAR.findall(part) or years))
        if all(r.status == "answered" for r in routed):
            text = "\n".join(f"Part {n} ({r.route}): {r.text}" for n, r in enumerate(routed, 1))
            caveats = tuple(dict.fromkeys(c for r in routed for c in r.caveats))
            citations = tuple(c for r in routed for c in r.citations)
            return RoutedAnswer(
                "mixed",
                "answered",
                question,
                text,
                citations=citations,
                caveats=caveats,
                parts=tuple(routed),
                editions=tuple(e for r in routed for e in r.editions),
                trace=("mixed",),
            )
        codes = ", ".join(f"part {n}: {r.code}" for n, r in enumerate(routed, 1) if r.code)
        return _refuse(
            question,
            "route.mixed_unsupported",
            f"Each part of a combined question needs its own supported answer ({codes}).",
            parts=tuple(routed),
            trace=("mixed",),
        )

    def _documents(self, question: str, years: list[str]) -> RoutedAnswer:
        trace = ("documents",)
        if CURRENCY.search(question):
            return _refuse(
                question,
                "rag.currency_unverifiable",
                "Documents are static editions; the newest approved edition is not "
                "assumed to be current. Name the edition year.",
                trace=trace,
            )
        domain = detect_domain(question)
        if domain is not None and domain not in DOCUMENT_DOMAINS:
            return _refuse(
                question,
                "rag.no_eligible_documents",
                f"No approved document covers the {domain} domain.",
                trace=trace,
            )
        if self.index is None:
            return _refuse(
                question,
                self.index_error or "rag.index_unavailable",
                "The document index is unavailable or does not match the approved corpus.",
                trace=trace,
            )
        # Every approved document of an allowed edition is searched: two approved documents of
        # the same edition are both eligible (none is silently dropped). Documents without an
        # edition are never eligible, because no edition guard could apply to them.
        editions = {d.edition for d in self.index.corpus.documents if d.edition}
        allowed = set(editions)
        for year in sorted(set(years)):
            if year in editions:
                allowed &= {year}
            elif int(year) > max(int(e) for e in editions):
                return _refuse(
                    question,
                    "rag.edition_unavailable",
                    f"No approved document covers {year}; later or other editions are "
                    "never used in its place.",
                    trace=trace,
                )
            else:
                allowed &= {e for e in editions if int(e) > int(year)}
        if not allowed:
            return _refuse(
                question,
                "rag.edition_unavailable",
                f"No single approved edition matches the years named ({', '.join(years)}).",
                trace=trace,
            )
        docs = frozenset(
            d.document_id for d in self.index.corpus.documents if d.edition in allowed
        )
        method = self.config.gate
        r = retrieve(self.index, question, method, self.encoder, self.config.retrieval, docs)
        doc_answer: DocumentAnswer = answer(r, self.index, question)
        if doc_answer.status != "answered":
            return _refuse(
                question,
                doc_answer.code,
                doc_answer.text.split(": ", 1)[-1],
                stage="retrieval",
                editions=tuple(sorted(allowed)),
                trace=(*trace, f"retrieve:{method}"),
            )
        for c in doc_answer.citations:
            if not self._eligible(c.document_id, c.page, allowed):
                return _refuse(
                    question,
                    "rag.ineligible_evidence",
                    "A retrieved passage failed the eligibility re-check.",
                    trace=(*trace, f"retrieve:{method}"),
                )
        return RoutedAnswer(
            "documents",
            "answered",
            question,
            doc_answer.text,
            document=doc_answer.to_dict(),
            citations=tuple(asdict(c) for c in doc_answer.citations),
            caveats=doc_answer.caveats,
            editions=tuple(sorted(allowed)),
            trace=(*trace, f"retrieve:{method}"),
        )

    def _eligible(self, document_id: str, page: int, allowed: set[str]) -> bool:
        doc = next((d for d in self.index.corpus.documents if d.document_id == document_id), None)
        return (
            doc is not None
            and doc.edition in allowed
            and page in doc.pages_indexed
            and page not in doc.excluded_pages
            and page not in doc.no_text_pages
        )


def route_question(question: str, root: str | Path = ROOT, **kwargs: Any) -> RoutedAnswer:
    """Convenience: build a Router and route one question (loads and verifies the index)."""
    return Router(root, **kwargs).route(question)


__all__ = [
    "DEFAULT_ROUTER",
    "INGEST_FAILURE_CODES",
    "PROTECTED_CODES",
    "ROUTE_CODES",
    "RoutedAnswer",
    "Router",
    "RouterConfig",
    "document_eligible",
    "route_question",
]
