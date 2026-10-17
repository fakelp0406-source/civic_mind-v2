# Batch 02 intake report — water series extension and MoRTH road-safety tables

**Status (2026-10-17, stage 3 — approved decisions executed):** see **§0** for the actual outcomes.
- 6 water months are **promoted** to `data/raw/water/`.
- June 2025 is **quarantined** in `data/quarantine/batch-02/`.
- January 2026 is **not trusted** (keep_profiled). It is readable only through labelled exploratory ingestion (§0.5, approved and implemented).
- **Batch 02 milestone closure verified (§0.10).** Commit scope proposed (§0.11); not committed.
- The four A47 2020–2023 editions are **promoted** to `data/raw/roads/` after the owner's explicit accept decisions (§0.6).
- The 2024 Annexures 1, 2 and 49 are **kept profiled**, with no analytics.
- Batch 01 trust statuses and files are unchanged.

This file is the single source of truth for Batch 02 acquisition.

**Stages.**
- **Stage 3 (execution):** §0 — what was actually done. It supersedes the *planned* dispositions in §12 and the "proposed" wording of §9–§13.
- **Stage 1 (intake):** §1–§7 — inventory, profiling and comparability.
- **Stage 2 (controlled preparation):** §8–§16 — evidence verification, investigations, identity design and proposals. This is kept as the record of that stage.

**Supporting evidence**, all under `docs/acquisition/batch-02/` unless noted:

| Path | Content | Produced by |
|---|---|---|
| `REVIEW_DECISIONS.yaml` | **The recorded decisions** (stage 3), bound to SHA-256, in the Batch 01 schema | Recorded from the owner's chat decisions of 2026-10-17 |
| `summary.json` | **Actual outcome per dataset**, plus re-ingestion results in trusted and exploratory modes | `scripts/process_batch_02.py` |
| `data/manifests/<ID>.yaml` (15 new) | The real manifests used by the planner and ingestion | same |
| `profiles/<ID>.json`, `cross_checks.json` | Stage 1 profiles and cross-period checks | `scripts/profile_batch_02.py` |
| `proposed_manifests/`, `proposed_schemas.yaml`, `dry_run_ingest.json`, `REVIEW_RECOMMENDATIONS.yaml` | Stage 2 proposals and dry run (historical; **superseded** by the items above) | `scripts/propose_batch_02.py` |

---

## 0. Stage 3 — actual outcomes (2026-10-17)

### 0.1 Owner decisions and how each was recorded

| # | Owner decision | How it was recorded | Outcome |
|---|---|---|---|
| 1 | Approve the road identity fix | Code (from stage 2), kept | Road intents resolve within Annexure 47 only. Verified on the real catalogue, which now also holds A1, A2 and A49 for 2024: the 2024 question is answered from `ROAD-RA2024-A47` |
| 2 | Register A47 schema versions for 2020–2023 | `catalog/schemas.py`: `morth_city_a47/ra2020_2021`, `/ra2022`, `/ra2023` | Registered (§0.3) |
| 3 | Seven water months for trusted promotion review | `REVIEW_DECISIONS.yaml`: `accept` for Jul, Sep, Oct, Nov, Dec 2025 and Feb 2026, each listing exactly the warning codes the processor produced | **6 promoted** through the existing gate. January follows decision 5 |
| 4 | Keep June 2025 quarantined | `decision: quarantine` | Moved (`os.rename`, bytes unchanged) to `data/quarantine/batch-02/`; status `quarantined`, human_review `rejected` |
| 5 | January 2026 exploratory-only until the Horamavu condition is met | `decision: keep_profiled`, `permitted_uses: [exploratory]` | **Not promoted, not trusted.** The planner refuses it (`dataset.not_trusted`). See the limitation in §0.5 |
| 6 | Swing and zero-accident checks as warnings only | Validators (§0.4) | Both emit `warning` only. They never change values or reject anything; a dataset with the warning is promoted only if the review lists it as an accepted caveat |
| 7 | Pune 2021 and the MoRTH 2020 revision note as source caveats | `known_limitations` ("SOURCE CAVEAT: …") in the `ROAD-RA2021-A47` and `ROAD-RA2020-A47` manifests; plus the `casualties.zero_accidents` warning finding on 2021 | Recorded |
| 8 | Defer derived cross-year growth rates and category sums | A `known_limitations` entry on each A47 2020–2023 manifest. No analytics were added (none exist that sum categories or compute growth) | Deferred |
| 10 | Accept A47 2020, 2022 and 2023 (no caveats) and 2021 (accepting `casualties.zero_accidents`), given after §0.6 was first reported | `decision: accept` entries in `REVIEW_DECISIONS.yaml`, bound to SHA-256 | **4 promoted** through the existing gate (§0.6) |
| 9 | Keep 2024 A1, A2 and A49 separate; no analytics | `decision: keep_profiled`, with no permitted uses; no schema registered; no intent added | Status `integrity_passed`, human_review `pending`; trusted and exploratory ingestion both refused |

### 0.2 Actual disposition of the 15 files

| Dataset ID | Status | Review | Location (hash-verified) | Trusted ingest | Exploratory ingest |
|---|---|---|---|---|---|
| WATER-BWSSB-2025-06 | **quarantined** | quarantine (rejected) | `data/quarantine/batch-02/Water_Consumption_Data_June_2025.csv` | refused `status.quarantined` | refused |
| WATER-BWSSB-2025-07 | **promoted** | accept | `data/raw/water/Water_Consumption_Data_July_2025_0.csv` | ✔ `bwssb_monthly/v1` | n/a |
| WATER-BWSSB-2025-09 | **promoted** | accept | `data/raw/water/Water_Consumption_Data_Sept_25_4.csv` | ✔ | n/a |
| WATER-BWSSB-2025-10 | **promoted** | accept | `data/raw/water/Water_Consumption_Data_Oct_25_3.csv` | ✔ | n/a |
| WATER-BWSSB-2025-11 | **promoted** | accept (+ `series.swing`) | `data/raw/water/Water_Consumption_Data_Nov_25_2.csv` | ✔ | n/a |
| WATER-BWSSB-2025-12 | **promoted** | accept (+ `series.swing`) | `data/raw/water/Water_Consumption_Data_Dec_25_5.csv` | ✔ | n/a |
| WATER-BWSSB-2026-01 | **validated** (not promoted) | keep_profiled, exploratory permitted | `data/external/batch-02/water/` (staging) | refused `status.not_trusted` | ✔ labelled `EXPLORATORY` (§0.5) |
| WATER-BWSSB-2026-02 | **promoted** | accept (+ `series.swing`) | `data/raw/water/Water_Consumption_Data_Feb_26_0_1.csv` | ✔ | n/a |
| ROAD-RA2020-A47 | **promoted** | accept | `data/raw/roads/RA2020_A47.csv` | ✔ `morth_city_a47/ra2020_2021` | n/a |
| ROAD-RA2021-A47 | **promoted** | accept (+ `casualties.zero_accidents`) | `data/raw/roads/RA2021_A47.csv` | ✔ `morth_city_a47/ra2020_2021` | n/a |
| ROAD-RA2022-A47 | **promoted** | accept | `data/raw/roads/Transport_2022_Annexure_47.csv` | ✔ `morth_city_a47/ra2022` | n/a |
| ROAD-RA2023-A47 | **promoted** | accept | `data/raw/roads/Transport_2023_Annexure_47.csv` | ✔ `morth_city_a47/ra2023` | n/a |
| ROAD-RA2024-A1 | integrity_passed | keep_profiled (no uses) | staging | refused | refused |
| ROAD-RA2024-A2 | integrity_passed | keep_profiled (no uses) | staging | refused | refused |
| ROAD-RA2024-A49 | integrity_passed | keep_profiled (no uses) | staging | refused | refused |

