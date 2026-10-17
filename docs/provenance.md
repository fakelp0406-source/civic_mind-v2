# Data provenance register

This file will be generated from `data/manifests/*.yaml` once datasets are registered.

## Current state (2026-10-17)

| Category | Count | Where |
|---|---|---|
| Verified datasets in this repository (downloaded, hash-pinned, validated, manifest) | **0** | `data/manifests/` (empty) |
| Candidate sources with portal-metadata evidence | 124 records | `docs/discovery/civicmind_dataset_catalog.csv` (see its `status` column) |
| Unverified legacy files | 1 (BWSSB Aug 2025 CSV) | kept **outside** this repo, in the legacy clone; quarantine policy |
| Legacy files with verified official resources (by name and size only, not yet by hash) | 3 exact-size matches (RA2019 A2, A47, A49); A52 differs by 13 bytes; BWSSB Aug 2025 matches a Karnataka OGD resource by name and size | see `docs/audit/` and `docs/discovery/` |

"Candidate" means a portal page or catalogue entry was checked. It does not mean the data
has been downloaded, validated or approved for use.
