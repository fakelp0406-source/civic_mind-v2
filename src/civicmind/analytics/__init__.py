"""Deterministic analytics: the only source of numeric answers.

Responsibilities (not yet implemented):
- Typed, tested operations (lookup, count, sum, mean, share, rate, rank, compare, trend)
  over validated datasets from ``civicmind.catalog``.
- Each operation declares its units, filters, denominator, tie rule, missing-value rule,
  and time/geographic granularity, and returns structured evidence.
- No forecasting without a separately approved, evaluated method.

Boundary: depends on ``catalog`` and ``evidence`` only. Never calls a language model.
"""
