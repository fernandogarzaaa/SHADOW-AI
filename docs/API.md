# API

See root PRD, ARCHITECTURE, and SECURITY for product-wide decisions.

## MVP Contract
This document formalizes the production seam implemented in code. Interfaces are real and test-covered where critical; provider-specific integrations remain adapter-backed.

## Shadow Node Endpoints
`GET /health`, `POST /pair/start`, `POST /pair/confirm`, `POST /memory/ingest`, `GET /memory/search`, `POST /agent/ask`, `GET /agent/self`, `POST /agent/plan`, `POST /agent/execute`, `GET /executions`, `GET /executions/{id}`, `GET /approvals`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/deny`, `GET /audit`, `POST /devices/register`, `GET /devices`, `WS /ws/tasks`.

Self-awareness: `GET /agent/self` returns SHADOW's runtime-derived self-model (identity, runtime, capabilities). `POST /agent/ask` answers "what are you", "where are you", and "what can you do" deterministically from the same live state (`model_used: "self_model"`) instead of sending them to the LLM.

Ambient GHOST capabilities: `GET /ambient/status`, `POST /ambient/config`, `POST /ambient/tick`, `GET /ambient/runs`, `GET /ambient/runs/{id}`, `POST /ghost/runs`, `POST /ghost/runs/{id}/resume`, `POST /ghost/runs/{id}/interrupt`, `GET /claims`, `POST /claims`, `POST /claims/{id}/confirm`, `POST /claims/{id}/refute`.

Approval binding: `POST /agent/execute` and every `POST /ghost/runs` step resolve their `approval_id` against the server-side approval store (must exist, be approved, be unexpired, and match the step's tool, params, and description). Approval is never manufactured: a ghost step without a valid referenced approval runs unapproved under the normal policy gate, and an unknown, denied, expired, or mismatched approval fails before that step executes. Steps may carry their own `approval_id`, falling back to the run-level one.

Cloud egress authorization: `POST /agent/ask` with `allow_cloud` first passes the coarse cloud gate (explicit approval plus an active cloud-capable consent grant), then authorizes every retrieved memory item individually for the provider and purpose. Items flagged `do_not_send_to_cloud` never leave the node, independent of the `sensitive` flag, grants, or approvals; revoked items and items whose consent grant is missing, revoked, or local-only are also held back. The frontier provider only receives the authorized cloud context (including on grounding retries). The response carries `cloud_manifest` (provider, purpose, per-item allow/deny with reasons, counts, policy decision) when cloud was requested, and every actual cloud egress is recorded in the Sentinel audit trail with that manifest.

See `VERIFICATION.md` for the evidence-based completion model behind `/agent/execute` and `/executions`. See `AMBIENT.md` for checkpointed runs, journals, claims, the ambient scheduler, and the Stealth Mode definition.

## Approval binding on `POST /agent/execute`

The client-supplied `approved` boolean is never trusted. To execute an
approval-requiring action, the request must carry an `approval_id`
referencing a server-side approval record that is `APPROVED`, unexpired,
and granted for the same action (matching `tool_name`, `params`, and
`description`). Unknown ids return 404; pending, denied, expired, or
mismatched approvals return 403. All rejections happen before any
execution takes place.
