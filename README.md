# civic_mind-v2 — CivicMind AI

Evidence-grounded decision support for municipal officers and civic analysts. CivicMind AI
answers questions **only from validated, hash-pinned official data**. Every answer names its
dataset, SHA-256, metric, unit, period, method and caveats. When the data cannot support a
question, it refuses with a stable code and a reason instead of guessing.

> **Status: v0.0.1, a deterministic water + traffic slice with a local HTTP API and
> extractive, page-cited answers from two approved MoRTH reports.** No language model,
> knowledge graph or website exists. The API is a development interface (no authentication
> or rate limiting), not a production deployment.
> Nothing here is an autonomous action system, a forecaster or a Digital Twin.

## What works today

| Area | Implemented | Code |
|---|---|---|
| Catalogue | Manifests, fingerprinting (SHA-256, size, encoding, BOM, line endings), verbatim-header profiling, a schema registry, validators for 4 dataset families, an identifier assessment that never joins, a header scan for personal data | `src/civicmind/catalog` |
| Review and promotion | Person decisions bound to file SHA-256; a promotion gate; byte-identical copy to `data/raw/`; quarantine that never overwrites | `catalog/review.py`, `promote.py`, `quarantine.py` |
| Ingestion | Fail-closed re-verification of every file before use; `trusted` and (only if a review permits it) `exploratory` modes | `catalog/ingest.py` |
| Analytics | Water city totals, rankings of published rows (with flags against other months), two-month change; MoRTH city count with share of the Total row, top cities | `src/civicmind/analytics` |
| Query pipeline | A deterministic parser producing a typed `QuerySpec`, a feasibility check, an allowlisted dispatcher, evidence validation and a templated answer | `planner`, `orchestrator`, `evidence`, `respond` |
| HTTP API | FastAPI app factory: `GET /health`, `GET /api/v1/ready`, `POST /api/v1/query` over the same pipeline; typed responses, request ids, safe errors; document answers through the router after the pipeline refuses (additive `route` and `citations` fields) | `src/civicmind/api` |
| Evaluation | 25 golden analytics questions (re-derived by an independent standard-library script); 55 end-to-end pipeline questions | `eval/`, `tests/` |

**Documents and retrieval (Milestone 05, stages 1-2C):** official PDFs go through a
person-gated workflow: intake, one verified read that yields the SHA-256 and the page text
(pypdf, no OCR), screening, a review bound to both the PDF hash and the extracted-text hash, and
a promotion gate. Batch `docs-01`: MoRTH *Road Accidents in India* 2023 and 2019 are approved
(OpenCity mirror copies, with caveats); 2024 is quarantined (incomplete text layer, mirror
provenance). A retrieval layer indexes approved documents only (BM25 via SQLite FTS5 and
MiniLM ONNX vectors) and returns verbatim, page-cited passages or abstains. A small labelled evaluation (65 items) calibrated its thresholds and
compared the methods ([docs/evaluation/M05_RAG_EVALUATION.md](docs/evaluation/M05_RAG_EVALUATION.md)).
A routing layer with edition and currency guards (deterministic first, documents only for
definition, methodology or report-attributed questions) is evaluated and serves the API
after the deterministic pipeline, BM25 gate only ([docs/ROUTING.md](docs/ROUTING.md),
[eval/reports/api.v1.results.md](eval/reports/api.v1.results.md)). Coverage is deliberately
low: on the 65-item labelled set, 7 of 38 document questions are answered with a correct page
citation and every expected refusal is refused. See
[docs/RAG_RETRIEVAL.md](docs/RAG_RETRIEVAL.md),
[docs/DOCUMENT_MANIFEST_SPEC.md](docs/DOCUMENT_MANIFEST_SPEC.md) and
[docs/design/M05_RAG_DESIGN.md](docs/design/M05_RAG_DESIGN.md).

Planned, **not implemented**: a source-supported knowledge graph,
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
.venv-py313/Scripts/python.exe -m pip install -e ".[api,dev,rag,rag-embed]" -c constraints-py313.txt
```

`constraints-py313.txt` pins the exact versions resolved on Windows / Python 3.13 (44
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
.venv-py313/Scripts/python.exe scripts/process_doc_batch.py docs-01
.venv-py313/Scripts/python.exe scripts/build_doc_index.py
```

