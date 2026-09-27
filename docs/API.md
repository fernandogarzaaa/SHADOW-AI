# API

See root PRD, ARCHITECTURE, and SECURITY for product-wide decisions.

## MVP Contract
This document formalizes the production seam implemented in code. Interfaces are real and test-covered where critical; provider-specific integrations remain adapter-backed.

## Shadow Node Endpoints
`GET /health`, `POST /pair/start`, `POST /pair/confirm`, `POST /memory/ingest`, `GET /memory/search`, `POST /agent/ask`, `GET /agent/self`, `POST /agent/plan`, `POST /agent/execute`, `GET /executions`, `GET /executions/{id}`, `GET /approvals`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/deny`, `GET /audit`, `POST /devices/register`, `GET /devices`, `WS /ws/tasks`.

Self-awareness: `GET /agent/self` returns SHADOW's runtime-derived self-model (identity, runtime, capabilities). `POST /agent/ask` answers "what are you", "where are you", and "what can you do" deterministically from the same live state (`model_used: "self_model"`) instead of sending them to the LLM.

Ambient GHOST capabilities: `GET /ambient/status`, `POST /ambient/config`, `POST /ambient/tick`, `GET /ambient/runs`, `GET /ambient/runs/{id}`, `POST /ghost/runs`, `POST /ghost/runs/{id}/resume`, `POST /ghost/runs/{id}/interrupt`, `GET /claims`, `POST /claims`, `POST /claims/{id}/confirm`, `POST /claims/{id}/refute`.

See `VERIFICATION.md` for the evidence-based completion model behind `/agent/execute` and `/executions`. See `AMBIENT.md` for checkpointed runs, journals, claims, the ambient scheduler, and the Stealth Mode definition.

## Approval binding on `POST /agent/execute`

The client-supplied `approved` boolean is never trusted. To execute an
approval-requiring action, the request must carry an `approval_id`
referencing a server-side approval record that is `APPROVED`, unexpired,
and granted for the same action (matching `tool_name`, `params`, and
`description`). Unknown ids return 404; pending, denied, expired, or
mismatched approvals return 403. All rejections happen before any
execution takes place.
