# M05 stage 2D: routing and edition-guard evaluation

Status: 2026-10-18, branch `feat/m05-stage2-secure-rag`. Generated numbers:
[`eval/reports/route.v1.results.md`](../../eval/reports/route.v1.results.md) and `.json`, from
`python eval/route_metrics.py`. Same frozen labels as stage 2E
(`eval/questions/rag.v1.yaml`, SHA-256 `3abd4257…e85f`, checked by the harness; unchanged), same
34/31 calibration/test split, same index `f10ba588d120b144`. **Thresholds were not re-tuned**:
the router uses the stage 2E calibrated thresholds (BM25 21.775342, dense 0.638919). The stage 2C
provisional thresholds appear only as a comparison row. The stage 2E reports are unchanged
(verified by hash). **The set is small and single-labeller; the numbers describe it only.**

## Results (65 items: 38 supported, 18 expecting abstention, 6 analytics, 3 composite)

| Router (calibrated thresholds) | Split | Supported answered with a gold citation | Abstentions correct | Analytics identical to pipeline | Unsupported answers |
|---|---|---|---|---|---|
| **BM25 gate** | calibration | 4/19 (0.21) | 10/10 | 3/3 | **0** |
| **BM25 gate** | test | 3/19 (0.16) | 8/8 | 3/3 | **0** |
| Dense gate | calibration | 4/19 (0.21) | 10/10 | 3/3 | 1 |
| Dense gate | test | 5/19 (0.26) | 8/8 | 3/3 | 0 |

Gate selection on the calibration split: balanced accuracy tied (0.605), and the BM25 gate was
chosen on the pre-set tie-break (fewer unsupported answers: 0 against 1). `RouterConfig` defaults
to BM25, tied to the report by `tests/test_route_eval.py`.

With the provisional thresholds, both gates gave **5 unsupported answers on the calibration
split** (BM25 also answered three abstention items: A05 property tax, M01 speed limit, M03 helmet
fine). This confirms the calibrated values are needed.

### Per-category outcomes (BM25 gate, all items)

| Category | Items | Outcome | Codes |
|---|---|---|---|
| supported | 38 | 7 answered with gold citations, 31 abstained, 0 unsupported | `query.metric_missing` 10, `query.causal` 8, `rag.no_evidence` 8, `query.period_missing` 2, `city.not_found` 1, `query.unrecognised_terms` 1, `status.quarantined` 1 |
| edition (2024 / latest) | 4 | 4 refused | `rag.edition_unavailable` 1, `query.metric_missing` 1, `query.causal` 1, `query.period_missing` 1 |
| absent | 8 | 8 refused | `query.out_of_scope` 4, `rag.no_eligible_documents` 1, `rag.no_evidence` 1, `query.unit_unsupported` 1, `modelled.not_trusted` 1 |
| misleading overlap | 6 | 6 refused | `rag.no_evidence` 2, `query.period_missing`, `query.metric_missing`, `query.causal`, `query.cross_domain` |
| analytics | 6 | 6 answered by the pipeline, identical | none |
| composite | 3 | 3 refused (not scored) | `route.mixed_unsupported` 2 (C01: data part answered, document part `rag.no_evidence`; C02: second part numeric and unattributed), `query.unit_unsupported` 1 |

Answered document questions (BM25): S05, S06, S09, S10, S33, S35 and S38, each citing at least
one gold page. Every edition question was refused, either by the edition guard or by the
deterministic refusal (unattributed numeric or causal 2024 questions never reach documents). No
citation came from RA2024 or from RA2019 pages 2-7; this is also asserted in
`tests/test_router.py` across all 65 questions and three extra adversarial ones.

### Compared with raw retrieval (stage 2E, test split, same thresholds)

| | Evidence-supported (supported items) | Abstain rate | Unsupported answers |
|---|---|---|---|
| Raw BM25 | 0.42 | 1.00 | 0.00 |
| Raw dense | 0.53 | 0.75 | 0.25 |
| **Router, BM25 gate** | **0.16** | **1.00** | **0** |
| Router, dense gate | 0.26 | 1.00 | 0 |

The router removes the dense failure mode completely: the four 2024/"latest" items and M04 are
no longer answered. The price is coverage. Most supported items are **unattributed numeric
questions** ("How many road accidents were reported in 2019?"), which by design keep their
deterministic refusal, and the BM25 gate still abstains on short definition questions.

## Interpretation, without over-claiming

- On this set, the router answered **nothing it should have refused**, returned every
  deterministic answer unchanged, and kept every protected refusal.
- The dense gate answers more definition questions (S01-S04, S37). Its one unsupported answer
  (S03) cites the definitions appendices (RA2023 p270, RA2019 p211), whose "Minor Injury
  Accident" wording the extractor did not recover in the labelled phrase. That may be a gold-label
  undercount, but under the frozen rules it counts as unsupported. **Higher coverage is not
  evidence that semantic retrieval is better**: with 19 test items, the difference between 3 and 5
  answers is within noise, and the calibration split favoured BM25 on the pre-set tie-break.
- Coverage is low (7 of 38). This is a deliberate safety choice, not a retrieval result.

## Does the evidence support API integration?

**Yes, for a conservative, additive integration, with conditions:**

1. Route through the router with the BM25 gate. Keep every existing response field and code:
   deterministic answers and refusals already pass through unchanged (6/6 identical).
2. Add document fields additively (`route`, `citations`, document caveats). The deterministic
   refusal codes stay authoritative for non-document questions.
3. Load the index once at start-up with full verification, and re-verify on a schedule or on
   manifest change (`Router.reload()`); refuse with `rag.index_*` or `rag.corpus_integrity` when
   verification fails.
4. Re-run `eval/rag_metrics.py`, `eval/route_metrics.py` and `eval/coverage_metrics.py` after
   integration, and present coverage honestly: most report-statistic questions will still be
   refused.

**Not supported by this evidence:** widening document routing to unattributed numeric
questions, switching to the dense gate, or any general accuracy claim. Each needs a fresh
labelled set, because these labels have now informed two design decisions.

## Limitations

- 65 items, one labeller, two documents of one publisher. Composite items are unscored (no gold).
- The document-question patterns are closed lists; paraphrases outside them are refused, which is
  safe but reduces coverage. They were designed with knowledge of this question set, so their
  coverage on new questions is unknown.
- The router reuses the parser's domain detection; a document question whose wording the parser
  maps to another domain (S30 maps to census) follows that domain's rules.
- Latency: router start-up about 3 s (index verification). Per question, the deterministic
  pipeline dominates (median about 0.7 s); BM25 retrieval adds about 4 ms.
