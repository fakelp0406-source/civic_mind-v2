"""Document retrieval (RAG) over approved official documents.

Implemented (Milestone 05 stage 1): PDF inspection and page-text extraction (``extract``),
screening of extracted text (``screen``) and document manifest building (``doc_intake``); the
review and promotion gate are in ``catalog``.

Responsibilities (not yet implemented):
- Extract page text from documents registered in manifests, keeping document id, page and
  section; chunk; index; retrieve passages with citations.
- Baseline: lexical BM25 (SQLite FTS5, standard library) with metadata filters.
  Embeddings or a vector store only if a labelled retrieval evaluation shows the baseline fails.
- Retrieved text is untrusted data, never instructions.

Boundary: depends on ``catalog`` and ``evidence``. Not used for numeric answers.
"""
