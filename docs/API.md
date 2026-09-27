# API

See root PRD, ARCHITECTURE, and SECURITY for product-wide decisions.

## MVP Contract
This document formalizes the production seam implemented in code. Interfaces are real and test-covered where critical; provider-specific integrations remain adapter-backed.

## Shadow Node Endpoints
`GET /health`, `POST /pair/start`, `POST /pair/approve`, `POST /pair/confirm`, `POST /memory/ingest`, `GET /memory/search`, `POST /agent/ask`, `GET /agent/self`, `POST /agent/plan`, `POST /agent/execute`, `GET /executions`, `GET /executions/{id}`, `GET /approvals`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/deny`, `GET /audit`, `POST /devices/register`, `GET /devices`, `WS /ws/tasks`.

Self-awareness: `GET /agent/self` returns SHADOW's runtime-derived self-model (identity, runtime, capabilities). `POST /agent/ask` answers "what are you", "where are you", and "what can you do" deterministically from the same live state (`model_used: "self_model"`) instead of sending them to the LLM.

Persona (Cookie-style assistant identity): `GET /persona` returns the assistant's editable identity (name, avatar_emoji, vibe, status). `PUT /persona` updates it (all fields optional; name 1-32 chars, vibe up to 500 chars, status up to 120 chars); changes are audited as `persona_updated`, persisted encrypted in the runtime DB when configured, and take effect immediately: the vibe becomes the frontier-model system prompt, and `/agent/self` plus self-questions answer with the persona name.

Memory cards (dated entries + search): `GET /memory/recent?limit=&offset=` returns memory items newest-first, paginated (limit clamped to 1-200, default 20), with `count`, `total`, `limit`, `offset`; sensitive items are excluded unless `include_sensitive=true`. `DELETE /memory/{item_id}` revokes one item (soft delete; audited as `memory_item_deleted`; 404 if unknown or already revoked). `GET /memory/search` runs semantic search over the blind HMAC FTS index (sensitive excluded by default).

Goals with progress and briefings: `POST /goals` creates a goal (title 1-120 chars, optional description, optional `target_date` YYYY-MM-DD). `GET /goals?status=` lists goals newest-updated first, each with a progress roll-up (`entry_count`, `latest_percent`, `last_progress_at`). `GET /goals/{goal_id}` returns the goal with progress entries newest-first. `PATCH /goals/{goal_id}` updates title/description/status (`active`/`completed`/`abandoned`)/target_date (`""` clears it). `DELETE /goals/{goal_id}` removes the goal and its entries (audited as `goal_deleted`; 404 if unknown). `POST /goals/{goal_id}/progress` logs a progress entry (note + optional 0-100 percent; audited as `goal_progress`; also bumps the goal's `updated_at`). `GET /goals/briefing` returns stale goals (no progress in 7+ days), goals due within 7 days, overdue goals, goals completed this week, and the 10 most recent progress entries. Goal mutations are audited (`goal_created`, `goal_updated`, `goal_deleted`, `goal_progress`) and persisted encrypted in the runtime DB when configured.

Feed and Ideas: `POST /feed/generate` renders editorial feed units from live node state (morning brief, goals briefing, memory digest) into the append-only feed journal; `kinds` selects which to render (empty = all), `force` bypasses the ~20h per-kind dedupe. `GET /feed?limit=&offset=` lists units newest-first, paginated (limit clamped to 1-200, default 20) with `count`, `total`, `limit`, `offset`. The built-in ambient task `feed_digest` runs the same generation on the scheduler interval, so the digest is produced without manual triggers. Idea cards: `POST /ideas` creates one (title 1-140 chars, optional description). `GET /ideas?status=` lists newest-updated first. `PATCH /ideas/{idea_id}` updates title/description/status (`new`/`running`/`done`/`dismissed`). `DELETE /ideas/{idea_id}` removes it (404 if unknown). `POST /ideas/{idea_id}/run` turns an idea into a real agent plan via `AgentCore.propose`, marks it `running`, and stores the plan summary on the card; risky actions raise approval requests and execute only through the approval-gated `/agent/execute` path, nothing runs inside the endpoint. All feed and idea mutations are Sentinel-audited and persisted encrypted in the runtime DB when configured. Generation is fully offline: prose is rendered from structured data with templates, never by a cloud model.

Reminders and quiet hours: `POST /reminders` creates a reminder (title 1-140 chars, optional note, `due_at` unix timestamp, `recurrence` one of none/daily/weekly). `GET /reminders?status=` lists soonest-due first; `GET /reminders/due` shows pending reminders whose due time has passed. `PATCH /reminders/{reminder_id}` updates title/note/due_at/recurrence/status (pending/fired/dismissed); `DELETE /reminders/{reminder_id}` removes it. `POST /reminders/check` fires due reminders now: each firing marks the reminder (recurring ones advance to their next occurrence, skipping catch-up bursts), sends a proactive Expo push, emits an SSE `reminder.fired` event, and records a `reminder` feed unit. The built-in ambient task `reminder_check` runs the same firing on the scheduler interval. Quiet hours: `POST /ambient/config` accepts `quiet_start`/`quiet_end` as HH:MM in node-local time (empty clears, bad format is a 400); while quiet, `reminder_check` and `POST /reminders/check` fire nothing and report held reminders, which fire on the first check after quiet hours end. All reminder mutations and firings are Sentinel-audited and persisted encrypted in the runtime DB when configured.

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

## List endpoints and device revocation

Every list endpoint (`GET /approvals`, `GET /devices`) returns a uniform
page object `{"items": [...], "count": n, "next_cursor": null}`, never a
bare array. `GET /approvals` accepts `?status=` to filter by
`pending`, `approved`, `denied`, `expired`, or `consumed`.
`POST /approvals/sweep` returns `{"expired": [...], "remaining_pending": n}`.

Device revocation is `POST /devices/{id}/revoke`. A device may always
revoke itself; revoking another device requires an owner device (the
first-ever bootstrap-paired device is the owner; nodes enrolled before
the owner flag existed grandfather existing trusted devices until an
owner exists). Unknown device ids return 404.