**Trusted water coverage is now July 2025 to March 2026, except January 2026:** 8 months, with August and March from Batch 01. The planner answers, for example, "water consumption in July 2025" with 30,457.44 ML, citing WATER-BWSSB-2025-07 and its SHA-256.

**Download method:** every Batch 02 manifest records `retrieved_by` and `method` as **"UNKNOWN (not yet provided by the project owner)"**. `retrieved_at` is the Downloads file's modification time, and is labelled as such in each manifest's note.

### 0.3 Schema registrations (in `src/civicmind/catalog/schemas.py`)

| Version | Datasets | Columns | Label | Numeric columns exclude |
|---|---|---:|---|---|
| `morth_city_a47/ra2020_2021` | ROAD-RA2020-A47, ROAD-RA2021-A47 | 33 | `Million Plus Cities` | the label |
| `morth_city_a47/ra2022` | ROAD-RA2022-A47 | 34 | `Million Plus Cities` | `Sl. No.` and the label |
| `morth_city_a47/ra2023` | ROAD-RA2023-A47 | 34 | `Million Plus Cities` | `Sl. No` and the label |

How the versions were built:
- **Headers are generated verbatim from the files**, with no aliasing. Rank columns: over-speeding accidents and killed.
- **2020 and 2021 share one version:** their headers are byte-identical, and the registry requires every header to be unique (`assert len(_BY_HEADER) == len(SCHEMAS)`). So "distinct schema versions" is satisfied per distinct header. Each edition remains its own dataset, with its own manifest, hash and period.
- **Not registered:** no A1, A2 or A49 schema (decision 9).

### 0.4 Validator changes

| Validator | Change | Severity | Effect on values |
|---|---|---|---|
| `morth_city_table.validate` | New finding `casualties.zero_accidents`: persons killed or injured in a category whose accident count is 0, listed per row | warning | None (read-only) |
| `bwssb_monthly.series_swing(previous, current, …)` | New cross-month check: emits `series.swing` (connections ≥ 200 or ML ≥ 10, change ≥ 30%), or `series.not_comparable` if the (ward, name) rows differ | warning | None (read-only) |
| `scripts/process_batch_02.py` | Runs `series_swing` against the previous calendar month only when that month passes validation. Otherwise it records an information finding, `series.not_compared` (July 2025, whose previous month is the quarantined June) | info | None |

**Findings actually produced:**
- `casualties.zero_accidents`: **RA2021-A47 only** (Pune, Over-Speeding, 6 killed and 15 injured). There are none in 2020, 2022 or 2023. The trusted Batch 01 2019 and 2024 files produce **no** new warning, so their trusted ingestion is unaffected.
- `series.swing`:
  - Nov 2025: Chowdeshwari ML +259%.
  - Dec 2025: Varthur (85) ML +30%.
  - Jan 2026: Horamavu connections −38%.
  - Feb 2026: Horamavu connections +76% and Varthur (85) ML +38%.

  There were none in Sep or Oct; July was not compared.

**Not changed:** the June-related checks. June is still refused with `schema.columns` and `consumption_ml.negative`, both errors.

### 0.5 January 2026 exploratory access (owner-approved change, implemented)

**Before.**
- The `keep_profiled` + `permitted_uses: [exploratory]` decision kept January out of trusted use.
- However, `ingest._source` admitted exploratory reads only for `status: integrity_passed`. That path was designed for profile-only data without a validator.
- January's honest status is `validated`, so it was refused with `exploratory.not_permitted`.

**Change.** This was approved after its scope was reported. Only `src/civicmind/catalog/ingest.py` changed:
1. **Status check.** The exploratory status condition is now `status in ("integrity_passed", "validated")`. Every other condition is unchanged:
   - a `keep_profiled` review;
   - an explicit `exploratory` permitted use;
   - a review bound to the file's SHA-256;
   - reading only from `data/external/`.

   The module docstring says so.
2. **Label.** The exploratory caveat is now honest about the value's nature:
   - modelled data keeps "EXPLORATORY: modelled or profile-only values; not measurements.";
   - other data gets "EXPLORATORY: not promoted to trusted use (review decision keep_profiled); values as published, review caveats not accepted."

**Result.**
- `ingest(<January manifest>, root, "exploratory")` returns 202 rows from `data/external/batch-02/water/…`, with mode `exploratory`.
- It carries all five restrictions: `no_trusted_analytics`, `no_measured_performance`, `no_ward_ranking`, `no_ward_efficiency_ranking` and `no_cross_dataset_join`.
- **Trusted access is still refused at every layer:**
  - trusted ingestion (`status.not_trusted`);
  - the planner and pipeline (`dataset.not_trusted`);
  - analytics, even with its restrictions stripped (the mode check);
  - evidence validation.
- January's manifest, status and review are unchanged; it is **not promoted**.

**Tests:** `tests/test_exploratory_access.py`, 17 tests.
- **Real January (6):** manifest state; labelled exploratory read; trusted refused; analytics refused; evidence rejected; planner and pipeline refused.
- **Synthetic gate (11):** validated + keep_profiled + exploratory admitted. Refused: no review; no permitted use; an `accept` review; promoted, received and planned status; quarantined and rejected; a stale review; trusted mode. The modelled label is unchanged.
- **Mutation check:** with the old status line restored, the 4 tests that rely on the new path fail. The 13 blocking tests pass with either version, so the blocking does not depend on this change.

### 0.6 A47 2020–2023: promoted after an explicit accept decision

**First run.**
- No accept decision had been given, so the four editions were catalogued `validated` / `pending`, and the planner refused them.
- That was reported, and the owner then decided: "record accept decisions for ROAD-RA2020-A47, 2022 and 2023 (no caveats) and ROAD-RA2021-A47 (accepting casualties.zero_accidents)".

**Second run.** The decisions were recorded in `REVIEW_DECISIONS.yaml`, bound to each file's SHA-256, and `scripts/process_batch_02.py` was re-run. Results:
- All four editions passed the unchanged promotion gate. They were copied byte-identically to `data/raw/roads/`, and each re-ingests in trusted mode under its registered schema version.
- **Every other manifest and raw file was byte-identical before and after the re-run**, including Batch 01, the other Batch 02 datasets and the 2019/2024 A47 files.
- The planner now answers "over-speeding accidents in Bengaluru in 2021" from ROAD-RA2021-A47: 3,041, or 6.62% of the published Total of 45,942. This matches the source row.

**Caveats that stay on the manifests:**
- the Tamil Nadu revision (2020);
- Pune (2021: the accepted warning plus a source caveat);
- the category-allocation instability;
- the deferral of derived growth rates and category sums (decision 8).

Trend analytics across editions are **not** implemented. The existing road intents still answer one edition at a time.

### 0.7 Verification

| Check | Result |
|---|---|
| Batch 01 files and manifests | All 12 pre-run SHA-256 values unchanged (8 manifests, 4 raw files); `git diff data/manifests` empty for Batch 01 |
| Promoted and quarantined copies vs the Downloads originals | 7 / 7 byte-identical (6 new raw files plus June in quarantine), and the August Batch 01 raw file too |
| Staged copies vs the Downloads originals | 14 / 14 byte-identical (June was moved, not copied) |
| Every manifest's `integrity.sha256` vs its `local_path` and `promoted_to` files | 23 / 23 manifests OK |
| Processor idempotence | A second run left every manifest and `summary.json` byte-identical |
| New raw and quarantine files in Git | Ignored by the existing default-deny rules; nothing added to the allowlist |
| Focused tests: `test_dataset_identity.py` (18), `test_batch02_validators.py` (13), plus `test_analytics.py` | **75 passed** |
| Full suite | **299 passed** (284 at stage 2, plus 13 validator/schema tests and 2 catalogue-level identity tests). First execution: run twice, because the first run had 3 failures, fixed as described below. After the A47 promotion: 299 passed again, and the focused identity, validator and pipeline tests passed (113) |
| A47 re-run | 4 / 4 promoted copies byte-identical to the Downloads originals; manifest hash = `local_path` = `promoted_to`; all other manifests and raw files unchanged |
| Ruff `check` and `format --check` | Clean |

