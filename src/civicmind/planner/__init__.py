"""Query planning: turn a question into a validated, inspectable query specification.

Responsibilities (not yet implemented):
- ``QuerySpec``: intent, metric, entities, geography (with ward scheme), period, filters,
  desired output.
- Resolve entities against the actual data vocabulary and alias tables. Unresolved
  entities lead to clarification, not guessing.
- Feasibility check before any tool runs: coverage, period, granularity, join legality,
  forecast/causal requests. The decision is answer, clarify or abstain, with a reason.
- Fail closed: an unmatched or ambiguous question is never routed to a nearby intent.

Boundary: reads catalogue metadata; produces plans for ``orchestrator``.
"""
