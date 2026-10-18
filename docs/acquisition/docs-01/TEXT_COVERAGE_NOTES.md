# Text coverage and metadata notes, batch docs-01 (review aid, 2026-10-18)

Companion to `REVIEW_PACKAGE.md`. Findings come from a read-only inspection of each PDF's page
objects (fonts, image XObjects, text-showing operators, content-stream size), run on the exact
bytes recorded in the manifests (SHA-256 checked first). Nothing here is a decision; no document
is approved, promoted, indexed or embedded.

## Why pages yield no text

| Document | Pages | With text | Blank | Raster images (OCR needed) | Short text only (section dividers) | Text drawn as outlines (no text layer) |
|---|---|---|---|---|---|---|
| DOC-MORTH-RA2024 | 266 | 127 | 21 (3, 5, 7, 9, 11, 13, 15, 27, 33, 53, 87, 101, 103, 115, 117, 135, 137, 143, 145, 151, 157) | 6 (4, 6, 8, 10, 12, 14) | 10 (32, 52, 72, 86, 102, 116, 136, 144, 150, 156) | **102 (164-265)** |
| DOC-MORTH-RA2023 | 272 | 256 | 0 | 6 (3-8) | 10 (24, 43, 72, 87, 98, 116, 122, 127, 131, 138) | 0 |
| DOC-MORTH-RA2019 | 213 | 210 | 0 | 2 (1, 213: covers) | 1 (94) | 0 |

How each category was identified:

- **Blank**: content stream of 34 bytes, no fonts, no images.
- **Raster images**: no fonts and no text operators; one or two images of roughly 0.7 to
  0.8 megapixels fill the page. In RA2024 and RA2023 these are the front-matter pages
  (messages and forewords) before the List of Contents.
- **Section dividers**: one font with a ToUnicode map, and extraction is **correct**
  ("Section - 1" … "Section - 10"). They fall under the 20-character threshold. They are not
  extraction failures and carry no content beyond the section number.
- **Outlines (RA2024 pages 164-265)**: no font resources and no text operators, but very large
  content streams (median 1.4 MB, up to 3.4 MB). Page 200, for example, has 49,342 curve and
  14,560 line operators: the glyphs are drawn as vector paths. By the List of Annexures
  (PDF pages 24-26), these pages are **Annexures 1-49 and the Appendix formats** (printed page
  113 onwards). pypdf cannot recover them; only rendering the pages and running OCR could.

No page in any of the three documents shows an *extraction failure*, meaning fonts and text
operators present but no text recovered.

## Is OCR necessary?

**Not for the narrative content.** In RA2024, Sections 1-10 (PDF pages 27-163) have text. That
covers the Executive Summary, the million-plus cities chapter (Section 6) and the data-collection
methodology note (Section 10, pages 158-163). Definitions, methodology and findings questions
draw on these pages.

**Yes, if the RA2024 annexure tables or front-matter messages must be retrievable.** What is
missing, and what that means:

- *Annexure tables (RA2024 pages 164-265)*: statistical tables. Their numbers belong to the
  deterministic pipeline, where the published CSVs exist (for example Annexure 47 as
  `ROAD-RA2024-A47`). OCR of dense tables produces digit errors, so OCR'd numbers must never be
  quoted as document evidence without a separate review.
- *Front-matter messages (6 pages each in RA2024 and RA2023)*: forewords. Low value for
  municipal questions.

Recommendation: no OCR in this milestone. Record the gap so it is never mistaken for
irrelevance:

1. Exclude nothing silently. The pages stay listed in `extraction.no_text_pages` and cannot be
   cited.
2. When a question concerns an RA2024 annexure (for example "Annexure 35"), retrieval must
   abstain with a coverage reason, or the question must be routed to the deterministic pipeline.
   It must not fall back to a different edition.
3. RA2023's annexures *are* text, so a 2024 question must not be answered from the 2023 tables
   (cross-edition rule).

## Remaining screening hits (contexts checked; values not recorded in files)

| Document | Pages | What matched |
|---|---|---|
| RA2024 | 122, 123, 125, 126, 140 | Aadhaar-like 4+4+4 digit runs that are table cells and chart axes (city counts such as "4178 4720 5652 …", axis ticks "0 2000 4000 …") |
| RA2023 | 79, 81, 82, 89, 103-107, 119 | Same: age-profile counts, state table rows, chart axes |
| RA2019 | 4-7 | E-mail addresses at `nic.in` in the MoRTH and TRW contact blocks (official contacts, not private individuals) |

All of these look like false positives. Accepting `content.personal_data_suspected` as a caveat
is a reviewer decision.

## Missing or inconsistent metadata

1. **Publication date unknown** for all three (not on the extracted covers). The OpenCity dates
   (RA2024 created 2026-06-18; RA2023 and RA2019 created 2025-11-25) are upload dates, not
   publication dates.
2. **Licence evidence is the mirror's** (OpenCity "Other (Public Domain)"); no MoRTH reuse notice
   was read. `licence.exemptions_checked` is `false`.
3. **RA2024 is a re-processed copy**: the PDF producer is `iLovePDF`. RA2023 and RA2019 report
   `Corel PDF Engine`. The mirror's RA2024 bytes are therefore probably not MoRTH's original
   file, and the outlined annexures may be a side effect of that processing. An official copy
   might have a text layer. The official `morth.nic.in` links returned an HTML page, not a PDF.
4. **`retrieved_by` is a tool session**, not a person, although the field is defined for a
   person. The approval in chat is recorded in the intake comments.
5. **`stated_bytes` comes from the OpenCity resource size**, not from the publisher.
6. **Hindi text in a legacy (non-Unicode) font** extracts as Latin-looking characters (for
   example RA2019 pages 2-3). The non-English screen does not detect it because the extracted
   characters are Latin. Such passages would be noise in retrieval.
7. **File names for RA2023 and RA2019 are mirror UUIDs**, not descriptive names (recorded
   verbatim as `original_filename`).
8. **Titles match the covers** ("ROAD ACCIDENTS IN INDIA 2024", "… 2023", "… 2019"); editions
   match. No inconsistency was found there.