**Test and fixture adjustments** (all caused by the new catalogue state or the new warning, none weakening a check):
1. `eval/questions/pipeline.v1.yaml` P60 (June 2025) changed from `period.unavailable` to `status.quarantined`, because June is now catalogued as quarantined. P61 was moved from 2021, which is now promoted and answerable, to 2018, which is still uncatalogued. It keeps its expected `period.unavailable`. The question count stays at 55.
2. `tests/test_analytics.py`: one synthetic fixture zeroes over-speeding accidents while deaths stay non-zero. The new warning fires, and the review must accept it, which proves the warning gates through review rather than silently rejecting. The fixture now accepts `casualties.zero_accidents` explicitly. A new optional `caveats` argument on `_road` supports this.
3. `tests/test_dataset_identity.py`: the catalogue test now checks that every road manifest is indexed by its own annexure. Two real-catalogue tests were added: 2024 resolves to A47 beside A1, A2 and A49; January 2026 is refused.

### 0.8 Remaining blockers

1. **Download method:** UNKNOWN for all 15 files until you provide it. Each manifest says so.
2. **January 2026:** stays not trusted until the Horamavu anomaly is explained, or an explicit, documented decision accepts it. Exploratory access is available and labelled (§0.5); no analytics function accepts exploratory data.
3. **A47 2020–2023:** promoted (§0.6). Cross-edition use still needs the city alias table, and trend analytics need the §10.3 rules (deferred by decision 8).
4. **Unchanged from earlier stages:**
   - the MoRTH methodology on category exhaustiveness and the Tamil Nadu revision outcome;
   - the ward-scheme authority;
   - A1, A2 and A49 family validators and reviewed questions.

### 0.9 Changed and new files (not committed)

- **Modified:**
  - `src/civicmind/catalog/ingest.py` (§0.5)
  - `src/civicmind/catalog/schemas.py`
  - `src/civicmind/catalog/validators/bwssb_monthly.py`
  - `src/civicmind/catalog/validators/morth_city_table.py`
  - `src/civicmind/planner/catalog_index.py`
  - `src/civicmind/planner/feasibility.py`
  - `tests/test_analytics.py`
  - `eval/questions/pipeline.v1.yaml`
- **New:**
  - `scripts/process_batch_02.py`, `scripts/propose_batch_02.py`, `scripts/profile_batch_02.py`
  - `tests/test_dataset_identity.py`, `tests/test_batch02_validators.py`, `tests/test_exploratory_access.py`
  - `scripts/verify_batch_02.py` (read-only closure checks → `docs/acquisition/batch-02/closure_checks.json`)
  - 15 manifests in `data/manifests/`
  - `docs/acquisition/batch-02/` (this report, `REVIEW_DECISIONS.yaml`, `summary.json` and the stage 1–2 evidence)
- **Data, git-ignored:**
  - 6 files in `data/raw/water/`
  - 4 in `data/raw/roads/`
  - 1 in `data/quarantine/batch-02/`
  - 14 staged in `data/external/batch-02/` (left in place as the source of the promoted copies)

### 0.10 Milestone closure verification (final state)

`scripts/verify_batch_02.py` ran on the final state and wrote `closure_checks.json`. It is read-only.

| Check | Result |
|---|---|
| Manifest SHA-256 vs files on disk (`local_path` and `promoted_to` of all 23 manifests) | **37 / 37 files match**, 0 failures |
| Recorded decisions vs manifests (decision, SHA-256, accepted caveats, permitted uses) | **15 / 15 applied**, 0 mismatches |
| Batch 02 dispositions | 10 promoted (6 water, 4 A47); 1 quarantined (June); 1 validated keep_profiled (January); 3 integrity_passed keep_profiled (A1, A2, A49) |
| Download method | **UNKNOWN** in all 15 Batch 02 manifests (`retrieved_by` and `method`) |
| Source caveats | Present: Tamil Nadu revision (2020), Pune (2021), deferral of derived trends (2020–2023) |
| Batch 01 manifests vs `git show HEAD` | **8 / 8 byte-identical** |
| Trusted 2019 and 2024 A47 | Status promoted; file SHA-256 = `40bed81d…` and `702f75f3…`, unchanged |
| A47 query resolution on the real catalogue | Every year 2019–2024 → `ROAD-RA<year>-A47`. The 2024 top-cities question → `ROAD-RA2024-A47`. **A1, A2 and A49 never selected** (indexed as tables `A1`, `A2`, `A49`) |
| Evaluation set | **55 items** (13 answered, 42 refused expected): **55 / 55** match status and refusal code through the full pipeline |
| Processor re-run after the §0.5 change | Every manifest, raw and quarantine file byte-identical. `summary.json` refreshed: January's exploratory ingestion is now `ingested` |
| Full test suite (once, after the final approved change) | **316 passed**: 299 + 17 exploratory-access tests |
| Ruff `check` / `format --check` | Clean (57 files) |

**Unresolved at closure:**
1. Download method and retrieval route for all 15 files: **unknown**, waiting for your input.
2. January 2026 Horamavu anomaly: unexplained, so January stays not trusted.
3. A47 category exhaustiveness and the outcome of the Tamil Nadu 2017–2020 revision. Cross-edition trend analytics and the city alias table are deferred.
4. The ward-scheme authority (BBMP 198-ward delimitation): no ward-level joins.
5. A1, A2 and A49 have no family validators, schemas or reviewed questions.
6. The new raw and quarantine files are git-ignored under the default-deny policy. Tracking them would need explicit allowlist lines in `.gitignore`; none were added.

### 0.11 Proposed commit scope (not committed)

**Include:**

| Group | Paths |
|---|---|
| Code | `src/civicmind/catalog/ingest.py`, `src/civicmind/catalog/schemas.py`, `src/civicmind/catalog/validators/bwssb_monthly.py`, `src/civicmind/catalog/validators/morth_city_table.py`, `src/civicmind/planner/catalog_index.py`, `src/civicmind/planner/feasibility.py` |
| Tests and eval | `tests/test_dataset_identity.py`, `tests/test_batch02_validators.py`, `tests/test_exploratory_access.py`, `tests/test_analytics.py` (fixture caveat), `eval/questions/pipeline.v1.yaml` (P60/P61) |
| Scripts | `scripts/process_batch_02.py`, `scripts/verify_batch_02.py`, `scripts/profile_batch_02.py`, `scripts/propose_batch_02.py` (process imports its verified portal metadata) |
| Manifests | 15 new `data/manifests/*.yaml` (already re-included by `.gitignore`) |
| Batch 02 record | `docs/acquisition/batch-02/INTAKE_REPORT.md`, `REVIEW_DECISIONS.yaml`, `summary.json`, `closure_checks.json`, `profiles/*.json`, `cross_checks.json` |

**Optional:** the stage-2 history — `proposed_manifests/`, `proposed_schemas.yaml`, `dry_run_ingest.json`, `REVIEW_RECOMMENDATIONS.yaml`. These are superseded by the real manifests and decisions. Including them keeps the audit trail; leaving them out reduces noise.

**Exclude** (git-ignored, policy unchanged): `data/raw/**`, `data/quarantine/**` and `data/external/**`.

Suggested message: *"Batch 02: promote 6 BWSSB months and A47 2020–2023; annexure-aware road identity; swing and zero-accident warnings; labelled exploratory access for January 2026"*.

