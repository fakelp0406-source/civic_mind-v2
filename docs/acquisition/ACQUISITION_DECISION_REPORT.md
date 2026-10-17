# Acquisition decision report — P0 candidates (no downloads performed)

Date: 2026-10-17 · Basis:
- portal metadata read through the data.gov.in catalogue API, which serves the central,
  Smart Cities and Karnataka portals;
- resource pages and the GODL page;
- the legacy files profiled in `docs/audit/`.

**Nothing has been downloaded.** Every row below is a **candidate**, not an approved file.

**Correction to the previous review:** the P0 candidate count is **32 CSVs** (12 water, 2 ward
reference, 2 waste, 16 MoRTH), not 33, plus 3 documents.

Licence for every data.gov.in-hosted file:
- **GODL-India.** Evidence: the https://www.data.gov.in/Godl page, the "Released under NDSAP" catalogue field, and the karnataka.data.gov.in footer.
- **Attribution format (verified on the GODL page):** "[Data provider], [Year], [Name of data], [Repository], [Version/date of publication], [URL]. Published under [Licence]: [Licence URL]."
- **GODL does not cover personal information.**

## 1. Classification

### 1.1 Verified against authoritative metadata
"Verified" here means the portal states the filename and size, *and* the schema is known from
the portal's own field list or a profiled legacy copy. It does **not** mean downloaded or validated.

| ID | Dataset (publisher) | Resource page | Direct download URL (from catalogue API; not fetched) | Format / size | Period | Schema (source of evidence) | Geography / ward scheme |
|---|---|---|---|---|---|---|---|
| WATER-BWSSB-2025-08 | Water consumption, Aug 2025 (BWSSB) | https://www.data.gov.in/resource/water-consumption-data-month-august-2025 | https://www.data.gov.in/files/ogdpv2dms/s3fs-public/BWSSB_Water_Consumption_August_2025.csv | CSV, 6,045 B | 2025-08 | `Ward number`, `Ward Name`, `Number of Connections`, `Consumption in ML` (resource page; legacy copy profiled: 202 rows) | Bengaluru wards; **scheme UNKNOWN** (numbers 1–198) |
| DEMO-SC-BLR-2011-DEM | Demographic Profile: Bengaluru, as on 01-03-2011 (BBMP via Smart Cities) | https://www.data.gov.in/resource/demographic-profile-bengaluru-01-03-2011 | https://data.gov.in/files/ogdpv2dms/s3fs-public/datafile/Demographic_Profile_Bengaluru_ason_01-03-2011_1.csv | CSV, 14,921 B | Census 2011 | City; Zone; Ward Name; Ward No.; Area; population (thousands) by sex and age (portal field list) | Bengaluru wards; **scheme UNKNOWN** (expected BBMP-2010) |
| DEMO-SC-BLR-2011-HH | Household Profile: Bengaluru, as on 01-03-2011 | https://www.data.gov.in/resource/household-profile-bengaluru-01-03-2011 | https://data.gov.in/files/ogdpv2dms/s3fs-public/datafile/Household_Profile_Bengaluru_ason_01-03-2011.csv | CSV, 11,592 B | Census 2011 | City; Zone; Ward Name; Ward No.; Total no. of Households | as above |
| WASTE-BLR-GCP | Solid waste generated, collected, processed, 2015-16 to 2017-18 (BBMP SWM via Smart Cities) | https://www.data.gov.in/resource/solid-waste-generated-collected-processed-data-bengaluru-2015-16-2017-18 | https://data.gov.in/files/ogdpv2dms/s3fs-public/datafile/Solid_Waste_Generated_Collected_Processed_Data_Bengaluru_from_2015-16to2017-18_1.csv | CSV, 23,868 B | FY 2015-16 to 2017-18 | City; Zone; Ward_Name; Ward_No.; MSW generated, collected and processed (MT) per year | as above |
| WASTE-BLR-D2D | Door-to-door collection coverage, as on 01-01-2019 | https://www.data.gov.in/resource/d2d-collection-coverage-bengaluru-01-01-2019 | https://data.gov.in/files/ogdpv2dms/s3fs-public/datafile/D2D_Collection_Coverage_Bengaluru_ason_01-01-2019.csv | CSV, 32,324 B | snapshot 2019-01-01 | City; Zone; Ward Name; Ward No; households/establishments; covered by D2D; with source segregation | as above |
| ROAD-RA2019-A2 | State/UT road accidents 2016–2019 (MoRTH) | https://www.data.gov.in/resource/stateut-wise-total-number-road-accidents-india-2016-2019 | https://data.gov.in/files/ogd20/ogdpv2dms/s3fs-public/RA2019_A2.csv | CSV, 9,015 B | 2016–2019 | profiled legacy copy: 37×21 incl. `Total` row | state; no wards |
| ROAD-RA2019-A47 | Million-plus cities by traffic violation, 2019 | https://www.data.gov.in/resource/cities-wise-accidents-classified-according-type-traffic-violations-million-plus-cities | https://data.gov.in/files/ogd20/ogdpv2dms/s3fs-public/RA2019_A47.csv | CSV, 6,807 B | 2019 | 51×33 incl. `Total` | city; no wards |
| ROAD-RA2019-A49 | Million-plus cities by junction type, 2019 | https://www.data.gov.in/resource/cities-wise-accidents-classified-according-type-junctions-million-plus-cities-during-2019 | https://data.gov.in/files/ogdpv2dms/s3fs-public/RA2019_A49.csv | CSV, 8,295 B | 2019 | 51×38 incl. `Total`; Madurai −54 | city; no wards |

