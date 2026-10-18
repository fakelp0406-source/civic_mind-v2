# M05 stage 2E: document retrieval evaluation

Status: 2026-10-18, branch `feat/m05-stage2-secure-rag`. Generated numbers:
[`eval/reports/rag.v1.results.md`](../../eval/reports/rag.v1.results.md) and `.json`, produced by
`python eval/rag_metrics.py`. This page interprets them. **The set is small (65 items, 38
answerable), single-labeller, over two documents of one publisher: the numbers describe this
set only and are not general accuracy claims.**

## What was evaluated

| | |
|---|---|
| Corpus | DOC-MORTH-RA2023, DOC-MORTH-RA2019 (pages 2-7 excluded); RA2024 quarantined |
| Index | `f10ba588d120b144`: 2,394 chunks (`chunk@v1`, `docscreen@v2`) |
| Methods | BM25 (SQLite FTS5) and dense (`all-MiniLM-L6-v2` ONNX @ `1110a243`), both extractive; the existing deterministic pipeline as a third system |
| Labels | `eval/questions/rag.v1.yaml`, SHA-256 `3abd425762429179869390ef744f08a65eee4f8783c9234f6e87e93271d3e85f`, frozen before any retriever ran on it |
| Split | stratified alternation by category: 34 calibration, 31 test; thresholds chosen on calibration only |

### How the labels were made

Supported items: the labeller (the session that built the system, with no second reviewer) read
the extracted text and chose key phrases stating each answer. Gold pages were then computed by
exact phrase search over approved, non-excluded pages, within the asked edition, and are
re-derived by `tests/test_rag_eval.py`. Absent and misleading items: their verification phrases
match no page (also re-checked by the test). Disclosure: the labeller had seen retrieval output
for one question (S02) during the stage 2C sanity check.

Categories: supported 38; edition 4 (three ask about 2024, absent from the corpus, and one about
an unnamed "latest" report); absent 8; misleading keyword overlap 6; analytics routing probes 6;
composite (data plus documents) 3. Prompt injection is measured on a separate synthetic corpus,
because the real documents contain none.

## Results

### Retrieval quality (threshold-free, 38 supported items; test split n = 19)

| | Recall@1 | Recall@3 | Recall@5 | MRR@10 |
|---|---|---|---|---|
| BM25, all / test | 0.45 / 0.47 | 0.66 / 0.68 | 0.71 / 0.79 | 0.59 / 0.62 |
| Dense, all / test | 0.50 / 0.58 | 0.66 / 0.68 | 0.76 / 0.79 | 0.61 / 0.66 |

Dense is slightly ahead at rank 1, and the methods tie at ranks 3 and 5 on the test split. With
19 to 38 items, a difference of one or two questions is within noise: **no meaningful
difference in retrieval quality is shown**. About a quarter of supported questions have no gold
page in the top 5 under either method.

### Answer and abstention decisions at the calibrated thresholds

| | Threshold | Answer rate | Evidence-supported | Abstain rate (should abstain) | Unsupported answers | Edition accuracy |
|---|---|---|---|---|---|---|
| BM25, test | 21.78 | 0.58 | 0.42 | **1.00** | **0.00** | 0.67 |
| Dense, test | 0.639 | 0.84 | 0.53 | 0.75 | 0.25 | **0.92** |

*Evidence-supported* means a cited hit is on a gold page. Citation page precision is low for both
methods (0.39 to 0.57), because three passages are cited and usually only one is on a gold page.
Some answered supported items cite no gold page at all (BM25: 0.58 answered against 0.42
supported).

The two methods fail in different ways:

- **BM25's perfect abstention is partly an artefact of query length.** BM25 scores grow with the
  number of matched terms, and the calibrated threshold (21.8) is high enough to reject every
  short definition question (S01-S04, S36, S37) along with the absent ones. One global BM25
  threshold does not transfer across question types.