---

## 1. Executive summary

**Owner decisions (2026-10-17):**
- Advance 7 water months and the 4 A47 editions (2020–2023) to manifest preparation and detailed validation.
- Keep June 2025 quarantined.
- Keep the 2024 Annexures 1, 2 and 49 as separate datasets, with no promotion.
- Do not change Batch 01.

**Evidence check (§8).**
- All 15 files still match their recorded SHA-256 and byte size.
- Their filenames are stable: Downloads, the staged copies and the catalogue records agree.
- **Portal titles, catalogues and published/updated dates are now verified** from the resource pages, read on 2026-10-17 (metadata only, no downloads).
- Each table's identity was confirmed from its header and its portal title.
- **No candidate is contradicted by the evidence.**
- One discrepancy is in the review instruction, not the data: June's defect is a negative *consumption* value (ML), **not** a negative connection count (§8.3).
- The retrieval route (who downloaded the files, and how) is still **unverified**.

**Water (§9).**
- All 7 advancing months pass the **real trusted-ingestion gate** in a sandbox dry run, once their recorded caveats are accepted.
- **Horamavu, January 2026:** the connection count drops from 14,384 to 8,867, then returns to 15,565. Consumption does not fall that month. The drop is isolated to that one cell: city connections excluding Horamavu rise every month. **The cause is not established.**
- **Chowdeshwari Ward, from November 2025:** consumption per connection becomes the highest of the 201 rows with connections, at about 1.7–2.2× the 99th percentile, while its connection count stays at 456–467. No other row shows a matching fall. **The cause is not established.**
- Neither anomaly is corrected. Both are recorded as a proposed `series.swing` warning that the owner must accept explicitly.

**Roads (§10).**
- The 4 A47 editions pass the trusted-ingestion dry run once 3 new schema versions are registered (in memory only for the dry run).
- **Pune 2021:** "Over-speeding" shows 0 accidents but 6 killed and 15 injured. No official evidence resolves this; it stays an **unresolved source inconsistency**.
- The publisher's 2021 resource note says Tamil Nadu data for 2017–2020 was "undergoing revision". This affects four cities in the 2020 edition, and also the trusted Batch 01 2019 edition (noted only; status unchanged).
- **Trend analytics should not be enabled yet.** The rules in §10.3 come first.

**Identity fix (§11).** This was a real defect, not a hypothetical one. Before the fix:
- the planner keyed road datasets only by family and year;
- once a 2024 Annexure 49 or Annexure 1 was catalogued, a 2024 road question would either be refused as ambiguous or, **if no A47 existed, be answered from the wrong table**.

The fix:
- each road entry now records its source table, parsed from the ID (`ROAD-RA<edition>-<annexure>`);
- the two existing road intents resolve within **Annexure 47 only**;
- 16 regression tests are added; 5 of them fail against the old code;
- the full suite passes: **284 passed**, with Ruff clean.

## 2. Inventory of the 15 expected files

| # | Candidate filename | Found | Staged copy (git-ignored) | Dataset ID |
|---|---|---|---|---|
| 1 | `Water_Consumption_Data_June_2025.csv` | yes | `data/external/batch-02/water/` | WATER-BWSSB-2025-06 |
| 2 | `Water_Consumption_Data_July_2025_0.csv` | yes | `…/water/` | WATER-BWSSB-2025-07 |
| 3 | `Water_Consumption_Data_Sept_25_4.csv` | yes | `…/water/` | WATER-BWSSB-2025-09 |
| 4 | `Water_Consumption_Data_Oct_25_3.csv` | yes | `…/water/` | WATER-BWSSB-2025-10 |
| 5 | `Water_Consumption_Data_Nov_25_2.csv` | yes | `…/water/` | WATER-BWSSB-2025-11 |
| 6 | `Water_Consumption_Data_Dec_25_5.csv` | yes | `…/water/` | WATER-BWSSB-2025-12 |
| 7 | `Water_Consumption_Data_Jan_26_0_0.csv` | yes | `…/water/` | WATER-BWSSB-2026-01 |
| 8 | `Water_Consumption_Data_Feb_26_0_1.csv` | yes | `…/water/` | WATER-BWSSB-2026-02 |
| 9 | `RA2020_A47.csv` | yes | `data/external/batch-02/roads/` | ROAD-RA2020-A47 |
| 10 | `RA2021_A47.csv` | yes | `…/roads/` | ROAD-RA2021-A47 |
| 11 | `Transport_2022_Annexure_47.csv` | yes | `…/roads/` | ROAD-RA2022-A47 |
| 12 | `Transport_2023_Annexure_47.csv` | yes | `…/roads/` | ROAD-RA2023-A47 |
| 13 | `Transport_2024_Annexure_1.csv` | yes | `…/roads/` | ROAD-RA2024-A1 |
| 14 | `Transport_2024_Annexure_2.csv` | yes | `…/roads/` | ROAD-RA2024-A2 |
| 15 | `Transport_2024_Annexure_49.csv` | yes | `…/roads/` | ROAD-RA2024-A49 |

- None of the files is missing, and the originals in the project owner's local Downloads folder are unmodified.
- The staged copies were made with `cp -p` and hash-checked.
- Downloads mtimes run from 2026-10-17 17:57 to 18:05 IST. The proposed manifests use them as `retrieved_at`, following the Batch 01 convention.
- **Not processed (outside the 15):** `RA2019_A2.csv`, `RA2019_A49.csv`, `RA2019_A52.csv`, `annexure 1.xlsx`, and copies of Batch 01 files.

## 3. Sizes and SHA-256 (re-verified in stage 2)

| Dataset ID | Bytes | Catalogue bytes | Portal page size | SHA-256 |
|---|---:|---:|---|---|
| WATER-BWSSB-2025-06 | 6,624 | 6,624 ✔ | 6.5 KB ✔ | `b198f725f5ca7e49624a7a63df2db5b6ec9515bb3ba4a72b3e10d803517e56e8` |
| WATER-BWSSB-2025-07 | 5,844 | 5,844 ✔ | 5.7 KB ✔ | `0034b08291e591ca0d94a535db172eea408746c35c3681551e58b39d316698b3` |
| WATER-BWSSB-2025-09 | 5,845 | 5,845 ✔ | 5.7 KB ✔ | `3f5ef8d0dc3ed08e2b593ba8a48ef584f913824a01eb80b34eb5584de1117b48` |
| WATER-BWSSB-2025-10 | 5,844 | 5,844 ✔ | 5.7 KB ✔ | `84e0b2ca373327ae7555078ee2b1a1af86cc88a96035a218f78ac8fb971e4da6` |
| WATER-BWSSB-2025-11 | 5,841 | 5,841 ✔ | 5.7 KB ✔ | `d4ccfb00a970c13320b3a911fde69b959b92c83c8b0a17818523a90de5730012` |
| WATER-BWSSB-2025-12 | 5,843 | 5,843 ✔ | 5.7 KB ✔ | `deb04248fe61aaa1019bbbd51592d2aa8c2838d26af5c75bc7bc52768dd24476` |
| WATER-BWSSB-2026-01 | 5,845 | 5,845 ✔ | 5.7 KB ✔ | `39d38c1b41f156d64fdd7cb9b87614bd920e1d596acdb04edb4a0e72df015b2f` |
| WATER-BWSSB-2026-02 | 5,848 | 5,848 ✔ | 5.7 KB ✔ | `a5ea2b8c60a0f54ebbe2b141222e48a0c5844496feafbd6fa74710f034166525` |
| ROAD-RA2020-A47 | 6,607 | 6,607 ✔ | 6.5 KB ✔ | `279575421cb29ea90c08e5290355c00c170674ba4d43491e01780e08337684be` |
| ROAD-RA2021-A47 | 6,640 | 6,640 ✔ | 6.5 KB ✔ | `8da252e5a6edb7db6ec4303730826c8da207665d22a82a333b92871891aa08a5` |
| ROAD-RA2022-A47 | 6,870 | 6,870 ✔ | 6.7 KB ✔ | `d4300164f267d72cffdf60139c84f87c590eacd38195994dee4943f9a52877f0` |
| ROAD-RA2023-A47 | 6,918 | 6,918 ✔ | 6.8 KB ✔ | `aa3aece258183067f32fb29bdb34389854982472e6fa26f50c4ca61c68b56004` |
| ROAD-RA2024-A1 | 3,939 | 3,939 ✔ | 3.8 KB ✔ | `1780d0a58496a8906036cd0128b1ae403a3d0ed3eef6ce7d0106d5dd5b7cc96c` |
| ROAD-RA2024-A2 | 4,074 | 4,074 ✔ | 4.0 KB ✔ | `fdfa67d0a031e5494178ed409ae41fb3be8063ca97f4ac8a1486de3020eab6c7` |
| ROAD-RA2024-A49 | 5,762 | 5,762 ✔ | 5.6 KB ✔ | `4a01cd8fd842ca44b2a4a42ad7e75f9a33fdffcdce82a828d4aaff0d6775a257` |

