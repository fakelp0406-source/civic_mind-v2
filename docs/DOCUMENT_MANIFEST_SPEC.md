# Document manifest specification and approval workflow

Status: **in use** (2026-10-18, Milestone 05 stage 1). Implemented by
`civicmind.catalog.documents`, `civicmind.catalog.doc_review`, `civicmind.catalog.doc_promote`,
`civicmind.rag.extract`, `civicmind.rag.screen`, `civicmind.rag.doc_intake` and
`scripts/process_doc_batch.py`. No document has been acquired yet; batch `docs-01` holds four
`planned` entries. Retrieval, indexing and answering are **not** implemented (stages 2–3 of
[docs/design/M05_RAG_DESIGN.md](design/M05_RAG_DESIGN.md)).

A document manifest (`data/doc_manifests/<document_id>.yaml`) is the single record of where an
official document came from, which exact bytes were received, how its text was extracted, what
screening found, and the person review that decides whether it may become a retrieval source.
Only an **approved** document may ever be indexed or cited.

Document manifests are kept apart from dataset manifests (`data/manifests/`), which the dataset
catalogue reads as datasets.

## 1. Allowed documents

| `document_type` | Examples |
|---|---|
| `statistical_report` | MoRTH *Road Accidents in India* |
| `act`, `rules`, `notification` | Motor Vehicles Act; gazette notifications |
| `tariff_order` | water tariff orders |
| `handbook_manual` | MoHUA Service Level Benchmarks handbook, CPHEEO manuals |
| `audit_report` | CAG performance audits |
| `methodology_note` | publisher methodology or definitions notes |