In order, these:
1. run the tests. With all promoted files present: 562 pass (Milestone 05 stage 1). On a fresh
   clone without data, the data-dependent tests **skip** with a reason (the skip count
   has not been re-measured since batch 01);
2. run the lint check;
3. check formatting;
4. print the golden answers from an independent standard-library derivation (the tests
   compare them with `eval/golden/`);
5. re-verify, re-validate and re-promote. This needs the files in `data/external/`;
   `--legacy-raw DIR` optionally compares against a legacy clone;
6. write `data/processed/ingest/ingest_report.json` (git-ignored; identical across runs);
7. process the document batch: manifests in `data/doc_manifests/`, a summary in
   `docs/acquisition/docs-01/document_summary.json` (entries without a downloaded file stay
   `planned`).

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
  share of the published Total row; top-n cities; **two cities compared within one edition**
  (both published counts, their shares, and a derived difference);
- data coverage: **which months or editions are available**, the latest trusted period, and
  why other periods are not used (answered from manifests only; no data value is read).

Every answer states its `value_basis` (`published`, `derived`, `published_and_derived` or
`catalogue`), and water and road answers **and refusals** carry the catalogue coverage. The
full inventory, including candidates that were deliberately not implemented, is in
[docs/query_capabilities.md](docs/query_capabilities.md).

**Refused, each with a code:**
- quarantined, modelled or unavailable periods;
- "current", "now", "this year" or "the latest month's" values without a named period: the
  newest local file is never treated as current (the coverage section names the latest
  trusted period);
- all-violation accident totals (the categories are not an established partition);
- unique-ward rankings (ward numbers repeat), single-ward or per-ward water figures, and named
  wards;
- cross-edition MoRTH comparisons, and cross-domain questions;
- causal ("why", "did X reduce Y") and predictive questions, averages and trends, and
  unsupported units;
- text that looks like instructions.

The parser uses a closed vocabulary, so unusual phrasings are refused rather than guessed.

## HTTP API