- **"Catalogue bytes"** are exact byte sizes from the data.gov.in catalogue API, recorded before download (`docs/discovery/civicmind_dataset_catalog.csv`).
- **"Portal page size"** is the rounded KB figure shown on each resource page (bytes ÷ 1024, to 0.1 KB).
- The portal publishes no hash, so a size match is strong evidence but **not proof of byte identity**.

## 4. Schema and data-quality profiles (stage 1, unchanged)

All 15 files are UTF-8 without a BOM, comma-delimited, with no NUL bytes, no HTML, no fully duplicated rows and no repeated header rows. The header-name sensitivity scan found no matches.

| Dataset | Rows × cols | Line endings | Validator errors | Warnings | Notes |
|---|---|---|---|---|---|
| WATER 2025-06 | 202 × 4 | CR 202 + CRLF 1 | `schema.columns`, `consumption_ml.negative` | `ward.duplicated` | Header `Number of Connectionss`; ward 40 = `-2.00E-06`; up to 6 decimals |
| WATER 2025-07 … 2026-02 (7) | 202 × 4 | CR 202 + CRLF 1 | 0 | `ward.duplicated`, `consumption_ml.zero` (+ `file.newline_style`) | Exact `bwssb_monthly/v1` header; same (ward, name) row sequence as the trusted August 2025 file |
| A47 2020, 2021 | 51 × 33 | CRLF | 0 | 0 | No serial column; `Greviously`; double space before ` - ` |
| A47 2022 | 51 × 34 | CRLF | 0 | 0 | `Sl. No.`; `Grievously` |
| A47 2023 | 51 × 34 | CRLF | 0 | 0 | `Sl. No` (no period); `&` |
| A1 2024 | 34 × 16 | CRLF | n/a | n/a | National, 1970–2024; irregular years; a `CAGR` row; `NA` for 2023–24 vehicles and roads |
| A2 2024 | 37 × 17 | CRLF | n/a | n/a | States/UTs 2021–24; Σ = Total; shares 99.7–100.0 |
| A49 2024 | 51 × 29 | CRLF | 0 (provisional run) | 0 | 5 junction types, with no "other" class |

For the A47 editions and A49, the checks that hold are:
- the published `Total` equals the sum of the city rows for every count column;
- every publisher rank recomputes;
- grievous + minor injured = total injured.

For A1, the per-lakh-population and per-vehicle rates reproduce from their published bases. Full detail is in `profiles/*.json`.

## 5. Provenance and licence (verified in stage 2)

**How the metadata was read.**
- **When:** each resource page was rendered in the built-in browser on 2026-10-17 and read as text.
- **Constraints:** no file was downloaded, and no form was submitted.
- **Personal data:** the pages' Chief Data Officer contact details are deliberately **not recorded**.
- **Control:** the trusted ROAD-RA2024-A47 page was read too; it shows "18/06/2026", matching its Batch 01 manifest (`portal_published: 2026-06-18`).

| Dataset ID | Portal title (verbatim) | Portal catalogue | Published = updated |
|---|---|---|---|
| WATER-BWSSB-2025-06 | Water consumption Data for the month of June 2025 | Water consumption data | 10/07/2025 |
| WATER-BWSSB-2025-07 | BWSSB Water consumption data for the month of July-2025 | Water consumption data | 30/08/2025 |
| WATER-BWSSB-2025-09 | BWSSB Water Consumption data for the month of Septemeber 2025 | Water consumption data | 09/12/2025 |
| WATER-BWSSB-2025-10 | Water consumption data for the month of October-25 | Water consumption data | 05/02/2026 |
| WATER-BWSSB-2025-11 | Water consumption data for the month of November-25 | Water consumption data | 05/02/2026 |
| WATER-BWSSB-2025-12 | BWSSB Water consumption data for the month of December-25 | Water consumption data | 05/02/2026 |
| WATER-BWSSB-2026-01 | Water consumption data for the month of January-2026 | Water Consumption Data-2026 | 04/05/2026 |
| WATER-BWSSB-2026-02 | Water consumption data for the month of February-2026 | Water Consumption Data-2026 | 04/05/2026 |
| ROAD-RA2020-A47 | Cities-wise Accidents Classified according to Type of Traffic Violations in Million Plus Cities during 2020 | Road Accidents in India 2020 | 26/04/2023 |
| ROAD-RA2021-A47 | Cities-wise Accidents Classified according to Type of Traffic Violations in Million Plus Cities during 2021 | Road Accidents in India 2021 | 25/09/2023 |
| ROAD-RA2022-A47 | Million Plus City-wise Number of Accidents Classified According to Type of Traffic Violations in Million Plus Cities during 2022 | Road Accidents in India 2022 | 05/06/2026 |
| ROAD-RA2023-A47 | Million Plus Cities-wise Number of Accidents Classified according to Type of Traffic Rule Violations in Million Plus Cities during 2023 | Road Accidents in India 2023 | 30/05/2026 |
| ROAD-RA2024-A1 | Year-wise Details of Road Accidents, Persons Killed and Injured from 1970 to 2024 | Road Accidents in India 2024 | 19/06/2026 |
| ROAD-RA2024-A2 | State/UT-wise Number of Road Accidents in India from 2021 to 2024 | Road Accidents in India 2024 | 19/06/2026 |
| ROAD-RA2024-A49 | Million Plus City-wise Accidents Classified According to Type of Junctions during 2024 | Road Accidents in India 2024 | 18/06/2026 |

**Field values on the pages.**
- **Publisher:**
  - all water pages list "Karnataka, Urban Development Department, Karnataka, Bangalore Water Supply and Sewerage Board (BWSSB)";
  - all road pages list "Ministry of Road Transport and Highways".
- **Granularity:** "Monthly" for water and "Annual" for roads.
- **Fields:** the water pages list `Ward number, Ward Name, Number of Connections, Consumption in ML`. **The June page itself lists `Number of Connectionss`**, so the misspelling is the publisher's, not a download artefact.

**Publisher notes relevant to analysis** (verbatim excerpts are in each proposed manifest under `compatibility.publisher_note`):
- **2021 A47:** "The Data for the years 2017, 2018, 2019 and 2020 of Tamil Nadu is undergoing revision."
- **2024 A1:** data was reconciled for Tamil Nadu 2017–2020 and West Bengal (2015–17, 2019, 2020). Road length and vehicles are financial-year figures; accidents are calendar-year. Road length for 2023–24 is not available. Two footnotes are lost in the CSV: "# Data for the year 1971. ## Data for the year 1981."
- **2024 A2:** road length for 2022 is provisional, marked `(P)`.