**RA2019 caveat:** the legacy byte sizes that matched were Windows CRLF working copies of
LF-normalised Git blobs. Only fresh downloads plus hashes can confirm byte identity.

### 1.2 Confirmed download route, unresolved schema or compatibility
| ID | Resource page slug (`https://www.data.gov.in/resource/…`) | Direct URL (`…/s3fs-public/` + path) | Size | Unresolved |
|---|---|---|---|---|
| WATER-BWSSB-2025-04 | `water-consumption-data-month-april-2025` | `Water_consumtion_data_april_2025.csv` | 5,845 | schema assumed; portal period metadata wrong (shows 2025-06-21) |
| WATER-BWSSB-2025-05 | `water-consumption-data-month-may-2025` | `Water_Consumption_Data_May_2025.csv` (host `data.gov.in`) | 6,625 | **~780 B larger than neighbours: possible schema/row change** |
| WATER-BWSSB-2025-06 | `water-consumption-data-month-june-2025` | `Water_Consumption_Data_June_2025.csv` (host `data.gov.in`) | 6,624 | same as May |
| WATER-BWSSB-2025-07 | `bwssb-water-consumption-data-month-july-2025` | `Water_Consumption_Data_July_2025_0.csv` | 5,844 | schema assumed |
| WATER-BWSSB-2025-10 | `water-consumption-data-month-october-25` | `Water_Consumption_Data_Oct_25_3.csv` | 5,844 | schema assumed |
| WATER-BWSSB-2025-11 | `water-consumption-data-month-november-25` | `Water_Consumption_Data_Nov_25_2.csv` | 5,841 | schema assumed |
| WATER-BWSSB-2025-12 | `bwssb-water-consumption-data-month-december-25` | `Water_Consumption_Data_Dec_25_5.csv` | 5,843 | schema assumed |
| WATER-BWSSB-2026-01 | `water-consumption-data-month-january-2026` | `Water_Consumption_Data_Jan_26_0_0.csv` | 5,845 | different catalogue ("Water Consumption Data-2026"); schema assumed |
| WATER-BWSSB-2026-02 | `water-consumption-data-month-february-2026` | `Water_Consumption_Data_Feb_26_0_1.csv` | 5,848 | as above |
| WATER-BWSSB-2026-03 | `water-consumption-data-month-march-2026` | `Water_Consumption_Data_Mar_26_0.csv` | 5,844 | as above; post-GBA (Nov 2025) month still numbered on the old scheme? |
| ROAD-RA2020-A47 / A49 | `…traffic-violations-million-plus-cities-0` / `…junctions-million-plus-cities-during-2020` | `ogd20/ogdpv2dms/s3fs-public/RA2020_A47.csv` / `RA2020_A49.csv` | 6,607 / 6,812 | columns not inspected |
| ROAD-RA2021-A47 / A49 | `…traffic-violations-million-plus-cities-1` / `…junctions-million-plus-cities-during-2021` | `…/RA2021_A47.csv` / `RA2021_A49.csv` | 6,640 / 6,814 | columns not inspected |
| ROAD-RA2022-A2 / A47 / A49 | `stateut-wise-details-road-accidents-india-2019-2022`, `million-plus-city-wise-number-accidents-classified-according-type-traffic-violations`, `million-plus-cities-wise-number-accidents-classified-according-type-junctions-million-0` | `604783543/Version_1/Transport_2022_Annexure_2.csv`, `604784046/…_47.csv`, `604784052/…_49.csv` | 4,594 / 6,870 / 5,844 | columns not inspected; city list may differ |
| ROAD-RA2023-A47 / A49 | `million-plus-cities-wise-number-accidents-classified-according-type-traffic-rule`, `…type-junctions-million-plus` | `604777242/Version_1/Transport_2023_Annexure_47.csv`, `604777249/…_49.csv` | 6,918 / 5,837 | category renamed "Traffic Rule Violations" |
| ROAD-RA2024-A1 / A2 / A47 / A49 | `year-wise-details-road-accidents-persons-killed-and-injured-1970-2024`, `stateut-wise-number-road-accidents-india-2021-2024`, `million-plus-city-wise-accidents-classified-according-type-traffic-rule-violations-during`, `million-plus-city-wise-accidents-classified-according-type-junctions-during-2024` | `604807230/…_1.csv`, `604807238/…_2.csv`, `604807629/…_47.csv`, `604807642/…_49.csv` (all `Version_1/Transport_2024_Annexure_*`) | 3,939 / 4,074 / 6,925 / 5,762 | columns not inspected |

