# civic_mind-v2 — CivicMind AI

Evidence-grounded decision support for municipal officers and civic analysts. CivicMind AI
answers questions **only from validated, hash-pinned official data**. Every answer names its
dataset, SHA-256, metric, unit, period, method and caveats. When the data cannot support a
question, it refuses with a stable code and a reason instead of guessing.

> **Status: v0.0.1, a deterministic water + traffic slice with a local HTTP API.** No
> language model, retrieval (RAG), knowledge graph or website exists yet. The API is a
> development interface (no authentication or rate limiting), not a production deployment.
> Nothing here is an autonomous action system, a forecaster or a Digital Twin.

## What works today

| Area | Implemented | Code |
|---|---|---|
| Catalogue | Manifests, fingerprinting (SHA-256, size, encoding, BOM, line endings), verbatim-header profiling, a schema registry, validators for 4 dataset families, an identifier assessment that never joins, a header scan for personal data | `src/civicmind/catalog` |
| Review and promotion | Person decisions bound to file SHA-256; a promotion gate; byte-identical copy to `data/raw/`; quarantine that never overwrites | `catalog/review.py`, `promote.py`, `quarantine.py` |
| Ingestion | Fail-closed re-verification of every file before use; `trusted` and (only if a review permits it) `exploratory` modes | `catalog/ingest.py` |
| Analytics | Water city totals, rankings of published rows (with flags against other months), two-month change; MoRTH city count with share of the Total row, top cities | `src/civicmind/analytics` |
| Query pipeline | A deterministic parser producing a typed `QuerySpec`, a feasibility check, an allowlisted dispatcher, evidence validation and a templated answer | `planner`, `orchestrator`, `evidence`, `respond` |
| HTTP API | FastAPI app factory: `GET /health`, `GET /api/v1/ready`, `POST /api/v1/query` over the same pipeline; typed responses, request ids, safe errors | `src/civicmind/api` |
| Evaluation | 25 golden analytics questions (re-derived by an independent standard-library script); 55 end-to-end pipeline questions | `eval/`, `tests/` |

Planned, **not implemented**: RAG over official PDFs, a source-supported knowledge graph,
optional LLM phrasing behind a claim verifier, and a React website (see
[docs/architecture.md](docs/architecture.md)).

## Datasets (batch 01)

Files are **not in Git** (`data/` is ignored except manifests). Their provenance, hashes,
findings and review are in `data/manifests/*.yaml` and
[docs/acquisition/batch-01/](docs/acquisition/batch-01/).

| Dataset | Status | Why |
|---|---|---|
| `WATER-BWSSB-2025-08`, `WATER-BWSSB-2026-03` (BWSSB monthly ward water consumption) | **trusted** (promoted) | Validated; caveats accepted: ward numbers 14, 85, 153 and 191 each appear on two rows; ward 40 has zero consumption; March has bare-CR line endings |
| `ROAD-RA2019-A47`, `ROAD-RA2024-A47` (MoRTH million-plus cities, traffic violations) | **trusted** (promoted) | Totals and injury checksums consistent. Two separate schema versions, never mapped onto each other |
| `WATER-BWSSB-2025-04`, `WATER-BWSSB-2025-05` | **quarantined** | Header misspelt `Number of Connectionss`; May also has a negative value |
| `DEMO-SC-BLR-2011-DEM` (2011 ward demographic profile) | **quarantined** | 67 ward names cycle over 198 numbers; mislabelled units; empty columns |
| `WASTE-BLR-GCP` (solid waste 2015–18) | **modelled, profile only** | Fixed multipliers, not measurements; no trusted or exploratory use is permitted |

### Batch 02

Recorded in [docs/acquisition/batch-02/INTAKE_REPORT.md](docs/acquisition/batch-02/INTAKE_REPORT.md)
and `REVIEW_DECISIONS.yaml` there. How the batch-02 files were downloaded is **unknown** (not
yet recorded) and is marked so in each manifest.

| Dataset | Status | Why |
|---|---|---|
| `WATER-BWSSB-2025-07`, `-09`, `-10`, `-11`, `-12`, `WATER-BWSSB-2026-02` | **trusted** (promoted) | Same schema as batch 01; month-to-month swing warnings (e.g. Chowdeshwari Ward from Nov 2025) accepted as caveats |
| `WATER-BWSSB-2026-01` | **exploratory only** | Horamavu connection count unexplained; readable only through labelled exploratory ingestion, never in answers |
| `WATER-BWSSB-2025-06` | **quarantined** | Same defects as May 2025 |
| `ROAD-RA2020-A47` … `ROAD-RA2023-A47` | **trusted** (promoted) | Own verbatim schema versions; caveats: Tamil Nadu 2017–2020 revision (2020), Pune 2021 zero-accident casualties (2021) |
| `ROAD-RA2024-A1`, `-A2`, `-A49` | **profile only** | Different tables (national, state, junction type); never used for Annexure 47 questions |

