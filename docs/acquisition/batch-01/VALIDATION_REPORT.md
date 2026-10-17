# Acquisition batch 01 — retrieval and validation report

Date: 2026-10-17 · Plan: `docs/acquisition/ACQUISITION_DECISION_REPORT.md` §4 (8 CSVs plus the GODL page)
Processing: `scripts/process_batch_01.py`
Machine-readable outputs: `summary.json`, `profiles/*.json`, `cross_dataset_checks.json`, and
`data/manifests/*.yaml` (8 manifests).

**All 8 planned files are retrieved.** After the person review of 2026-10-17
(`REVIEW_DECISIONS.yaml`), **4 files are promoted** to `data/raw/` (still git-ignored), 3 are
quarantined and 1 is kept as modelled estimates. Nothing is joined, and nothing is committed.

## 1. Summary

| Dataset | Status | Bytes (= portal) | SHA-256 | Errors / warnings |
|---|---|---|---|---|
| WATER-BWSSB-2025-08 | **promoted** | 6,045 ✓ | `108639ce30129414e1dbd3d67b8403dcc83878bf2c2dc674b58d895f2adca974` | 0 / 2 |
| WATER-BWSSB-2026-03 | **promoted** | 5,844 ✓ | `798243f90aad7697d4c5fb9e76bc2ef32c1e91b75b9e987be52685c115d8bc3c` | 0 / 3 |
| ROAD-RA2019-A47 | **promoted** | 6,807 ✓ | `40bed81dc88f3350b2bd13f3f3699d2d07e7b6afdfdf7e02a286e568897bedcc` | 0 / 0 |
| ROAD-RA2024-A47 | **promoted** | 6,925 ✓ | `702f75f332a273e9c09eb500a7d2f90c2ae71eec3bf06fe01d48a6fc56bd37e9` | 0 / 0 |
| WATER-BWSSB-2025-04 | **quarantined** | 5,845 ✓ | `0bafa2d91c821db63161c213c7fe0def179d10e53eed87ab72e325ef77dc20ee` | 1 / 3 |
| WATER-BWSSB-2025-05 | **quarantined** | 6,625 ✓ | `d266a3a27c8f01c5c4d005bdeab018ccf19aa76ce83f268a80c2bbdb7c31da56` | 2 / 2 |
| DEMO-SC-BLR-2011-DEM | **quarantined (person decision)** | 14,921 ✓ | `ec32966c4d43b24bd5b98ff3718e65b6dcd398d2968310c6d9d8ab720e266e37` | no validator yet |
| WASTE-BLR-GCP | **integrity passed; `value_nature: modelled`** | 23,868 ✓ | `7c51dc6a3c8dfdef0a0174e4e7f60b3444acdab13e7024a71293013fd074e394` | no validator yet |

All files are UTF-8 without a BOM.
- **Line endings:** August 2025, RA2019 A47, RA2024 A47, the census file and the waste file use CRLF. **April 2025, May 2025 and March 2026 use bare CR** (202 bare CR + 1 CRLF).
- **Files are never edited.** Parsing uses universal newlines in memory.

## 2. Retrieval and provenance

