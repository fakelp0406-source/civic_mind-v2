"""Application factory for the CivicMind HTTP API.

Run locally::

    python -m uvicorn civicmind.api.app:create_app --factory --host 127.0.0.1 --port 8000

``create_app`` loads no structured data: manifests are read per request, and datasets are
ingested only when a planned query needs them (exactly as the CLI does). It does load and verify
the approved-document index once (stage 2F, ``civicmind.api.retrieval``); it never builds or
downloads one.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from civicmind import __version__
from civicmind.api import errors
from civicmind.api.retrieval import DocumentRetrieval
from civicmind.api.routes import health_router, v1
from civicmind.orchestrator.pipeline import ROOT, answer_question

log = logging.getLogger("civicmind.api")

MAX_BODY_BYTES = 8 * 1024
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class _TooLarge(StarletteHTTPException):
    """413. An HTTPException so FastAPI re-raises it when the limit trips mid-body.

    FastAPI converts any other exception raised while reading a body into
    "400 There was an error parsing the body"; that hid the limit for chunked uploads.
    """

    def __init__(self, limit: int = MAX_BODY_BYTES):
        super().__init__(status_code=413, detail=f"The request body exceeds {limit} bytes.")


class RequestContext:
    """Pure ASGI middleware: request id, body-size limit and one access-log line per request.

    The access log records method, path, status, outcome code and duration - never the
    question text or any header other than the request id.
    """

    def __init__(self, app: ASGIApp, max_body: int = MAX_BODY_BYTES):
        self.app = app
        self.max_body = max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        supplied = headers.get(b"x-request-id", b"").decode("latin-1")
        rid = supplied if REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = rid
        started = time.perf_counter()
        status = {"code": 500, "sent": False}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"], status["sent"] = message["status"], True
                raw = [(k, v) for k, v in message.get("headers", []) if k != b"x-request-id"]
                message = {**message, "headers": [*raw, (b"x-request-id", rid.encode())]}
            await send(message)

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    raise _TooLarge(self.max_body)
            return message

        try:
            declared = int(headers.get(b"content-length", b"0") or 0)
        except ValueError:
            declared = 0
        try:
            if declared > self.max_body:
                raise _TooLarge(self.max_body)
            await self.app(scope, limited_receive, send_with_id)
        except _TooLarge:
            if status["sent"]:
                raise
            await self._too_large(rid, send_with_id)
        finally:
            log.info(
                "request_id=%s method=%s path=%s status=%s outcome=%s ms=%.1f",
                rid,
                scope.get("method"),
                scope.get("path"),
                status["code"],
                state.get("outcome", "-"),
                (time.perf_counter() - started) * 1000,
            )

    async def _too_large(self, rid: str, send: Send) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "request.too_large",
                    "message": f"The request body exceeds {self.max_body} bytes.",
                    "request_id": rid,
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def create_app(
    root: str | Path = ROOT,
    *,
    docs: bool = True,
    answer: Callable[..., object] = answer_question,
    documents: bool = True,
    router: object | None = None,
) -> FastAPI:
    """Build the API. ``root`` is the repository root holding ``data/manifests``.

    ``answer`` is the pipeline entry point; it is a parameter only so tests can inject
    failures. ``documents=False`` serves the deterministic pipeline alone; ``router`` is a
    prebuilt, already verified ``Router`` (tests). Clients cannot choose any of these, the
    root, or any dataset or document.
    """
    app = FastAPI(
        title="CivicMind AI",
        version=__version__,
        summary="Deterministic, evidence-checked answers about Bengaluru water and road data.",
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.root = Path(root)
    app.state.answer = answer
    app.state.retrieval = DocumentRetrieval(root, answer, router=router, enabled=documents)
    app.add_exception_handler(RequestValidationError, errors.on_validation_error)
    app.add_exception_handler(StarletteHTTPException, errors.on_http_error)
    app.add_exception_handler(Exception, errors.on_unhandled)
    app.include_router(health_router)
    app.include_router(v1)
    app.add_middleware(RequestContext)
    _configure_logging()
    return app


def _configure_logging() -> None:
    """Give the API logger a stderr handler once, so access lines show under Uvicorn.

    Uvicorn configures only its own loggers. Records still propagate, so a host application
    (or pytest) that configures the root logger receives them too.
    """
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s %(message)s"))
        log.addHandler(handler)
    if log.level == logging.NOTSET:
        log.setLevel(logging.INFO)


__all__ = ["MAX_BODY_BYTES", "RequestContext", "create_app"]
