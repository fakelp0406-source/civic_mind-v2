"""Civic Knowledge Graph built only from source-supported entities and relations.

Responsibilities (not yet implemented):
- Schema: nodes such as City, Corporation, Zone, Ward (with ward scheme), AssemblyConstituency,
  PoliceStation, STP, WasteFacility, Dataset, Indicator, ReportingPeriod, Document.
- Every edge carries ``source_dataset``, ``source_row`` and ``valid_period``. No causal edges,
  no merges without an alias-table entry, and no equivalence between ward schemes
  (BBMP-198 vs GBA-369) without an official crosswalk.
- Query templates for entity context, cross-source lookup and evidence paths.

Boundary: depends on ``catalog`` and ``evidence``. An in-memory representation is the
provisional choice; a graph database is a future option only if scale or queries require it.
"""
