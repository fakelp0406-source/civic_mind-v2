# CivicMind AI — Multi-domain Dataset Discovery (read-only)

Date: 2026-10-17 · Companion file: [`civicmind_dataset_catalog.csv`](civicmind_dataset_catalog.csv) (124 records; opens in Excel)

> **Nothing was downloaded and no repository was changed.** Evidence came from:
> - the data.gov.in public catalogue API (which also covers the Smart Cities and Karnataka state portals);
> - the OpenCity CKAN API (metadata and column names only, no data rows);
> - the IUDX catalogue API;
> - the CPCB SWM, NWDP and IUDX landing pages;
> - web search for documents.
>
> No grievance rows were read.

**Status legend** (column `status` in the CSV)

| Status | Meaning | Count |
|---|---|---|
| VERIFIED_RESOURCE | Resource-level metadata read: file name, byte size, and (where shown) field list or column names | 87 |
| VERIFIED_CATALOG | Catalogue/dataset page exists; individual files not inspected | 22 |
| DOC_LINK_UNVERIFIED | Official document identified; exact official PDF URL not yet confirmed | 6 |
| REGISTRATION | Login, consent or API key required | 5 |
| NOT_VERIFIED | Could not be checked (navigation refused / not attempted) | 2 |
| NOT_FOUND | Searched; no open source exists | 2 |

---

## 0. Workflow acknowledgement and two things to confirm