**Resource URLs.**
- Each page URL is `https://www.data.gov.in/resource/<slug>`, using the slugs recorded in stage 1 (now observed to resolve to the titles above).
- The direct file URLs are the catalogue-API records (`ACQUISITION_DECISION_REPORT.md` §1.2) and were **not fetched**.
- **September 2025:** no direct URL is recorded, because the catalogue exposed only a signed, expiring link.

**Licence.**
- GODL-India. Every page footer says the content is "licensed under the Government Open Data License-India".
- The licence text is recorded in the Batch 01 GODL evidence note.
- Attribution strings in the GODL §5 format are in each proposed manifest.

**Still unverified:**
1. Who downloaded each file, and by which route (resource-page form or direct link). The manifests say `UNVERIFIED` / `UNRECORDED`.
2. Byte identity with the portal, beyond the size match.

## 6. Duplicate detection (stage 1, unchanged)

No candidate's bytes or rows duplicate another candidate or any Batch 01 file. Same-size pairs, such as July and October (5,844 B), differ in content.

## 7. Cross-period comparability (stage 1 summary)

- **Water:** every month from May 2025 to March 2026 has the identical header and the identical 202-row (ward number, ward name) sequence. Rows align on that pair; the ward number alone is not a key.
- **A47:** the six category names normalise to the same set across 2019–2024. The same 50 cities appear once 7 spelling variants are mapped (`Bengaluru` is constant). Headers differ by edition. Category meaning and stability are assessed in §10.3.
- **A1, A2 and A49** are different tables; none is a longitudinal partner for A47.

---

## 8. Stage 2 — evidence verification

### 8.1 Per-candidate checklist

| Dataset ID | Stable original filename | SHA-256 + size recorded | Provenance | Period and table identity | Schema / validation requirement |
|---|---|---|---|---|---|
| WATER 2025-07, -09, -10, -11, -12, 2026-01, -02 | ✔ Downloads = staged = catalogue `save_as` | ✔ (§3) | Portal title, date and publisher **verified**; retrieval route **unverified** | Month: from the portal title (the file has no date). Table: header = `bwssb_monthly/v1` | Registered v1; `bwssb@v1` passes; proposed `series.swing` check |
| WATER 2025-06 | ✔ | ✔ | as above | June 2025 (title); header **matches no schema** | Stays quarantined (§9.4) |
| ROAD-RA2020-A47, RA2021-A47 | ✔ | ✔ | Verified as above | Year: from the portal title (no year in the file). Table: A47 header (6 violation categories) | Needs `morth_city_a47/ra2020` (both editions share one byte-equal header) |
| ROAD-RA2022-A47 | ✔ (catalogue path `604784046/Version_1/…_47.csv`) | ✔ | as above | 2022 (title) / A47 header | Needs `morth_city_a47/ra2022` |
| ROAD-RA2023-A47 | ✔ (`604777242/Version_1/…`) | ✔ | as above | 2023 (title) / A47 header | Needs `morth_city_a47/ra2023` |
| ROAD-RA2024-A1 | ✔ | ✔ | as above | 1970–2024 (year rows) / national table | New family `morth_national_a1` |
| ROAD-RA2024-A2 | ✔ | ✔ | as above | 2021–2024 (column names) / state table | New family `morth_state_a2` |
| ROAD-RA2024-A49 | ✔ | ✔ | as above | 2024 (title) / junction-type header | New family `morth_city_a49` |

### 8.2 Contradictions

**None found.**
- Every staged file still hashes to its stage 1 value and is byte-equal to its Downloads original.
- Every portal title names the period and table that the stage 1 report assigned.
- No candidate is stopped on evidence grounds.

### 8.3 Discrepancy in the stage 2 instruction

The instruction refers to June 2025's "header and negative **connection-count** issues". The evidence shows otherwise:
- June's connection counts are all non-negative; ward 40 has 1 connection.
- The negative value is ward 40's **`Consumption in ML` = `-2.00E-06`** (validator error `consumption_ml.negative`).
- The header defect is `Number of Connectionss`, which the June resource page also shows.

The quarantine decision is unaffected. This report uses the evidenced description.

## 9. Stage 2 — water

### 9.1 Proposed manifests and validation plan

`proposed_manifests/WATER-BWSSB-2025-07 … 2026-02.yaml` set `status: validated` and `human_review: pending`.

Each manifest records:
- the verified title and dates, GODL attribution and catalogue size;
- SHA-256 and newline counts;
- the verbatim schema, `period` (calendar month) and `ward_scheme: UNKNOWN`;
- findings, including proposed checks, and the Batch 01 limitations.

**Validation plan.** At promotion, `process_batch_02.py` would run these steps; the dry run in `dry_run_ingest.json` has already exercised them.
1. **Integrity:** size = catalogue bytes; SHA-256 recorded; encoding, newline and delimiter fingerprint.
2. **Schema:** the raw header must equal `bwssb_monthly/v1` verbatim (no aliasing).
3. **`bwssb@v1`:** integer wards 1–198; duplicated ward numbers listed; non-numeric, negative and zero values flagged; column totals.
4. **Series check (proposed `series.swing`, warning):**
   - **Scope:** compares each month with the previous calendar month within the trusted/advancing series, on the identical (ward, name) row sequence.
   - **Flags:** any row whose connections (≥ 200) or ML (≥ 10) changed by ≥ 30%.
   - **Not compared:** July, because June is quarantined.
   - **Status:** prototyped in `propose_batch_02.py`; **not yet in the validator**.
5. **Review gate:** every warning code must be listed in `accepted_caveats`, bound to the SHA-256.

**Dry-run result.**
- All 7 months were ingested as `bwssb_monthly/v1`, 202 rows each, once the caveats were accepted.
- **Control:** January 2026 with no caveats accepted was refused with `validation.unaccepted_warnings` (`consumption_ml.zero`, `ward.duplicated`).

### 9.2 Horamavu (ward 25) — January 2026 connections

| | Jul | Aug | Sep | Oct | Nov | Dec | **Jan** | Feb | Mar |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Connections | 10,381 | 11,232 | 11,889 | 12,789 | 12,820 | 14,384 | **8,867** | 15,565 | 16,181 |
| Consumption (ML) | 146.72 | 156.55 | 148.35 | 104.67 | 97.26 | 119.40 | 131.31 | 140.77 | 165.27 |
| kL per connection | 14.1 | 13.9 | 12.5 | 8.2 | 7.6 | 8.3 | **14.8** | 9.0 | 10.2 |

**Facts:**
- **Isolated cell.** City-wide connections *excluding Horamavu* rise every month from April 2025 to March 2026 (December 1,050,329 → January 1,053,889 → February 1,057,859). The city-wide January dip comes entirely from this one cell.
- **Consumption did not fall** in January (+10% on December). Only the connection count breaks the trend.
- **Largest move.** Horamavu's change of −5,517 is the largest Dec→Jan connection change of any row. The next largest fall is Ramamurthynagar, at −54.
- **Earlier changes.** Connections also rose sharply from June to July 2025 (6,532 → 10,381, +59%), and kL per connection has fallen since then. A rising count could be genuine operational growth; no evidence decides this either way.

**Not established:** whether the January figure is an entry error, a reporting-scope change, or a real temporary change. **No value is corrected.**

**Analytical impact.** If January 2026 is accepted, these must carry the caveat:
- any January 2026 per-connection figure for Horamavu;
- any city-total connection change involving January.

### 9.3 Chowdeshwari Ward (ward 2) — consumption from November 2025

