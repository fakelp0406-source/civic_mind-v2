"""HTTP API (FastAPI): the only interface the future website will use.

Planned endpoints (not yet implemented): ``/health``, ``/ask``, ``/datasets``,
``/datasets/{id}``, ``/documents``, ``/feedback``. Typed request and response schemas
expose the answer, evidence, citations, plan/tool summary and abstention reason.

Boundary: depends on ``orchestrator``, ``respond`` and ``catalog``. Built by an app factory,
so importing this package loads no data and starts no server. Secrets stay server-side.
"""
