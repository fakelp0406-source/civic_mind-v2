# Evaluation (not yet implemented)

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