| | Apr | May | Jun | Jul | Aug | Sep | Oct | **Nov** | Dec | Jan | Feb | Mar |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ML | 10.90 | 9.83 | 9.81 | 25.69 | 23.62 | 18.95 | 17.36 | **62.34** | 56.86 | 73.73 | 74.08 | 56.01 |
| kL per connection | 23.9 | 21.4 | 21.3 | 55.7 | 51.0 | 40.8 | 37.3 | **133.8** | 122.0 | 157.9 | 158.6 | 119.9 |
| Rank of kL per connection (of 201 rows) | 154 | 175 | 174 | 12 | 13 | 30 | 33 | **1** | 1 | 1 | 1 | 1 |

**Facts:**
- **Stable connection count:** 456–467 throughout (April–March).
- **Two step changes:** July (+162%) and November (+259%).
- **Outlier size:** from November onwards the ward has the highest consumption per connection, about 1.7–2.2× the 99th percentile; the city median is about 26 kL.
- **No offsetting fall.** The October → November rise of +44.98 ML is the largest of any row. No row fell by a comparable amount: the largest falls are Vidyaranyapura −26.32 and HSR Layout −25.70. So a simple reallocation between published rows is not visible.

**Not established:** whether this reflects bulk or institutional supply, a metering change, or an error. It is recorded as a `series.swing` warning for November (and for any later month that crosses the threshold); **no value is corrected or rejected**.

### 9.4 Existing caveats, re-checked on the 7 months

- **Repeated ward numbers** (14, 85, 153, 191):
  - Each pair keeps two **independent** trajectories every month. For example, 191 Singasandra goes from 3,845 to 4,790 connections while 191 Singsandra goes from 953 to 1,157.
  - The pairs are therefore distinct published rows that share a number, **not duplicate records**. They must not be summed or de-duplicated by ward number.
  - The name "Varthur" appears on two different numbers, 85 and 149, again with independent series.
- **Ward 40, Doddabidirakalu:** 1 connection and `0.00` ML in all 7 months, as in the trusted August and March files. Only the quarantined May and June files show `-2.00E-06`.
- **Line endings:** every month uses bare CR between records (CR 202) and a final CRLF. This is identical to the trusted March 2026 file. It is recorded as `file.newline_style`; the bytes stay unchanged.

**June 2025:** a proposed manifest with `status: quarantined` is prepared.
- **Validators are unchanged.** The dry run that forced June through ingestion was refused with `schema.unknown`, before value checks.
- **File location:** the file stays in staging. The proposal is that the processor moves it to `data/quarantine/batch-02/` once decisions are recorded. **It has not been moved.**

## 10. Stage 2 — roads (A47, 2020–2023)

### 10.1 Proposed manifests and schema registrations

`proposed_manifests/ROAD-RA2020-A47 … RA2023-A47.yaml` set `status: validated` and `human_review: pending`. Each records:
- the verified title, catalogue and published date;
- the verbatim header and integrity details;
- the year as its period, and `level: million-plus city`;
- MoRTH limitations, plus edition-specific limitations (Tamil Nadu revision for 2020; Pune for 2021).

**Edition identity is preserved**: four distinct dataset IDs, each bound to its own SHA-256.

`proposed_schemas.yaml`, **not registered**:

| Version | Applies to | Label column | Serial column | Rank columns |
|---|---|---|---|---|
| `morth_city_a47/ra2020` | 2020 and 2021 (byte-equal headers) | `Million Plus Cities` | — | 2 (over-speeding) |
| `morth_city_a47/ra2022` | 2022 | `Million Plus Cities` | `Sl. No.` | 2 |
| `morth_city_a47/ra2023` | 2023 | `Million Plus Cities` | `Sl. No` | 2 |

**Dry-run result.**
- With these three versions registered **in memory only**, all four editions were ingested through real trusted ingestion (51 rows each), with no validator warnings under the current validator.
- The proposed `casualties.zero_accidents` warning (2021) is recorded in the manifest, and must be accepted at review once it is implemented.

### 10.2 Pune 2021 — over-speeding

- **What the file says** (row Pune): over-speeding accidents **0** (rank 50); persons killed **6** (rank 50); grievous 11 + minor 4 = total injured 15.
- **Internally consistent otherwise:** the injured identity holds, the `Total` row includes these values, and the ranks recompute.
- **Context:** Pune over-speeding was 250 accidents and 76 killed in 2020, and 0 accidents and 0 killed in 2022. Pune "Others" was 723 accidents and 243 killed in 2021.
- **Official evidence:** the 2021 resource page's note mentions only Tamil Nadu. No document in hand explains Pune.
- **Status: unresolved source inconsistency, kept as published.** The proposed check `casualties.zero_accidents` (warning) records it.
- **Analytical consequence:** any per-accident ratio, such as deaths per accident, is undefined for this cell and must be refused.

### 10.3 Cross-year comparability — conditions before trend analytics

Matching names are **not** treated as matching meanings. The evidence in hand is limited.

**What the evidence shows:**
- **Titles change.** 2020–2022 say "Type of Traffic Violations"; 2023–2024 say "Type of Traffic **Rule** Violations". The category list is unchanged, but no MoRTH definition document is in hand to confirm the definitions are unchanged.
- **Per-city allocation is unstable.** Examples:
  - Chennai "Others": 11 in 2021, then 2,597 in 2023;
  - Pune over-speeding: 0 in 2021–22, then 909 in 2023;
  - Mumbai "Others": 0 in every year from 2020.

  This is consistent with changes in how cities record or classify violations, not necessarily with real changes.
- **Revisions.** The publisher flagged Tamil Nadu 2017–2020 as under revision. The 2020 values for Chennai, Coimbatore, Madurai and Tiruchirapalli (and those in the trusted 2019 edition) may be superseded. A47 editions do not restate earlier years, so the revised values are not available in these files.
- **Exhaustiveness.** Whether the six categories partition all city accidents is still not established.

**Rules proposed for review.** No trend analytics have been implemented.
1. A "trend" answer may only list **per-edition published values side by side**: one city, one category, one measure. Each value cites its own edition and dataset ID.
2. Every such answer carries:
   - the classification-stability caveat;
   - the Tamil Nadu revision caveat for TN cities in 2019–2020.
3. **Refuse** these:
   - derived growth rates and "total accidents" trends from summed categories;
   - cross-city aggregates of a category across years;
   - per-accident ratios where accidents = 0.
4. A city whose category share moves by more than a threshold between editions should be flagged in the answer. The threshold needs the owner's approval; 20 percentage points is suggested.
5. Cross-edition city matching needs the alias table (7 variants; `Bengaluru` needs none).

## 11. Stage 2 — road dataset identity (implemented)

### 11.1 Defect

`planner/catalog_index.py` mapped every `ROAD-RA*` ID to the family `roads`, with a period key equal to the year of `period.start`. `feasibility._resolve` matched only on family and period. Consequences once Batch 02 manifests exist:

| Situation | Old behaviour |
|---|---|
| A47-2024 and A49-2024 both catalogued | A 2024 road question is refused as "more than one roads dataset claims 2024", **breaking existing Batch 01 answers** |
| A49-2024 (or A1 keyed 2024) catalogued and **no** A47-2024 | **The question resolves to the wrong table** (confirmed by test) |
| A2 (2024 edition, period 2021–2024) catalogued | Keyed as "2021", where it **collides with RA2021-A47** |

### 11.2 Design (minimal, backward-compatible)

- **`DatasetEntry.table`:** a new optional field, defaulting to `None`. It is the source table within the family, parsed from the ID with `ROAD_ID = ^ROAD-RA(?P<edition>\d{4})-(?P<table>A\d+)$`.
  - `ROAD-RA2024-A47` → `"A47"`;
  - an unparseable road ID → `None`, which **never matches**;
  - non-road families → `None`.
