# Query capability inventory (Water & Road-Safety Query Coverage v1)

Status: 2026-10-17. Single source for which questions CivicMind answers, how, and when it
refuses. Every intent goes through the same pipeline (parser → feasibility → trusted ingest →
analytics → evidence validation → composer); there is no second parser or query path.

Datasets: see `data/manifests/` and the README. Water = BWSSB monthly ward consumption
(trusted July 2025 – March 2026 except January 2026); roads = MoRTH million-plus city
traffic-rule violations, Annexure 47 (trusted editions 2019 – 2024).

## Implemented intents

| Intent | Example | Parameters | Data and fields | Method (`value_basis`) | Trust / comparability conditions | Refused when | Tests |
|---|---|---|---|---|---|---|---|
| `water_total` | What was water consumption in July 2025? | measure (ML or connections), one month | one trusted BWSSB month; `Consumption in ML` / `Number of Connections` | sum of every published row, duplicates included (`derived`) | month trusted; values numeric | month missing/ambiguous, untrusted month, ward or row scope, units other than ML/connections, non-numeric cell (`values.missing`) | golden A1, pipeline.v1, coverage.v1 C07, C14 |
| `water_rank_rows` | Top 5 published rows by litres per connection per day in August 2025 | measure, n, order, one month (+ reference months for flags) | one trusted month (+ trusted reference months) | rank of published rows (`published`; litres/connection/day `derived`) | rows are published rows, not wards; flags never re-rank | as above; reference months only for intensity | golden A2/T10 |
| `water_rank_wards` | Which ward had the highest consumption in August 2025? | as above | one trusted month | unique-ward ranking | refused while ward numbers repeat (`ward.identifiers_not_unique`) | always today (repeated ward numbers) | golden A2 |
| `water_month_change` | How did water consumption change from August 2025 to March 2026? | measure, exactly two months | two trusted months | difference of city totals and % (`derived`) | city totals only; rows never matched across months | not exactly two months; litres/connection/day; either month untrusted | golden A3, coverage.v1 C13 |
| `road_city_value` | How many over-speeding accidents did Bengaluru record in 2021? | city (exact label), category, measure, one edition | one trusted A47 edition | published cell + share of the published Total row (`published_and_derived`) | Annexure 47 only; exact city label | no/multiple editions (`query.cross_edition`), no category (no all-violation total exists), unknown city | golden A4, coverage.v1 C01 |
| `road_top_cities` | Top 3 cities by over-speeding deaths in 2024 | category, measure, n, one edition | one trusted A47 edition | rank of published cells, ties share rank (`published`) | highest first only | as above; lowest-first rankings | golden A4, coverage.v1 C02 |
| **`road_compare_cities`** (new) | Compare over-speeding deaths in Bengaluru and Chennai in 2024 | exactly two cities, category, measure, one edition; comparison wording required | one trusted A47 edition; label column + one measure column | both published cells, their shares of the Total row, difference = first − second (`published_and_derived`) | same edition and column only; no category summation; shares null if Total is 0 | two editions (`query.cross_edition`), same city twice / three cities (`query.entity_ambiguous`), unknown city (`city.not_found`), missing value (`values.missing`), untrusted edition | `tests/test_coverage_v1.py`, coverage.v1 C08–C12, C19, C20, C27 |
| **`data_coverage`** (new) | Which months of water data are available? / What is the latest edition of road accident data? | domain (water or roads) | dataset manifests only (status, review decision, period, portal publication date); no data file is read | catalogue metadata (`catalogue`); no evidence items, no data value | quarantined / exploratory / profile-only periods listed with the reason, never as usable; Annexures 1, 2, 49 listed as "never used" | domain not water or roads | `tests/test_coverage_v1.py`, coverage.v1 C03–C06 |
| `dataset_family` | Rank wards by waste collection efficiency | — | waste, census | — | always refused: no trusted data (`modelled.not_trusted`, `status.quarantined`) | always | pipeline.v1, coverage.v1 C30, C31 |

## Transparency on every water and road response (Phase D)

- `result.value_basis`: `published`, `derived`, `published_and_derived` or `catalogue`.
- `coverage` (answers **and** refusals for water or road questions): trusted periods, the
  latest trusted period with its dataset and portal publication date, every non-trusted period
  with its reason (`quarantined`, `exploratory_only`, `profile_only`, …) and a freshness note:
  *static files as published; no live data connection; "latest" is the latest trusted file,
  not current conditions.* Ordinary road answers never list other annexures; only the explicit
  availability question does.
- "Current", "now", "this year", "the latest month's consumption" are refused
  (`query.period_missing`) with the coverage block; the newest local file is never treated as
  current.
- Review-accepted manifest caveats that ingestion does not re-derive (`series.swing`,
  `file.newline_style`) now reach every answer that uses the file, naming the affected rows
  (e.g. Chowdeshwari Ward, November 2025; Horamavu, February 2026).

## Candidates investigated and not implemented

| Candidate | Why not (now) |
|---|---|
| Water value for one ward and month | Ward numbers repeat (14, 85, 153, 191) and no ward-identifier authority is recorded; the parser refuses named wards. Needs the BBMP/GBA ward delimitation. |
| City-wide consumption per connection | Formula is defined (ML ÷ connections ÷ days) but bulk/commercial connections make a city average easy to misread; deferred until reviewed. Row-level intensity rankings exist. |
| Record-level anomaly listing ("which rows changed suspiciously?") | Swing findings exist in manifests and now reach answers as caveats; a listing intent needs its own response template and review of thresholds. |
| Road edition-to-edition comparison | Category allocation shifts between editions (Chennai, Pune, Mumbai) and the categories are not shown to be exhaustive; owner decision 2026-10-17 defers it. |
| All-violation accident totals | The categories are not established as a partition of all accidents; refused (`query.metric_missing`). |
| Lowest-first city rankings | Many zero cells and ties; not reviewed. |
| Definitions, policy, tariffs (needs official documents) | No document retrieval in this milestone; refused by the parser. |
| Ward ↔ city or water ↔ road relationships | No geographic mapping or identifier authority; refused (`query.cross_domain`). |

## Evaluation

`eval/questions/coverage.v1.yaml` (35 items) classifies questions as answerable from trusted
data, answerable only by derivation, requiring documents, requiring relationships,
underspecified, unsupported by data, or blocked by trust. `eval/coverage_metrics.py` runs it
through the pipeline and reports correct-answer and correct-refusal rates,
unsupported-answer rate, evidence completeness, provenance correctness, comparability
violations and freshness coverage. Road comparison values were derived independently with the
standard-library `csv` module. The rates describe this fixed set only.
