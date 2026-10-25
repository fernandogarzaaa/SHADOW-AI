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

## Artifacts, voice, and media

Artifacts are versioned documents the assistant builds for the user
(markdown, html, code, csv, json, text). Fully offline, encrypted at rest,
500 artifacts and 50 versions each retained.

- `POST /artifacts` `{title, kind, content, tags?}` -> 201 artifact
- `GET /artifacts?limit&offset&kind` -> meta-only list (no content)
- `GET /artifacts/{id}` -> full artifact with content
- `PATCH /artifacts/{id}` `{title?, kind?, content?}` -> new version
- `GET /artifacts/{id}/versions` and `GET /artifacts/{id}/versions/{v}`
- `DELETE /artifacts/{id}` -> 204

The agent has `artifact_create`, `artifact_update`, and `artifact_read`
tools; tool results carry an `artifact:<id>` reference the mobile app
renders as a tappable card.

Voice is dual-path: the mobile app speaks and records on-device with no
server needed; the node also proxies to BYOK audio endpoints when
configured (`SHADOW_TTS_ENDPOINT` / `SHADOW_STT_ENDPOINT` plus
`SHADOW_TTS_API_KEY_ENV` / `SHADOW_STT_API_KEY_ENV`, OpenAI-compatible).

- `GET /voice/capabilities` -> `{tts: {available, provider, note}, stt: {...}}`
- `POST /voice/speak` `{text, voice?, format?}` -> audio bytes; 503 when unconfigured
- `POST /voice/transcribe` -> `{text, language?}`; 503 when unconfigured.
  Two shapes: multipart with an `audio` file field, or JSON
  `{audio_base64, filename?, mime_type?}` (recommended: binary-safe, signs
  as ordinary JSON text). Multipart bodies may contain non-UTF-8 bytes, so
  the HMAC canonical body for `multipart/form-data` is
  `"sha256:<hex of raw body bytes>"` rather than the body text.

Media generation is BYOK (`SHADOW_IMAGE_ENDPOINT`,
`SHADOW_IMAGE_API_KEY_ENV`, OpenAI-compatible `/images/generations`).
Generated PNGs are stored encrypted, 200 images retained.

- `GET /media/capabilities`
- `POST /media/generate` `{prompt, size?}` -> 201 `{id, prompt, size, mime, bytes}`
- `GET /media` -> meta list; `GET /media/{id}/content` -> image bytes
- `DELETE /media/{id}` -> 204

Unconfigured provider endpoints return 503 with the exact environment
variables to set; provider failures return 502. Nothing pretends to work.

<!-- BEGIN GENERATED ENDPOINTS (scripts/gen_api_docs.py) -->

## Endpoint reference

Generated from the route table. "signed" routes need the `x-shadow-*` request-signature headers (see AUTHENTICATED_TRANSPORT.md).

### accounts

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/accounts/{service_id}/connect` | signed |  |
| `POST` | `/accounts/{service_id}/disconnect` | signed |  |
| `GET` | `/accounts/{service_id}` | signed |  |
| `GET` | `/accounts` | signed |  |

### agent

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/agent/ask_stream` | signed | Run the ask pipeline, then stream the answer as agent.message.delta chunks followed by agent.message.done. |
| `POST` | `/agent/ask` | signed |  |
| `POST` | `/agent/execute` | signed |  |
| `POST` | `/agent/plan` | signed |  |
| `GET` | `/agent/self` | signed | Runtime-derived self-description: what SHADOW is, where it runs, and what it can do. |
| `POST` | `/agent/sessions/{session_id}/close` | signed | Close a session. |
| `POST` | `/agent/sessions/{session_id}/handoff` | signed | Start an explicit handoff of a conversation to another device. |
| `GET` | `/agent/sessions/{session_id}` | signed | Session detail with full message history. |
| `GET` | `/agent/sessions` | signed | List sessions, most recently active first. |
| `POST` | `/agent/sessions` | signed | Create a durable conversation session. |
| `GET` | `/agent/stream` | signed | Long-lived SSE bus: node.hello on connect, then approval.created / approval.updated as they happen. |

