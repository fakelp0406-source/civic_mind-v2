"""HTTP API (FastAPI): a thin, versioned layer over the deterministic pipeline.

Endpoints: ``GET /health`` (liveness), ``GET /api/v1/ready`` (catalogue readiness) and
``POST /api/v1/query`` (answers via ``orchestrator.pipeline.answer_question``). Modules:
``app`` (factory ``create_app``), ``routes``, ``schemas``, ``errors``.

Boundary: depends on ``orchestrator``, ``respond`` and ``catalog``. Importing this package
loads nothing (FastAPI is imported only by its submodules); secrets stay server-side.
"""
