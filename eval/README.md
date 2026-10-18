# Evaluation

Implemented so far:

- `golden/batch01_analytics.v1.yaml`: 25 questions for analytics A1-A4 on batch-01 promoted
  data (13 answerable: numeric, ranking, comparison, including T10 intensity flags; 12 that
  must be refused). Run by
  `tests/test_golden_analytics.py`; items skip when the git-ignored source files are absent.
- `golden/derive_batch01.py`: independent standard-library derivation of the expected values;
  the golden tests check the YAML against it.
- `questions/pipeline.v1.yaml`: 55 end-to-end pipeline questions (expected status and
  refusal code), run by `tests/test_pipeline.py` and, through the HTTP API, by
  `tests/test_api.py`.
- `questions/coverage.v1.yaml`: 35 research-classified questions (answerable from trusted
  data, derived, requiring documents, requiring relationships, underspecified, unsupported by
  data, blocked by trust). `coverage_metrics.py` runs them and reports correct-answer,
  correct-refusal and unsupported-answer rates, evidence completeness, provenance correctness,
  comparability violations and freshness coverage
  (`.venv-py313/Scripts/python.exe eval/coverage_metrics.py`); `tests/test_coverage_v1.py`
  asserts them.

- `questions/rag.v1.yaml`: 65 labelled document-retrieval items (supported with gold pages
  derived from key phrases, edition, absent, misleading, analytics and composite probes).
  `rag_metrics.py` compares BM25, MiniLM dense retrieval and the deterministic pipeline, calibrates
  thresholds on a calibration split and reports on a held-out split, plus a synthetic
  prompt-injection check; results in `reports/rag.v1.results.{json,md}`, interpreted in
  `docs/evaluation/M05_RAG_EVALUATION.md`. `tests/test_rag_eval.py` checks the scoring functions
  and re-derives the labels from the corpus.

- `api_metrics.py`: stage 2F, the router through `POST /api/v1/query`. Three separate
  measurements: deterministic regression (`coverage.v1`, `pipeline.v1` and the rag.v1
  analytics items against the deterministic-only API), the frozen rag.v1 labels scored from
  HTTP responses and compared item by item with the frozen stage 2D results, and citation
  leakage, plus machine-dependent cold-start and warm latency. Results in
  `reports/api.v1.results.{json,md}`; it never writes the rag.v1 or route.v1 reports.

- `route_metrics.py`: evaluates the stage 2D router on the same frozen labels and split
  (thresholds not re-tuned; gate chosen on the calibration split), writing
  `reports/route.v1.results.{json,md}`, interpreted in `docs/evaluation/M05_ROUTING_EVALUATION.md`.

Planned contents:

- `questions.v1.jsonl`: a versioned question set. Each item records the expected tool(s),
  the expected answer, abstain or clarify decision, the expected sources, and a category:
  numeric, filtered, RAG/definition, graph/cross-source, unanswerable/trap, or
  prompt-injection.
- `golden/`: hand-computed expected values with a derivation note per item.
- `run_eval.py`: runs component metrics separately — validation, retrieval Recall@k/MRR,
  graph-path correctness, tool-selection accuracy, numeric exact match, citation
  precision/recall, unsupported-claim rejection, abstention precision/recall, latency.
- `baselines/`: keyword router, LLM without tools, and a code-generating agent, compared on
  the same set.
- `results/` (git-ignored): run outputs.

Reports must state the question-set size and composition. A small fixed benchmark is never
presented as general real-world accuracy.
