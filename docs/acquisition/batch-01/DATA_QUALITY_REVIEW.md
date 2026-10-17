# Batch 01 — data-quality review: water, traffic, waste readiness

Date: 2026-10-17 · Scope: BWSSB Apr/May/Aug 2025 and Mar 2026; MoRTH A47 2019 and 2024; legacy
traffic files (read-only); waste readiness. Builds on `VALIDATION_REPORT.md` (not repeated here).

**Method.** Every cell was re-read with the Python standard library (`csv`, `decimal`), separately
from the `civicmind` code, by a read-only probe. No file was written, renamed or re-encoded.
All 12 source copies still match their manifest SHA-256. Nothing was promoted, and no review
decision was changed.

## 1. Water (BWSSB monthly ward consumption)

### 1.1 File level
| Check | Apr 2025 (quarantined) | May 2025 (quarantined) | Aug 2025 | Mar 2026 |
|---|---|---|---|---|
| Bytes = manifest | 5,845 ✓ | 6,625 ✓ | 6,045 ✓ | 5,844 ✓ |
| Encoding | UTF-8, no BOM, ASCII only | same | same | same |
| Line endings | 202 bare CR + 1 CRLF | 202 CR + 1 CRLF | 203 CRLF | 202 CR + 1 CRLF |
| Records / fields | 203 × 4, no blank or ragged records | same | same | same |
| Header | `Ward number ` (trailing space), **`Number of Connectionss`** | same as Apr | expected schema | expected schema |
| Cells with surrounding spaces | 0 | 0 | 0 | 0 |
| `Consumption in ML` decimals | 2 | **4–6** (182 cells have 6) | 2 | 2 |

### 1.2 Values
| Check | Apr | May | Aug | Mar |
|---|---|---|---|---|
| Ward numbers | 1–198, 198 distinct, no gaps | same | same | same |
| Non-numeric / fractional connections | 0 | 0 | 0 | 0 |
| Negative ML | 0 | **1**: ward 40 `-2.00E-06` (scientific notation) | 0 | 0 |
| Zero ML | ward 40 | — | ward 40 | ward 40 |
| Rows with < 100 connections | ward 40 (1 connection) in every month |||
| Connections total | 1,023,813 | 1,029,539 | 1,047,734 | 1,077,862 |
| ML total | 31,608.71 | 30,816.50328 | 30,580.05 | 29,732.45 |
| City litres/connection/day | 1,029.12 (30 days) | 965.56 | 941.51 | 889.83 |

### 1.3 Identifiers and labels
- **The same 4 ward numbers repeat in every month:** 14 Bagalagunte / sidedahalli, 85 Doddanekkundi / Varthur,
  153 Jayanagar / Jayangar, 191 Singasandra / Singsandra.
- **The paired rows are not duplicates.** Their values differ and stay stable from month to month. For
  example, 153 Jayanagar has 339–344 connections while 153 Jayangar has 3,638–3,659. 191 Singasandra and
  Singsandra have 3,301–4,790 vs 900–1,157. So a name-similarity "spelling fix" (Jayangar → Jayanagar) would
  merge two different rows. **Totals must keep both rows; current behaviour is correct.**
- "Varthur" appears under ward 85 and ward 149 in every month, with different values.
- **Label variants:**
  - `herohalli` is lower case in May, August and March but `Herohalli` in April;
  - `sidedahalli` is lower case throughout;
  - `H.M.T` keeps its punctuation.

  No label differs between August and May or March. April differs only in that one case.
- **Volatile rows** (descriptive; matched by ward number and exact name within this one publisher's series,
  not a join):
  - ward 2 Chowdeshwari Ward has 456–467 connections, but its ML goes 10.90 → 9.83 → 23.62 → 56.01
    (Apr → May → Aug → Mar). That gives 3,868.9 L/connection/day in March 2026, the top value and golden
    item G07;
  - ward 85 Varthur grows from 708 to 2,403 connections.

  Both are published as-is, but they dominate intensity rankings.

### 1.4 Units, aggregation and periods
- **Units:** `Consumption in ML` is megalitres per month and `Number of Connections` is a count. The files
  state neither the month nor the unit beyond the header, so the period comes from the manifest. April's
  portal period metadata is wrong (it shows 2025-06-21), as recorded earlier.
- **Totals:** there is no Total row and no checksum. A city total is the sum of all 202 rows, which is
  correct because the paired rows are distinct.
- **Period lengths:** April has 30 days; May, August and March have 31. A3 reports both months' day counts
  and a per-day change when they differ.