- **`feasibility.INTENT_TABLE`** = `{"road_city_value": "A47", "road_top_cities": "A47"}`.
  - `_resolve` filters by family **and** table when the intent names one, then by period.
  - The rule refusing two matches is kept unchanged (never choose silently).
  - Refusal text now names the table, e.g. "No roads A47 dataset covers 2021".
- **Unchanged:**
  - water intents (no table filter);
  - `dataset_family`;
  - trust checks, which still run after resolution;
  - the parser, analytics, ingestion and every manifest.
- **Future A1, A2 and A49 analytics** get their own intents mapped to `"A1"`, `"A2"` and `"A49"`. Nothing is added for them now.

**Changed files:**
- `src/civicmind/planner/catalog_index.py`: `ROAD_ID`, `source_table()`, `DatasetEntry.table`;
- `src/civicmind/planner/feasibility.py`: `INTENT_TABLE`, table-aware `_resolve`.

## 12. Final candidate dispositions

These are recommendations for the owner's decision. They are drafted, bound to SHA-256, in `REVIEW_RECOMMENDATIONS.yaml`. **No promotion happens until decisions are recorded and the gate passes.**

| Dataset ID | Proposed manifest status | Recommendation | Caveats to accept | Blocked until |
|---|---|---|---|---|
| WATER-BWSSB-2025-06 | `quarantined` | **Keep quarantined** | — | A documented resolution: the header defect and the negative ML |
| WATER-BWSSB-2025-07 | `validated` | Accept | `consumption_ml.zero`, `file.newline_style`, `ward.duplicated` | Decision recorded |
| WATER-BWSSB-2025-09 | `validated` | Accept | same | as above |
| WATER-BWSSB-2025-10 | `validated` | Accept | same | as above |
| WATER-BWSSB-2025-11 | `validated` | Accept | same + `series.swing` (Chowdeshwari) | as above |
| WATER-BWSSB-2025-12 | `validated` | Accept | same + `series.swing` (Varthur 85, ML +30%) | as above |
| WATER-BWSSB-2026-01 | `validated` | **Accept or keep_profiled — owner decision** | same + `series.swing` (Horamavu) | as above |
| WATER-BWSSB-2026-02 | `validated` | Accept | same + `series.swing` (Horamavu recovery; Varthur 85 ML +38%) | as above |
| ROAD-RA2020-A47 | `validated` | Accept (Tamil Nadu caveat) | — | Schema `ra2020` registered; alias table before cross-edition use |
| ROAD-RA2021-A47 | `validated` | Accept (Pune caveat) | `casualties.zero_accidents` | as above |
| ROAD-RA2022-A47 | `validated` | Accept | — | Schema `ra2022` registered |
| ROAD-RA2023-A47 | `validated` | Accept | — | Schema `ra2023` registered |
| ROAD-RA2024-A1 | `integrity_passed` | Hold (separate family) | — | Family validator, schema registration and reviewed questions |
| ROAD-RA2024-A2 | `integrity_passed` | Hold (separate family) | — | as above |
| ROAD-RA2024-A49 | `integrity_passed` | Hold (separate family) | — | as above; junction types are not a partition |

## 13. Proposed manifest, schema and validator changes (summary)

- **Manifests:** there are 15 proposed manifests in `proposed_manifests/`.
  - Each validates against the `Manifest` model.
  - `retrieval.retrieved_by` and `method` are explicitly `UNVERIFIED` / `UNRECORDED`.
  - September 2025's `download_url` states that no URL is recorded.
- **Schemas:** six versions are proposed in `proposed_schemas.yaml`: three A47 versions, plus `morth_city_a49/ra2024`, `morth_state_a2/ra2024` and `morth_national_a1/ra2024`. Registering them means a code change in `catalog/schemas.py`, which waits for approval.
- **Validators** (proposed; not implemented):
  - `series.swing` (BWSSB, cross-month, warning);
  - `casualties.zero_accidents` (MoRTH city tables, warning);
  - a rank-recomputation check (information).
  - New family validators: `morth_city_a49`, `morth_state_a2`, `morth_national_a1`. The A1 validator should treat the 1970/1980 per-km mismatch as explained by the publisher's footnote ("# 1971 / ## 1981"), though which column the footnote applies to is not visible in the CSV.
- **Not changed:** the June-related validators. No alias or relaxation was added.

## 14. Tests and checks run

| Check | Result |
|---|---|
| New `tests/test_dataset_identity.py` (16 tests: ID parsing; Batch 01 index; A47 chosen among A1/A2/A49; no stand-in when A47 is missing; A2 restated year not matched; duplicate A47 still refused; unparseable ID never used; trust still enforced; water unchanged) | **16 passed** |
| Mutation check: the same tests run against the **old** `feasibility.py` | **5 failed**, as intended (each exposes the defect); restored byte-identically afterwards |
| Full suite, required by the planner code change | **284 passed** (268 before + 16 new) in 27.9 s |
| `ruff check .` / `ruff format --check .` | Clean |
| Trusted-ingestion dry run (`dry_run_ingest.json`) | 11 / 11 advancing candidates ingested; 3 / 3 negative controls refused (`schema.unknown` ×2, `validation.unaccepted_warnings`) |
| Determinism | `propose_batch_02.py` run twice: byte-identical outputs |

## 15. Remaining manual actions (owner)

| # | Action | Needed for |
|---|---|---|
| 1 | Record the retrieval route for the 15 files: who downloaded them, from the resource-page form or a direct link. A `data/external/batch-02/manual_downloads.tsv` in the Batch 01 columns is enough; the hashes and mtimes in §3 can be copied. | Replacing `UNVERIFIED` in the manifests |
| 2 | Review `REVIEW_RECOMMENDATIONS.yaml`. Copy the entries you approve into `docs/acquisition/batch-02/REVIEW_DECISIONS.yaml` (Batch 01 format, listing every warning code as an accepted caveat). | Any promotion |
| 3 | Decide on January 2026: accept with the Horamavu caveat, or keep it profiled only. Optionally ask the BWSSB data officer listed on the resource page about Horamavu (Jan 2026) and Chowdeshwari (Nov 2025 onwards). | Water series completeness |
| 4 | Approve: (a) registering the 3 A47 schema versions; (b) implementing `series.swing` and `casualties.zero_accidents`; (c) the trend rules in §10.3, including the stability threshold. | A47 promotion; trend analytics |
| 5 | Locate the MoRTH "Road Accidents in India" methodology (category definitions and exhaustiveness; Tamil Nadu revision outcome). The official morth.gov.in URL is still not found. | Lifting the A47 trend restrictions |
| 6 | Ward-scheme authority (unchanged from Batch 01): the official BBMP 198-ward delimitation. | Any ward-level join |
| 7 | Note for Batch 01, with no action proposed: the trusted ROAD-RA2019-A47 falls inside the publisher's Tamil Nadu 2017–2020 revision window. Its status is **not** changed; the caveat could be added to its limitations by a separate, explicit decision. | Information |

## 16. Next steps (after explicit approval)

1. Record decisions (§15, items 2 and 3).
2. Write `scripts/process_batch_02.py`, mirroring Batch 01. It will:
   - write the real manifests to `data/manifests/`;
   - move June to `data/quarantine/batch-02/`;
   - promote the accepted water months and A47 editions through the existing gate.
3. Register the three A47 schema versions.
4. Implement the two proposed validator checks, with tests.
5. Add the city alias table and the A47 side-by-side series analytics under the §10.3 rules, plus the multi-month water analytics. Each needs golden cases.
6. Later, after review of their meanings and intended questions: the A1, A2 and A49 families (schemas, validators and intents).
