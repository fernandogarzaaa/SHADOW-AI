# CONNECTORS

Shadow Agent beta keeps local-first defaults and requires explicit consent for sensitive data access, cloud escalation, and execution.

## Local File Connector
`POST /memory/ingest_file` supports `.txt`, `.md`, `.markdown`, and `.json`. It requires an active consent grant, stores source attribution, supports source-level deletion through `DELETE /memory/source/{source_id}`, and supports re-ingestion through duplicate detection/content hashes.
