# Data handling rules

| Folder | Purpose | In Git? |
|---|---|---|
| `external/verify_YYYY-MM-DD/` | Manual downloads, exactly as received, awaiting verification | No |
| `quarantine/` | Files with unknown or unconfirmed provenance | No |
| `raw/` | Promoted copies: hash-pinned, validated, never edited | Only small public files after review |
| `manifests/` | One YAML per dataset: source URL, publisher, licence evidence, retrieved date, SHA-256, period, geography, ward scheme, sensitivity, caveats, status | Yes |
| `aliases/` | Entity alias tables (wards, states, cities), each row with a source | Yes |
| `docs/` | Official PDFs for RAG, recorded in manifests by URL and hash | No |

## Promotion from `external/` to `raw/`

1. The file is downloaded manually from the official resource page. Nothing is scraped, and
   no portal form is filled in by tools.
2. The URL, retrieval date, size and SHA-256 are recorded in a manifest.
3. Licence evidence is recorded. If it is unknown, the manifest says `UNKNOWN`.
4. Sensitivity is reviewed. Files with personal data (for example grievance records with
   staff names or free text) are never committed; only reviewed aggregates may be.
5. Dataset-specific validators pass, or their findings are recorded as caveats.
6. The file is copied unchanged to `raw/`. Cleaned or derived outputs are separate,
   reproducible artifacts.

## What Git ignore rules can and cannot protect

`.gitignore` denies everything under `data/raw/` by default. Each approved file needs its own
`!data/raw/...` line at the end of `.gitignore`. Ignore rules also cover PDFs, credential files,
and grievance/complaint/Sahaaya data files anywhere in the repository, in any letter case.

**Ignore rules match file names, not contents.** A file with an innocuous name that contains
personal or restricted data (for example `tests/fixtures/ward_issues.csv` holding real
complaint rows) is not caught. Therefore:

- test fixtures must be synthetic, never copied from real records;
- personal-data files stay in `data/external/` or `data/quarantine/` (both always ignored);
- before any commit that adds a CSV/XLSX/JSON, the staged file headers must be checked for
  sensitive columns (e.g. `Staff Name`, `Staff Remarks`, names, phone numbers, e-mail
  addresses, complaint text). An automated pre-commit check is planned but not yet in place.

## Ward schemes

Bengaluru data uses different ward schemes: BBMP 198 (2010), 243 (2022), 225 (2023), and
GBA 369 (2025). Every ward-level manifest must state its scheme. Data on different schemes
is never joined without an official crosswalk.

## Current state (2026-10-17)

Batch 01 has 8 manifests: 4 trusted (promoted to `data/raw/`, still git-ignored), 3
quarantined and 1 modelled/profile-only. See the dataset table in the top-level `README.md`
and `docs/acquisition/batch-01/`. Each manifest records a header-name personal-data scan
(`sensitivity.header_scan`); it inspects column names only. The planned pre-commit header
check for staged CSV/XLSX/JSON files is still not in place.
