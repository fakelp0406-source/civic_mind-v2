"""Approved-document retrieval behind ``POST /api/v1/query`` (stage 2F).

The stage 2D ``Router`` (BM25 gate, stage 2E thresholds, unchanged) is added *after* the
deterministic pipeline; it never replaces it:

* **Deterministic first, unchanged.** The route handler runs ``answer_question`` exactly as
  before. If it answers, refuses with a server-side failure (any refusal ``status_for`` maps to
  HTTP 5xx: damaged data, failed evidence check, internal error; the router is then not even
  consulted), refuses for another protected reason, or the question is not a document
  question, the response is the deterministic one byte for byte (no ``route`` field).
* **Otherwise the router decides.** A document or mixed answer carries ``route`` and
  ``citations``. A refusal keeps the deterministic ``refusal.code``; the router's own outcome
  (why documents could not answer either) is ``route.code``.
* **Startup verification.** ``Router`` loads the index once and verifies it fully: approved
  manifests, PDF and page-file hashes, recomputed chunks, every index file's hash, the model
  specification in the index id. Nothing is downloaded or built. A failure leaves retrieval
  unavailable with a code (``rag.index_unavailable`` / ``rag.index_stale`` /
  ``rag.corpus_integrity``) that ``/api/v1/ready`` reports and document questions refuse with.
* **Before use.** Before document evidence is returned, the approved corpus is re-derived from
  the manifests (``Router.index_is_current``, metadata only) and must equal the loaded index's
  corpus.
  A document quarantined, withdrawn or re-reviewed since startup withholds the answer
  (``rag.index_stale``, HTTP 503) and keeps retrieval unavailable until the process restarts.
* **Fail closed.** An exception while routing never becomes an answer: the deterministic
  refusal is returned with ``route.code = pipeline.internal_error`` (HTTP 500), details logged.

Concurrency: the index is read-only after loading, but its in-memory BM25 index is one SQLite
connection shared by FastAPI's worker threads. Routing is therefore always serialised with a
lock, whatever the SQLite build's thread-safety mode: one ``execute().fetchall()`` at a time on
that connection. Deterministic answers never take the lock (the router is not consulted), so
the cost falls only on questions the pipeline refused (~10 ms each; a mixed question also runs
the pipeline for each part while holding it).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from civicmind.api.errors import status_for
from civicmind.api.schemas import (
    CitationOut,
    QueryResponse,
    RetrievalReadiness,
    RouteOut,
    RoutePartOut,
    from_answer,
)
from civicmind.respond.compose import Answer

log = logging.getLogger("civicmind.api")

#: Router codes that mean server-side document data failed a check (HTTP 503, like datasets).
INTEGRITY_CODES = frozenset({"rag.index_stale", "rag.corpus_integrity"})
#: Router traces that mean "the deterministic outcome stands": the response is left untouched.
PASSTHROUGH = "deterministic"


class DocumentRetrieval:
    """Holds the verified router for one app. Built once in ``create_app``."""

    def __init__(
        self,
        root: str | Path,
        answer_fn: Callable[[str, Path], Answer],
        router: Any | None = None,
        enabled: bool = True,
    ):
        self.root = Path(root)
        self.enabled = enabled
        self.router = None
        self._startup_error: str | None = None
        self._state = threading.Lock()
        self._serial = threading.Lock()  # one routing call (one SQLite connection user) at a time
        if not enabled:
            return
        if router is None:
            try:
                from civicmind.orchestrator.router import Router

                router = Router(self.root, answer_fn=answer_fn)
            except Exception:  # noqa: BLE001 - retrieval unavailable; analytics unaffected
                log.exception("document retrieval could not be initialised")
                self._startup_error = "rag.index_unavailable"
                return
        if router.config.gate != "bm25" or router.encoder is not None:
            raise ValueError("the API serves the evaluated BM25 gate only")
        self.router = router

    # --- state ------------------------------------------------------------------------------

    def _index(self):
        return self.router.index if self.router is not None else None

    def _current(self, index) -> bool:
        """The loaded index still describes exactly what the manifests approve now."""
        return self.router.index_is_current(index)

    def _mark_stale(self) -> None:
        with self._state:
            if self.router is not None:
                self.router.index, self.router.index_error = None, "rag.index_stale"
        log.warning("document index no longer matches the approved manifests; disabled")

    def status(self) -> RetrievalReadiness:
        if not self.enabled:
            return RetrievalReadiness(status="disabled")
        index = self._index()
        if index is not None and not self._current(index):
            self._mark_stale()
            index = None
        if index is None:
            code = self._startup_error or self.router.index_error or "rag.index_unavailable"
            return RetrievalReadiness(status="unavailable", code=code)
        return RetrievalReadiness(
            status="ready",
            index_id=index.index_id,
            documents=[d.document_id for d in index.corpus.documents],
            chunks=len(index.chunks),
        )

    # --- routing ----------------------------------------------------------------------------

    def route(self, question: str, deterministic: Answer):
        """``(routed, index_id)``, or ``None`` when the deterministic answer stands unchanged."""
        if self.router is None or deterministic.status == "answered":
            return None
        if status_for(deterministic.status, deterministic.stage, deterministic.code) >= 500:
            # A server-side failure (damaged data, failed evidence check, internal error) is
            # never answered from documents: that would hide it. Same mapping as the response.
            return None
        index = self._index()
        with self._serial:
            routed = self.router.route(question, deterministic=deterministic)
        if routed.trace[:1] == (PASSTHROUGH,):
            return None
        cited = routed.citations or any(p.citations for p in routed.parts)
        if cited and (index is None or not self._current(index)):
            self._mark_stale()
            routed = replace(
                routed,
                route="refused",
                status="refused",
                text="Cannot answer (rag.index_stale): the approved documents changed after "
                "the index was loaded; no document evidence is returned.",
                code="rag.index_stale",
                stage="router",
                reason="The approved documents changed after the index was loaded.",
                document=None,
                citations=(),
                caveats=(),
                parts=(),
                trace=(*routed.trace, "before_use_check:failed"),
            )
        return routed, index.index_id if index is not None else None


# --- response mapping -------------------------------------------------------------------------


def _citations(items) -> list[CitationOut]:
    return [CitationOut(**c) for c in items]


def _part(part, request_id: str) -> RoutePartOut:
    result, evidence = None, []
    if part.analytics is not None and part.status == "answered":
        mapped = from_answer(Answer(**part.analytics), request_id)
        result, evidence = mapped.result, mapped.evidence
    return RoutePartOut(
        kind=part.route,
        status=part.status,
        question=part.question,
        answer_text=part.text,
        code=part.code,
        result=result,
        evidence=evidence,
        citations=_citations(part.citations),
    )


def routed_response(
    deterministic: Answer, routed, index_id: str | None, request_id: str
) -> tuple[QueryResponse, int]:
    """The response for a question the router handled, and its HTTP status."""
    base = from_answer(deterministic, request_id)
    parts = [_part(p, request_id) for p in routed.parts]
    route = RouteOut(
        kind=routed.route,
        code=routed.code,
        reason=routed.reason,
        index_id=index_id,
        editions=list(routed.editions),
        parts=parts,
        trace=list(routed.trace),
    )
    if routed.status == "answered":
        response = base.model_copy(
            update={
                "status": "answered",
                "answer_text": routed.text,
                "refusal": None,
                "result": None,  # document text is never a CivicMind value
                "caveats": list(routed.caveats),
                "assumptions": [],
                "evidence": [e for p in parts for e in p.evidence],
                "coverage": None,
                "route": route,
                "citations": _citations(routed.citations),
            }
        )
        return response, 200
    http = status_for(deterministic.status, deterministic.stage, deterministic.code)
    codes = {routed.code, *(p.code for p in routed.parts)}
    if codes & INTEGRITY_CODES:
        http = max(http, 503)
    for p in routed.parts:
        if p.analytics is not None and p.status == "refused":
            http = max(http, status_for(p.status, p.stage, p.code))
    return base.model_copy(update={"route": route, "citations": []}), http


def failed_response(deterministic: Answer, request_id: str) -> tuple[QueryResponse, int]:
    """Routing raised: the deterministic refusal, flagged as an internal failure (no answer)."""
    if deterministic.status != "refused":
        raise ValueError("failed_response applies to refusals only; an answer stands unchanged")
    route = RouteOut(
        kind="refused",
        code="pipeline.internal_error",
        reason="Document routing failed; no document answer is given.",
        index_id=None,
        trace=["router:error"],
    )
    base = from_answer(deterministic, request_id)
    return base.model_copy(update={"route": route, "citations": []}), 500


__all__ = [
    "INTEGRITY_CODES",
    "DocumentRetrieval",
    "failed_response",
    "routed_response",
]
