# Milestone 05 — Document Retrieval-Augmented Generation (design, not implemented)

Status: **approved 2026-10-18** (extractive first, BM25 first). Stage 1 (document catalogue)
is implemented on `feat/m05-stage1-document-catalogue`: see
[docs/DOCUMENT_MANIFEST_SPEC.md](../DOCUMENT_MANIFEST_SPEC.md). Stages 2–6 are not implemented.
The audit below describes `main` before stage 1.
Baseline: `main` at `81f19a1` (Query Coverage v1 + API 413 fix), working tree clean.

The verified system today has **no language model, no retrieval and no RAG**. Every claim
below about what RAG "does" describes the proposed design.

---

## 1. Repository audit

### 1.1 Query flow and module boundaries (as implemented)

```
POST /api/v1/query {question}                      api/routes.py  (thin; no data access)
  └─ answer_question(question, root)               orchestrator/pipeline.py
       parse()            planner/parser.py        closed vocabulary → QuerySpec | PlanRefusal
       load_index/coverage planner/catalog_index.py manifest metadata only
       check()            planner/feasibility.py   trust status per period → Plan | PlanRefusal
       ingest(trusted)    catalog/ingest.py        re-hash + re-validate every file on every use
       DISPATCH[intent]   analytics/{water,roads}  allowlisted, tested functions only
       validate_package() evidence/model.py        hash/status/path/period/columns vs manifests
       compose_answer()   respond/compose.py       fixed templates + "no number not in evidence"
  └─ from_answer()        api/schemas.py           field-by-field mapping, nothing computed
```

Properties the design must keep:

- **Fail closed, stable codes.** Every stage returns a `Refusal(code, stage, reason)`; codes are
  declared in frozensets (`PLANNER_CODES`, `FEASIBILITY_CODES`, `EVIDENCE_CODES`, `PIPELINE_CODES`)
  and never renamed.
- **Step limit** (`MAX_STEPS = 10`) and an audit `trace` of step names (no question text, no
  reasoning).
- **Evidence first.** `compose_answer` raises unless the package passed validation *and* its
  SHA-256 digest is unchanged since validation; `check_numbers` refuses any number in the
  answer text that is not in the package.
- **Layer allowlist enforced by test** (`tests/test_pipeline.py::ALLOWED`): `evidence` imports
  nothing; `respond` only `evidence`; `orchestrator` only planner/analytics/catalog/evidence/
  respond; `api` only orchestrator/respond/catalog. The same test forbids importing
  `anthropic|openai|langchain|langgraph|requests` in those layers.
- **Lightweight import** (`tests/test_smoke.py`): importing every layer must not load pandas,
  numpy, fastapi, pydantic, yaml, **torch or transformers**.

### 1.2 Response and evidence schemas

- `EvidencePackage` / `EvidenceItem` (`evidence/model.py`) are **dataset-shaped**: dataset id,
  schema version, SHA-256, source path, mode, period, columns, `rows_used > 0`. There is no
  passage, page or document concept. `validate_package` requires `value is not None`, a unit,
  a method and caveats — a document answer cannot fit this without a parallel type.
- `Answer` (`respond/compose.py`) and `QueryResponse` (`api/schemas.py`, `extra="forbid"`):
  `status`, `answer_text`, `refusal`, `result{operation, value, value_basis, unit, metric,
  periods, method, denominator}`, `caveats`, `assumptions`, `evidence[]`, `trace`, `coverage`.
  Precedent: `value_basis` and `coverage` were added **additively** in Coverage v1.
- HTTP mapping (`api/errors.py::status_for`): answered → 200; question/catalogue refusals → 200;
  evidence or integrity failure → 503; `pipeline.*` → 500.

### 1.3 Documentation and authoritative source references

- `src/civicmind/rag/__init__.py` is a docstring-only stub that already fixes the contract:
  documents registered in manifests; page and section provenance; **baseline BM25 via SQLite
  FTS5**; embeddings "only if a labelled retrieval evaluation shows the baseline fails";
  retrieved text is untrusted; **rag never answers numeric questions**.
- `docs/architecture.md` (provisional decisions): RAG retrieval = SQLite FTS5 BM25 + metadata
  filters; embeddings / vector store = future option needing a measured need; LLM provider =
  "after the evidence path and claim verifier are tested"; response phrasing = templates until
  an LLM provider is approved *and* the claim verifier exists; LangChain not planned.
- `docs/discovery/civicmind_dataset_catalog.csv` has 13 `documents_rag` candidates. Relevant
  to water and roads:

  | id | priority | status in catalogue | source class | use |
  |---|---|---|---|---|
  | DOC-MORTH-RA2019 | P0 | VERIFIED_RESOURCE | official (morth.nic.in) | definitions, methodology for RA2019 tables |
  | DOC-MORTH-RA2024 | P0 | DOC_LINK_UNVERIFIED | official (via OpenCity) | latest definitions, million-plus city chapter |
  | DOC-SLB-HANDBOOK | P1 | DOC_LINK_UNVERIFIED | official (mohua.gov.in) | water service-level benchmarks (e.g. LPCD) |
  | DOC-MV-ACT | P1 | DOC_LINK_UNVERIFIED | official (indiacode.nic.in) | offence wording for violation categories (quote only) |
  | DOC-GODL | P0 | VERIFIED_RESOURCE | official | licence/attribution text |

  **Gap:** no BWSSB document (tariff orders, BWSSB Act 1964, consumption methodology) is
  catalogued, so water-specific document questions (e.g. coverage.v1 `C33`, domestic tariff)
  have no candidate source yet.
