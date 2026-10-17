# CivicMind AI — Phase 1 Audit Report (read-only)

Audit date: 2026-10-17 · Machine: Windows 11 home PC (no NVIDIA GPU, CPU-only PyTorch 2.3.0, Python 3.10.9, Node 22.15) · Auditor: Claude Code

> Scope: repository, data, source/licence verification and literature review. **Nothing in the
> repository was modified**, no packages were installed, no data or models were downloaded, no
> database or graph store was created. Tests were run from source with bytecode and pytest cache disabled
> (`git status` remained clean afterwards).

---

## 1. Executive summary

1. **Keep and refactor the repo. Don't start from scratch.** The repo already has a sound, honest foundation: deterministic pandas analytics, an `Evidence` object, a provider layer that discards LLM text which drops computed figures, a FastAPI factory, and 570 passing tests. Starting over would throw that away for no benefit.
2. **The historical test claims reproduce exactly:** 570 passed, 2 skipped, Ruff clean. But the 11-case benchmark (7 supported, 4 unsupported, all metrics 1.0) **does not generalise.** I sent 12 questions it had not seen:
   - Off-topic or policy questions were *answered*, not refused. "Which ward has the most potholes?", "Should we increase water tariffs in ward 12?" and "Is there a link between water consumption and road accidents?" all returned the water-consumption ranking. "What does the Motor Vehicles Act say about overspeeding fines?" returned the over-speeding city ranking.
   - "Top blackspots in Karnataka" **silently dropped the state filter** and returned Chennai locations.
   - "How many accidents in Delhi in 2017" was **refused** even though A2 contains that value.
   - Root cause: `src/civicmind/ai/intent.py` is a keyword router with no slot validation. It fails *open*, which is the most dangerous failure for an evidence-grounded system.
3. **RAG, Knowledge Graph, agentic orchestration and web UI do not exist.**
   - No embedding, BM25, graph or LangGraph code is present; the only hit is a docstring in `storage/__init__.py` saying an index is deferred.
   - The "engine" is a single-step dispatch pipeline, which its own docstring says it is.
4. **Four of the five CSVs have verified official provenance.** They are MoRTH *Road Accidents in India 2019* tables on data.gov.in. Filenames match, and three byte sizes match exactly. A52 is 13 bytes larger locally than the published file.
   - **BWSSB_WATER (Aug 2025) provenance is UNKNOWN.** It is not on OpenCity's `bwssb-data` page or catalogue search, and no other source was found.
5. **The data has structural traps the system must handle explicitly:**
   - A2, A47 and A49 each include a `Total` row (sums come out exactly 2×).
   - A49 has a negative count (Madurai, −54).
   - In 9 A52 rows the yearly figures don't add up to the stated 3-year total.
   - A52 uses non-standard state spellings ("Orrisha", "Tamilnadu", "Maharastra"…).
   - BWSSB has 4 ward numbers shared by two names ("Jayanagar"/"Jayangar") and uses the old 198-ward scheme.
6. **The closest published work is OGD4All** (IEEE CAI 2026, ETH Zürich): an LLM agent over 430 Zurich open datasets with retrieval, sandboxed code and rejection of unanswerable questions. A novelty claim must be narrower than "evidence-grounded agentic civic QA" (see §9).

---

## 2. Actual repository / commit state

| Item | Value |
|---|---|
| Remote | `https://github.com/lp-0406/civicmind-ai.git` (public, reachable) |
| Local checkout | `C:\Desktop\civicmind-ai-main\repo` (fresh clone today) |
| Branch / HEAD | `main` @ `e3b194f` "Add local ingestion research run" (2026-10-12) |
| History | 11 commits, 2026-10-10 → 2026-10-12. 10 by `lp-0406`, 1 by `byteMonk` (HEAD) |
| Tracked files | 101 (~25.6k lines incl. docs/tests/data) |
| Working tree | clean |
| Manifest | `pyproject.toml`. Core deps are only `python-dotenv` and `pandas`. Extras: `dev` (pytest, ruff, httpx), `api` (fastapi, uvicorn), `ai` (torch, transformers) |
| Secrets | `.env.example` only (values redacted in this report); `.env` is git-ignored |
| Tests | `570 passed, 2 skipped in 45.7s` (skips: GPU integration opt-in; transformers-missing path) |
| Lint | `ruff check` → All checks passed |