- **Automated (plain HTTPS GET of the catalogue's direct URL, HTTP 200):** WATER-BWSSB-2026-03 and ROAD-RA2024-A47.
- **Manual, by the project owner** through the resource page's Data → CSV Download form, with the CAPTCHA completed by a person. This covers the other 6 files; the automated GET of their direct URLs had returned HTTP 403.
  - Files were copied byte-identically from `Downloads` (SHA-256 verified) and stored under the served names.
  - The browser had appended " (1)" to two names; this is recorded in the manifests.
  - `retrieved_at` is the downloaded file's modification time (`manual_downloads.tsv`).
  - The originals remain in `Downloads`.
- **Legacy provenance resolved:**
  - **WATER-BWSSB-2025-08 is byte-identical to the legacy repository's quarantined `BWSSB_Water_Consumption_August_2025.csv`.** The legacy file is therefore the official Karnataka OGD resource.
  - **ROAD-RA2019-A47 is byte-identical to the legacy `RA2019_A47.csv`.**
  - Both manifests record this in `same_bytes_as`.
- **Licence:** GODL-India for all 8 files. The attribution string is filled into each manifest; the evidence note is in `data/external/verify_2026-10-17/licence/`.

## 3. Semantic validation (Stage B)

**BWSSB monthly (validator `bwssb@v1`)** — common to all 4 months:
- 202 rows; ward numbers 1–198, no gaps.
- **4 ward numbers appear twice** and are left unresolved: 14 Bagalagunte/sidedahalli, 85 Doddanekkundi/Varthur, 153 Jayanagar/Jayangar, 191 Singasandra/Singsandra.
- **"Varthur" also appears under two ward numbers** (85 and 149).
- Ward 40 Doddabidirakalu has 1 connection.

| Month | Connections | Consumption (ML) | Month-specific findings |
|---|---|---|---|
| Apr 2025 | 1,023,813 | 31,608.71 | **error:** header `Number of Connectionss` (misspelt); zero consumption for ward 40 |
| May 2025 | 1,029,539 | 30,816.50 | **error:** same misspelt header; **error:** ward 40 consumption `-2.00E-06` (a negative value in scientific notation) |
| Aug 2025 | 1,047,734 | 30,580.05 | zero consumption for ward 40 |
| Mar 2026 | 1,077,862 | 29,732.45 | zero consumption for ward 40; bare-CR line endings |

April and May are **quarantined** (`data/quarantine/batch-01/`); the project owner decided to keep them there. The misspelt header is probably a publisher typo for the same column, and the −0.000002 ML probably means zero. **Neither is assumed or corrected.**

**MoRTH city tables (validator `morth_city@v1`):**
- RA2019 A47 and RA2024 A47 each have 50 cities plus a `Total` row that **equals the sum of the city rows in every count column**.
- **Between editions:** 18 column names are identical; 15/16 changed (capitalisation, spelling, the new `Sl. No.` column).
- **City labels:** 7 differ in spelling (Vizaq → Vishakhapatnam, Vadodra → Vadodara, Khozikode → Kozhikode, Thiruvanthapuram → Thiruvananthapuram, Tiruchirapalli → Tiruchirappalli, Vijaywada city → Vijayawada city, Allahabad(Prayagraj) → Allahabad (Prayagraj)). They are **not equated** without a cited alias table.

## 4. Census profile — critical data-quality defects (profiled; no validator yet)

`Demographic Profile: Bengaluru as on 01-03-2011`, 198 rows, 12 columns.
1. **Ward names cycle.** Only **67 distinct names** exist for 198 ward numbers. The 67-name sequence repeats at wards 68 and 135 (e.g. "Atturu" appears under wards 3, 70 and 137; "Kempegowda Ward" under 1, 68 and 135). Zone names follow the same cycle. **Ward names and zones for wards 68–198 are unreliable.**
2. **Mislabelled units.** "Total Population (in thousands)" ranges from 21,171 to 95,368. These are plausibly persons, not thousands (the published "thousands" would imply 21–95 million per ward).
3. **Three empty age columns.** Youth, adults and seniors contain only `NA`.
4. **Areas look shuffled.** Some wards have implausible areas (e.g. ward 198, 30.5 km²).

**Consequence:** this file **cannot serve as the ward-identifier reference.** **Decision (2026-10-17): quarantined** (`data/quarantine/batch-01/`); the defects are recorded in its
`known_limitations`. Another official ward-population source is needed.

## 5. Solid waste — modelled values, not measurements (profiled; no validator yet)

`Solid Waste Generated, Collected, Processed Data Bengaluru from 2015-16 to 2017-18`, 198 rows, 13 columns. Ward names and numbers are internally consistent (198 distinct each). Zone spelling varies (`BOMMANAHALLI` / `BOMMANHALLI`).

Ratios hold **exactly in all 198 wards**:
- generated 2016-17 = generated 2015-16 × 1.052632;
- collected 2017-18 = collected 2016-17 × 1.052632;
- processed = **60% / 65% / 70%** of generated (2015-16, 2016-17) or of collected (2017-18).

In addition:
- collected = generated in every ward for 2015-16 and 2016-17, i.e. 100% "efficiency" everywhere;
- in 2017-18 collected exceeds generated in 197 of 198 wards (1,390,756 MT vs 832,039 MT in total).

**Interpretation (recorded as caveats, not corrected):** these figures are estimates derived from one base series with fixed growth and processing factors. They are **not ward-level measurements**, so they cannot support collection- or processing-efficiency comparisons between wards. The 2017-18 "generated" column is internally inconsistent with "collected".

## 6. Identifier assessments (Stage C) — no joins; `join_authorised: false` everywhere

| Comparison | Matched | Name conflicts | Unmatched | Ambiguous / duplicated |
|---|---|---|---|---|
| BWSSB Aug-25 vs BWSSB Mar-26 | 194 | 0 | 0 / 0 | 4 / 4 on both sides |
| BWSSB Aug-25 vs SWM | 93 | 101 | 0 / 0 | BWSSB 4 / 4; SWM 0 / 0 |
| BWSSB Aug-25 vs census | 29 | 165 | 0 / 0 | BWSSB 4 / 4; census 0 / 0 (but 67 names reused) |
| SWM vs census | 24 | 174 | 0 / 0 | 0 / 0 |

How to read this:
- **BWSSB ↔ SWM:** most "conflicts" are spelling, case or underscore variants of what appear to be the same ward names (e.g. 1 `Kempegowda Ward` vs `KEMPEGOWDA_`, 7 `Byatarayanapura` vs `BYATRAYANAPURA`). This is **evidence consistent with** both using the BBMP 198-ward numbering. **It is not proof, and it does not authorise a join.**
- **Census:** names agree only within wards 1–67 (spelling aside) because of the name cycle. It is unusable as an arbiter.
- **Still missing:** an authoritative definition of the 198-ward list (official BBMP delimitation notification) or a documented crosswalk.

## 7. Review decisions and promotion

Decisions by the project owner, 2026-10-17, recorded in `REVIEW_DECISIONS.yaml` (each bound to
the file's SHA-256) and applied by `civicmind.catalog.review.apply_review` on every run.

| Dataset | Decision | Result |
|---|---|---|
| WATER-BWSSB-2025-08 | accept; caveats `ward.duplicated`, `consumption_ml.zero` | promoted → `data/raw/water/BWSSB_Water_Consumption_August_2025.csv` |
| WATER-BWSSB-2026-03 | accept; caveats `file.newline_style`, `ward.duplicated`, `consumption_ml.zero` | promoted → `data/raw/water/Water_Consumption_Data_Mar_26_0.csv` |
| ROAD-RA2019-A47 | accept (no warnings) | promoted → `data/raw/roads/RA2019_A47.csv` |
| ROAD-RA2024-A47 | accept (no warnings) | promoted → `data/raw/roads/Transport_2024_Annexure_47.csv` |
| WATER-BWSSB-2025-04 | quarantine | stays in `data/quarantine/batch-01/` |
| WATER-BWSSB-2025-05 | quarantine | stays in `data/quarantine/batch-01/` |
| DEMO-SC-BLR-2011-DEM | quarantine | moved to `data/quarantine/batch-01/`; 3 defect limitations added |
| WASTE-BLR-GCP | keep, labelled modelled | `value_nature: modelled`; 3 caveats added; not eligible for promotion until a `swm_gcp` validator is approved and passes |

- **Promotion** (`civicmind.catalog.promote.promote`) re-hashed each source and verified each copy.
  The 4 promoted files are byte-identical to their sources in `data/external/`, which stay in place.
- **Git:** all promoted files are still ignored by `data/raw/**`. Tracking any of them needs an
  explicit `!data/raw/...` allowlist line, approved per file.
- **Reproducibility:** two consecutive runs of the processor produced identical manifests,
  reports, profiles and data files. Profile paths are now repo-relative.

## 8. Unresolved issues and decisions needed

1. A ward-identifier authority for the BBMP 198 scheme is still needed before any ward-level join.
2. An official ward-population source to replace the quarantined census file.
3. A city alias table with citations is needed before linking MoRTH editions.
4. Validators for the census and SWM families, written against the real schemas shown in §4–§5, need your approval.
5. Whether any promoted file should be tracked in Git (one allowlist line per file).
