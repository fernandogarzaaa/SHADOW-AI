# API

See root PRD, ARCHITECTURE, and SECURITY for product-wide decisions.

## MVP Contract
This document formalizes the production seam implemented in code. Interfaces are real and test-covered where critical; provider-specific integrations remain adapter-backed.

## Shadow Node Endpoints
`GET /health`, `POST /pair/start`, `POST /pair/confirm`, `POST /memory/ingest`, `GET /memory/search`, `POST /agent/ask`, `POST /agent/plan`, `POST /agent/execute`, `GET /executions`, `GET /executions/{id}`, `GET /approvals`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/deny`, `GET /audit`, `POST /devices/register`, `GET /devices`, `WS /ws/tasks`.

Ambient GHOST capabilities: `GET /ambient/status`, `POST /ambient/config`, `POST /ambient/tick`, `GET /ambient/runs`, `GET /ambient/runs/{id}`, `POST /ghost/runs`, `POST /ghost/runs/{id}/resume`, `POST /ghost/runs/{id}/interrupt`, `GET /claims`, `POST /claims`, `POST /claims/{id}/confirm`, `POST /claims/{id}/refute`.

See `VERIFICATION.md` for the evidence-based completion model behind `/agent/execute` and `/executions`. See `AMBIENT.md` for checkpointed runs, journals, claims, the ambient scheduler, and the Stealth Mode definition.
