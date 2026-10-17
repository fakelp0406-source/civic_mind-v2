"""Bounded orchestration: execute a plan with read-only tools under explicit limits.

Responsibilities (not yet implemented):
- Tool registry of read-only tools (analytics, rag, graph, catalog) with typed arguments.
- Limits: maximum steps, per-tool timeouts, at most one repair retry, explicit stop conditions.
- Collect evidence, check consistency and coverage, then hand an evidence package to ``respond``.
- Safe audit trail (JSONL): plan steps, tool names, statuses and source ids. No secrets,
  no personal data, no hidden reasoning.
- No writes to data, no external contact, no real-world municipal actions.

Boundary: depends on ``planner``, the tool layers and ``evidence``.
"""
