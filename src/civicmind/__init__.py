"""CivicMind AI: evidence-grounded, bounded-agent municipal decision intelligence.

Skeleton only. Each subpackage marks an architectural boundary; see docs/architecture.md.
Importing this package must stay lightweight: no data access, no network, no heavy
third-party imports at import time.
"""

__version__ = "0.0.1"

#: Architectural layers, in the order data flows through them.
LAYERS: tuple[str, ...] = (
    "catalog",
    "analytics",
    "rag",
    "graph",
    "planner",
    "orchestrator",
    "evidence",
    "respond",
    "api",
)

__all__ = ["LAYERS", "__version__"]
