# Data provenance register

The authoritative record for each dataset is its manifest in `data/manifests/*.yaml`: source
URL, publisher, licence evidence, retrieval, SHA-256, size, encoding, schema, findings,
person review (bound to the SHA-256), status and promotion target.

## Current state (2026-10-17)

| Category | Count | Where |
|---|---|---|
| Datasets with manifests (batch 01) | 8 | `data/manifests/` |
| Trusted (promoted, review accepted) | 4: BWSSB Aug 2025, Mar 2026; MoRTH RA2019 A47, RA2024 A47 | `data/raw/` (git-ignored) |
| Quarantined | 3: BWSSB Apr 2025, May 2025; 2011 census ward profile | `data/quarantine/batch-01/` (git-ignored) |
| Modelled, profile only | 1: solid waste 2015–18 | `data/external/verify_2026-10-17/waste/` (git-ignored) |
| Byte-identical to a legacy file | 2: BWSSB Aug 2025, RA2019 A47 (`same_bytes_as`) | legacy clone, read-only |
| Candidate sources (portal metadata only) | 124 records | `docs/discovery/civicmind_dataset_catalog.csv` |

"Candidate" means a portal page or catalogue entry was checked. It does not mean the data has
been downloaded, validated or approved for use.