The API serves the same pipeline as `scripts/ask.py`; it adds no planner, analytics or data
access of its own. Questions the pipeline refuses may then be answered from approved
documents (see [Document answers](#document-answers)). FastAPI and Uvicorn come with the `api` extra (installed by the setup
command above; no further dependencies).

```bash
.venv-py313/Scripts/python.exe -m uvicorn civicmind.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Interactive documentation: `http://127.0.0.1:8000/docs` (OpenAPI at `/openapi.json`).

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness only: `{"status": "ok"}`. Says nothing about data. |
| `GET /api/v1/ready` | Readiness: manifests readable, at least one promoted dataset, every promoted file present. Returns counts per family; `503` with a reason (`catalogue.empty`, `catalogue.unreadable`, `data.missing`) otherwise. File hashes are re-checked on every query, not here. Also reports `retrieval` (`ready`, or `unavailable` with `rag.index_unavailable` / `rag.index_stale` / `rag.corpus_integrity`, or `disabled`), which never changes `status`. |
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

`result.value_basis` and a `coverage` object (trusted periods, `latest_trusted_period`,
non-trusted periods with their reason, and a freshness note) were added in Query Coverage
v1; both are additive. `coverage` is `null` for questions outside water and roads and for
empty, oversized or instruction-like questions.

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

### Document answers

When the pipeline refuses a definition, methodology or report-attributed question about roads,
the router may answer it from the approved MoRTH 2019 and 2023 reports (RA2024 is
quarantined). Such a response adds two fields; every other response is exactly as before.
A refusal that reports a server-side failure (HTTP 503 or 500: damaged or invalid dataset
files such as `integrity.hash_mismatch`, `file.missing` or `csv.malformed`, `evidence.invalid`,
`pipeline.internal_error`) is never answered from documents: it is returned exactly as the
deterministic API returns it, without `route` or citations.

```json
{
  "status": "answered",
  "question": "What is the Integrated Road Accidents (IRAD) project in the 2019 report?",
  "answer_text": "Relevant passages from approved documents:
[1] Road Accidents in India 2019 (2019), page 21: \"… (MoRTH) has formulated the Integrated Road Accidents (IRAD) Project under World Bank Assistance.\"",
  "refusal": null,
  "result": null,
  "caveats": ["Quoted document text, not a CivicMind calculation; check the cited page.", "Copy obtained from the OpenCity mirror (data.opencity.in), not from MoRTH directly.", "Publication date not verified.", "…"],
  "evidence": [],
  "route": {"kind": "documents", "code": null, "gate": "bm25", "index_id": "f10ba588d120b144", "editions": ["2019"], "parts": [], "trace": ["documents", "retrieve:bm25"], "reason": null},
  "citations": [{"n": 1, "document_id": "DOC-MORTH-RA2019", "edition": "2019", "page": 21, "source_class": "secondary_mirror", "publication_date": null, "chunk_id": "DOC-MORTH-RA2019:p21:c6", "chunk_sha256": "1fcbd3e1…", "document_sha256": "b656c762…", "extraction_sha256": "67109e87…", "score": 21.775342, "quote": "…", "…": "…"}]
}
```

A refusal keeps the pipeline's `refusal.code` (and `answer_text`); `route.code` and
`route.reason` say why documents could not answer either. Show `route.reason` when present:

```json
{"status": "refused", "refusal": {"code": "query.out_of_scope", "stage": "planner", "reason": "…"},
 "route": {"kind": "refused", "code": "rag.edition_unavailable", "reason": "No approved document covers 2024; later or other editions are never used in its place.", "…": "…"},
 "citations": []}
```

| `route.code` | Meaning | HTTP |
|---|---|---|
| `rag.currency_unverifiable` | "latest", "current", "recent": the newest approved edition is not assumed current | 200 |
| `rag.edition_unavailable` | the named year has no approved edition; another edition is never substituted | 200 |
| `rag.no_eligible_documents` | no approved document for the domain (water, waste, census) | 200 |
| `rag.no_evidence` / `rag.query_empty` | nothing relevant enough to cite (BM25 below the calibrated threshold) | 200 |
| `route.mixed_unsupported` | a combined question where some part has no supported answer (`route.parts` lists each code) | 200 |
| `rag.ineligible_evidence` | a passage failed the eligibility re-check | 200 |
| `rag.index_unavailable` | no index built for the approved corpus | 200 |
| `rag.index_stale` / `rag.corpus_integrity` | index or document bytes do not match their approval, or approvals changed since startup | 503 |
| `pipeline.internal_error` | routing raised on a refused question; no document answer (a deterministic answer is kept unchanged) | 500 |

**Local setup for documents.** PDFs, page files, model files and indexes are git-ignored and
never fetched by the API. With the approved documents present (see
[docs/RAG_RETRIEVAL.md](docs/RAG_RETRIEVAL.md)), build the index once:
`.venv-py313/Scripts/python.exe scripts/build_doc_index.py`. The API verifies it at startup
(about 3 s) and serves BM25 only; it needs no model at runtime. Without an index the API still
runs: document questions refuse with `rag.index_unavailable`.
`create_app(documents=False)` serves the deterministic pipeline alone.

Run the API tests: `.venv-py313/Scripts/python.exe -m pytest -p no:cacheprovider -q tests/test_api.py tests/test_api_routing.py`.

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

- **Document answers are extractive and sparse:** verbatim passages only (no summarising),
  BM25 at a threshold calibrated on 34 items, most document questions refused. The two
  approved reports are OpenCity mirror copies with unverified publication dates and
  licences. See the limitations in [docs/ROUTING.md](docs/ROUTING.md#http-api-stage-2f).

## Next milestone

Find an official BBMP-198 ward list; decide deployment concerns for the API
(authentication, rate limiting, packaging); then RAG, the graph and LLM phrasing.

## Related material

[docs/architecture.md](docs/architecture.md) · [data/README.md](data/README.md) ·
[docs/audit/](docs/audit/) (legacy repository audit) · [docs/discovery/](docs/discovery/)
(124-record source catalogue) · [eval/README.md](eval/README.md)
