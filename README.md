# civic_mind-v2 — CivicMind AI

Evidence-grounded, bounded-agent decision support for municipal officers and civic analysts.
CivicMind AI answers questions about city services (roads and traffic safety, solid waste,
water and sewerage, drainage, environment, complaints, infrastructure and finance) **only
from validated data and cited official documents**. When the evidence is insufficient, it
clarifies or abstains.

> **Status: project skeleton (v0.0.1). Nothing is implemented yet.**
> The repository holds the directory structure, configuration, architecture documentation
> and one smoke test. No dataset has been downloaded or registered. No legacy code has been
> ported. There is no model or LLM provider.

## What this system is (and is not)

- **Is:** a decision-support tool. Numbers come from deterministic, tested functions over
  validated datasets. Explanations come from cited passages of official documents.
  Relationships come from source-supported graph edges. A bounded planner chooses among
  these tools, and every answer carries its sources, period, geography, units and caveats.
- **Is not:** an autonomous action system, a chatbot that guesses, a forecasting engine
  (without a separately evaluated method), or a Digital Twin. Recommendations require
  human review.

## Architecture layers

| Layer | Package | Status |
|---|---|---|
| Catalogue, manifests, validation | `src/civicmind/catalog` | skeleton |
| Deterministic analytics | `src/civicmind/analytics` | skeleton |
| Document retrieval (RAG) | `src/civicmind/rag` | skeleton |
| Civic Knowledge Graph | `src/civicmind/graph` | skeleton |
| Query planning and feasibility | `src/civicmind/planner` | skeleton |
| Bounded orchestration | `src/civicmind/orchestrator` | skeleton |
| Evidence model | `src/civicmind/evidence` | skeleton |
| Response composition and verification | `src/civicmind/respond` | skeleton |
| HTTP API | `src/civicmind/api` | skeleton |
| Evaluation | `eval/` | skeleton |
| Website | `web/` | future (after the API contract is frozen) |

See [docs/architecture.md](docs/architecture.md) for boundaries, data flow and decisions that
are still provisional.

## Data status

No dataset is registered in this repository yet. Candidate sources come from the discovery
work in [docs/discovery/](docs/discovery/):

- **Candidate sources:** the 124 records in `civicmind_dataset_catalog.csv`. Each has a
  `status` (VERIFIED_RESOURCE, VERIFIED_CATALOG, DOC_LINK_UNVERIFIED, REGISTRATION,
  NOT_VERIFIED, NOT_FOUND). This is *portal metadata* evidence; it does not mean the
  data has been downloaded or validated.
- **Verified datasets in this repo:** none yet. A dataset becomes "verified" only after it is
  downloaded to `data/external/verify_*/`, hash-pinned, validated, and described by a
  manifest in `data/manifests/`.
- **Unverified legacy files:** the legacy repository's `BWSSB_Water_Consumption_August_2025.csv`
  stays outside this repo (quarantine policy) until its hash matches the official
  Karnataka OGD resource.

Data handling rules are in [data/README.md](data/README.md).

## Local setup

Requirements: Python 3.11+ (developed and tested on Python 3.13.15; 3.11 and 3.12 are
declared but not yet tested), Git. On Windows, the `py` launcher selects the version.

```bash
git clone https://github.com/fakelp0406-source/civic_mind-v2.git
cd civic_mind-v2
py -3.13 -m venv .venv-py313
```

Dependency installation is a later, separately approved step. Once approved:

```bash
.venv-py313/Scripts/python -m pip install -e ".[api,dev]"
```

Run the checks (after installation):

```bash
.venv-py313/Scripts/python -m pytest
.venv-py313/Scripts/python -m ruff check .
```

Virtual environments (`.venv*/`) are git-ignored. An older Python 3.10 environment (`.venv`)
may still exist locally; it is no longer the supported setup.

## Related material

- Audit of the legacy repository (`lp-0406/civicmind-ai`): [docs/audit/](docs/audit/)
- Dataset discovery report and catalogue: [docs/discovery/](docs/discovery/)
- Porting log for any legacy code reused later: [docs/PORTING_NOTES.md](docs/PORTING_NOTES.md)
