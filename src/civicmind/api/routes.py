"""HTTP routes. Thin: every query goes to the existing pipeline first, unchanged.

``POST /api/v1/query`` calls ``answer_question`` (parse -> feasibility -> trusted ingest ->
analytics -> evidence validation -> composer) and maps its ``Answer`` onto the response
model. Only when that refuses does the document router run (``civicmind.api.retrieval``); a
response it did not change is exactly the deterministic one. No route reads datasets, accepts
dataset selectors or paths, or uses exploratory ingestion. Readiness reads manifests
(metadata) and checks that promoted files exist; it never ingests or hashes data -
``ingest()`` re-verifies every file on each query. It also reports the document index state
(``retrieval``), which never changes the readiness ``status``.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from civicmind.api.errors import request_id_of, status_for
from civicmind.api.retrieval import failed_response, routed_response
from civicmind.api.schemas import (
    ROUTE_FIELDS,
    ErrorResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    ReadinessResponse,
    from_answer,
)
from civicmind.catalog.manifest import read_manifest

log = logging.getLogger("civicmind.api")

health_router = APIRouter(tags=["health"])
v1 = APIRouter(prefix="/api/v1")

ERRORS = {
    400: {"model": ErrorResponse, "description": "Malformed JSON body"},
    413: {"model": ErrorResponse, "description": "Request body too large"},
    422: {"model": ErrorResponse, "description": "Invalid request fields"},
    500: {"model": QueryResponse, "description": "Internal failure (refusal; no answer)"},
    503: {"model": QueryResponse, "description": "Server data failed an integrity check"},
}


@health_router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness only: the process is running. Says nothing about data."""
    return HealthResponse(status="ok")


def readiness(root: Path) -> tuple[ReadinessResponse, int]:
    try:
        manifests = [read_manifest(p) for p in sorted((root / "data/manifests").glob("*.yaml"))]
    except Exception:  # noqa: BLE001 - reported as not ready, details logged only
        log.exception("readiness: manifests could not be read")
        return ReadinessResponse(status="not_ready", reason="catalogue.unreadable"), 503
    promoted = [m for m in manifests if m.status == "promoted"]
    counts = Counter(m.dataset_id.split("-", 1)[0].lower() for m in promoted)
    body = {"promoted_datasets": dict(sorted(counts.items())), "manifests": len(manifests)}
    if not promoted:
        return ReadinessResponse(status="not_ready", reason="catalogue.empty", **body), 503
    missing = [m for m in promoted if not m.promoted_to or not (root / m.promoted_to).is_file()]
    if missing:
        log.warning("readiness: %d promoted files missing", len(missing))
        return ReadinessResponse(status="not_ready", reason="data.missing", **body), 503
    return ReadinessResponse(status="ready", **body), 200


@v1.get(
    "/ready",
    tags=["health"],
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse, "description": "Not ready"}},
)
def ready(request: Request) -> JSONResponse:
    """Readiness: catalogue readable, at least one promoted dataset, promoted files present.

    Hashes are not re-checked here (that happens in ``ingest()`` on every query)."""
    body, status = readiness(request.app.state.root)
    body.retrieval = request.app.state.retrieval.status()  # reported; never changes `status`
    return JSONResponse(jsonable_encoder(body), status_code=status)


@v1.post("/query", tags=["query"], response_model=QueryResponse, responses=ERRORS)
def query(body: QueryRequest, request: Request) -> JSONResponse:
    """Answer one question with the deterministic pipeline, or refuse with a stable code.

    Questions the pipeline refuses may then be answered from approved documents (definitions,
    methodology, explicitly attributed report content) with verbatim, page-cited passages;
    those responses add ``route`` and ``citations``. A refusal keeps the pipeline's code.

    A refusal is a normal outcome (HTTP 200) unless it reports damaged server data (503) or
    an internal failure (500)."""
    answer = request.app.state.answer(body.question, request.app.state.root)
    request.state.outcome = answer.code or answer.status
    rid = request_id_of(request)
    try:
        routed = request.app.state.retrieval.route(body.question, answer)
    except Exception:  # noqa: BLE001 - fail closed; the text is logged, never returned
        log.exception("document routing failed request_id=%s", rid)
        if answer.status != "answered":  # a refusal: flag the failure (500, no answer)
            request.state.outcome = "route:pipeline.internal_error"
            response, status = failed_response(answer, rid)
            return JSONResponse(jsonable_encoder(response), status_code=status)
        # An answer was validated by the pipeline without retrieval; a retrieval error must
        # not turn it into a 500 or alter it. It is returned exactly as the deterministic API.
        routed = None
    if routed is None:  # the deterministic outcome stands, unchanged
        response = from_answer(answer, rid)
        return JSONResponse(
            jsonable_encoder(response, exclude=set(ROUTE_FIELDS)),
            status_code=status_for(answer.status, answer.stage, answer.code),
        )
    response, status = routed_response(answer, *routed, rid)
    request.state.outcome = f"route:{routed[0].code or routed[0].route}"
    return JSONResponse(jsonable_encoder(response), status_code=status)


__all__ = ["health_router", "readiness", "v1"]