- **Dense answers edition questions it should refuse.** All four edition items (2024 and
  "latest") match RA2023 passages at high similarity (0.75 to 0.83), as does one misleading item
  (M04, electric scooters, 0.69). Similarity cannot tell that the asked year has no approved
  edition; that needs an explicit rule.

### The stage 2C provisional thresholds were unusable

At BM25 ≥ 4.0 and dense ≥ 0.45, retrieval answered **100% (BM25) and 72% (dense)** of the
questions that should be refused. The defaults in `RetrievalConfig` are now the calibrated values
(`tests/test_rag_eval.py` ties them to this report).

### Deterministic-only behaviour

The existing pipeline answers all 6 analytics questions and **none** of the 38 document
questions, refusing them with its usual codes (`query.period_missing` 11, `query.metric_missing`
11, `query.causal` 9, `query.out_of_scope` 4, …). It refuses every absent, misleading, edition
and composite question. Documents add answerable coverage that the pipeline does not have; the
question is how to gate it safely.

### Routing probes

At the calibrated thresholds, dense retrieval would answer **3 of the 6 analytics questions**
(R01, R03, R05: city traffic counts) by quoting report passages. Those questions belong to the
deterministic pipeline, which answers them from trusted tables. BM25 would answer none. Both
would answer 2 of the 3 composite questions with the document half only. **Routing must happen
before retrieval**: analytics intents must never fall through to document quotes.

### Prompt injection (synthetic corpus, 6 pages, 6 questions)

All 4 screened injections were dropped at indexing (0 indexed, 0 quoted). The 2 unscreened
steering passages were indexed, and each method quoted one of them once; every answered response
(4 for BM25, 6 for dense) kept the fixed template, the "quoted document text" caveat and correct
attribution. Dropping a flagged chunk also drops the benign text sharing that chunk.

### Performance (Windows, Python 3.13.15, CPU only)

Index load with full verification 2.6 s; encoder load 1.6 s; BM25 query p50 3.9 ms (p95 6.3 ms);
dense query p50 12.7 ms (p95 18.0 ms); peak memory 339 MB; index files 8.8 MB. Building the dense
vectors took about 7 minutes (single-threaded, for reproducibility).

### Reproducibility

Two complete runs gave identical results outside the performance block. Pinned inputs: the label
hash, index id and corpus digest, model revision and file hashes, chunker and screen versions.

## What this means for stage 2D (API integration)

1. **Route first.** Deterministic intents (the parser's answerable analytics and catalogue
   questions) never go to retrieval. Only questions the router classifies as document questions
   may.
2. **An explicit edition guard.** A question naming a year with no approved edition, or asking for
   the "latest" or "current" report, is refused (for example `rag.edition_unavailable`, or the
   existing `query.period_missing`). This fixes the dense failure mode deterministically, rather
   than by tuning a threshold.
3. **Abstention gate**: BM25 at its calibrated threshold gave zero unsupported answers on this
   set but low coverage. A combined gate (for example both methods agreeing, or a length-normalised
   BM25 score) is promising but was **not** evaluated. Choosing it on these labels would overfit,
   so it needs a fresh labelled set.
4. **Cite fewer, better passages.** Page precision is low with three citations; citing only
   passages that clear the threshold *and* contain a query term would help, but needs evaluation.
5. **Composite questions** stay unsupported until the orchestration in the design (each half
   independently supported) is built.

## Limitations

- 65 items, one labeller, two documents of one publisher, all English, so wide error bars. Gold
  is page-level and phrase-based: a page stating the answer in other words is not gold, which can
  undercount correct retrievals.
- Thresholds are fitted to 34 calibration items and this index; any re-chunking or re-indexing
  needs recalibration.
- No answer-generation model is involved (extractive only). "Correctness" here means that the
  cited page contains the labelled evidence, not that a reader judged the quote sufficient.
- Many supported questions are long and specific, which favours BM25 at its high threshold;
  shorter natural phrasings were not sampled systematically.