**Compatibility, unresolved for every ward-level dataset above and in §1.1:** no document
yet establishes which ward scheme BWSSB, the Smart Cities SWM tables, or the census profile
use. Matching ward numbers 1–198 is a lead, not proof.

### 1.3 Requires manual download or additional permission checks
| ID | Why |
|---|---|
| WATER-BWSSB-2025-09 (`bwssb-water-consumption-data-month-septemeber-2025`, 5,845 B) | The catalogue only exposes a **signed, expiring** S3 link, so download it from the resource page |
| All data.gov.in files | It is **untested** whether the direct file URLs work without the portal's download/usage form. If a form appears, you complete it (personal details are not entered by tools) |
| DOC-GODL | Save https://www.data.gov.in/Godl (verified page) as the licence record |
| DOC-SWM-RULES-2026 | The official PDF URL must be captured from https://swmp.cpcb.gov.in/en ("Download SWM Rules, 2026 (PDF)") and cross-checked with G.S.R. 388(E) on egazette.gov.in |
| DOC-MORTH-RA2024 | The official morth.gov.in URL is not yet found; only an OpenCity mirror is known |

## 2. Per-dataset caveats and validation checks

| Family | Known caveats | Stage A (integrity) | Stage B (semantic) | Stage C (compatibility) |
|---|---|---|---|---|
| BWSSB monthly | recorded consumption; bulk/commercial included; 4 duplicate ward numbers in Aug; May/Jun size anomaly; Apr period metadata wrong; ward scheme unknown | hash, size vs portal, encoding, 4-column header | ints ≥0; ML ≥0; duplicates listed; same columns every month; month totals | **join blocked** until a documented identifier source or crosswalk exists; produce matched / unmatched / ambiguous / duplicated lists vs the census profile |
| Census ward profile (SC) | 2011 data; population in thousands; scheme undocumented on the page | as above | 198 unique Ward No? units; zone names consistent; DEM vs HH Ward No/Name pairs identical | candidate reference **only if** an official delimitation document confirms it |
| SWM GCP / D2D (SC) | 2015–2019 snapshots; SWM Rules 2016 era; units MT/yr | as above | collected ≤ generated; processed ≤ collected; coverage ≤ total; repeated header rows | as BWSSB |
| MoRTH city/state tables | editions revise earlier years; `Total` rows; city spellings and category names change; no city boundary definition | hash, size | `Total` = sum of other rows; negatives flagged; edition recorded per value | **never joined to ward data**; city labels across editions require an alias table, with source per alias |

