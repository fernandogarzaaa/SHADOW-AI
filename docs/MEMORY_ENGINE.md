# MEMORY ENGINE

The memory engine encrypts memory rows with Fernet, indexes approved text with SQLite FTS5, chunks input, deduplicates by source/content hash, and returns attribution, confidence, freshness, sensitivity, do-not-send-cloud, and retrieval explanations.

Phase 4 adds app-facing memory list/search contracts and iOS display of source previews, confidence, freshness, sensitive indicators, and untrusted-context explanations.
