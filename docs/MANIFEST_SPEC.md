# Dataset manifest specification and promotion workflow

Status: **in use** (2026-10-17). Batch 01 has 8 manifests; 4 files are promoted (see
`docs/acquisition/batch-01/VALIDATION_REPORT.md`). Implemented by `civicmind.catalog.manifest`,
`civicmind.catalog.review` and `civicmind.catalog.promote`.

A manifest (`data/manifests/<dataset_id>.yaml`) is the single record of where a file came
from, what it contains, and which checks it passed. A file may enter `data/raw/` only when
its manifest passes **every gate** below.

## 1. Required fields

| Group | Field | Required | Notes |
|---|---|---|---|
| Identity | `dataset_id` | ✅ | Matches the discovery catalogue id (e.g. `WATER-BWSSB-2025-08`) |
| | `title` | ✅ | As shown by the publisher |
| | `manifest_version` | ✅ | Integer; bump on any change |
| Source | `publisher` | ✅ | The original agency, e.g. *Bangalore Water Supply and Sewerage Board* |
| | `host_portal` | ✅ | e.g. `karnataka.data.gov.in`, `data.opencity.in` |
| | `source_class` | ✅ | `official` or `secondary_mirror` |
| | `resource_page` | ✅ | Human-facing URL of the resource |
| | `download_url` | ✅ | Exact URL used. Signed or expiring URLs are recorded as `"signed URL from resource page"` |
| | `portal_published`, `portal_updated` | ✅ | From portal metadata |
| Licence | `licence.name`, `licence.url` | ✅ | `UNKNOWN` is allowed but blocks promotion to tracked status |
| | `licence.evidence` | ✅ | Where the licence statement was seen (page, footer, catalogue field) |
| | `licence.attribution` | ✅ | Filled GODL template (or the publisher's own) |
| | `licence.exemptions_checked` | ✅ | e.g. GODL excludes personal information |
| Retrieval | `retrieved_at` | ✅ | ISO 8601 with time zone |
| | `retrieved_by` | ✅ | Person; tools never fill portal forms |
| | `original_filename` | ✅ | As served |
| Integrity | `bytes` | ✅ | Exact size on disk as received |
| | `sha256` | ✅ | 64 hex characters |
| | `format` | ✅ | `csv`, `xlsx`, `kml`, `pdf`, … |
| | `encoding` | ✅ (text) | charset, BOM yes/no, newline (CRLF/LF), delimiter |
| Content | `schema` | ✅ | Column name (verbatim, incl. trailing spaces), type, unit, key flag |
| | `row_count` | ✅ (tabular) | Excluding header |
| | `period` | ✅ | start, end, granularity, `as_on` for snapshots |
| | `geography` | ✅ | country/state/city, level (national/state/city/ward/point/station) |
| | `ward_scheme` | ✅ (ward data) | e.g. `BBMP-198-2010`, `GBA-369-2025`, or `UNKNOWN` |
| | `identifier_evidence` | ✅ (ward data) | Document that defines the identifiers, or `none` |
| Sensitivity | `sensitivity` | ✅ | `public` / `personal_data` / `restricted` |
| | `contains_personal_data` | ✅ | true/false, with the columns concerned |
| Validation | `integrity_checks` | ✅ | Results of Stage A |
| | `semantic_checks` | ✅ | Results of Stage B |
| | `compatibility` | ✅ (if joined) | Results of Stage C |
| | `findings` | ✅ | List; empty only if truly none |
| | `value_nature` | ✅ | `measured` / `modelled` / `unknown` (default). `modelled` = derived estimates, e.g. fixed growth factors |
| Review | `human_review` | ✅ | `pending` / `accepted` / `rejected`, set only from a recorded decision (section 3) |
| | `review` | when reviewed | decision, reviewer, date, the SHA-256 reviewed, accepted caveats (warning codes), note |
| Lifecycle | `status` | ✅ | `received` → `integrity_passed` → `validated` → `promoted` (or `rejected`) |
| | `promoted_to` | when promoted | `data/raw/...` path |
| | `git_tracked` | ✅ | `false` unless an explicit allowlist line was approved |
| | `supersedes` / `same_bytes_as` | optional | e.g. the legacy file's SHA-256 if identical |
| | `known_limitations` | ✅ | Interpretation limits users must see |

## 2. Validation stages

### Stage A — Source-file integrity (is this the exact file the publisher served?)
- SHA-256 and byte size recorded; size compared with the portal's stated size.
- The format opens; encoding, BOM, newline and delimiter detected.
- **Structural** schema check: header present, expected column count, no ragged rows.
- File stored byte-identical (`.gitattributes` disables line-ending conversion under `data/`).

Passing Stage A says **nothing** about whether the numbers are correct or usable.

### Stage B — Semantic validation (are the contents internally coherent?)
Dataset-family validators record findings and **never edit values**:
- types and units per column; non-negative counts; plausible ranges;
- `Total` rows equal the sum of the other rows (MoRTH); totals vs component columns;
- key uniqueness; duplicated keys listed (e.g. BWSSB ward numbers 14, 85, 153, 191 in Aug 2025);
- period coverage complete (e.g. 12 monthly files, same column set each month);
- cross-edition consistency (e.g. 2019 values restated in later MoRTH editions are flagged).

### Stage C — Compatibility (may this dataset be combined with another?)
**Joins are blocked by default.** A join between datasets A and B is allowed only if
**one** of the following is documented in both manifests:

1. **Verified stable identifiers.** Both datasets use the same identifier system, *and* an
   authoritative document defines it (e.g. the official ward delimitation notification for
   the scheme), *and* both manifests cite that document. Similar names or matching numbers
   are evidence to investigate, not authorisation.
2. **Version-aware crosswalk.** A crosswalk table (`data/crosswalks/<schemeA>__<schemeB>.csv`,
   created only when needed) with its source, method, date and scheme versions. It must
   cover every entity or list exclusions.

Every compatibility assessment reports four separate lists:
- **matched**: identifier and name agree;
- **unmatched**: present in one dataset only;
- **ambiguous**: one identifier maps to several names, or one name to several identifiers;
- **duplicated**: repeated identifiers within a dataset.

**A name-match percentage (e.g. 95%) never authorises a join on its own.** Datasets on
different ward schemes (BBMP-198, BBMP-243, BBMP-225, GBA-369) are never joined without an
official crosswalk. Equivalence is never inferred from similar names.

### Stage D — Licence and sensitivity
- Licence evidence recorded; attribution string filled in.
- Personal-data review: column headers and a sample of values checked for names, phone
  numbers, e-mail addresses and free text. `personal_data` files are never promoted to a
  tracked location; only reviewed aggregates may be, and only via explicit allowlisting.

## 3. Person review and promotion gate (`data/external/verify_*` → `data/raw/`)

### Recording a review
Manifests are regenerated by the batch processor, so review decisions are **not** typed into
the manifest. They live in a reviewed file per batch (`docs/acquisition/<batch>/REVIEW_DECISIONS.yaml`)
and are applied on every run by `civicmind.catalog.review.apply_review`:

| Decision | `human_review` | Effect on `status` |
|---|---|---|
| `accept` | `accepted` | unchanged (`validated`); eligible for promotion |
| `quarantine` | `rejected` | `quarantined`; the processor moves the file to `data/quarantine/<batch>/` |
| `reject` | `rejected` | `rejected` |
| `keep_profiled` | `pending` | unchanged; may set `value_nature` and add `known_limitations` |

The function fails closed. A decision applies only to the SHA-256 it records (otherwise the
finding is `review.stale`). An `accept` applies only to a `validated` manifest
(`review.not_applicable`) and only if every warning finding code is listed in
`accepted_caveats` (`review.incomplete`). In each case `human_review` stays `pending`.

### Gate
`civicmind.catalog.promote.promote` refuses unless all of these are true:
- [x] `status: validated` (Stage B validator ran with 0 errors) and Stage A passed with a hash.
- [x] `human_review: accepted` with an `accept` review bound to the same SHA-256.
- [x] Licence known (an `UNKNOWN` licence is not promoted), `sensitivity: public`, no personal data.
- [x] Source is under `data/external/<…>/<domain>/` with a known domain
      (`water`, `roads`, `waste`, `demographics`), and `original_filename` is a plain file name.
- [x] Source size and SHA-256 re-checked just before copying.
- [x] Copy written to a `.partial` file, hash-verified, then renamed into
      `data/raw/<domain>/<original_filename>`. An existing target with the same bytes is left
      alone (idempotent); one with different bytes is never overwritten.

Promotion sets `status: promoted` and `promoted_to`. It does **not** change `git_tracked`.

Tracking in Git additionally requires: `sensitivity: public`, known licence, small size, and
an explicit `!data/raw/...` line approved for that one file.

## 4. Example (draft values, not yet true)

```yaml
dataset_id: WATER-BWSSB-2025-08
manifest_version: 1
title: Water consumption data for the month of August-2025
publisher: Bangalore Water Supply and Sewerage Board
host_portal: karnataka.data.gov.in
source_class: official
resource_page: https://www.data.gov.in/resource/water-consumption-data-month-august-2025
download_url: https://www.data.gov.in/files/ogdpv2dms/s3fs-public/BWSSB_Water_Consumption_August_2025.csv
portal_published: 2025-09-17
portal_updated: 2025-09-17
licence:
  name: Government Open Data License - India
  url: https://www.data.gov.in/Godl
  evidence: karnataka.data.gov.in footer; data.gov.in GODL page
  attribution: >-
    Bangalore Water Supply and Sewerage Board, 2025, Water consumption data for the month of
    August-2025, Open Government Data Platform India, 17/09,
    https://www.data.gov.in/resource/water-consumption-data-month-august-2025.
    Published under Government Open Data License - India: https://www.data.gov.in/Godl.
  exemptions_checked: true
retrieved_at: null            # filled at download
retrieved_by: null
original_filename: BWSSB_Water_Consumption_August_2025.csv
bytes: null                   # portal states 6045
sha256: null
format: csv
encoding: {charset: null, bom: null, newline: null, delimiter: ","}
schema:
  - {name: "Ward number ", type: int, unit: null, key: candidate}
  - {name: "Ward Name", type: str}
  - {name: "Number of Connections", type: int, unit: connections}
  - {name: "Consumption in ML", type: float, unit: megalitres}
row_count: null
period: {start: 2025-08-01, end: 2025-08-31, granularity: month}
geography: {country: India, state: Karnataka, city: Bengaluru, level: ward}
ward_scheme: UNKNOWN          # numbering 1-198 suggests BBMP-2010; not verified
identifier_evidence: none
sensitivity: public
contains_personal_data: false
integrity_checks: {}
semantic_checks: {}
compatibility: {}
findings: []
status: planned
promoted_to: null
git_tracked: false
same_bytes_as: null           # legacy quarantined copy, if the hash matches
known_limitations:
  - Recorded consumption, not supply; bulk and commercial connections included.
```