Trusted water months are now July 2025 to March 2026 except January 2026; trusted MoRTH
Annexure 47 editions are 2019 to 2024. Cross-edition comparisons remain refused.

Licence: Government Open Data License – India (attribution in each manifest).

**Obtaining the files.** Download each file by hand from the `resource_page` in its manifest
(data.gov.in requires a usage form and a CAPTCHA, which tools must not complete). Save it
unchanged under `data/external/verify_2026-10-17/<domain>/` with the `original_filename`
from the manifest. Then run the batch processor (below): it recomputes every SHA-256 and
compares it with the manifest, re-validates, and promotes only files whose recorded review
matches their bytes. A file whose hash differs is never trusted.

## Trust workflow

1. **Acquire:** a person downloads the file to `data/external/verify_*/`.
2. **Verify:** integrity (size against the portal, SHA-256, encoding, line endings), an exact
   header match against a registered schema, the family validator, and the personal-data
   header scan.
3. **Review:** a person records a decision in `REVIEW_DECISIONS.yaml` (`accept`,
   `quarantine`, `keep_profiled`, `reject`), bound to the file's SHA-256. An `accept` must
   list every warning as an accepted caveat.
4. **Promote:** a gated, hash-verified copy to `data/raw/<domain>/`. It is refused for
   quarantined, modelled, non-public or unreviewed data.
5. **Use:** analytics read data only through `ingest()`, which re-checks all of the above.
   Joins across datasets are refused; the only exception is the documented T10 volatility
   flag (an exact match on ward number and name, used for flags only).

Details: [docs/MANIFEST_SPEC.md](docs/MANIFEST_SPEC.md) and
[DATA_QUALITY_REVIEW.md](docs/acquisition/batch-01/DATA_QUALITY_REVIEW.md).

## Setup

Python 3.11+ is declared; development and testing use **Python 3.13.15** only.

```bash
py -3.13 -m venv .venv-py313
.venv-py313/Scripts/python.exe -m pip install -e ".[api,dev]" -c constraints-py313.txt
```

`constraints-py313.txt` pins the exact versions resolved on Windows / Python 3.13 (31
packages). On another platform, regenerate it rather than reusing it. No credentials or API
keys are needed.

## Running the checks

```bash
.venv-py313/Scripts/python.exe -m pytest -p no:cacheprovider -q
.venv-py313/Scripts/python.exe -m ruff check .
.venv-py313/Scripts/python.exe -m ruff format --check .
.venv-py313/Scripts/python.exe -I eval/golden/derive_batch01.py
.venv-py313/Scripts/python.exe scripts/process_batch_01.py
.venv-py313/Scripts/python.exe scripts/ingest_manifests.py
```

In order, these:
1. run the tests. With all promoted files present: 367 pass (Milestone 03). On a fresh
   clone without data, the data-dependent tests **skip** with a reason (the skip count
   has not been re-measured since batch 01);
2. run the lint check;
3. check formatting;
4. print the golden answers from an independent standard-library derivation (the tests
   compare them with `eval/golden/`);
5. re-verify, re-validate and re-promote. This needs the files in `data/external/`;
   `--legacy-raw DIR` optionally compares against a legacy clone;
6. write `data/processed/ingest/ingest_report.json` (git-ignored; identical across runs).

## Asking questions

```bash
.venv-py313/Scripts/python.exe scripts/ask.py "Water consumption in August 2025?"
.venv-py313/Scripts/python.exe scripts/ask.py --json "Top 3 cities by speeding deaths in 2024"
```

**Supported:**
- water: city totals of consumption (ML) or connections for a month; rankings of **published
  rows** by consumption, connections or litres per connection per day, optionally flagged
  against another trusted month; the change in city totals between two months;
- traffic: one city's count for one violation category and measure in one edition, with its
  share of the published Total row; top-n cities.

**Refused, each with a code:**
- quarantined, modelled or unavailable periods;
- unique-ward rankings (ward numbers repeat), single-ward or per-ward water figures, and named
  wards;
- cross-edition MoRTH comparisons, and cross-domain questions;
- causal ("why", "did X reduce Y") and predictive questions, averages and trends, and
  unsupported units;
- text that looks like instructions.

The parser uses a closed vocabulary, so unusual phrasings are refused rather than guessed.

## HTTP API

