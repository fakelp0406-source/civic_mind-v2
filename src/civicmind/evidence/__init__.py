"""Evidence model shared by all tools and the response layer.

Responsibilities (not yet implemented):
- Typed evidence items: dataset records (with row ids), calculation traces (operation,
  inputs, units, filters, denominator), document passages (doc id, page, section), and
  graph paths (edges with provenance).
- Stable citation identifiers that the response verifier can check.
- Explicit separation of observed data, calculated results, interpretation and caveats.

Boundary: pure data structures; depends on nothing else in ``civicmind``.
"""