### 1.5 Water: validated vs unresolved
| Field | Aug 2025, Mar 2026 | Apr / May 2025 |
|---|---|---|
| `Ward number ` | validated as an integer; **ward scheme unresolved**; 4 numbers repeat (unresolved) | same |
| `Ward Name` | text as published; case variants not normalised | same |
| `Number of Connections` | validated (integer, ≥ 0) | **header misspelt** → schema unknown |
| `Consumption in ML` | validated (numeric, ≥ 0); ward 40 is 0 | Apr validated except the header; May has 1 negative and mixed precision |

## 2. Traffic (MoRTH A47, million-plus cities)

| Check | RA2019 A47 | RA2024 A47 |
|---|---|---|
| Bytes / encoding / line endings | 6,807 · UTF-8 · 52 CRLF | 6,925 · UTF-8 · 52 CRLF |
| Records × fields | 52 × 33 | 52 × 34 (adds `Sl. No.`) |
| Schema version | `morth_city_a47/ra2019` (label `States/UTs`) | `morth_city_a47/ra2024` (label `Million Plus Cities`) |
| Cities / Total rows | 50 / 1 | 50 / 1 |
| Duplicate city labels | 0 | 0 |
| Non-numeric city cells | 0 | 0 |
| Negative counts | 0 | 0 |
| Total row = sum of cities (every count column) | ✓ | ✓ |
| Grievous + minor = total injured (6 categories × 51 rows) | ✓ (0 violations) | ✓ (0 violations) |
| Total row rank / serial cells | `NA` | `NA`, `Total` |
| Published ranks vs ranks recomputed from counts (min method) | 0 disagreements (2 rank columns) | 0 disagreements |

- **Schema drift between the editions** (unchanged from the validation report): 18 column names are
  identical and 15/16 differ (`Greviously`/`Grievously`, `Driving on Wrong side`/`Wrong Side`, spacing in
  `drug  -`). 7 city spellings changed, and 43 labels are common to both. **Nothing is mapped between
  editions.**
- **Rank and serial columns** are excluded from measures by the schema registry. Tests confirm that using
  them as a measure is refused (golden items G20 and G21).
- **Denominators:** a share is the city ÷ the published Total row. Over 50 cities the shares sum to 100%
  (real-data test), and the Total row equals the sum of the cities.
- **Legacy files** (`C:\Desktop\civicmind-ai-main\repo\data\raw`, read-only, not trusted):

  | File | Bytes | Finding |
  |---|---|---|
  | RA2019_A47.csv | 6,807 | **Byte-identical** to the promoted RA2019 A47 |
  | RA2019_A49.csv | 8,295 | 38 columns (road features); Total consistent; **Madurai `-54`** in "Others – Greviously Injured" |
  | RA2019_A2.csv | 9,015 | State-level table; **contains rates and shares** (per lakh population, per 10,000 vehicles, per 10,000 km) whose Total row is not a sum. The 10,000-km rate repeats 1021.947721 for 2016 and 2017. 6 non-numeric cells |
  | RA2019_A52.csv | 25,368 (portal 25,355) | **Not UTF-8** (3 cp1252 bytes: `½`, `ü`). The 13-byte size gap is unexplained. A police-station-level table |
  | BWSSB_Water_Consumption_August_2025.csv | 6,045 | Byte-identical to the promoted August file |

  **Consequence for future batches:** the current MoRTH validator assumes every non-rank column is a
  summable count. Tables like A2 need a column-type registry (count / rate / share) before ingestion, or
  the Total check will raise false mismatches.

### 2.1 Traffic: validated vs unresolved
Every count column in both editions is validated. Still unresolved:
- MoRTH's city boundary definition;
- the cross-edition column and city crosswalk;
- whether later editions restate earlier years.

## 3. Proposed transformations (none applied)

All are derived-layer rules. Raw files stay untouched, and each derived value keeps its original next to
it with the rule ID and version.

