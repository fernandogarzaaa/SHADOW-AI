# MEMORY ENGINE

The memory engine encrypts memory rows with Fernet, indexes approved text with SQLite FTS5, chunks input, deduplicates by source/content hash, and returns attribution, confidence, freshness, sensitivity, do-not-send-cloud, and retrieval explanations.

The FTS keyword index never stores plaintext: it holds HMAC blind-index
tokens derived from a domain-separated index key, so the database file
reveals only token equality and counts, never the underlying terms.
Databases written by the old plaintext-index format are rebuilt from the
encrypted blobs on open (tracked by `meta.fts_version`).

Phase 4 adds app-facing memory list/search contracts and iOS display of source previews, confidence, freshness, sensitive indicators, and untrusted-context explanations.