Folder note: `C:\Desktop\civicmind-ai-main\` also contains a `README.md` and `.gitignore` that match the **initial commit** `3f3d281`. They look like a stale zip extract, and I have left them untouched.

Commands run (all read-only): `git clone`, `git log/ls-files/status`, `pytest -p no:cacheprovider` with `PYTHONDONTWRITEBYTECODE=1`, `ruff check --no-cache`, pandas profiling scripts run from a temp folder with `python -I -B`.

---

## 3. Verified dataset inventory and quality profile

All five files are UTF-8 (no BOM) except **A52, which is cp1252**. All use CRLF line endings and contain no NUL bytes. SHA-256 prefixes are listed for later manifest pinning.

| Local file | Bytes | sha256 (16) | Shape | Matches history? |
|---|---|---|---|---|
| RA2019_A2.csv | 9,015 | 6e9393b6af5c76a4 | 37 × 21 | yes |
| RA2019_A47.csv | 6,807 | 40bed81dc88f3350 | 51 × 33 | yes |
| RA2019_A49.csv | 8,295 | f449338a53d2dbf2 | 51 × 38 | yes |
| RA2019_A52.csv | 25,368 | f3e569e932c37d9f | 273 × 15 | yes (but see size note) |
| BWSSB_Water_Consumption_August_2025.csv | 6,045 | 108639ce30129414 | 202 × 4 | yes |

### RA2019_A2 — State/UT-wise total road accidents, 2016–2019
- 36 States/UTs + 1 `"Total "` row (trailing space). Every count column sums to exactly 2 × the Total row, so **the Total row is a free checksum** and must be excluded from rankings.
- Measures:
  - Accident counts for 2016–2019.
  - 2019 rank.
  - Percentage share (0–100) for 2016–2019.
  - Accidents per lakh population for 2016–2019 (1 null each).
  - Accidents per 10,000 vehicles for 2016–2019 (2018 and 2019 have 1 null).
  - Accidents per 10,000 km of road for **2016–2018 only**, with 2018 marked **(P) provisional**. There is no 2019 road-length rate.
- Geography reflects 2019 boundaries: J&K is undivided (no Ladakh), and Dadra & Nagar Haveli and Daman & Diu are listed separately.
- Caveat: a later PIB annexure gives *different* state figures for 2019 (e.g. Tamil Nadu 62,685 vs 57,228 here). Answers must cite the **edition**, never "the" accident count.

### RA2019_A47 — Million-plus cities: accidents by traffic violation, 2019
- 50 cities + `Total`. Categories: Over-speeding, Drunken driving, Wrong side, Red-light jumping, Mobile phone, Others. Each has accidents, killed, and grievous/minor/total injured; ranks exist for over-speeding only.
- City names use the source's spellings ("Vizaq", "Vadodra", "Khozikode", "Mallapuram", "Thiruvanthapuram", "Allahabad(Prayagraj)").
- **There is no state column.** City→state linkage needs a separate, cited mapping.

### RA2019_A49 — Million-plus cities: accidents by junction type, 2019
- Same 50 cities + `Total`, in the same order as A47. Junction types: T, Y, Four-arm, Staggered, Roundabout, Others, Total.
- **Anomaly:** Madurai "Others – Grievously injured" = **−54** (total injured 666 = −54 + 720). The Total row includes it, so it is a source defect, not a parsing error. Flag it and don't silently fix it.
- Engine wording issue: `junction_injury_totals` answers "which *cities* … at T-junctions?" with *category totals*. That's a different question.

### RA2019_A52 — State-wise top-10 black spots, 2016–2018
- 273 rows across 30 states (mostly 10 each, fewer for Assam, Chandigarh, Mizoram, Arunachal, Manipur, Meghalaya). Officially excluded: A&N, DNH, Daman & Diu, Lakshadweep, Puducherry, Sikkim.
- Data quality:
  - Nulls: 2017 has 7 nulls and 2018 has 18; police station has 1.
  - The km "start/end" columns are mixed text and numbers.
  - The `NH/SH/MDR/OR No.` column is free text.
  - **In 9 rows the yearly figures don't add up to the "Total of all three years"** (e.g. J&K "Rajbagh": 15+10+17 = 42 vs stated 75).
- State spellings differ from A2: Orrisha, Tamilnadu, Maharastra, Megahalaya, Chhattishgarh, Uttrakhand. An explicit alias table is required for any cross-dataset link.

### BWSSB_WATER — ward-wise connections and consumption, "August 2025"
- 4 columns: `Ward number ` (trailing space), `Ward Name`, `Number of Connections`, `Consumption in ML`.
- 202 rows, but only **198 unique ward numbers**. Wards 14, 85, 153 and 191 each appear twice with different names. Two look like typos (Jayanagar/Jayangar, Singasandra/Singsandra) and two like sub-areas (Bagalagunte/sidedahalli, Doddanekkundi/Varthur). Totals must be computed per *row* and the duplication disclosed. Never merge silently.
- Ward 40 (Doddabidirakalu) has 1 connection and 0.0 ML.
- Totals: ~10.48 lakh connections and 30,580 ML. That is *plausible* against a press report of 10.53 lakh connections (Sept 2024), which is **not** a validation.
- Ward numbering 1–198 matches the **old BBMP (2010) delimitation**. Bengaluru's governance was restructured in 2025, which I have not verified here. Any ward-level linkage needs the delimitation version pinned.
- Derived litres/connection/day ranges from 0 to ~2,487. High values (Bellandur, Gandhinagar) likely reflect bulk or commercial connections. **Don't interpret them as household use.**

### Joinability (verified)
- **There is no defensible key between road (state/city) data and BWSSB (Bengaluru wards).** The repo's `join_assessment` reaches the same conclusion.
- A47 ↔ A49 share identical city labels, so a same-period, same-geography join is valid.
- A2 ↔ A52 can be joined by state only after alias resolution (A52 is a top-10 *list*, not a census, so it can't be used for state totals).

---

## 4. Sources, licences and download instructions

data.gov.in resource metadata was read in the in-app browser through the portal's public catalogue endpoint (direct automated fetches return HTTP 403).

| Local ID | Official resource (data.gov.in) | Publisher | Verification | Licence |
|---|---|---|---|---|
| RA2019_A2 | "State/UT-wise Total Number of Road Accidents in India from 2016 to 2019" — `/resource/stateut-wise-total-number-road-accidents-india-2016-2019`, file `RA2019_A2.csv`, 9,015 B | Ministry of Road Transport & Highways (MoRTH) | **Filename + exact byte size match** | Catalogue "Released under NDSAP". OGD platform terms = GODL-India (attribution required). *Confirm the attribution template text on https://www.data.gov.in/Godl* |
| RA2019_A47 | "Cities-wise Accidents Classified according to Type of Traffic Violations in Million Plus Cities during 2019" — `/resource/cities-wise-accidents-classified-according-type-traffic-violations-million-plus-cities`, 6,807 B | MoRTH | **Filename + exact size match** | as above |
| RA2019_A49 | "Cities-wise Accidents Classified according to Type of Junctions in Million Plus cities during 2019" — `/resource/cities-wise-accidents-classified-according-type-junctions-million-plus-cities-during-2019`, 8,295 B | MoRTH | **Filename + exact size match** | as above |
| RA2019_A52 | "States wise list of top ten black spots from 2016 to 2018" — `/resource/states-wise-list-top-ten-black-spots-2016-2018`, published 15/02/2023, 25,355 B | MoRTH | Filename + fields + excluded-state note match. **Local file is 13 bytes larger.** Must be checked against a fresh download before it is "verified" | as above |
| BWSSB_WATER | **UNKNOWN.** Not among the 7 resources on https://data.opencity.in/dataset/bwssb-data (licence there: "No License Provided"), and not found via OpenCity catalogue search or web search | UNKNOWN | **Unverified** | **UNKNOWN** |

Common catalogue: *Road Accidents in India 2019* — https://www.data.gov.in/catalog/road-accidents-india-2019 (60 resources, contributor MoRTH, published 15/02/2023, updated 14/02/2025). Every resource lists the reference report https://morth.nic.in/sites/default/files/RA_Uploading.pdf. The same catalogue also has **A3 (killed), A4 (injured), A5 (fatal accidents), A6 (severity), A51 (blackspot counts), A45/A46/A48/A50 (city tables)**, which share A2's provenance and grain and would enable severity and rate questions.

**Human download steps (only after approval; save to a new folder such as `data/external/verify_2026-10-xx/`, never over `data/raw/`):**
1. Open https://www.data.gov.in/catalog/road-accidents-india-2019.
2. Search the resource list for the exact title in the table above, and open the resource page.
3. Click **Download**, choose CSV, fill the portal's usage form if asked, then save the file with its original name.
4. Record the retrieval date and SHA-256 hash, then compare with the hash prefixes in §3.

**BWSSB:** please tell me where this file came from (an RTI response, a BWSSB office spreadsheet, a news-article table, a classmate?). Until then it stays labelled *provenance UNKNOWN*. Candidate replacements with documented sources:
- OpenCity "Bengaluru Ward-wise Census Data – 2011"
- BBMP Ward Wise Work Orders (2018–2023)
- Bengaluru Lakes data by ward

**Repo catalogue defects** (`configs/datasets/canonical_metadata.csv`, 21 rows):
- TRF-005 ("Traffic Violations") points at the BWSSB URL.
- ENV-003's licence reads "Knowledge Graph License".
- TRF-002's dataset_url is the ministry homepage.
- CIT-004 points to indiastat (paywalled, not authoritative).
- TRF-003, WST-003 and CIT-001 are marked `ACQUIRED`, but none of their files exist locally.
- **None of the four MoRTH CSVs actually present is in this catalogue.**

---

## 5. Existing architecture map

```
CLI (cli.py) ─┐
              ├─> DecisionEngine.ask (ai/engine.py)