| ID | Original field / value | Proposed derived value | Reason and evidence | Rule (version) | Effect on analytics | Your approval needed |
|---|---|---|---|---|---|---|
| T1 | Apr/May header `Number of Connectionss` | `Number of Connections` (derived alias; raw header kept in the manifest) | Same column position, same publisher series, a one-letter typo; values are plausible counts | `bwssb_header_alias@v1` | Would let Apr/May pass schema checks. **They stay quarantined until a separate review decision.** | **Yes**, and it is a dataset-usage decision |
| T2 | May ward 40 `-2.00E-06` ML | 0 | Every other month shows 0.00 for this 1-connection ward; the value is −2 litres, a likely float artefact | `bwssb_tiny_negative_to_zero@v1` (only if \|value\| < 1e-5 ML) | Changes a sign. Affects May only. | **Yes** (changes meaning). Recommendation: **do not apply**; keep May quarantined |
| T3 | May ML at 4–6 decimals | none | A precision difference, not an error | — | None; record as a caveat | No (no change) |
| T4 | `herohalli`, `sidedahalli` | Display label in title case; the published label stays the analytic value | Presentation only | `display_label@v1` | None (labels are not joined) | Yes (low risk) |
| T5 | Repeated ward numbers 14/85/153/191 | **No merge.** Row key = (ward number, published name, source record) | The paired rows have different values in all 4 months | already used | Unique-ward answers stay refused | No (records current behaviour) |
| T6 | Name aliases such as Jayangar → Jayanagar | **Rejected** | Would merge distinct rows (§1.3) | — | — | — |
| T7 | MoRTH 2019 → 2024 city spellings (7) | Cited city alias table | Needed for cross-edition comparison; needs an official source | `morth_city_alias@v1` | Enables a future cross-edition operation | **Yes**, plus a citation |
| T8 | MoRTH 2019 → 2024 column names (`Greviously` → `Grievously`, …) | Column crosswalk per schema version | Same as T7 | `morth_a47_columns@v1` | Same as T7 | **Yes** |
| T9 | MoRTH `NA` in Total-row rank cells | NaN in the typed view; raw `NA` kept | Already the ingestion behaviour; recorded in a `values.unparsed` finding | ingestion | None (ranks are not measures) | No (already applied, no change to raw) |
| T10 | Intensity rankings dominated by volatile or tiny rows (ward 2 March; ward 40) | **Approved and implemented 2026-10-17 as flags only** (see §3.1) | §1.3 | `water_intensity_flags@v1` | Ranks, values and row sets unchanged; rows gain `flags` | Approved (flag only, no exclusions) |

### 3.1 T10 as implemented: `water_intensity_flags@v1`
Applies only to `water_rank_rows(..., measure="litres_per_connection_per_day")`. Flags annotate; they
never exclude a row, change a value or change a rank.

**Per row** (always present on intensity rankings):

| Field | Meaning |
|---|---|
| `volatility_status` | `volatile` / `not_comparable` / `within_threshold` / `not_assessed` (no reference month given). If two references disagree, the order is volatile > not_comparable > within_threshold |
| `reference_status`, `reference_values`, `reference_notes` | Per reference month: the status, the same row's intensity there (`null` if unusable), and why it is unusable |
| `connections`, `flags` | `small_connection_base`, `volatile_vs_reference`, `not_comparable` |

**Per result:**
- `flag_summary` counts each status and small-base rows, over all ranked rows and over the returned
  rows. `not_comparable` and `not_assessed` are counted apart from `within_threshold`, so they can't
  be read as passes. The caveat repeats the counts and labels not-comparable rows "not assessed, not
  passed".
- `flag_policy` carries the id, thresholds, match key, reference months, the definition of each flag,
  and the scope statement.

**Rules** (identical in the code, the unit tests, the golden answers and the independent derivation):
1. **`small_connection_base`:** fewer than 100 connections on the row. **This is a provisional
   operational threshold chosen for this project on 2026-10-17, not a universal statistical
   standard.**
2. **Zero connections in the reference month:** intensity there is undefined, so the status is
   `not_comparable`. The same applies when there is no row with exactly the same (ward number,
   published name) pair, or more than one.
3. **Zero consumption** (with connections) gives an intensity of 0, which is comparable:
   - 0 against a positive value is `volatile`, in either direction;
   - 0 against 0 is `within_threshold`.
4. **Otherwise** the status is `volatile` if the larger intensity is >= 2x the smaller (inclusive),
   else `within_threshold`.

**Interpretation.** `volatile_vs_reference` is a **descriptive difference between two months**. It is
not evidence of an anomaly, a data error or a cause. **Only two trusted months exist today** (August
2025 and March 2026), so each month can be compared with one other month only. April and May 2025
stay quarantined and are refused as references (golden G24).

**Scope of the exception.** Matching the same row across months is a **narrow, explicit exception**
approved on 2026-10-17 for these flags only:
- matching uses the exact published key, with no case-folding, no aliases and no fuzzy matching;
- reference values are never summed, averaged or used to rank;
- `water_rank_rows` is the only public analytics function that accepts `references` (tested);
- every dataset still carries `no_cross_dataset_join`, and `require_use(..., "cross_dataset_join")`
  still refuses (tested).

**Real data, March against August** (golden G25, re-derived independently): of 202 rows, 1 volatile
(ward 2 Chowdeshwari Ward, 3,868.9 vs 1,645.6 L/connection/day), 0 not comparable, 201 within
threshold, and 1 small base (ward 40, 1 connection, 0 consumption in both months, so within threshold).

