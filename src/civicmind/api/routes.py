"""HTTP routes. Thin: every query goes to the existing pipeline, unchanged.

``POST /api/v1/query`` calls ``answer_question`` (parse -> feasibility -> trusted ingest ->
analytics -> evidence validation -> composer) and maps its ``Answer`` onto the response
model. No route reads datasets, accepts dataset selectors or paths, or uses exploratory
ingestion. Readiness reads manifests (metadata) and checks that promoted files exist; it never
ingests or hashes data - ``ingest()`` re-verifies every file on each query.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from civicmind.api.errors import request_id_of, status_for
from civicmind.api.schemas import (
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
    return JSONResponse(jsonable_encoder(body), status_code=status)


@v1.post("/query", tags=["query"], response_model=QueryResponse, responses=ERRORS)
def query(body: QueryRequest, request: Request) -> JSONResponse:
    """Answer one question with the deterministic pipeline, or refuse with a stable code.

    A refusal is a normal outcome (HTTP 200) unless it reports damaged server data (503) or
    an internal failure (500)."""
    answer = request.app.state.answer(body.question, request.app.state.root)
    request.state.outcome = answer.code or answer.status
    response = from_answer(answer, request_id_of(request))
    return JSONResponse(
        jsonable_encoder(response),
        status_code=status_for(answer.status, answer.stage, answer.code),
    )


__all__ = ["health_router", "readiness", "v1"]