## 3. Critical join rule (adopted)
- A name-match rate (e.g. 95%) **does not authorise a join**.
- A join requires verified stable identifiers backed by an authoritative definition, or a documented, version-aware crosswalk (see `docs/MANIFEST_SPEC.md`, Stage C).
- Unmatched, ambiguous and duplicated entities are always reported separately.
- No joins across ward schemes (BBMP-198/243/225, GBA-369) without an official crosswalk, and no equivalence inferred from similar names.

**Open evidence gap:** the official notification that defines the BBMP 198-ward list
(the 2009/2010 delimitation) has not been located in an official repository.
- OpenCity hosts later delimitation documents (2019–2023) and a 2015 ward map, but those are secondary.
- Locating the original notification (Karnataka Gazette / Urban Development Department) is the prerequisite for any ward-level join.
- Until then, Bengaluru ward datasets are analysed **side by side, each on its own identifiers**.

## 4. Recommended minimal first batch (8 CSVs, ~85 KB, plus 1 page)

The first batch is chosen to **test the pipeline and the riskiest assumptions** before acquiring everything.

| # | ID | Why it is necessary |
|---|---|---|
| 1 | WATER-BWSSB-2025-08 | Settles the legacy file's provenance (hash comparison); schema already known; anchors the water domain |
| 2 | WATER-BWSSB-2025-04 | First month of the series, from the 2025 catalogue; checks schema stability and the wrong period metadata |
| 3 | WATER-BWSSB-2025-05 | The size anomaly (+780 B); reveals whether the monthly series really has one schema before fetching all 12 |
| 4 | WATER-BWSSB-2026-03 | From the separate 2026 catalogue and after GBA's 369-ward notification; shows whether numbering changed |
| 5 | DEMO-SC-BLR-2011-DEM | The candidate ward identifier reference; needed to *assess* identifiers (not to join) |
| 6 | WASTE-BLR-GCP | Solid waste is a required domain; a second ward-level source for the identifier assessment |
| 7 | ROAD-RA2019-A47 | Byte comparison with the legacy copy; known schema baseline |
| 8 | ROAD-RA2024-A47 | Latest edition; measures schema drift 2019→2024 for the city road-safety series |
| — | DOC-GODL (page capture) | Licence and attribution record for all of the above |

**Deferred to batch 2** (after batch-1 validators pass): the remaining 8 BWSSB months, the
household profile, D2D coverage, the other 13 MoRTH tables, SWM Rules 2026 and the MoRTH 2024
report PDFs (only needed once RAG work begins).

**Expected batch-1 outputs (after approval and download):**
- 8 manifests;
- Stage A and Stage B results;
- an **identifier assessment report** comparing BWSSB (3 months) and SWM GCP against the
  census profile, with separate matched / unmatched / ambiguous / duplicated lists;
- **no joins.**

## 5. Questions the P0 set could support (once validated)

Each question is answerable within a single dataset:
- **Water:** top/bottom wards by consumption and per connection in a month; month-on-month change.
- **Waste:** collection efficiency by ward and zone, 2015-16 to 2017-18; lowest D2D coverage, 2019.
- **Road safety:** Bengaluru's rank among million-plus cities by violation and junction type,
  2019–2024; national 1970–2024 series; state changes 2021→2024.

**Cross-dataset ward profiles** (water + waste + population) become possible **only after the
join rule in §3 is satisfied.**
