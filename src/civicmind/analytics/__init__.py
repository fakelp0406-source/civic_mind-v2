"""Deterministic analytics: the only source of numeric answers.

Implemented (each returns an ``AnalyticsResult`` with unit, method, denominator, evidence and
caveats, or raises ``AnalyticsRefused`` with a stable code):
- ``water.water_total`` (A1); ``water.water_rank_rows`` (A2, published rows) and
  ``water.water_rank_wards`` (A2, unique wards; refuses repeated ward numbers);
  ``water.water_month_change``
  (A3): BWSSB monthly ward water consumption, one trusted dataset per month.
- ``roads.road_city_value`` and ``roads.road_top_cities`` (A4): MoRTH million-plus city
  Annexure 47, one edition at a time, verbatim columns and city labels.

Responsibilities (the rest not yet implemented):
- Typed, tested operations (lookup, count, sum, mean, share, rate, rank, compare, trend)
  over validated datasets from ``civicmind.catalog``.
- Each operation declares its units, filters, denominator, tie rule, missing-value rule,
  and time/geographic granularity, and returns structured evidence.
- No forecasting without a separately approved, evaluated method.

Boundary: depends on ``catalog`` and ``evidence`` only. Never calls a language model.
"""