- **The old clone** (`C:\Desktop\civicmind-ai-main\repo\`) stays read-only. Nothing will be pushed until you approve the first push. Nothing will be installed, downloaded or created until you approve the exact commands.
- **New repository:** `https://github.com/fakelp0406-source/civic_mind-v2`.
  - It is public; I can read it without authorisation.
  - It already has one commit (`84297f5`) containing `.gitignore` (4,664 B) and `README.md` (15 B). **So we should *clone* it, not `git init`**; otherwise the first push would conflict with the existing history.
- **Push access:**
  - This PC already has **Git Credential Manager 2.6.0** set as Git's credential helper. On the first `git push`, GCM opens GitHub's own sign-in page in your browser. You authorise there, and the token is stored in Windows Credential Manager. It never appears in chat, and I never need to see it.
  - The `fakelp0406-source` account must own the repo or be a collaborator with write access. Please confirm this once you've reviewed the first local commit.
- **Local folder mismatch, please confirm:**
  - Your prompt names `C:\Desktop\civicmind-ai-main\civicmind\`.
  - You also attached `C:\Desktop\civic-v2\`, which is empty.
  - I recommend `C:\Desktop\civic-v2\` (short path, already separate from the old clone), but it's your call.

---

## 1. Headline findings

1. **The quarantined BWSSB file is very likely official.** Karnataka OGD resource "Water consumption data for the month of August-2025" (`karnataka.data.gov.in`, published 2025-09-17) is served as `BWSSB_Water_Consumption_August_2025.csv`, **6,045 bytes**. Its fields are `Ward number, Ward Name, Number of Connections, Consumption in ML`. That is the same name, size and columns as the legacy file. A hash check after a fresh download would close the question. The same publisher has **12 consecutive months (Apr 2025 – Mar 2026)**, which gives a real monthly series.
2. **MoRTH has published five more editions since 2019:** *Road Accidents in India* 2020, 2021, 2022, 2023 and **2024** (published on OGD 2026-06-18). They include:
   - million-plus-city tables (violations A47, junctions A49) for **every year 2019–2024**;
   - state totals (Annexure 2) chaining **2016–2024**;
   - a **national series 1970–2024** (Annexure 1).

   Trend questions become defensible. Forecasting remains a *separate* research decision that needs evaluation.
3. **Bengaluru is the only city with multiple domains on a shared ward key.** BBMP's 198-ward numbering (2010 delimitation) links:
   - BWSSB monthly water (2025–26)
   - Smart Cities solid-waste tables (generated/collected/processed 2015–18; D2D coverage, segregation, vehicles, bins as of 2019)
   - water revenue (2013–18)
   - STPs (with Ward No and coordinates)
   - 2011 Census ward population and households
   - the ward reference, area/road-length and public-goods tables
   - the 2015 198-ward KML

   **Caveat:** Bengaluru moved to **GBA with 369 wards in 5 corporations** (notified Nov 2025, renamed Dec 2025). Almost no service data is published on the new wards yet.
4. **Solid waste data is old but rich, and nothing recent is open.** Bengaluru's ward-level waste data stops at 2019. The CPCB SWM portal is a *registration/reporting* system with no public export found. The BBMP SWM site couldn't be checked automatically. The new **SWM Rules 2026** (G.S.R. 388(E), 27 Jan 2026, in force 1 Apr 2026) are a strong RAG document, but they post-date all the open waste data.
5. **Complaints data exists but is personal-data sensitive.** BBMP grievances 2020–Jun 2025 (via OpenCity) total about 106 MB, and 2024 alone has 207,016 rows. They contain **Staff Name and free-text Staff Remarks**, and there is **no closure date**, so resolution time can't be computed.
6. **Secondary-portal caution.** Many Bengaluru files are reachable only through **OpenCity** (a civic-tech mirror). Its licence fields are either "Other (Public Domain)" or empty, and the original publisher's terms are UNKNOWN. These are labelled `secondary mirror` in the catalogue. Prefer the official OGD copy whenever one exists; for example, Smart Cities D52 duplicates OpenCity's water coverage file.

---

## 2. Proposed staged scope

**Anchor:** Bengaluru, ward level, BBMP 198-ward scheme, with national/state/million-plus-city road-safety context. **Shivamogga** is an optional second Karnataka city for service-level benchmark questions that Bengaluru's data can't answer.

| Stage | Domains | Why |
|---|---|---|
| **P0 – MVP research set** | Road safety (MoRTH 2019–2024 + BTP Bengaluru), water (BWSSB monthly), solid waste (Bengaluru SC tables), ward geography/demography (198), RAG core (MoRTH reports, SWM Rules 2026, GODL) | All official or traceable. Small files (< 1 MB total excluding PDFs). One shared ward key plus a clean national/city series. Supports structured, RAG and graph tools |
| **P1 – extensions** | Sewerage (STPs), air quality (KSPCB hourly), rainfall (IMD), flooding/drains (KML), complaints (aggregated), budget (XLSX/PDF), public goods, RA severity/deaths/injuries, Basic Road Statistics, Shivamogga water/SWM, more RAG docs | Adds cross-domain questions; needs spatial overlay or PII handling |
| **P2 – optional** | IUDX APIs (OPEN BTP blackspots/events; SECURE others), OGD AQI API, NWDP, other cities' SWM, 243/225-ward maps, signal-timing PDFs, ward SWM micro-plans | Registration, heavy extraction, or low marginal value |

---

## 3. P0 manual download checklist (exact steps)

Save **everything** under the new project's `data/external/verify_YYYY-MM-DD/<domain>/`, keeping the **original filename**. For each file, record the URL, retrieval date, size and SHA-256 hash. Never place files directly in `data/raw/`.

### P0-A. MoRTH road accidents (data.gov.in, GODL-India) — 16 CSVs, each < 10 KB
For each row below:
1. Open the resource URL.
2. Click **Download** and choose **CSV**.
3. If the portal asks for a usage form (name/email/purpose), fill it in yourself. That is personal data, so I won't enter it.
4. Save the file with the original name shown.

| Save as (original) | Resource page (`https://www.data.gov.in/resource/…`) | Bytes |
|---|---|---|
| RA2019_A2.csv | `stateut-wise-total-number-road-accidents-india-2016-2019` | 9,015 |
| RA2019_A47.csv | `cities-wise-accidents-classified-according-type-traffic-violations-million-plus-cities` | 6,807 |
| RA2019_A49.csv | `cities-wise-accidents-classified-according-type-junctions-million-plus-cities-during-2019` | 8,295 |
| RA2019_A52.csv | `states-wise-list-top-ten-black-spots-2016-2018` | 25,355 |
| RA2020_A47.csv / RA2020_A49.csv | `…traffic-violations-million-plus-cities-0` / `…junctions-million-plus-cities-during-2020` | 6,607 / 6,812 |
| RA2021_A47.csv / RA2021_A49.csv | `…traffic-violations-million-plus-cities-1` / `…junctions-million-plus-cities-during-2021` | 6,640 / 6,814 |
| Transport_2022_Annexure_2/47/49.csv | `stateut-wise-details-road-accidents-india-2019-2022`, `million-plus-city-wise-number-accidents-classified-according-type-traffic-violations`, `million-plus-cities-wise-number-accidents-classified-according-type-junctions-million-0` | 4,594 / 6,870 / 5,844 |
| Transport_2023_Annexure_47/49.csv | `million-plus-cities-wise-number-accidents-classified-according-type-traffic-rule`, `…type-junctions-million-plus` | 6,918 / 5,837 |
| Transport_2024_Annexure_1/2/47/49.csv | `year-wise-details-road-accidents-persons-killed-and-injured-1970-2024`, `stateut-wise-number-road-accidents-india-2021-2024`, `million-plus-city-wise-accidents-classified-according-type-traffic-rule-violations-during`, `million-plus-city-wise-accidents-classified-according-type-junctions-during-2024` | 3,939 / 4,074 / 6,925 / 5,762 |

The full slugs are in the CSV (`landing_url`). Expected contents: one row per state/UT or city plus a `Total` row; counts of accidents, killed and injured.

### P0-B. BWSSB monthly ward water (Karnataka OGD, GODL-India) — 12 CSVs, ~6 KB each
1. Open `https://www.data.gov.in/resource/<slug>` (the same resource also appears under `karnataka.data.gov.in`).
2. Download the CSV and keep the original name.

The 12 slugs and file names are the `WATER-BWSSB-2025-04 … 2026-03` rows in the CSV. Expected contents: ~202 rows with `Ward number, Ward Name, Number of Connections, Consumption in ML`. **The August-2025 file should be byte-identical to the quarantined legacy file**, and we'll prove it by hash.

### P0-C. Bengaluru solid waste (Smart Cities, GODL-India) — 4 CSVs
Download `WASTE-BLR-GCP` (23,868 B), `WASTE-BLR-D2D` (32,324 B), `WASTE-BLR-SEG` (26,237 B) and `WASTE-BLR-PROC` (19,253 B) from their `landing_url`. Expect ward rows (Zone, Ward Name, Ward No) with tonnes or household counts.

### P0-D. Ward geography and demography (OpenCity mirror — licence UNKNOWN; record that)
1. Open `https://data.opencity.in/dataset/bbmp-ward-information` and download **"BBMP Ward Information"** (CSV, 19,452 B) and **"BBMP Ward Map - 2015"** (KML, 1,195,953 B).
2. Open `https://data.opencity.in/dataset/bengaluru-bbmp-ward-details` and download **"BBMP 2014 Ward Delimitation Details"** (CSV, 17,545 B).
3. Official alternative for population: the Smart Cities "City Profile: Bengaluru", *Demographic Profile* (14,921 B) and *Household Profile* (11,592 B). Prefer these where the fields overlap.

### P0-E. Bengaluru Traffic Police (OpenCity mirror)
From `https://data.opencity.in/dataset/bengaluru-road-crashes-data`, download the 6 CSVs (635 B – 3 KB each).

### P0-F. Documents for RAG
- **MoRTH RA 2019 report:** `https://morth.nic.in/sites/default/files/RA_Uploading.pdf`. This is the reference URL cited by every RA2019 resource; I haven't opened the file.
- **MoRTH RA 2024 report:** find it on morth.gov.in → Publications. OpenCity mirror: `https://data.opencity.in/dataset/road-accidents-in-india-2024`. Prefer the official copy.
- **SWM Rules 2026:** on `https://swmp.cpcb.gov.in/en`, click "Download SWM Rules, 2026 (PDF)" and record the final URL. Cross-check G.S.R. 388(E) in the Gazette of India (egazette.gov.in).
- **GODL-India text:** `https://www.data.gov.in/Godl`. Save it as a page or PDF.

**P0 total:** about 45 small files (~0.5 MB) plus 3–4 PDFs.

---

## 4. Domain coverage matrix

| Domain | National/State | Bengaluru city | Bengaluru ward | Time series | Best P0/P1 source | Gap |
|---|---|---|---|---|---|---|
| Road safety | ✅ MoRTH 2016–2024, 1970–2024 | ✅ MoRTH city tables 2019–24; BTP 2007–25 | ⚠️ police stations only (spatial overlay) | ✅ | MoRTH + BTP | Ward-level crashes |
| Transport | ✅ RTYB | ✅ BMTC perf to 2024-25 | ❌ | ✅ | BMTC (P1) | GTFS needs IUDX consent |
| Solid waste | ⚠️ CPCB portal (no export) | ✅ processing/disposal/cost 2015–19 | ✅ gen/coll/proc 2015–18; D2D, segregation, vehicles, bins 2019 | ⚠️ 3 years | Smart Cities BBMP SWM | **No ward data after 2019** |
| Water supply | — | ✅ coverage 2018–21 | ✅ BWSSB monthly 2025-04..2026-03; revenue 2013–18 | ✅ 12 months | BWSSB monthly | NRW, piped-water quality |
| Sewerage | — | ✅ STPs (capacity, inflow) | ⚠️ STP Ward No | ❌ | SC D88 / OpenCity STP | Sewer overflows |
| Drainage/flood | — | ✅ SWD network KML, flood points | ⚠️ spatial only | ❌ | OpenCity (BBMP/KSRSAC) | Desilting, waterlogging logs |
| Climate | — | ✅ IMD rainfall 1900–2025 | ❌ | ✅ | IMD (mirror) | Ward rainfall |
| Air/lakes | ✅ CPCB AQI (API unclear) | ✅ 14 CAAQMS stations hourly 2017–23; lake WQ 2020–21 | ⚠️ spatial | ✅ | KSPCB | — |
| Complaints | ⚠️ district (KA) | ✅ | ✅ ward names 2020–25 | ✅ | BBMP grievances (aggregated) | Closure times |
| Assets/geography | — | ✅ | ✅ 198 KML, 369 KML, public goods, toilets, streetlights | — | OpenCity/BBMP/GBA | Official licence |
| Demographics | ✅ Census | ✅ | ✅ Census 2011 by ward | ❌ (2011 only) | SC City Profile | Current population |
| Finance | — | ✅ BBMP budget 2023–26 XLSX | ⚠️ work orders by ward (derived) | ✅ | BBMP budget | Actuals by service |
| Policy/RAG | ✅ MoRTH, SWM Rules, SLB, MV Act | ✅ GBA notifications, CAG SWD audit, BBMP performance report | ⚠️ SWM micro-plans | — | — | Official URLs for 6 docs |

---

## 5. Source / licence / access verification matrix

| Source class | Examples | Access | Licence evidence | Verification level |
|---|---|---|---|---|
| data.gov.in (central) | MoRTH RA 2019–2024, BRS | Download form; no login seen | GODL-India / NDSAP (catalogue + https://www.data.gov.in/Godl) | Resource metadata via API; file sizes |
| karnataka.data.gov.in | BWSSB monthly, KSPCB lakes, BMTC | Same platform | Portal footer: "licensed under Government Open Data License - India" | Resource metadata; Aug-2025 fields confirmed on page |
| smartcities.data.gov.in | BBMP SWM, STP, water revenue, census profile | Same platform | GODL-India (OGD platform) | Resource metadata incl. field lists |
| OpenCity (CKAN) | BBMP wards, BTP, grievances, AQI, budget, KMLs | Open download | "Other (Public Domain)" or none; **original terms UNKNOWN** | Package/resource metadata; datastore column names (no rows) |
| IUDX | BTP events/blackspots (OPEN), others SECURE | API + registration/consent | IUDX policies (not read) | Catalogue entries + accessPolicy |
| CPCB SWMP | SWM Rules 2026, registration | Registration portal | — | Landing page read |
| BBMP SWM site | dashboard | — | UNKNOWN | **Not reachable by automation; check manually** |
| NWDP | CGWB, IMD, CWC data | Likely registration | UNKNOWN | Landing page only |

---

## 6. Municipal questions answerable from P0 (and what they exercise)

**Structured (deterministic):**
1. Which 10 Bengaluru wards had the highest BWSSB consumption in March 2026, and how did each change from April 2025? *(ML; per row; duplicate ward numbers disclosed)*
2. Which wards had the largest month-on-month change in connections in 2025–26?
3. What was average consumption per connection by BBMP zone in Aug 2025? *(ward→zone via ward reference)*
4. Which wards had the lowest door-to-door collection coverage (%) as of Jan 2019?
5. What was BBMP's waste collection efficiency (collected / generated) by zone, 2015-16 to 2017-18?
6. How much processing capacity (TPD) existed by technology in 2019, versus processed quantity?
7. How did Bengaluru's road accident and death totals change 2007–2025 (BTP)?
8. Among million-plus cities, where did Bengaluru rank for over-speeding accidents each year 2019–2024?
9. Which junction type caused the most accidents in Bengaluru in 2024, and how did that change since 2019?
10. Which states had the largest increase in accidents 2021→2024?
11. What were national accidents, deaths and injuries 1970–2024, and what are the deaths per 100 accidents by year?

**RAG:**
12. How does MoRTH define a black spot?
13. What are the four segregation streams under SWM Rules 2026, and who must register as a bulk waste generator?
14. What obligations do the SWM Rules 2026 place on urban local bodies?

**Graph / multi-hop:**
15. For ward X, show its zone, assembly constituency, water use (latest month), waste coverage (2019), STPs located in it, and 2011 population, each with its own date.
16. Which datasets mention Bengaluru, and at what geography and period?

**Must abstain or qualify (evaluation traps):**
- "Waste per capita in ward X in 2025" (no post-2019 waste data; 2011 population).
- "Did higher water use cause more accidents?" (no causal design; incompatible geography).
- "Water use for GBA ward 250" (data is on the 198 scheme; no official crosswalk).
- "Resolution time of complaints" (no closure date).
- "Forecast 2027 accidents" (only as a separately evaluated method, if approved).

---

## 7. Compatibility matrix

| Pair | Verdict | Condition |
|---|---|---|
| BWSSB month × BWSSB month | ✅ join on Ward number | Check the scheme each month; 4 duplicated ward numbers → aggregate per (ward no) only with disclosure |
| BWSSB × ward reference (198) | ✅ Ward No | Name alias table for spelling variants |
| SWM 2015–19 × ward reference | ✅ Ward No (segregation file: **name only** → alias) | Different snapshot dates; label each |
| SWM × Census 2011 households | ⚠️ allowed as *dated denominator* | Show "2011 denominator" caveat; no 2025 per-capita claims |
| BWSSB 2025 × SWM 2019 | ⚠️ side-by-side only | 6-year gap; never ratio or correlate as current |
| STP (Ward No) × ward reference | ⚠️ | Confirm the STP file uses the 198 scheme |
| Anything × GBA 369 wards | ❌ | No official areal crosswalk; the 198↔243 file is an AC co-listing, not a crosswalk |
| BTP station × ward | ❌ (key) / ⚠️ spatial overlay | Station polygons ≠ wards; only a documented areal method, flagged approximate |
| AQI station / flood point / STP coords × ward | ⚠️ point-in-polygon | Needs the 198 KML; record the method |
| MoRTH city (Bengaluru) × BTP city totals | ⚠️ compare, don't merge | Different collection systems/definitions |
| MoRTH editions across years | ⚠️ | Use the latest edition per year; state boundary changes (J&K/Ladakh 2019, DNH&DD 2020); city spelling aliases |
| Ward data × state/national data | ❌ | Different geography |
| Rainfall (city) × ward outcomes | ❌ for ward claims; ⚠️ city-level association only | No causation |

---

## 8. RAG corpus (initial)

| ID | Document | Status | Use |
|---|---|---|---|
| DOC-MORTH-RA2019 | MoRTH RA 2019 (`RA_Uploading.pdf`) | URL cited by OGD; not opened | definitions/method for 2019 tables |
| DOC-MORTH-RA2024 | MoRTH RA 2024 | official URL to confirm (mirror found) | latest definitions; city chapter |
| DOC-SWM-RULES-2026 | SWM Rules 2026, G.S.R. 388(E) | link on CPCB portal; capture final URL | ULB duties, segregation, BWG thresholds |
| DOC-SWM-RULES-2016 | SWM Rules 2016 (superseded) | to locate | rules in force for 2015–19 data |
| DOC-SLB-HANDBOOK | MoUD/MoHUA SLB Handbook | official URL to confirm | benchmark definitions (LPCD, D2D %, efficiency) |
| DOC-CPHEEO-MSW-2016 | CPHEEO MSW Manual 2016 | to locate | technical definitions |
| DOC-MV-ACT | MV Act 1988 (as amended) — India Code | to locate | offence wording (quote only) |
| DOC-CAG-SWD | CAG audit of Bengaluru SWDs | OpenCity catalogue | drainage findings |
| DOC-BBMP-PERF-2425 | BBMP Performance Report 2024-25, Budget Speech 2025-26 | resource verified (PDF sizes) | stated targets/achievements |
| DOC-GBA-NOTIF | GBA 5-corporation and 369-ward notifications | catalogue | which ward scheme applies when |
| DOC-GODL | GODL-India | verified page | attribution |

---

## 9. Preliminary Knowledge Graph (only from verified fields)

| Node | Key | Source fields |
|---|---|---|
| City | name | constant "Bengaluru"; MoRTH city label (alias) |
| Corporation (GBA) | name | GBA notification (P1) |
| Zone | BBMP Zone Name | ward reference |
| Ward (scheme=BBMP-198) | Ward No | ward reference, BWSSB, SWM, Census, public goods |
| AssemblyConstituency | AC name | ward reference |
| PoliceStation (BTP) | Station | BTP CSVs (+ jurisdiction KML) |
| STP | STPId / name | STP CSVs |
| WasteFacility | plant location | SWM processing/disposal (2019) |
| Dataset | catalogue id | manifests |
| Indicator | e.g. `water_consumption_ml` | manifests |
| ReportingPeriod | month/year/as-on date | file metadata |
| Document | DOC id + page | RAG corpus |

**Edges** (each carries `source_dataset`, `source_row`, `valid_period`):
- `Ward –IN_ZONE→ Zone`
- `Ward –IN_AC→ AssemblyConstituency`
- `Zone –PART_OF→ City`
- `STP –LOCATED_IN→ Ward` (from the STP Ward No field; spatial check optional)
- `WasteFacility –SERVES→ City`
- `Dataset –MEASURES→ Indicator`
- `Dataset –COVERS→ Ward/City/State`
- `Dataset –REPORTED_FOR→ ReportingPeriod`
- `Indicator –DEFINED_IN→ Document`
- `PoliceStation –IN_CITY→ City`

**Not modelled:** `Ward–PoliceStation` (no key), causal `AFFECTS` edges, or any 198↔369 ward equivalence.

---

## 10. Gap report (to request from agencies, not assume)

| Need | Why missing | Lawful route |
|---|---|---|
| Ward-level waste generation/collection after 2019, on GBA wards | Not published openly; CPCB portal is reporting-only | Data request to GBA/corporations SWM; RTI |
| BWSSB NRW, piped-water quality, sewer overflow incidents by ward | Not published | BWSSB data request/RTI |
| Complaint closure dates/SLA | Not in the OpenCity export | GBA (Sahaaya) aggregate request |
| Drain desilting/waterlogging logs | Not published | GBA SWD dept |
| Ward-level road crashes (geo-coded) | BTP publishes by station only | BTP request (aggregated, no PII) |
| Official crosswalk 198→369 wards | None published | GBA delimitation cell |
| Current ward population | Census 2011 is latest; 2025 delimitation populations exist in the KML/CSV (OpenCity) and need verification | GBA/Census |
| Licence terms for OpenCity-hosted originals | Not stated | Email OpenCity / original publisher |

---

## 11. Proposed new repository structure and setup plan

```
civic_mind-v2/                      (clone of github.com/fakelp0406-source/civic_mind-v2)
  README.md  .gitignore  pyproject.toml  .env.example
  data/
    external/verify_YYYY-MM-DD/     manual downloads land here (git-ignored except manifests)
    raw/                            promoted, hash-pinned, immutable copies (small official CSVs committed)
    quarantine/                     unverified files (git-ignored)
    manifests/*.yaml                one per dataset: URL, licence, retrieved, sha256, period, geography, ward_scheme, caveats
    aliases/                        ward/state/city alias tables with sources
  docs/  (architecture, provenance, limitations, discovery/ <- this report + CSV, audit/)
  src/civicmind/ catalog/ tools/ planner/ orchestrator/ respond/ api/
  eval/  tests/  web/ (later)
```

**Setup commands, for your approval (nothing has been run):**
```bash
git clone https://github.com/fakelp0406-source/civic_mind-v2.git C:/Desktop/civic-v2
```
```bash
python -m venv C:/Desktop/civic-v2/.venv
```
```bash
C:/Desktop/civic-v2/.venv/Scripts/python -m pip install pandas pydantic fastapi uvicorn pytest ruff httpx pyyaml
```
- Expected changes: a new working tree in the chosen folder; `.venv/` (git-ignored); then a skeleton commit made **locally only**.
- Legacy files ported later are cited as `legacy e3b194f:<path>` in commit messages and `docs/PORTING_NOTES.md`.
- **Large or sensitive data is never committed:** grievance CSVs, AQI hourly files, KMLs over 1 MB and PDFs are git-ignored and recorded in manifests by URL and hash.

---

## 12. Actions requiring your approval

1. **Local folder:** `C:\Desktop\civic-v2\` (recommended) or `C:\Desktop\civicmind-ai-main\civicmind\`.
2. **Clone** the new repo into that folder. This replaces `git init`, because the remote already has a commit.
3. **Create `.venv` and install** the packages listed above.
4. **P0 downloads** (§3). You do them manually, or you approve me fetching the exact URLs (no portal forms). Either way they go to `data/external/verify_…/`.
5. **Use of OpenCity-mirrored data** with UNKNOWN original licence (ward reference, ward KML, BTP, rainfall) — labelled `secondary`.
6. **Grievances (P1):** approve the aggregate-only policy (drop Staff Name/Remarks; raw stays local and git-ignored).
7. **First push** to `fakelp0406-source/civic_mind-v2`, after you review the local commit (GCM browser sign-in).
8. Whether to include **Shivamogga** as the second city, or stay Bengaluru-only for v1.
9. Whether to **request data** (gap report) from GBA/BWSSB/BTP. You would send any requests; I won't.