### ambient

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/ambient/acts/run` | signed | Manually run one Shadow Act through the same policy gate the ambient tick uses. |
| `GET` | `/ambient/acts` | signed | List the registered Shadow Acts with their current policy evaluation. |
| `POST` | `/ambient/config` | signed | Enable/disable ambient work, set interval and stealth mode, choose tasks, set quiet hours (HH:MM). |
| `POST` | `/ambient/plans/{plan_id}/cancel` | signed | Cancel a paced plan. |
| `GET` | `/ambient/plans/{plan_id}` | signed | Inspect one paced plan: steps, scheduled times, delivery status. |
| `GET` | `/ambient/plans` | signed | List stored paced plans: multi-step proactive deliveries created by shadow acts. |
| `GET` | `/ambient/runs/{run_id}` | signed | Run detail: checkpoint, full journal, linked claims, linked executions. |
| `GET` | `/ambient/runs` | signed | Checkpointed runs (ghost agent runs and ambient ticks), newest first. |
| `GET` | `/ambient/status` | signed | Ambient scheduler state. |
| `POST` | `/ambient/tick` | signed | Run one ambient iteration now (operator-initiated, not scheduled). |
| `POST` | `/ambient/wake` | signed | Wake the always-on loop from a local source. |

### approvals

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/approvals/receipt` | signed | Idempotency receipt lookup (OpenDots' restorePageReview analog): returns the approval card for a (thread_id, tool_call_id) pair so a client that lost the sus... |
| `POST` | `/approvals/sweep` | signed | Expire pending approvals past their expiry threshold. |
| `POST` | `/approvals/{id}/approve` | signed |  |
| `POST` | `/approvals/{id}/deny` | signed |  |
| `GET` | `/approvals` | signed | Uniform page envelope. |
| `POST` | `/approvals` | signed |  |

### artifacts

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/artifacts/{artifact_id}/versions/{version}` | signed |  |
| `GET` | `/artifacts/{artifact_id}/versions` | signed |  |
| `DELETE` | `/artifacts/{artifact_id}` | signed |  |
| `GET` | `/artifacts/{artifact_id}` | signed |  |
| `PATCH` | `/artifacts/{artifact_id}` | signed |  |
| `GET` | `/artifacts` | signed |  |
| `POST` | `/artifacts` | signed |  |

### audit

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/audit` | signed | Audit trail, oldest first, as the uniform page envelope. |

### claims

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/claims/{claim_id}/confirm` | signed |  |
| `POST` | `/claims/{claim_id}/refute` | signed |  |
| `GET` | `/claims` | signed | World-state claims. |
| `POST` | `/claims` | signed |  |

### consent

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/consent` | signed |  |

### continuity

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/continuity/handoffs/{handoff_id}/cancel` | signed | Cancel a pending handoff. |
| `POST` | `/continuity/handoffs/{handoff_id}/claim` | signed | Claim a pending handoff and receive the full resume package: the frozen conversation snapshot plus live pending approvals and active plans. |
| `GET` | `/continuity/handoffs` | signed | Pending handoffs visible to the caller: open ones, ones targeted at this device, and ones this device created. |
| `GET` | `/continuity/overview` | signed | One screen's worth of continuity state: registered devices with presence, open sessions with last-active device, pending handoff count. |
| `POST` | `/continuity/presence` | signed | Heartbeat: tell the node this client is active. |

### custom-panels

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/custom-panels/parse` | signed | Parse "make a panel showing my top 5 overdue goals" into a panel proposal, or return a clarifying question. |
| `GET` | `/custom-panels/{panel_id}/render` | signed | Render a custom panel as panel JSON (same shape as built-in panels). |
| `DELETE` | `/custom-panels/{panel_id}` | signed | Delete a custom panel. |
| `GET` | `/custom-panels/{panel_id}` | signed |  |
| `PATCH` | `/custom-panels/{panel_id}` | signed |  |
| `GET` | `/custom-panels` | signed | List custom panel definitions (inspectable: the definition is the panel). |
| `POST` | `/custom-panels` | signed | Create a custom panel from a definition (or a confirmed parse proposal). |

### devices

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/devices/register` | signed | Owner-initiated enrollment. |
| `POST` | `/devices/{device_id}/push-token` | signed |  |
| `POST` | `/devices/{device_id}/renew` | signed | Start a fresh 30-day session window. |
| `POST` | `/devices/{device_id}/revoke` | signed | Revoke a device. |
| `GET` | `/devices` | signed |  |

### emergency_pause

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/emergency_pause` | signed |  |
| `POST` | `/emergency_pause` | signed | Kill-switch capability: any HMAC-authenticated trusted device may pause/resume the node. |

### executions

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/executions/{execution_id}` | signed | Full execution detail: intent, policy decision, tool observation, evidence, world-state diff, verdict. |
| `GET` | `/executions` | signed | Execution records, newest first. |

### feed

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/feed/generate` | signed | Render editorial feed units from live node state (offline, no cloud model). |
| `GET` | `/feed` | signed | Feed units newest-first, paginated. |

### ghost

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/ghost/runs/{run_id}/interrupt` | signed | Stop a run mid-flight. |
| `POST` | `/ghost/runs/{run_id}/resume` | signed | Resume an interrupted run from its checkpoint. |
| `POST` | `/ghost/runs` | signed | Start a checkpointed multi-step run. |

### goals

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/goals/briefing` | signed | Goal briefing: stale goals, goals due soon/overdue, completed this week, and recent progress entries. |
| `POST` | `/goals/{goal_id}/progress` | signed | Log a progress entry (note + optional 0-100 percent) on a goal. |
| `DELETE` | `/goals/{goal_id}` | signed |  |
| `GET` | `/goals/{goal_id}` | signed |  |
| `PATCH` | `/goals/{goal_id}` | signed | Update title/description/status/target_date. |
| `GET` | `/goals` | signed | List goals newest-updated first, each with a progress roll-up. |
| `POST` | `/goals` | signed | Create a user goal: a durable outcome with progress tracking. |

### health

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/health` | public |  |

### ideas

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/ideas/{idea_id}/run` | signed | Turn an idea into a real agent plan via AgentCore.propose. |
| `DELETE` | `/ideas/{idea_id}` | signed |  |
| `GET` | `/ideas/{idea_id}` | signed |  |
| `PATCH` | `/ideas/{idea_id}` | signed |  |
| `GET` | `/ideas` | signed | List idea cards newest-updated first. |
| `POST` | `/ideas` | signed | Create an idea card. |

### media

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/media/capabilities` | signed |  |
| `POST` | `/media/generate` | signed |  |
| `GET` | `/media/{item_id}/content` | signed |  |
| `DELETE` | `/media/{item_id}` | signed |  |
| `GET` | `/media` | signed |  |

### memory

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/memory/export` | signed |  |
| `POST` | `/memory/ingest_file` | signed |  |
| `POST` | `/memory/ingest` | signed |  |
| `GET` | `/memory/recent` | signed | Newest-first memory cards for the mobile Memory screen. |
| `GET` | `/memory/search` | signed |  |
| `DELETE` | `/memory/source/{source_id}` | signed |  |
| `DELETE` | `/memory/{item_id}` | signed | Revoke one memory item (soft delete; the ciphertext stays but is excluded from search, export, and recent). |
| `GET` | `/memory` | signed |  |

### model

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/model/providers` | signed |  |

### pair

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/pair/approve` | signed | Owner-approved challenge: only a trusted, non-revoked device (HMAC authenticated by the middleware) can approve a pending pairing. |
| `POST` | `/pair/confirm` | public | The new device collects its credentials. |
| `GET` | `/pair/pending` | signed | Pending (not yet approved) pairings, for an owner to review and approve. |
| `POST` | `/pair/start` | public | New device proposes enrollment. |

### panels

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/panels` | signed | Glanceable data panels for the client's PanelCard: pending approvals, goals progress, and memory inventory as panel JSON (title, headline, stat tiles, rows). |

### persona

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/persona` | signed | The assistant's Cookie-style identity: name, avatar emoji, vibe, status. |
| `PUT` | `/persona` | signed | Update the assistant's identity. |

### providers

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/providers/{name}/connect` | signed |  |
| `POST` | `/providers/{name}/oauth/exchange` | signed |  |
| `GET` | `/providers/{name}/oauth/start` | signed |  |
| `DELETE` | `/providers/{name}` | signed |  |
| `GET` | `/providers` | signed |  |

### ready

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/ready` | public |  |

### reminders

| Method | Path | Auth | Summary |
|---|---|---|---|
| `POST` | `/reminders/check` | signed | Fire due reminders now: push + SSE event + feed unit per reminder. |
| `GET` | `/reminders/due` | signed | Pending reminders whose due time has passed (includes ones held by quiet hours). |
| `POST` | `/reminders/parse` | signed | Parse a natural-language scheduling request ("remind me every weekday at 7am") into a structured reminder proposal, or a clarifying question. |
| `DELETE` | `/reminders/{reminder_id}` | signed |  |
| `GET` | `/reminders/{reminder_id}` | signed |  |
| `PATCH` | `/reminders/{reminder_id}` | signed |  |
| `GET` | `/reminders` | signed | List reminders, soonest-due first. |
| `POST` | `/reminders` | signed | Create a reminder. |

### scheduled-tasks

| Method | Path | Auth | Summary |
|---|---|---|---|
| `DELETE` | `/scheduled-tasks/{task_id}` | signed |  |
| `GET` | `/scheduled-tasks/{task_id}` | signed |  |
| `PATCH` | `/scheduled-tasks/{task_id}` | signed |  |
| `GET` | `/scheduled-tasks` | signed | Every scheduled thing in one shape: reminders plus builtin ambient tasks, soonest next run first. |
| `POST` | `/scheduled-tasks` | signed | Create a reminder through the unified surface. |

### tools

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/tools` | signed |  |

### voice

| Method | Path | Auth | Summary |
|---|---|---|---|
| `GET` | `/voice/capabilities` | signed |  |
| `POST` | `/voice/speak` | signed |  |
| `POST` | `/voice/transcribe` | signed |  |

### ws

| Method | Path | Auth | Summary |
|---|---|---|---|
| `WS` | `/ws/tasks` | signed | Signed WebSocket (HMAC headers on the handshake). |

<!-- END GENERATED ENDPOINTS -->