**Rejected alternative.** A within-month outlier rule flagged 5–20 consistently high-consumption rows
a month and could not isolate the volatile row.

## 4. Analytics against the findings

- **Supported (trusted Aug 2025, Mar 2026, RA2019 A47, RA2024 A47):**
  - A1 city totals;
  - A2 published-row rankings, including intensity;
  - A3 month change (city totals, with day counts);
  - A4 city lookup with share of the Total row, and top cities in one edition.
- **Refused, each with a stable code:**
  - unique-ward rankings (`ward.identifiers_not_unique`);
  - April/May, census (`status.quarantined`);
  - waste in any mode (`modelled.not_trusted`, `exploratory.not_permitted`);
  - aliases (`city.not_found`);
  - other-edition column spellings, rank columns, serial numbers (`column.unknown`);
  - unknown units (`measure.unknown`);
  - reversed or identical months (`period.order`, `period.same`).
- **Changes in this review:**
  - MoRTH validator: new check that grievous + minor = total injured (`injured.sum_mismatch`, warning).
    It reports nothing on either edition, so the manifests are unchanged; a future file that breaks it is
    refused for trusted use until reviewed.
  - Real-data cross-checks:
    - our city ranks equal the publisher's rank columns for all 50 cities, in both editions and both rank
      columns;
    - shares sum to 100%;
    - all 202 water rows are ranked, none merged, and they sum to the A1 total.
  - Golden G22: the lowest-intensity published row is ward 40 (1 connection, 0 ML). This exposes the anomaly.
  - Fixture fix: the synthetic MoRTH fixture broke the injury identity. The new check caught it, and the
    fixture was made consistent.

## 5. Waste readiness (WASTE-BLR-GCP) — profile only

| Aspect | Finding |
|---|---|
| Schema | `swm_gcp/v1`: 13 columns, 198 rows; `City_Name`, `Zone_Name`, `Ward_Name`, `Ward_No.`, then generated / collected / processed × 3 financial years |
| Ward scheme | Numbers 1–198 and 198 distinct names (e.g. `KEMPEGOWDA_`); consistent with BBMP-198 but **unverified**. Zones are `BOMMANAHALLI` (14) and `BOMMANHALLI` (2) |
| Units | Headers say "Metric tonnes"; the period is presumably per financial year (not stated). The processed columns are labelled **"Average** quantum" although they are fixed percentages of a total, so the unit or meaning is ambiguous |
| Multiplier pattern | **The base series is 2017-18 collected** (0–2 decimals). For example, ward 1: 6,732 ÷ 1.052632 = 6,395.4 (2016-17), ÷ 1.052632 = 6,075.63 (2015-16). 1.052632 = 1/0.95, i.e. a constant 5% back-calculation in every ward. Generated = collected for 2015-16 and 2016-17. Processed = 60% / 65% / 70% |
| Generated vs collected | 2017-18 generated is an independent series (ratio to 2016-17 is 0.474–1.232) and is **below collected in 197 of 198 wards**: 832,039 vs 1,390,756 MT, i.e. 2,280 vs 3,810 t/day citywide |
| Validator | `swm_gcp@v1` reproduces all of the above as warnings (`values.modelled_signature`, `collected.equals_generated`, `collected.exceeds_generated`) |
| Current decision | `keep_profiled`, `value_nature: modelled`, `permitted_uses: []` → **trusted and exploratory ingestion both refused** (verified) |

**Recommendation.** Do not enable waste analytics with the current decision. If you want exploratory
views, approve them separately by adding `permitted_uses: [exploratory]` to its review decision. That
would allow only labelled, exploratory, non-ranking outputs (ward-efficiency rankings and
"measured performance" claims stay blocked by the ingestion restrictions). A trusted waste slice needs a
measured source (e.g. BBMP/SWM ward reports) and a ward-scheme authority.

## 6. Remaining blockers for a complete water + traffic demonstration
1. **Ward identifier authority (BBMP-198)**: needed for any unique-ward claim and any ward-level comparison
   across months or sources.
2. **Water intensity flags (T10)**: implemented as flags only. With just two trusted months, volatility can be
   assessed against one reference month only.
3. **Only two trusted months**: April/May are quarantined (T1/T2 decisions), and the other 8 months are not
   acquired (batch 02).
4. **MoRTH cross-edition crosswalks (T7, T8)**: required before any 2019 vs 2024 comparison.
5. **Planner**: no QuerySpec layer yet, so causal and unsupported questions are refused only at the
   function level.