- Licence column for these documents reads "Government publication; reuse terms per
  publisher" — GODL covers OGD datasets, not automatically every ministry PDF. Licence
  evidence must be recorded per document (§7).
- `data/docs/` exists (empty, `.gitkeep`); `data/` contents are git-ignored.

### 1.4 Exact integration point

1. **Router, in the planner, before the causal check.** `parse()` order is: empty/length →
   injection → **causal** → predictive → domain → … The `CAUSAL` list includes `policy`,
   `policies`, `enforcement`, `explain`; so "What does the MoRTH report say about the
   enforcement methodology?" is refused today as `query.causal`. A document question must be
   classified after the injection check and before the causal check, by a separate closed
   pattern set (§5.2). Genuinely causal questions keep their refusal.
2. **Branch in `orchestrator/pipeline.py::_run`**, alongside the existing
   `data_coverage` branch: `if plan.function == "document_question": return
   _document_answer(...)`. No change to `DISPATCH`; analytics are untouched.
3. **New evidence type** `DocumentEvidencePackage` + `validate_document_package` in
   `evidence/` (pure, no imports), and **`compose_document_answer`** in `respond/`.
4. **Additive API fields** (`route`, `citations`) in `api/schemas.py::from_answer`.

Observed defect relevant to evaluation: coverage.v1 `C32` ("What does MoRTH define as a
grievous injury?", class `requires_documents`) currently expects `query.period_missing`, an
accidental code from the roads parser. Once RAG exists, its expectation must change
deliberately, with a note in the YAML.

### 1.5 Reusable pieces

| Need | Reuse |
|---|---|
| Hashing, size, file identity | `catalog/fingerprint.py` |
| Manifest pattern (Pydantic, strict, YAML round-trip) | `catalog/manifest.py` (new model alongside, not a modification) |
| Review bound to SHA-256, `apply_review`, stale detection | `catalog/review.py` semantics, `REVIEW_DECISIONS.yaml` per batch |
| Gated hash-verified copy, never overwrite | `catalog/promote.py` pattern (`.partial` + rename) |
| Quarantine that never overwrites | `catalog/quarantine.py` |
| Stable refusals, trace, step limit, fail-closed wrapper | `orchestrator/pipeline.py` |
| Number guard | `respond/compose.py::check_numbers` (generalised to passages) |
| Index store | `sqlite3` + FTS5 from the standard library — **verified available** in `.venv-py313` (SQLite 3.50.4) |
| HTTP client for a local model server | `httpx` (already a dev dependency; would become a runtime extra) |
| Eval harness pattern | `eval/coverage_metrics.py`, YAML question sets with pre-declared expectations |

Nothing to reuse for PDF parsing, embeddings or LLM access: no such dependency exists
(`pyproject.toml` explicitly lists them as "deliberately absent").

### 1.6 Trust and provenance constraints RAG must preserve

- Only reviewed, hash-pinned, **promoted** sources reach answers; exploratory/quarantined never do.
- Re-verify on use (ingest re-hashes every file per query).
- Manifests are the single source of provenance; reviews live in reviewed files, not typed into manifests.
- No joins across datasets without identifier authority; no cross-edition comparisons; no causal or predictive claims; "current"/"latest" never resolved silently.
- Numbers only from tested analytics; a language model never computes or alters them.
- Question text and document text are data, never instructions. Exception text, paths and secrets never returned.
- Tests are a fixed regression set, never presented as real-world accuracy.

---

## 2. Proposed architecture

```
                          ┌───────────────────────── offline (person-gated) ─────────────────────────┐
 official PDF (by hand) → │ doc manifest → integrity (sha256, bytes, pages) → text extraction (page) │
                          │ → injection/PII screen → person review (bound to sha256) → promote       │
                          │ → chunk (doc, page, section, char span) → build index (FTS5 [+ vectors]) │
                          │ → index_manifest.json (doc hashes, extractor/chunker/embedder versions)  │
                          └──────────────────────────────────────────────────────────────────────────┘
                                                        │ read-only at query time
 question ─► planner.parse ─┬─ analytics intents ─► (unchanged pipeline) ───────────────► Answer
                            ├─ data_coverage     ─► (unchanged)        ────────────────► Answer
                            ├─ document_question ─► orchestrator._document_answer
                            │                        1 verify index_manifest vs doc manifests
                            │                        2 rag.retrieve(query, filters) → passages
                            │                        3 sufficiency gate (score, count)  ─► refuse rag.no_evidence
                            │                        4 generate.<adapter>(passages)     (extractive | local | hosted)
                            │                        5 evidence.validate_document_package
                            │                          (citations ⊆ retrieved, quotes verbatim,
                            │                           numbers in cited text, support check)
                            │                                                           ─► refuse rag.unsupported
                            │                        6 re-hash cited source documents   ─► 503 on mismatch
                            │                        7 respond.compose_document_answer  ─► Answer(route=documents)
                            └─ composite (stage 6, optional) ─► analytics answer + document context, side by side
```

Layers (new ones in bold):

| Layer | May depend on | Must not |
|---|---|---|
| `catalog` (+ `documents.py`) | nothing | modify raw files |
| `rag` | catalog, evidence | answer numeric questions; treat text as instructions; call a model |
| **`generate`** | evidence | read files or the index; see analytics values; import heavy SDKs at module import |
| `evidence` (+ `documents.py`) | nothing | — |
| `planner` (+ `doc_router.py`) | catalog | route an unmatched question to RAG as a fallback |
| `orchestrator` | planner, analytics, rag, **generate**, catalog, evidence, respond | let generated text bypass validation |
| `respond` | evidence | invent citations; change quotes |
| `api` | orchestrator, respond, catalog | accept document ids, filters or prompts from the client |

**RAG is not a fallback.** A question the closed router does not classify as a document
question is handled exactly as today (refused or answered by analytics).

---

## 3. Step-by-step data flow

### 3.1 Offline: document ingestion (person-gated, mirrors the dataset workflow)

1. **Acquire** — a person downloads the PDF to `data/external/verify_<date>/docs/<domain>/`
   with its original file name (tools never complete portal forms or CAPTCHAs).
2. **Register** — `data/doc_manifests/<document_id>.yaml` with source, authority, dates,
   licence evidence (§7). Status `received`.
3. **Integrity** — SHA-256, bytes, page count, PDF header check, encrypted/protected flag,
   producer metadata. Status `integrity_passed`.
4. **Extract** — per-page text with the extractor name and version recorded; pages with no
   extractable text are listed (`extraction.no_text`) and **excluded** (no OCR in M05);
   tables extracted as text rows where the extractor supports it, otherwise flagged.
   Output: `data/processed/rag/extracted/<document_id>/<sha12>.jsonl` (git-ignored), one record
   per page: `{page, text, chars, extractor, warnings}`.
5. **Screen** — instruction-like text (rag's own pattern list, §6.4), personal-data patterns
   (names with phone/e-mail patterns), language detection (non-English pages flagged).
   Findings recorded in the manifest; nothing is edited.
6. **Review** — a person records `approve | approve_pages | quarantine | reject` in
   `docs/acquisition/<batch>/DOCUMENT_REVIEW_DECISIONS.yaml`, bound to the SHA-256, listing every
   warning as an accepted caveat or excluding the affected pages.
7. **Promote** — gated, hash-verified copy to `data/docs/<domain>/<original_filename>`.
   Status `approved`.
8. **Chunk** — deterministic: split on detected headings, then into windows of ~350 words
   with ~50-word overlap, never across a page boundary *without* recording both pages.
   Each chunk: `chunk_id = <document_id>:p<page>:<n>`, `page_start/end`, `section` (heading
   text if detected), char span in the page text, `text_sha256`.
9. **Index** — rebuild from scratch (corpus is small): SQLite FTS5 table with
   `porter unicode61` tokenizer + metadata table (domain, authority, document_type,
   publication_date, effective dates, edition, status). Stage 5 only: an embedding column.
10. **Seal** — `data/processed/rag/index_manifest.json`: per document `{id, sha256,
    manifest_version, review sha256}`, extractor/chunker/embedder ids and versions, chunk
    count, and the index file's SHA-256. Same inputs → byte-identical outputs.

### 3.2 Online: a document question

1. `parse()` → empty/length → injection → **document router** → (non-document questions
   continue unchanged). The router emits `QuerySpec(intent="document_question", domain,
   params={topic terms, document_hint, edition_hint})` with assumptions stated (e.g. "latest
   approved edition used because none was named").
2. Feasibility: domain has ≥1 approved document; a named edition exists and is approved
   (otherwise `document.not_approved` / `document.unavailable` with the document coverage).
3. Index check: `index_manifest.json` matches current doc manifests (ids, SHA-256, review);
   otherwise `rag.index_stale` (503: server-side state, not the question).
4. Retrieve: BM25 top-k (k=8) with filters `status=approved`, `domain`, not superseded unless
   the edition is named. Stage 5: hybrid with reciprocal-rank fusion.
5. Sufficiency gate: top score ≥ calibrated threshold and ≥1 passage containing a query
   content term; otherwise refuse `rag.no_evidence` (200).
6. Generate (§4.4): adapter receives **only** the question and passages with ids; returns
   claims `[{text, chunk_ids, quotes[]}]` or `insufficient`.
7. Validate (`evidence/documents.py`, pure): every claim cites ≥1 retrieved chunk; cited ids
   ⊆ retrieved set; every quote is a verbatim substring of its chunk; every number in a claim
   appears in a cited chunk; support score ≥ threshold. Unsupported claims are **dropped**; if
   none survive → `rag.unsupported_claims`. Conflict rules (§7.6) applied.
8. Re-hash the source PDFs of cited chunks against their manifests (cheap: few documents) →
   `integrity.hash_mismatch` (503).
9. Compose: deterministic text = surviving claims, each followed by `[n]`; a citations list;
   caveats (secondary mirror, superseded edition, extraction warnings, "document text, not a
   CivicMind calculation"); `value_basis="document"`.

---

## 4. Technology comparison and recommendation

Corpus scale for this milestone: 3–10 documents, a few thousand pages at most, roughly
5k–30k chunks. That scale removes any need for a vector database service.

### 4.1 Document parsing

| Option | Licence | Strengths | Weaknesses | Verdict |
|---|---|---|---|---|
| **pypdf** | BSD-3 | pure Python, no binaries, page-level text, stable on Windows | weak on complex tables and multi-column layout | **baseline** |
| pdfplumber (pdfminer.six) | MIT | character positions, table extraction | slower; still no OCR | add for table-heavy pages if eval shows need |
| PyMuPDF | **AGPL-3.0** / commercial | fastest, good layout | licence incompatible with a permissive deployment unless a commercial licence is bought | avoid |
| Docling / unstructured | MIT / Apache-2.0 | layout models, tables, OCR | heavy (torch, models), slower, larger supply chain | future, only for scanned or table-critical documents |
| Tesseract OCR | Apache-2.0 | scanned pages | OCR errors break verbatim-quote checking | out of scope; scanned pages excluded and listed |

### 4.2 Retrieval index and embeddings

| Option | Cost | Latency (expected, not measured) | Privacy | Reproducibility | Deploy | Verdict |
|---|---|---|---|---|---|---|
| **SQLite FTS5 BM25** | none | ms on 30k chunks | local | deterministic | standard library | **stage 2 baseline** (matches architecture.md) |
| Local embeddings, brute-force cosine in numpy, vectors in SQLite | CPU only | ~10–50 ms query encode on CPU (small model) | local | deterministic given pinned model + weights hash | adds torch or onnxruntime (hundreds of MB) | **stage 5, only if BM25 fails the gate** |
| sqlite-vec / FAISS | free | sub-ms ANN | local | ANN is approximate unless flat index | extra native wheel | unnecessary at this scale |
| Chroma / Qdrant / pgvector | free–hosted | fast | local or hosted | good | a service to run | over-built for the corpus |
| Hosted embedding API | per-token | network-bound | text leaves the machine | depends on provider versioning | key management | not recommended: documents are public but query text may not be |

Candidate local embedding models (verify licence and model card at selection time):
`BAAI/bge-small-en-v1.5` (MIT, 384-d), `intfloat/e5-small-v2` (MIT),
`sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0). Reranker, only if justified by eval:
`BAAI/bge-reranker-base` (MIT) cross-encoder over the top 20.

Decision gate (pre-registered, §8.4): move to hybrid only if BM25 Recall@5 on the labelled
direct-question set is below 0.85 **or** the labelled set contains ≥3 paraphrase misses that
hybrid retrieves. Reranking only if it raises MRR by ≥0.05 at acceptable latency.

### 4.3 LLM access

| Option | Cost | Latency (expected) | Privacy | Reproducibility | Licence / terms | Notes |
|---|---|---|---|---|---|---|
| **Extractive (no LLM)** | none | ms | local | fully deterministic | n/a | returns ranked verbatim passages with citations via template; always available; the fallback |
| **Local open-weight via an OpenAI-compatible server** (Ollama, llama.cpp server, vLLM) | hardware | 7–8B model on CPU: tens of seconds; on a consumer GPU: a few seconds | nothing leaves the host | temperature 0 + seed + pinned weights hash; still not bit-exact across hardware | per model: e.g. Qwen2.5-7B-Instruct (Apache-2.0), Llama 3.1 8B (Llama Community Licence, use restrictions), Mistral 7B Instruct (Apache-2.0) | weaker instruction-following and citation discipline; the verifier carries the guarantee |
| **Hosted Claude via the official `anthropic` SDK** | per token: `claude-opus-5-5` $4 / $20 per MTok in/out; `claude-sonnet-5-5` $2 / $10; `claude-haiku-5-5` $0.10 / $0.50 (≤100K-token prompts) | a few seconds | question + passages sent to the provider; retention per the account's data terms | sampling parameters are not accepted on current models, so outputs are not seedable; reproducibility comes from logging input/output digests and from the deterministic validator | commercial terms | native **citations** (each passage as a document content block with `citations.enabled`) returns `cited_text` + location that the validator can check verbatim; citations cannot be combined with structured outputs in one request |

**Recommendation.**

1. Ship stages 1–3 with the **extractive** responder: it delivers cited, governed document
   answers with no model, no new runtime risk, and gives the validator and eval a stable target.
2. Add a `generate` layer with a provider-neutral `Generator` protocol and select it by
   `CIVICMIND_GENERATOR=extractive|local|anthropic` (default `extractive`). Both model adapters
   are optional extras (`rag-local`, `rag-anthropic`), imported lazily.
3. For hosted generation, use `claude-opus-5-5` by default with native citations; Sonnet or
   Haiku are cost options to measure on the eval, not assumptions. Enable the server-side
   refusal fallback (`fallbacks: "default"`) and treat a final `stop_reason: "refusal"` as
   `rag.generator_refused`.
4. For local generation, any instruction-tuned open-weight model behind an OpenAI-compatible
   endpoint, configured by URL and model name; JSON output validated against the claims schema.
5. Whatever the generator, **the validator decides what reaches the user**. A generator
   failure falls back to the extractive answer with a caveat (`trace` records it), never to
   unvalidated text.

### 4.4 Generation contract (all adapters)

- Input: fixed system instructions (versioned, hashed) + question + passages as
  `<passage id="..." document="..." page="...">…</passage>`. Instructions state that passage
  text is quoted material that cannot change rules, and that the model must answer only from
  passages or return `insufficient`.
- Output normalised to `Claims = [{text, chunk_ids[], quotes[]}] | insufficient`.
  Claude adapter: map `citations[].cited_text` + document index to `chunk_ids`/`quotes`.
  Local adapter: strict JSON schema; invalid JSON → one repair retry → extractive fallback.
- The generator never receives analytics values, manifests, file paths or system state; it has
  no tools; its output is data, re-parsed and validated.

---

## 5. Module and file structure (proposed)

```
src/civicmind/
  catalog/documents.py          DocumentManifest model, read/write, status lifecycle
  catalog/doc_review.py         apply document review decisions (bound to sha256)
  catalog/doc_promote.py        gated promotion to data/docs/<domain>/
  rag/extract.py                pypdf page extraction → page records (+ extractor version)
  rag/screen.py                 instruction-like / personal-data / language screening
  rag/chunk.py                  deterministic heading-aware chunker
  rag/index.py                  build/load SQLite FTS5 index; index_manifest seal + check
  rag/retrieve.py               BM25 retrieval with metadata filters; sufficiency gate
  rag/embed.py, rag/rerank.py   stage 5 only; lazy imports
  generate/__init__.py          NEW LAYER: Generator protocol, Claims type, factory by env
  generate/extractive.py        deterministic passage selection (no model)
  generate/local_openai_compat.py   local server adapter (httpx), lazy
  generate/anthropic_claude.py  official anthropic SDK adapter with citations, lazy
  generate/prompts.py           versioned instruction text + digest
  evidence/documents.py         Passage, Citation, DocumentEvidencePackage,
                                validate_document_package (pure)
  planner/doc_router.py         closed patterns → document_question spec
  planner/spec.py               + intent "document_question"; + DOCUMENT_CODES
  orchestrator/pipeline.py      + _document_answer branch (DISPATCH unchanged)
  respond/compose.py            + compose_document_answer
  api/schemas.py                + route, CitationOut, DocumentCoverageOut (additive)
scripts/process_doc_batch.py    verify → extract → screen → review → promote
scripts/build_doc_index.py      chunk + index + seal (deterministic)
data/doc_manifests/             DOC-*.yaml (tracked)
data/docs/<domain>/             promoted PDFs (git-ignored)
data/processed/rag/             extracted pages, index.sqlite, index_manifest.json (git-ignored)
docs/DOCUMENT_MANIFEST_SPEC.md
eval/questions/rag.v1.yaml      labelled set (§8)
eval/rag_metrics.py
tests/fixtures/docs/synthetic/  small SYNTHETIC documents (labelled as such) for hermetic tests
tests/test_doc_catalog.py, test_rag_index.py, test_rag_retrieve.py, test_doc_router.py,
tests/test_document_evidence.py, test_generate.py, test_rag_pipeline.py, test_rag_api.py
```

Boundary-test changes (deliberate, reviewed): add `rag`, `generate` to `ALLOWED`; orchestrator
may import `rag` and `generate`; `generate` may import only `evidence`; `anthropic` may be
imported only inside `generate/anthropic_claude.py`, inside a function. `HEAVY_MODULES` stays
as is (torch/transformers must still not load on package import).

`data/doc_manifests/` is a separate directory because `pipeline.sources()` and the catalogue
index glob `data/manifests/*.yaml` and parse each file as a dataset `Manifest`
(`extra="forbid"`); mixing document manifests there would break them.

---

## 6. API integration design

### 6.1 Request — unchanged

`POST /api/v1/query {"question": "..."}`. No document ids, filters, `top_k`, model or prompt
fields are accepted (same reasoning as "no dataset selectors").

### 6.2 Response — additive only

```json
{
  "request_id": "…",
  "status": "answered",
  "route": "documents",
  "question": "How does the MoRTH report define a grievous injury?",
  "answer_text": "The report defines … [1]. Source: DOC-MORTH-RA2024 p. 3.",
  "refusal": null,
  "result": {
    "operation": "document_answer",
    "value": {"claims": [{"text": "…", "citations": [1]}]},
    "value_basis": "document",
    "unit": null, "metric": null, "periods": ["2024 edition"],
    "method": "BM25 retrieval over approved documents; extractive|local|anthropic generator; claims validated against cited passages",
    "denominator": null
  },
  "citations": [{
    "n": 1, "document_id": "DOC-MORTH-RA2024", "title": "Road Accidents in India 2024",
    "issuing_authority": "Ministry of Road Transport and Highways",
    "publication_date": "…", "edition": "2024", "source_class": "official",
    "resource_page": "https://…", "page_start": 3, "page_end": 3, "section": "Definitions",
    "chunk_id": "DOC-MORTH-RA2024:p3:2", "quote": "≤ 300 characters, verbatim",
    "document_sha256": "…"
  }],
  "caveats": ["Document text as published, not a CivicMind calculation.", "…"],
  "assumptions": ["No edition named: the latest approved edition (2024) was used."],
  "evidence": [],
  "trace": ["parse", "feasibility", "index", "retrieve", "generate:extractive", "evidence", "integrity", "compose"],
  "coverage": null
}
```

- `route`: `analytics | catalogue | documents | composite | null` (null on refusals before routing).
  Existing answers get `analytics` or `catalogue`; nothing else about them changes.
- `value_basis` gains `"document"`. `evidence` stays dataset-only; documents appear in `citations`.
- Refusal codes (new, declared in a `DOCUMENT_CODES` frozenset):

  | code | stage | HTTP |
  |---|---|---|
  | `document.unavailable` (no approved document for the domain / named edition) | feasibility | 200 |
  | `document.not_approved` (exists but quarantined, superseded-only, pending) | feasibility | 200 |
  | `rag.no_evidence` (retrieval below threshold) | retrieve | 200 |
  | `rag.unsupported_claims` (no claim survived validation) | evidence | 200 |
  | `rag.conflicting_sources` (unresolved conflict, §7.6) | evidence | 200 |
  | `rag.index_unavailable`, `rag.index_stale` | index | 503 |
  | `integrity.hash_mismatch` (cited PDF changed) | integrity | 503 |

  `status_for` gains one rule: stage `index`/`integrity` → 503. Generator errors do not refuse;
  they fall back to extractive.
- `GET /api/v1/ready`: adds `documents: {approved: n, index: "ok|missing|stale"}`. Readiness
  does **not** become `not_ready` when the index is missing (analytics still work); document
  questions refuse with `rag.index_unavailable`.
- Logging: as today, request id/path/status/outcome/duration; plus generator name, token
  counts and latency; never question text, passages or model output.

### 6.3 Questions needing both data and documents (composite, stage 6)

Explicit, never implicit:

1. The router recognises a closed set of compound forms ("X in <month> and how is X defined").
   Anything else that mixes a numeric request with document language is refused
   `query.compound` with a suggestion to ask the two parts separately.
2. The analytics part runs through the **unchanged** pipeline and is composed by the existing
   template; its `result`, `evidence` and number check are untouched.
3. The document part runs the document path with the analytics **metric name** (not the value)
   as the topic. The generator never sees the analytics value.
4. The response carries both: `result` + `evidence` from analytics, `citations` + a separate
   `document_context` text from documents, `route: "composite"`.
5. A number that appears in both a document and a dataset is never reconciled; if they differ,
   both are shown with their own `value_basis` and a caveat. Document numbers are never used
   as inputs to calculations.

### 6.4 Document text as untrusted input

- Ingest-time screen (`rag/screen.py`, own pattern list modelled on the parser's `INJECTION`):
  matching chunks are recorded as `content.instruction_like` findings; the reviewer must
  explicitly accept or exclude those pages before approval.
- Query-time: passages are delimited and labelled as quoted material; the generator has no
  tools and no access to trust state; the claims are re-parsed and validated, and the final
  text is assembled by a template, so a passage cannot alter refusal codes, citations, trust
  status or caveats.
- The guarantee does not rest on the model obeying: an injected instruction can at worst make
  the generator produce a claim, which is then dropped unless it is supported verbatim by a
  cited passage — and then it is an accurate quotation of an approved document, labelled as such.

---

## 7. Document trust and provenance model

### 7.1 Allowed source types (M05)

Allowlist of `document_type`: `statistical_report` (MoRTH RAI), `act`, `rules`,
`notification` / `gazette`, `tariff_order`, `handbook_manual` (MoHUA SLB, CPHEEO),
`audit_report` (CAG), `methodology_note`. Issued by a government body or statutory
authority. `source_class`: `official` (publisher's own domain) or `secondary_mirror` (e.g.
OpenCity) — mirrors allowed only with a caveat on every answer and only when no official copy
was found (recorded). Not allowed: news, blogs, social media, unofficial summaries,
AI-generated text, drafts unless marked `draft` and excluded from default retrieval.

### 7.2 Document manifest (fields beyond the dataset manifest's identity/source/licence/retrieval/integrity groups)

| Field | Purpose |
|---|---|
| `document_id`, `manifest_version` | identity; bump on any change |
| `title`, `issuing_authority`, `publisher`, `document_type`, `language` | as printed on the document |
| `resource_page`, `download_url`, `source_class` | where it came from |
| `publication_date`, `effective_from`, `effective_to`, `edition`, `version_label` | temporal validity |
| `integrity`: `sha256`, `bytes`, `pages`, `pdf_producer`, `encrypted` | exact bytes |
| `extraction`: tool + version, pages with text, `pages_without_text`, table warnings | reproducibility |
| `supersedes`, `superseded_by`, `same_bytes_as` | version chain, duplicates |
| `relates_to_datasets` (e.g. `ROAD-RA2024-A47`) | documentation for a dataset, never a join |
| `domains` (`water`, `roads`) | retrieval filter |
| `licence`: name, url, evidence, attribution, quoting note | reuse terms |
| `findings` (screen results), `known_limitations` | caveats |
| `review`: decision, reviewer, date, sha256, accepted caveats, `excluded_pages` | person gate |
| `status`: `planned → received → integrity_passed → extracted → validated → approved` / `quarantined` / `rejected` / `withdrawn` (supersession is a relation, not a status) | lifecycle |

### 7.3 Duplicates and superseded versions

- Same SHA-256 under two ids → second gets `same_bytes_as`, indexed once.
- Same title/authority, different bytes → separate versions; the reviewer sets
  `supersedes`/`superseded_by`. Superseded documents stay approved for **named-edition**
  questions only, with a caveat; default retrieval uses the current version.
- A question about a period (e.g. "the 2019 definition") filters by `edition` /
  effective dates, never by "newest file".

### 7.4 Integrity

SHA-256 recorded at intake, re-checked at promotion, at index build (sealed in
`index_manifest.json`), and at query time for every cited document. Extracted text and chunks
carry their own `text_sha256`, so a citation can be traced to exact bytes.

### 7.5 Approval, corrections, deletion, re-indexing

- **Approval** = an `approve` (or `approve_pages`) decision bound to the SHA-256, every finding
  accepted or its pages excluded. Only `approved` documents enter the index.
- **Correction** (publisher issues a corrigendum or new edition) → new document id or
  manifest version, new review; the new one lists the old one in `supersedes`.
- **Withdrawal/deletion** → status `withdrawn` (manifest kept as a tombstone with reason and
  date); the next index build excludes it; the file is moved to quarantine, never silently
  deleted.
- **Re-indexing** = full deterministic rebuild on any manifest, extractor, chunker or embedder
  change; the query-time check refuses (`rag.index_stale`) until rebuilt.

### 7.6 Unsupported or conflicting passages

- Unsupported claim → dropped; if nothing remains → `rag.unsupported_claims`.
- Same authority, different editions → current edition, caveat naming the older one, unless an
  edition was asked for.
- Different authorities disagree (e.g. an Act's definition vs a report's operational
  definition) → both stated, each attributed with its citation; if the question requires a
  single answer → `rag.conflicting_sources`.
- Document number vs dataset value → never reconciled (§6.3).
- Legal texts (MV Act) → quotation with citation only and a "not legal advice" caveat.

---

## 8. Evaluation methodology

Defined before implementation. **No results exist**; every threshold below is a proposed
acceptance target.

### 8.1 Question set `eval/questions/rag.v1.yaml` (proposed ~70 items)

Each item: `id`, `question`, `category`, `expect` (`status`, `route`, `code` for refusals),
`gold_passages` (document id, page, a verbatim anchor string), `key_facts` (short strings an
answer must convey), `forbidden` (strings that must not appear). Gold labels are written by a
person reading the approved documents, before any retrieval is run, and frozen.

| Category | n | Expected outcome |
|---|---|---|
| Direct definition/methodology | 15 | answered, gold passage cited |
| Multi-passage (two sections or two documents) | 8 | answered, all gold passages cited |
| No supporting evidence (plausible but absent, e.g. BWSSB tariff before a tariff document exists) | 8 | `rag.no_evidence` |
| Conflicting / outdated (two editions, named and unnamed) | 6 | current edition + caveat; named edition honoured; conflict code where required |
| Prompt injection inside documents (synthetic fixture documents only, labelled; never in the production index) | 6 | instruction not followed; trust/refusal fields unchanged; no exfiltration of system text |
| Injection in the question | 4 | `query.prompt_injection` (existing) |
| Routing: numeric questions phrased with document words | 8 | analytics route, value identical to today |
| Routing: document questions phrased with numeric words | 5 | document route, no computed number |
| Causal/predictive with document words ("did the policy reduce …") | 5 | `query.causal` / `query.predictive` (unchanged) |
| Composite (stage 6) | 5 | analytics value unchanged + document context |

### 8.2 Metrics

| Aspect | Metric | Target |
|---|---|---|
| Retrieval relevance | Recall@5, MRR@10, nDCG@10 on gold passages | Recall@5 ≥ 0.85 (direct), ≥ 0.70 (multi-passage) |
| Citation correctness | citation precision (cited passages that contain the supporting text) / recall (gold passages cited) | precision ≥ 0.95, recall ≥ 0.80 |
| Faithfulness | share of answer claims supported by cited text: automatic (verbatim quote + number + lexical support) and a manual audit of every answered item | unsupported claims in answered responses ≤ 2% (manual) |
| Answer correctness | key facts present / forbidden absent | ≥ 0.85 |
| Appropriate refusal | abstention precision and recall on the no-evidence and conflict categories | both ≥ 0.90 |
| Injection | success rate (any instruction from a document influences output or trust fields) | 0 |
| Routing | route accuracy; numeric answers byte-identical to the pre-RAG pipeline | 100% |
| Regression | existing pytest suite, `pipeline.v1`, `coverage.v1`, golden analytics | all pass; only deliberately reclassified items change (e.g. `C32`), each documented |
| Latency | p50/p95 per stage (router, index check, retrieve, generate, validate, re-hash) | extractive end-to-end p95 ≤ 2 s locally; hosted p95 ≤ 10 s; local-LLM latency reported, not targeted |
| Resources | RSS, index size, build time, tokens and cost per answered question | reported |

An LLM-as-judge may be added as a secondary signal, never as the only faithfulness measure.

### 8.3 Test layers

- **Hermetic unit/integration tests** (run in CI, no downloads, no model): synthetic fixture
  documents created for tests; a fake generator that returns scripted claims (supported,
  unsupported, hallucinated ids, injected text, malformed JSON).
- **Labelled eval on real approved documents**: skips with a reason when the git-ignored files
  are absent (same convention as data-dependent tests).
- **Model evals** (local/hosted): opt-in, never in the default test run; costs reported.

### 8.4 Pre-registered decision gates

- BM25 → hybrid: Recall@5 < 0.85 on direct questions, or ≥3 labelled paraphrase misses fixed by hybrid.
- Add reranker: MRR gain ≥ 0.05 with p95 retrieval ≤ 300 ms.
- Enable a model generator by default: its faithfulness and citation precision are not worse
  than extractive and answer correctness is higher, on the same set.

Reports state the set size and composition; a small fixed set is not real-world accuracy.

---

## 9. Risks and research gaps

| Risk / gap | Effect | Mitigation |
|---|---|---|
| Water has no catalogued official document (tariffs, BWSSB Act, consumption methodology) | water document questions mostly refuse | source acquisition decision before stage 3; until then the set expects refusals |
| PDF tables (MoRTH annexures) extract poorly | wrong or missing passages; table numbers misread | prefer prose sections for definitions; flag table pages; never present document table numbers as dataset values |
| Scanned / image-only pages | silently missing content | listed as `pages_without_text`; coverage caveat; OCR out of scope |
| Bilingual or Kannada notifications | English-only retrieval misses them | M05 English only; non-English pages flagged |
| Lexical support check misses negation and paraphrase | a subtly wrong claim could pass | verbatim-quote requirement for every claim; manual audit; NLI-based check is a research item |
| Hosted models are not seedable | identical questions can yield different wording | validator + logged digests; extractive default; eval reports variance across repeated runs |
| Licence of ministry PDFs unclear | redistribution risk | store files git-ignored; quote ≤300 characters; record licence evidence per document |
| Router change touches the causal check order | regressions in existing refusals | router is a closed allowlist; full pipeline/coverage suites must pass unchanged |
| Small labelled set | overfitting thresholds | freeze labels first; hold out ~30% of items for final reporting |
| Heavy dependencies for embeddings | install size, Windows wheels, supply chain | stage 5 only, gated, optional extra, pinned with hashes in a constraints file |
| Question text sent to a hosted provider | privacy | hosted generator off by default; documented; no personal data in prompts beyond the question |

---

## 10. Staged implementation plan

Each stage is one PR, keeps all existing tests green, and needs approval before it starts.

| Stage | Scope | New dependencies | Done when |
|---|---|---|---|
| **0 — Decisions and sources** (no code) | approve this design; you choose and download 3–5 pilot documents (suggested: MoRTH RAI 2024 and 2019, MoHUA SLB handbook, optionally MV Act, plus one BWSSB document if found); write gold labels for `rag.v1` | none | documents in `data/external/verify_*/docs/`, labels frozen |
| **1 — Document catalogue** | `DocumentManifest`, intake/integrity, pypdf extraction with page provenance, screening, review + promotion, `DOCUMENT_MANIFEST_SPEC.md`, synthetic fixtures | `pypdf` (optional extra `rag`) | pilot documents approved through the gate; tests for every refusal path |
| **2 — Index and retrieval** | chunker, FTS5 index, deterministic build + seal, filtered retrieval, `rag_metrics.py` retrieval metrics | none | byte-identical rebuilds; retrieval metrics reported on the frozen set |
| **3 — Document route, extractive answers** | `doc_router`, `document_question` intent + codes, `_document_answer`, `evidence/documents.py`, `compose_document_answer`, additive API fields, readiness field; deliberate updates to `C32`-type expectations | none | full eval categories except model-generated; existing suites unchanged |
| **4 — Generator layer** | `generate/` protocol, extractive, local (OpenAI-compatible) and Claude adapters, claim verifier hardening, fallback | `httpx` (runtime extra `rag-local`), `anthropic` (extra `rag-anthropic`) | model evals run opt-in; default stays extractive unless gate 8.4 is met |
| **5 — Hybrid retrieval (gated)** | local embeddings, RRF fusion, optional reranker | `sentence-transformers` or `onnxruntime` + model weights (pinned) | only if gate 8.4 triggers |
| **6 — Composite questions (optional)** | compound router forms, side-by-side response | none | analytics outputs byte-identical; composite items pass |

Out of scope for M05: knowledge graph, autonomous agents, frontend, OCR, non-English documents,
live document fetching.

## 11. Decisions needed from you

1. Approve the staged plan, in particular **extractive first** and **BM25 first** (consistent
   with `docs/architecture.md`), with embeddings and a model generator behind evaluation gates.
2. Which pilot documents to acquire (you download them; tools will not).
3. Whether a hosted LLM (question text leaves the machine) is acceptable at all, or local only.
4. Whether `secondary_mirror` copies (OpenCity) may be approved when no official copy is found.
