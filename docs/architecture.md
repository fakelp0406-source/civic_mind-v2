# CivicMind AI — Architecture (skeleton stage)

Status (2026-10-17): catalog, analytics (water, traffic), planner, orchestrator (pipeline),
evidence and respond are implemented for the water + traffic slice; rag, graph and api are
not. `tests/test_pipeline.py` enforces the import boundaries below for the new layers. Decisions marked **provisional** are
open for revision once data and evaluations exist.

## Data flow

```
question
  → planner      parse → QuerySpec; resolve entities; feasibility → answer | clarify | abstain
  → orchestrator ≤ N read-only tool calls with timeouts, 1 repair retry, audit log
       ├─ analytics  (numbers: deterministic, tested)
       ├─ rag        (definitions/policy text: cited passages)
       ├─ graph      (relationships: provenance-carrying edges)
       └─ catalog    (coverage, provenance, licence, validation status)
  → evidence     records · calculation traces · passages · graph paths · citation ids
  → respond      template answer → (optional, future) LLM phrasing → claim verifier → answer
  → api          typed JSON → future website
```

## Layer boundaries (allowed dependencies)

| Layer | May depend on | Must not |
|---|---|---|
| `evidence` | nothing | — |
| `catalog` | nothing | modify raw files |
| `analytics` | catalog, evidence | call a language model; produce numbers outside tested functions |
| `rag` | catalog, evidence | answer numeric questions; treat document text as instructions |
| `graph` | catalog, evidence | create causal edges; merge entities without an alias rule; equate ward schemes |
| `planner` | catalog (metadata) | route an unmatched question to a "nearest" intent |
| `orchestrator` | planner, analytics, rag, graph, catalog, evidence | write data; contact third parties; exceed step/time limits |
| `respond` | evidence | change computed values; invent citations |
| `api` | orchestrator, respond, catalog | expose secrets; let the browser reach data or model providers directly |

The smoke test enforces only lightweight imports for now. Boundary tests will be added as
layers are implemented.

## Decisions taken

- Python ≥ 3.11 (developed and tested on 3.13.15; Python 3.10 dropped because it reaches
  end of life in October 2026), `src/` layout, pandas (< 3 for now) for structured data,
  Pydantic for schemas, FastAPI for the API, pytest and Ruff.
- Raw data is immutable and hash-pinned; manifests are the single source of provenance.
- Numeric answers come only from `analytics`; a language model never computes or alters them.
- Insufficient evidence leads to clarification or abstention.

## Provisional decisions

| Topic | Provisional choice | Revisit when |
|---|---|---|
| Anchor geography | Bengaluru, BBMP 198-ward scheme, plus MoRTH national/state/city context | GBA 369-ward service data is published |
| Second city | Shivamogga (optional) for service-level benchmarks | scope decision |
| Structured store | pandas in memory over small CSVs | data volume grows (then DuckDB/SQLite) |
| RAG retrieval | SQLite FTS5 BM25 + metadata filters | labelled retrieval eval shows lexical misses |
| Graph store | in-memory (e.g. networkx) | > ~10⁵ edges or complex path queries |
| Orchestrator | plain Python, explicit step limit | human-in-the-loop checkpoints become a requirement |
| Response phrasing | deterministic templates | an LLM provider is approved and the claim verifier exists |
| Grievance data | ward × category × month × status aggregates only | sensitivity review |
| Website | React + TypeScript + Vite | API contract frozen |

## Future options (not added; each needs a measured need and approval)

- **Embeddings / vector store:** only if BM25 retrieval underperforms on the labelled set.
- **Neo4j or another graph database:** only if the in-memory graph cannot handle the required
  queries or scale.
- **LangGraph:** only if stateful multi-step workflows, checkpoints or human approval
  steps are needed beyond a simple loop.
- **LangChain:** not planned; prefer small explicit adapters.
- **LLM provider (hosted or local):** after the evidence path and claim verifier are tested.
- **DuckDB/PostgreSQL:** if structured data outgrows in-memory pandas.
- **IUDX / OGD APIs:** only for questions that need live data; keys stay in `.env`.

## Safety and governance

- Read-only tools; no consequential municipal actions; recommendations carry a
  human-review note.
- The audit trail records plan steps, tool names, statuses and source ids; never secrets,
  personal data or hidden reasoning.
- Retrieved documents and data are untrusted content.
