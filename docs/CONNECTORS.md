# CONNECTORS

The beta connector path is user-approved local text ingestion. Backend file ingestion supports `.txt`, `.md`, `.markdown`, and `.json` via `POST /memory/ingest_file` with an active consent grant. iOS currently supports manual paste ingestion and documents the next security-scoped document picker path.

Shadow Agent must never scan files covertly. Every ingestion path requires user-selected content, a source name, and a consent explanation.
