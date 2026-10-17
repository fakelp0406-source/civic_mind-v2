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
