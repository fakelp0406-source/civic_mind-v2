"""HTTP status mapping and safe error responses.

Pipeline outcomes keep the pipeline's own refusal codes; only the HTTP status is chosen here:

* ``200`` - answered, or refused because of the question or the catalogue (planner,
  feasibility and analytics stages; ingest refusals caused by trust status).
* ``503`` - refused because server-side data failed an integrity or evidence check (any
  other ingest refusal, ``evidence.invalid``). The body is still a refusal; no number.
* ``500`` - ``pipeline.internal_error`` / ``pipeline.step_limit``, or an unhandled exception
  in the API layer (generic envelope; the exception text is logged, never returned).

Request problems use the envelope ``{"error": {code, message, request_id, fields?}}``:
``400 request.malformed_json``, ``413 request.too_large``, ``422 request.invalid``,
``404 request.not_found``, ``405 request.method_not_allowed``.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from civicmind.api.schemas import ErrorBody, ErrorResponse

log = logging.getLogger("civicmind.api")

#: Ingest refusals that reflect a dataset's trust status, not damaged server data.
TRUST_STATE_CODES = frozenset(
    {
        "status.quarantined",
        "status.rejected",
        "status.not_trusted",
        "modelled.not_trusted",
        "exploratory.not_permitted",
    }
)


def status_for(status: str, stage: str | None, code: str | None) -> int:
    """HTTP status for a pipeline answer (see the module docstring)."""
    if status == "answered":
        return 200
    if stage == "pipeline" and (code or "").startswith("pipeline."):
        return 500
    if stage == "evidence" or (stage == "ingest" and code not in TRUST_STATE_CODES):
        return 503
    return 200


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def error_response(
    request: Request, status: int, code: str, message: str, fields: list[str] | None = None
) -> JSONResponse:
    rid = request_id_of(request)
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, request_id=rid, fields=fields)
    )
    return JSONResponse(
        jsonable_encoder(body, exclude_none=True),
        status_code=status,
        headers={"X-Request-ID": rid},
    )


async def on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if any(e.get("type") == "json_invalid" for e in errors):
        return error_response(
            request, 400, "request.malformed_json", "The body is not valid JSON."
        )
    fields = sorted({".".join(str(p) for p in e.get("loc", ()) if p != "body") for e in errors})
    return error_response(
        request,
        422,
        "request.invalid",
        'Send a JSON object with one non-empty string field "question" '
        "(at most 1000 characters, no other fields).",
        [f for f in fields if f] or None,
    )


async def on_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    codes = {
        404: "request.not_found",
        405: "request.method_not_allowed",
        413: "request.too_large",  # body limit hit while the body was being read (chunked)
    }
    code = codes.get(exc.status_code, "request.http_error")
    message = (
        exc.detail
        if exc.status_code == 413 and isinstance(exc.detail, str)
        else "The request cannot be served."
    )
    return error_response(request, exc.status_code, code, message)


async def on_unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception(
        "unhandled error request_id=%s path=%s", request_id_of(request), request.url.path
    )
    return error_response(
        request, 500, "internal_error", "An internal error occurred; no answer is given."
    )


__all__ = [
    "TRUST_STATE_CODES",
    "error_response",
    "on_http_error",
    "on_unhandled",
    "on_validation_error",
    "request_id_of",
    "status_for",
]
