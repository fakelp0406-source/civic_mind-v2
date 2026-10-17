# Dataset discovery (2026-10-17)

Byte-identical copies of the discovery deliverables, verified by SHA-256 at copy time:

| File | Bytes | SHA-256 | Original location |
|---|---|---|---|
| `DATASET_DISCOVERY_REPORT.md` | 24,978 | `5a21516c06a31d3ac601c1ef323b7a90c716e3dda68306bcefbee7aae3c24d3a` | `C:\Desktop\civicmind-ai-main\discovery_2026-10-17\` |
| `civicmind_dataset_catalog.csv` | 72,090 | `f5fc7f96de010e47d927f05db3348e9ef07039b00ece6f7f60121a0480200d0a` | same |

**How to read the catalogue.** It lists *candidate sources*. Use the `status` column to tell
how far each was checked:

- `VERIFIED_RESOURCE`: the resource's file name and size (and, where available, its field
  list or column names) were read from the portal. **Not downloaded, not validated.**
- `VERIFIED_CATALOG`: the catalogue or dataset page exists; individual files were not inspected.
- `DOC_LINK_UNVERIFIED`: the official document was identified; its exact official URL is still
  to be confirmed.
- `REGISTRATION`: login, consent or an API key is required.
- `NOT_VERIFIED` / `NOT_FOUND`: not checkable, or no open source exists.

No row is a "verified dataset" in the sense used by `docs/provenance.md`. That status
requires download, hash pinning, validation and a manifest.

The report's section 0 still names the folder question and the clone-vs-init decision, as
they stood when it was written. Both have since been settled: `C:\Desktop\civic-v2`, cloned.