The API serves the same pipeline as `scripts/ask.py`; it adds no planner, analytics or data
access of its own. FastAPI and Uvicorn come with the `api` extra (installed by the setup
command above; no further dependencies).

```bash
.venv-py313/Scripts/python.exe -m uvicorn civicmind.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Interactive documentation: `http://127.0.0.1:8000/docs` (OpenAPI at `/openapi.json`).

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness only: `{"status": "ok"}`. Says nothing about data. |
| `GET /api/v1/ready` | Readiness: manifests readable, at least one promoted dataset, every promoted file present. Returns counts per family; `503` with a reason (`catalogue.empty`, `catalogue.unreadable`, `data.missing`) otherwise. File hashes are re-checked on every query, not here. |
| `POST /api/v1/query` | Body `{"question": "..."}` only (whitespace trimmed, 1–1000 characters, no other fields; the parser's own 400-character limit still applies). A blank or whitespace-only question is rejected as invalid input (`422 request.invalid`); the CLI and pipeline keep their own `query.empty` refusal for it. |

Response (`status` is `answered` or `refused`):

```json
{
  "request_id": "…",
  "status": "answered",
  "question": "How many over-speeding accidents did Bengaluru record in 2021?",
  "answer_text": "Bengaluru, 2021, 'Over-Speeding - Number of Accidents - Number': 3,041, 6.6192% of the published Total row. Source: ROAD-RA2021-A47, sha256 8da252e5a6ed.",
  "refusal": null,
  "result": {
    "operation": "road_city_value",
    "value": {"value": 3041, "share_of_total_pct": 6.6192},
    "unit": "count",
    "metric": "Over-Speeding - Number of Accidents - Number",
    "periods": ["2021"],
    "method": "published cell; share = city / published Total row x 100",
    "denominator": "published Total row (all million-plus cities in this edition)"
  },
  "caveats": ["…", "SOURCE CAVEAT: Pune, Over-Speeding: …"],
  "assumptions": [],
  "evidence": [{"dataset_id": "ROAD-RA2021-A47", "role": "primary", "sha256": "8da252e5…", "mode": "trusted", "…": "…"}],
  "trace": ["parse", "feasibility", "ingest:ROAD-RA2021-A47", "analytics:road_city_value", "evidence", "compose"]
}
```

A refusal has `"result": null`, no evidence, and
`"refusal": {"code": "dataset.not_trusted", "stage": "feasibility", "reason": "…"}` (for
example, January 2026). Refusal codes are the pipeline's own.

| HTTP | When |
|---|---|
| 200 | Answered, or refused because of the question or the catalogue (planner, feasibility, analytics; trust-status refusals) |
| 503 | Refused because server-side data failed an integrity or evidence check (no number is returned) |
| 500 | Internal failure (`pipeline.internal_error`, or an API error: `{"error": {"code": "internal_error", …}}`) |
| 400 / 413 / 422 | Malformed JSON / body over 8 KiB / invalid fields, as `{"error": {"code", "message", "request_id", "fields"}}` |

Every response carries `X-Request-ID` (a valid client-supplied value is kept). The server log
records the request id, path, status, outcome code and duration, never the question text.
Exception text, tracebacks and file paths are never returned. Only **trusted** data reaches
answers; exploratory data (January 2026) is not reachable through the API.

Run the API tests: `.venv-py313/Scripts/python.exe -m pytest -p no:cacheprovider -q tests/test_api.py`.

## Known limitations

- **Narrow data:** eight trusted water months (July 2025 to March 2026, without January),
  six MoRTH Annexure 47 editions, and no ward-identifier authority for the BBMP-198 scheme,
  so no unique-ward or ward-level comparisons and no cross-edition road trends.
- **The API is for local development:** no authentication, rate limiting or TLS; CORS is off.
  Each query re-reads the manifests and re-hashes the files it uses (about 0.7–1.6 s locally).
- **City names are matched exactly:** there is no alias table (`Bangalore` is not
  `Bengaluru`).
- **Prompt-injection screening is pattern-based:** it is a limited defence. Question text is
  never executed.
- **The personal-data scan reads column names only,** not cell values.
- **Tests are a fixed regression set,** not a measure of accuracy on real users' questions.

## Next milestone

Find an official BBMP-198 ward list; decide deployment concerns for the API
(authentication, rate limiting, packaging); then RAG, the graph and LLM phrasing.

## Related material

[docs/architecture.md](docs/architecture.md) · [data/README.md](data/README.md) ·
[docs/audit/](docs/audit/) (legacy repository audit) · [docs/discovery/](docs/discovery/)
(124-record source catalogue) · [eval/README.md](eval/README.md)
