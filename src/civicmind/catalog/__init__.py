"""Catalogue and validation layer: what data exists, where it came from, and whether it is valid.

Responsibilities (manifests, fingerprinting, profiling, validators, identifier assessment,
review decisions and the promotion gate are implemented; loading promoted data is not):
- Load and validate per-dataset manifests (``data/manifests/*.yaml``): source URL, publisher,
  licence evidence, retrieval date, SHA-256, period, geography, ward scheme, caveats,
  sensitivity, and verification status.
- Verify that raw files match their pinned hashes; never modify raw files.
- Run dataset-specific validators (``catalog.validators``) and record findings as data,
  rather than silently "fixing" source values.

Boundary: depends on nothing else in ``civicmind``. Every other layer reads datasets
only through this layer.
"""
