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
2. **Integrity** — size (against `stated_bytes` when given), SHA-256, `%PDF-` header, PDF
   version, page count, encryption. Errors: `integrity.size_mismatch`, `pdf.not_pdf`,
   `pdf.unreadable`, `pdf.encrypted` (a password is required). Encryption with an empty user
   password (permissions only) is `pdf.permissions_restricted` (info).
3. **Extraction** — pypdf, page by page, with 1-based page numbers; only line endings are
   normalised. Pages with fewer than 20 non-space characters are `pages_without_text` (warning
   `extraction.no_text_pages`; never indexed or cited). No page with text → error
   `extraction.empty`. No OCR. Output: `data/processed/rag/extracted/<id>/<sha12>.jsonl`
   (git-ignored, deterministic, hash recorded).
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
       accepted_caveats: [source.secondary_mirror]
       excluded_pages: [1, 2]       # never indexed or cited
       add_limitations: []
       note: <why>
   ```

   Fails closed, leaving `human_review: pending` with a finding: other bytes (`review.stale`);
   approving a document that is not `validated` (`review.not_applicable`); a warning neither
   accepted nor confined to excluded pages (`review.incomplete`); excluded pages that do not
   exist or that remove every page with text (`review.invalid_pages`). Approval resolves
   sensitivity to `public` only when every personal-data match was accepted or excluded.
7. **Promotion gate** (`catalog.doc_promote`) — all must hold: `validated`; an `approve` review
   bound to the same SHA-256; integrity passed; page text extracted; no error findings; not a
   duplicate; licence known; `sensitivity: public` and no personal data; a relative source path
   without `..`, under `data/external/…/docs/<domain>/` with the domain in `domains`; a plain `.pdf` file name; size
   and SHA-256 re-checked just before copying. The copy goes through a `.partial` file, is
   hash-verified, and is never written over a different file. Result: `status: approved`,
   `promoted_to: data/docs/<domain>/<file>`.
8. **Quarantine, withdrawal and stale copies** — `quarantine` moves the received file to
   `data/quarantine/<batch>/docs/`. `data/docs/` holds only approved documents: whenever a
   document of the batch is not approved after the run (quarantined, rejected, withdrawn, or its
   bytes changed so its review is stale), an existing promoted copy is moved to
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

## 6. Residual risks (security review, 2026-10-18)

The document catalogue is a local, single-operator tool: whoever can write to `data/external/`,
`data/docs/` or the intake and decision files can already change what is reviewed. Within that
threat model these limits remain and are accepted for stage 1:

- **Time-of-check / time-of-use.** Paths are validated (lexically, then after resolving links)
  immediately before each read, copy, move or write, but a process that swaps a directory for a
  link *between* the check and the operation is not prevented. What such a swap could still do:
  - *Source read* (build or promotion): read a file outside the intake folders. Promotion
    re-hashes the source and the `.partial` copy against the reviewed SHA-256, so only bytes
    identical to the reviewed ones can ever be copied into `data/docs/`.
  - *Promotion copy*: write the `.partial` file and the final copy into the directory the link
    points to, outside `data/docs/`.
  - *Extraction output*: write the page file outside `data/processed/rag/extracted/`.
  - *Orphan sweep or quarantine move*: `os.rename` a file from the linked location into
    `data/quarantine/` (a move, never a delete or an overwrite).

  Hardening, if the tool ever runs alongside untrusted local users: open the file or directory
  first and verify the opened handle's final path (`GetFinalPathNameByHandle` on Windows,
  `O_NOFOLLOW`/`openat` per path component on POSIX) before reading, writing or renaming.
- **Hash and extraction read the file separately.** A file replaced between the two reads would
  be extracted and screened from bytes other than the hashed ones. A reviewer approves the
  recorded SHA-256, and promotion copies only bytes with that hash, but the screening findings
  and page text the reviewer relied on could then describe different bytes. Smallest mitigation
  (proposed for stage 2, before any document is indexed): read the file once into memory, then
  hash, inspect and parse those same bytes (pypdf accepts a byte stream).
- **Filesystem errors abort the run.** An unreadable file raises (for example
  `PermissionError`) before any manifest or summary is written; extraction outputs already
  written for earlier documents in the same batch stay in the git-ignored
  `data/processed/rag/extracted/`.
- **Screening is pattern-based** and evidence for a reviewer, not a guarantee; matched personal
  values are never recorded.
- **Link tests** use symlinks where the OS allows them and Windows directory junctions
  otherwise; on a platform with neither, those tests skip with a reason.