FastAPI (ai/api.py: /health /ask /datasets /datasets/{id}) ─┘
     │
     ├─ QuestionRouter (ai/intent.py)        keyword regex → 9 intents, year parsing
     ├─ _DISPATCH → ai/analytics.py          9 pandas functions → AnalyticsResult + Evidence
     │      └─ ai/datasets.py                5 hard-coded specs, encoding fallback, column finder
     ├─ providers.py                         deterministic | local HF | OpenAI-compatible API,
     │                                       missing_grounding() check → deterministic fallback
     └─ evidence.py                          frozen Evidence dataclass, citation()

Ingestion side (separate, ~4.5k lines): ingestion/{base,registry,catalog,metadata,policy,
pilot,transfer,integration,evidence,research_run,identifiers,states}.py,
handlers/trf_001|trf_004|trf_005.py (for datasets NOT present locally), profiling/csv_profile.py
```

The AI path and the ingestion path are **not wired together**. `ai/datasets.py` reads `data/raw/*.csv` directly with its own specs, ignoring the ingestion catalogue and manifests.

---

## 6. Implemented / partial / missing / replace matrix

| Target stage | Status | Evidence | Recommendation |
|---|---|---|---|
| Source registry / provenance | **Partial, partly wrong** | `canonical_metadata.csv` (defects above); `ai/datasets.py` specs say `license_status="unverified"` | Replace with a small per-dataset manifest (YAML/JSON) holding verified URL, hash, retrieval date and licence |
| Raw-file immutability | Partial | 5 CSVs committed; `.gitignore` allowlist | Keep; add hash pinning + test |
| Dataset-specific validation | Partial | Generic `profiling/csv_profile.py`; TRF handlers target absent datasets | Write 5 dataset validators (Total-row checksum, negative values, year-sum consistency, alias table, duplicate wards) |
| Catalogue | Partial / overbuilt | ingestion/* ~4.5k lines for 0 matching datasets | **Simplify**: keep useful pieces (hashing, state machine if used), retire the rest after review |
| Deterministic analytics | **Implemented, verified by tests** | `ai/analytics.py`, 9 functions; stable ties; units and periods in Evidence | Keep; add filters (state, city, year), lookups, rates, and Total-row exclusion checks |
| Intent routing / planning | **Present, unsafe** | Keyword router mis-routes (§1.2) | **Replace** with typed query spec + slot validation against data vocabulary + abstention |
| Evidence objects | **Implemented** | `ai/evidence.py`, `supporting_records` | Keep; extend with claim-level IDs, document passages, graph paths |
| Grounded generation guard | Implemented (basic) | `providers.missing_grounding` (figure/limitation presence) | Keep; extend to claim verification (numbers must exist in evidence, no extra numbers, citation IDs valid) |
| RAG | **Missing** | no code/deps | Build minimal (§8) |
| Knowledge Graph | **Missing** | no code/deps | Small PoC (§8) |
| Agentic orchestration | **Missing** (single-step pipeline) | `engine.py` docstring | Bounded planner/executor (§7) |
| API | Implemented, tested | `ai/api.py`, `tests/test_ai_api.py` | Keep; extend schema (plan trace, evidence, citations, abstention reason); add rate limit if exposed |
| Web UI | **Missing** | no frontend | Build after API contract freezes |
| Evaluation | Partial | `ai/evaluation.py`, 11 cases | Replace with a versioned 80–120 question set incl. adversarial/unanswerable (§10) |
| LLM provider | Present, unverified here | `providers.py` (HF local / OpenAI-compatible) | Keep interface; choose provider (decision D6) |

---

## 7. Recommended lean target architecture

```
                 ┌──────────────── Web UI (React+TS, Vite, Recharts) ────────────────┐
                 │ chat · answer card · evidence/citations · plan trace · charts ·   │
                 │ dataset pages · abstention states · feedback                      │
                 └───────────────────────────────┬───────────────────────────────────┘
                                                 │ JSON (typed)
                          FastAPI  /ask  /datasets  /datasets/{id}  /feedback  /health
                                                 │
        ┌──────────────────────── Orchestrator (plain Python) ─────────────────────────┐
        │ 1 Parse → QuerySpec(intent, metric, entities, geo level, period, filters)   │
        │   rules first; optional LLM parse → Pydantic-validated, never trusted raw   │
        │ 2 Resolve entities against data vocabulary + alias table (else clarify)     │
        │ 3 Feasibility check: dataset coverage, period, granularity, join legality   │
        │ 4 Plan ≤ 4 ToolCalls; 5 Execute (timeouts, read-only tools)                 │
        │ 6 Verify evidence (coverage, units, period, numeric claims) → maybe 1 retry │
        │ 7 Answer | qualify | clarify | abstain   8 Audit log (JSONL, no secrets)    │
        └──────┬──────────────────┬───────────────────────┬────────────────────────┬──┘
               │                  │                       │                        │
      Structured tools     Document RAG tool       Graph tool               Catalog tool
      pandas (DuckDB       SQLite FTS5 / BM25      networkx in-memory,      manifests,
      optional later)      over MoRTH report       built from manifests     coverage,
                           pages + data notes      + alias tables           licences
               └────────── Evidence package (records, passages, paths, provenance) ─┘
                                                 │
                       Response composer: deterministic template + optional LLM
                       phrasing → claim verifier → fallback to template on failure
```

Why each piece:
- **pandas** (already used): the data is 5 small CSVs. DuckDB/Postgres are not justified yet.
- **Pydantic + FastAPI**: typed contracts for tools and API, already partly in place.
- **SQLite FTS5** (stdlib, zero new dependencies) for the BM25 baseline. Embeddings only if retrieval evaluation shows lexical misses on paraphrased questions.
- **networkx**: about 700 nodes. Neo4j adds ops cost with no query benefit at this scale.
- **Plain-Python orchestrator, not LangGraph**: ≤ 4 steps, no long-running state. Revisit if human-in-the-loop checkpoints become a requirement.
- **React + TS + Vite**: Node 22 is available. The chat, evidence panes and charts benefit from a component model. Recharts covers bar and line charts. (A simpler alternative is HTMX + Jinja; decision D7.)

---

## 8. RAG and Knowledge Graph scope, and tool choice

**Documents that actually justify RAG (start with #1 only):**
1. MoRTH *Road Accidents in India 2019* report (`RA_Uploading.pdf`, the reference for every CSV). It holds the definitions (black spot, junction types, violation categories, severity), data-collection methodology and caveats. Example questions: "How does MoRTH define a black spot?", "What counts as 'Others' junction?", "Are 2018 road-length figures provisional?"
2. (Later, if approved) the Motor Vehicles (Amendment) Act 2019 from India Code, for penalty context. This is *legal text*: answers must quote it and never give legal advice.
3. Dataset notes and manifests themselves, so "what does this dataset cover?" is answered from manifests, not the LLM.

- Chunk per page or section, keeping the page number.
- Retrieval: BM25 with metadata filters, top-k = 5.
- Evaluation: about 25 labelled question→page pairs, measured with Recall@5 and MRR.
- Answers must quote the passage with page number, or abstain if the top passage score or overlap is below a threshold.

**Graph (PoC, only verified relations):**

| Node | Source | Edge (semantics) | Provenance |
|---|---|---|---|
| State (36) | A2 | — | A2 row |
| City (50) | A47/A49 | `LOCATED_IN` → State | **curated city→state table with citation** (A47 lacks state). Needs approval |
| District/TrafficUnit (~140) | A52 | `LOCATED_IN` → State (via alias table) | A52 row |
| Blackspot (273) | A52 | `LOCATED_IN` → District; `ON_ROAD` → Road id (text, unnormalised) | A52 row |
| Ward (198 numbers / 202 rows) | BWSSB | `LOCATED_IN` → City Bengaluru (delimitation v2010) | BWSSB file (provenance UNKNOWN) |
| Indicator, Dataset, ReportingPeriod | manifests | `MEASURED_BY`, `REPORTED_IN`, `DERIVED_FROM` | manifest |

- No causal edges, no `AFFECTS`, and no merges without an alias-table entry.
- Graph value is honest but modest: entity context ("everything known about Karnataka/Bengaluru"), cross-source navigation, explainable evidence paths. Evaluate it against a SQL-only baseline before claiming benefit.

**Tool selection policy (deterministic first, then optionally learned):**
- Number, ranking, comparison or trend over a dataset metric → structured tool (authoritative).
- Definition, method or policy wording → RAG tool.
- "What is related to / what do we know about entity X across sources" or multi-hop → graph tool, then the structured tool for any numbers.
- Out-of-coverage period or geography, forecast without time series, causal claims, cross-granularity joins, unresolved entities → abstain or clarify, with the reason.
- An LLM may propose the QuerySpec, but the executor only runs tools whose arguments validate against the schema **and** the data vocabulary.

---

## 9. Literature review, related work, gaps, and novelty hypothesis

Everything below was checked against the arXiv, ACL Anthology, CIDR or project pages in this session unless marked otherwise.

| Work | Venue (verified) | Relevance |
|---|---|---|
| **OGD4All** — Siebenmann, Argota Sánchez-Vaquerizo, Arisona, Samp, Gisler, Helbing. arXiv 2602.00012 | IEEE CAI 2026, pp. 882–888 | **Closest system.** Semantic dataset retrieval + agentic code generation + sandboxed execution over 430 Zurich datasets. 199-question benchmark with factual and unanswerable items; reports 98% analytical correctness, 94% recall, reliable rejection of unsupported questions |
| UrbanLLM — Jiang et al. arXiv 2406.12360 | Findings of EMNLP 2024 | Fine-tuned LLM that decomposes urban queries and selects spatio-temporal models (tool selection in urban domain) |
| CityGPT — Feng et al. arXiv 2406.13948 | KDD 2025 (per project repo) | Urban spatial knowledge in LLMs; CityEval benchmark. Not a provenance/abstention system |
| Agentic RAG survey — Singh et al. arXiv 2501.09136 | arXiv survey (v4 2026) | Taxonomy of routing, reflection, multi-agent RAG |
| Adaptive-RAG — Jeong et al. | NAACL 2024 | Routes by question complexity (no / single / multi-step retrieval). Baseline for adaptive strategy selection |
| GraphRAG — Edge et al. arXiv 2404.16130 | arXiv (Microsoft) | Graph-indexed RAG for global sensemaking. *Different* goal from our explicit fact graph |
| HybridRAG — Sarmah et al. arXiv 2408.04948 | arXiv 2024 | KG + vector retrieval beats either alone on financial docs |
| INRAExplorer (Agentic RAG with KGs) — Lelong et al. arXiv 2507.16507 | ECAI 2025 demo | Agent with KG tools for multi-hop and exhaustive queries |
| TAG: Text2SQL is Not Enough — Biswal, Patel et al. arXiv 2408.14717 | CIDR 2025 | Shows Text2SQL/RAG alone answer ≤20% of realistic DB questions. Motivates combining structured tools with LM reasoning |
| Self-RAG — Asai et al. arXiv 2310.11511 | *Venue not stated on arXiv page; widely cited as ICLR 2024; confirm before citing* | Retrieve-on-demand + self-critique |
| ALCE — Gao, Yen, Yu, Chen. arXiv 2305.14627 | EMNLP 2023 | Citation-quality metrics. Use for attribution evaluation |
| ReAct (Yao et al.), Toolformer, RAGAS | *Not re-verified this session* | Foundational tool-use / RAG-eval references. Verify before citing |

Also seen but not verified: OrQA (TRL workshop @ ACL 2025, government table-QA dataset generation); an Open Data Institute study on unreliable LLM answers about public services (press coverage only).

**Gaps relative to the closest work (as far as abstracts show; the full OGD4All paper must be read):**
- Evaluated abstention for **cross-granularity / cross-source join refusal** (state vs city vs ward, differing periods and delimitations).
- **Entity resolution with provenance** across inconsistent official naming (Orrisha/Odisha, Vizaq/Visakhapatnam) and its effect on answer correctness.
- Combining **structured analytics + document RAG + explicit fact graph** under one bounded planner, with per-tool ablations.
- **Claim-level verification** of LLM-phrased answers against deterministic evidence.
- Indian multi-level civic data (most prior systems are single-city, Western portals).

**Cautious novelty hypothesis (to test, not claim):**

> On heterogeneous, multi-granularity Indian civic datasets, a bounded planner that validates query slots against data vocabulary and checks join legality before tool execution yields fewer *confident wrong answers* than (a) keyword routing, (b) an unconstrained LLM tool-calling agent, and (c) an OGD4All-style code-generating agent, at comparable coverage. Document RAG and fact-graph tools add measurable value only on definitional and cross-source questions respectively.

Measurable research questions:
- **RQ1:** False-answer rate on unanswerable or trap questions, and abstention precision/recall, compared across planners.
- **RQ2:** Numeric exact-match and claim-support rate with and without the claim verifier.
- **RQ3:** RAG Recall@5 / MRR, plus ALCE-style citation precision/recall on definitional questions.
- **RQ4:** Graph-path correctness and answer accuracy on cross-source questions, graph vs SQL-only.
- **RQ5:** Latency and step count.

---

## 10. Phased implementation roadmap (after approval)

| Phase | Deliverable | Acceptance criteria / tests |
|---|---|---|
| P0 Housekeeping | Branch `phase2/foundation`; decide fate of stale top-level files | CI-equivalent `pytest` + `ruff` still green |
| P1 Data foundation | `data/manifests/*.yaml` (URL, hash, retrieved, licence, period, geo, units, known issues); 5 validators; alias tables (state, city) with sources; re-verify A52 hash | Tests: hash pinning; Total-row checksum equals the column sum of the other rows; negative-value and year-sum anomalies reported, not fixed; duplicate wards reported |
| P2 Analytics v2 | Filterable lookup/rank/compare/share/rate/trend (2016–19 only) tools with Pydantic arg schemas | Golden values hand-computed for ≥ 30 cases; ties and nulls specified and tested |
| P3 Planner | QuerySpec parser (rules) + entity resolver + feasibility checker + abstention reasons; replaces `intent.py` | All 12 probe questions from this audit behave correctly; no regression on the existing 11 |
| P4 RAG | MoRTH report ingestion (page text, metadata), FTS5 BM25, passage evidence | Recall@5 ≥ target agreed with you on ~25 labelled questions; abstains below threshold |
| P5 Graph PoC | networkx build from manifests/alias tables; 5–8 query templates | Every edge has a source row ID; ambiguous merges rejected by test |
| P6 Orchestrator | ≤4-step plan, timeouts, 1 repair retry, JSONL audit trail, permissions (read-only tools) | Step limit and timeout tests; injection strings in documents/questions cannot change tool permissions |
| P7 Response + LLM | Template answers; optional LLM phrasing + claim verifier | No number outside the evidence survives; fallback tested |
| P8 API v2 | `/ask` returns plan trace, evidence, citations, abstention; `/feedback` | Contract tests; OpenAPI schema frozen before UI |
| P9 Web app | React/TS UI per spec | Playwright/RTL smoke tests; mobile layout; empty, error and abstain states |
| P10 Evaluation | Versioned 80–120 question set (~35 numeric, ~15 filtered, ~15 definitional, ~10 cross-source, ~25 unanswerable/trap, ~5 injection) + baselines | Report per-component metrics with set composition; no "general accuracy" claims |
| P11 Docs | Setup, architecture, provenance, limitations, reproducible experiments | Fresh-clone run reproduces the evaluation |

---

## 11. Decisions needed from you

1. **D1 – Keep & refactor this repo (recommended)** vs. a fresh repo. Recommendation: keep, work on a branch, and prune the ingestion layer after review.
2. **D2 – Working location:** use `C:\Desktop\civicmind-ai-main\repo` as the project root? And may I delete the two stale top-level files (`README.md`, `.gitignore` from the initial commit)?
3. **D3 – BWSSB file:** tell me its origin. Otherwise choose: keep it flagged "provenance UNKNOWN", or exclude it from answers until sourced.
4. **D4 – Approve downloading** (to a separate verify folder, not over `data/raw`): A52 fresh copy for hash comparison; optionally A3/A4/A5/A6/A51 from the same catalogue; the MoRTH 2019 report PDF for RAG.
5. **D5 – City→state mapping:** approve a small hand-curated, cited table (50 rows) for the graph.
6. **D6 – LLM:** this PC has no GPU. Options: (a) template-only for now, (b) hosted API (needs a key; data is public), or (c) local small model on the college PC. Recommendation: (a) until P7, then decide.
7. **D7 – Frontend:** React+TS+Vite (recommended) vs. HTMX/Jinja (simpler, fewer moving parts).
8. **D8 – Git workflow:** commit locally only, or push branches to `lp-0406/civicmind-ai` (and under which author identity)?

**Phase 1 stops here.** No implementation until you approve.