Issued by a government body or statutory authority. `source_class` is `official` (the issuing
authority's own site) or `secondary_mirror` (for example data.opencity.in). A mirror adds the
warning `source.secondary_mirror`, which a reviewer must accept, and is used only when no
official copy was found. Not allowed: news, blogs, social media, unofficial summaries,
AI-generated text. `domains` is `water` and/or `roads` in this milestone.

## 2. Fields

| Group | Fields | Who fills it |
|---|---|---|
| Identity | `document_id` (`DOC-…`), `manifest_version`, `title`, `issuing_authority`, `publisher`, `document_type`, `language`, `domains` | person (intake) |
| Source | `source_class`, `resource_page`, `download_url` | person |
| Validity | `publication_date`, `effective_from`, `effective_to`, `edition`, `version_label` | person, as printed on the document |
| Licence | `licence.name`, `url`, `evidence`, `attribution`, `exemptions_checked` | person; `UNKNOWN` blocks approval |
| Retrieval | `retrieved_at`, `retrieved_by`, `method`, `original_filename`, `local_path` | person |
| Integrity | `bytes`, `stated_bytes`, `size_matches_stated`, `sha256`, `pdf_header`, `pdf_version`, `pages`, `encrypted`, `producer`, `passed` | processor |
| Extraction | `extractor`, `extractor_version`, `pages`, `pages_with_text`, `pages_without_text`, `characters`, `output_path`, `output_sha256` | processor |
| Relations | `relates_to_datasets` (documentation only, never a join), `supersedes` (person), `superseded_by` (derived), `same_bytes_as` (derived) | mixed |
| Sensitivity | `sensitivity`, `contains_personal_data` (restricted / true until screened) | processor, then review |
| Findings | `findings[]`: `code`, `severity` (`error`/`warning`/`info`), `message`, `details` | processor |
| Review | `human_review`, `review` (decision, reviewer, date, SHA-256, `accepted_caveats`, `excluded_pages`, note) | person, via the decisions file |
| Lifecycle | `status`, `promoted_to`, `known_limitations` | processor |

## 3. Lifecycle

`planned` (no file) → `received` (file present; integrity failed) → `integrity_passed` (cannot
be read as a PDF) → `extracted` (text extracted but an error finding exists) → `validated`
(ready for review) → `approved` (promoted). Off-path: `quarantined`, `rejected`, `withdrawn`.

Supersession is a relation, not a status: a superseded document stays approved so a question
that names its edition can still cite it; later stages use `superseded_by` to prefer the
current edition by default.

## 4. Processing (`python scripts/process_doc_batch.py <batch>`)

1. **Intake** — `docs/acquisition/<batch>/DOCUMENT_INTAKE.yaml`. A person downloads the PDF by
   hand to `data/external/verify_<batch>/docs/<water|roads>/<original file name>` and records the
   metadata. Tools never download documents or complete portal forms. The intake is refused when
   a `document_id` does not match `DOC-[A-Z0-9][A-Z0-9-]*` (ids are used in output paths), when
   `local_path` is absolute, uses backslashes, contains `..` or is not under `data/external/`,
   when `original_filename` is not a plain file name, and when a `document_id` is already
   recorded in another batch's intake file (checked in both directions, so one batch can never
   overwrite another's manifest). These checks are lexical; in addition every path is checked
   **after resolving symlinks and junctions**: a source must resolve inside `data/external/` (or
   `data/quarantine/` for a quarantined copy), otherwise it is not read (`path.outside_intake`,
   error); extraction output must stay inside `data/processed/rag/extracted/`; promotion refuses
   a source outside `data/external/` or a target outside `data/docs/`; the orphan sweep never
   moves a file through a link. An entry without a file is
   `planned`, with `retrieval.method: not yet retrieved`.
2. **Integrity** (stage 2: one verified read) — the file is read **once** through a handle
   verified to be inside `data/external/` or `data/quarantine/` (`catalog.safe_fs`), bounded by
   `PreparationLimits.max_bytes`. Size, SHA-256, `%PDF-` header, PDF version, page count,
   encryption and the extracted text are all computed from that single byte sequence, so the
   recorded hash always describes exactly the bytes whose text was extracted and screened.
   Errors: `document.too_large` (not read beyond the limit), `integrity.size_mismatch`,
   `pdf.not_pdf`, `pdf.unreadable`, `pdf.encrypted` (a password is required),
   `pdf.too_many_pages`, `path.outside_intake`. Encryption with an empty user password
   (permissions only) is `pdf.permissions_restricted` (info).
3. **Extraction** — pypdf, page by page, with 1-based page numbers; only line endings are
   normalised. Pages with fewer than 20 non-space characters are `pages_without_text` (warning
   `extraction.no_text_pages`; never indexed or cited). No page with text → error
   `extraction.empty`. No OCR. More than `max_text_chars` characters is
   `extraction.too_large`; more than `extract_seconds` (checked between pages) is
   `extraction.timeout`; any failure leaves **no** extraction, never a partial one. Output:
   `data/processed/rag/extracted/<id>/<sha16>-docprep-v2-pypdf-<version>.jsonl` (git-ignored,
   deterministic). Each record carries the source SHA-256, the extractor version and the
   preparation version (`docprep@v2`), so the file's own SHA-256
   (`extraction.output_sha256`) identifies the exact text a reviewer reads. The file is created
   through a verified handle and never overwritten: an existing page file with other bytes is an
   error (evidence of tampering), not something to replace.
4. **Screening** (pages with text; evidence for the reviewer, nothing is edited):
   `content.instruction_like` (text addressed to an AI system), `content.personal_data_suspected`
   (e-mail, mobile number, Aadhaar-like groups; **values never recorded**), `content.non_english`
   (mostly Devanagari, Kannada or Tamil). `content.screen` (info) records the method.
5. **Linking** — identical bytes under a second id get `same_bytes_as` (never promoted twice);
   `superseded_by` is derived from other manifests' `supersedes`; an unknown `supersedes` id is
   `document.unknown_reference`.
6. **Review** — `docs/acquisition/<batch>/DOCUMENT_REVIEW_DECISIONS.yaml`:

   ```yaml
   reviewed_by: <person>
   reviewed_on: 'YYYY-MM-DD'
   decisions:
     DOC-MORTH-RA2024:
       decision: approve            # approve | quarantine | reject | withdraw
       sha256: <the SHA-256 reviewed>
       extraction_sha256: <the page file reviewed>   # required for approve (stage 2)
       accepted_caveats: [source.secondary_mirror]
       excluded_pages: [1, 2]       # never indexed or cited
       add_limitations: []
       note: <why>
   ```

   Fails closed, leaving `human_review: pending` with a finding: other bytes (`review.stale`);
   approving a document that is not `validated` (`review.not_applicable`); a warning neither
   accepted nor confined to excluded pages (`review.incomplete`); excluded pages that do not
   exist or that remove every page with text (`review.invalid_pages`); an approval without
   `extraction_sha256` (`review.extraction_unbound`) or for a different page file, for example
   after an extractor or preparation-version change (`review.stale_extraction`). Approval resolves
   sensitivity to `public` only when every personal-data match was accepted or excluded.
7. **Promotion gate** (`catalog.doc_promote`) — all must hold: `validated`; an `approve` review
   bound to the same SHA-256 **and** to the current page file (`extraction_sha256`); integrity
   passed; page text extracted; no error findings; not a duplicate; licence known;
   `sensitivity: public` and no personal data; a relative source path without `..`, under
   `data/external/…/docs/<domain>/` with the domain in `domains`; a plain `.pdf` file name.
   Just before copying, the source and the page file are re-read through verified handles and
   re-hashed. The copy is created through a verified handle inside `data/docs/` and never
   replaces a different file. Result: `status: approved`,
   `promoted_to: data/docs/<domain>/<file>`.
8. **Quarantine, withdrawal and stale copies** — `quarantine` moves the received file to
   `data/quarantine/<batch>/docs/`. `data/docs/` holds only approved documents: whenever a
   document of the batch is not approved after the run (quarantined, rejected, withdrawn, or its
   bytes or text changed so its review is stale), an existing promoted copy is moved to
   `data/quarantine/<batch>/docs/promoted/`, unless another batch's approved manifest claims that
   path. A withdrawn manifest is kept as a tombstone. Files are moved, never deleted or
   overwritten; a name collision in the quarantine folder stops the run for a person to resolve.

Re-running the processor on the same inputs produces byte-identical manifests and summary.

## 5. Corrections and re-indexing

A corrected or new edition gets a new `document_id` (or a bumped `manifest_version` when the
same publication is re-issued) and its own review; the older one records the relation through
`supersedes`. Any change to a document's bytes makes its review stale. Index building (stage 2)
will rebuild from approved manifests only and refuse to serve when the index no longer matches
them.

## 6. Limits (`catalog.doc_limits.PreparationLimits`)

| Limit | Default | Environment variable | Exceeded |
|---|---|---|---|
| file size | 50 MiB | `CIVICMIND_DOC_MAX_BYTES` | `document.too_large` |
| pages | 2,000 | `CIVICMIND_DOC_MAX_PAGES` | `pdf.too_many_pages` |
| extracted characters | 20,000,000 | `CIVICMIND_DOC_MAX_TEXT_CHARS` | `extraction.too_large` |
| extraction time (s) | 300 | `CIVICMIND_DOC_EXTRACT_SECONDS` | `extraction.timeout` |
| documents per batch | 50 | `CIVICMIND_DOC_MAX_BATCH` | the run stops before writing |

A value that is not a positive integer stops the run (`ValueError`); there is no silent default.
The time limit is cooperative (checked between pages), not a hard kill.

## 7. Residual risks (stage 2 security review, 2026-10-18)

The document catalogue is a local, single-operator tool: whoever can write to `data/external/`,
`data/docs/` or the intake and decision files can already change what is reviewed. Within that
threat model:

**Closed in stage 2**

- *Hash and extraction from different bytes*: one verified read; hash, inspection and text come
  from the same byte sequence.
- *Reads through a swapped link*: every read opens the file first and checks the handle's final
  path (`GetFinalPathNameByHandleW`, `/proc/self/fd`, `F_GETPATH`); a handle outside the
  permitted folder is refused even if the pre-check passed. `O_NOFOLLOW` is used where defined.
- *Writes through a swapped link*: new files (page files, promoted copies) are created with
  `O_EXCL`, the created handle is verified, and a file created outside the folder is removed and
  the operation refused. Nothing is overwritten.
- *Stale approvals*: approval binds the source SHA-256 and the page-file SHA-256; both are
  re-checked from disk at promotion.

**Remaining**

- *Moves are detected, not prevented*: a rename by path cannot be bound to a handle with the
  standard library. `move_verified` hashes the verified source first and re-reads the
  destination through a verified handle afterwards; a swap during the rename raises
  `UnsafePath`, but the rename itself has already happened. On POSIX, `rename` can replace a
  destination that appears between the existence check and the rename.
- *Directories*: `mkdir` for a new file's parent folders is pre-checked but not handle-verified;
  a swap there could leave empty directories outside the folder (no file is ever written there).
- *Unsupported platforms*: where a handle's final path cannot be determined, every verified
  operation refuses (fail closed) rather than falling back.
- *Dataset promotion* (`catalog.promote`) is unchanged and still uses the stage 1 path-based
  copy.
- *Filesystem errors abort the run*: an unreadable file raises before any manifest or summary
  is written.
- *Screening is pattern-based* and evidence for a reviewer, not a guarantee.
- *Link tests* use symlinks where allowed and Windows junctions otherwise; on a platform with
  neither, they skip with a reason.
