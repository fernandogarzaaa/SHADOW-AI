# Ambient GHOST Capabilities

The node can do background work on its own schedule: journaled, checkpointed
multi-step agent runs; world-state claims that later observations confirm or
refute; and an opt-in background scheduler for periodic tasks like the
morning brief. This document defines each primitive, the Stealth Mode
contract, and how to operate them.

Design rule: everything ambient is user-controlled and inspectable. Ambient
is OFF by default. Nothing runs in the background until the operator enables
it explicitly.

## 1. Checkpointed runs (real, not a stub)

`GhostRunSession` (in `packages/agent-core/agent_core/ambient.py`) executes a
multi-step plan step by step. Each step runs through `AgentCore.execute`, so
every step gets the policy gate, evidence capture, and a deterministic
verification verdict like any other execution.

After every step the session saves a checkpoint: the run id, the objective,
the full step list, per-step results, and the index of the next step to run.
Checkpoints persist in the encrypted runtime DB (`ambient_checkpoints`
collection), so they survive process restarts.

Resume: a fresh session loads the checkpoint and continues at the saved
index. Finished steps are never re-executed. A run that is interrupted, by
process death, operator stop, or an unexpected error, can be resumed with:

- `POST /ghost/runs/{run_id}/resume`
- or `session.resume(run_id)` in Python

Honest scope: checkpoints cover step-granular tool runs through the local
action executor. A step that was mid-flight when the process died is retried
from its start on resume; completed steps are skipped. There is no
transactional rollback of partial world-state changes. Each step's own
verification verdict tells you what actually happened.

## 2. Run journals

Every run appends to an append-only journal (`ambient_journals` collection).
Entry types: `run_started`, `attempt`, `observation`, `decision`, `note`,
`checkpoint`, `interrupted`, `completed`, `claim`. Step observations link to
their execution record ids, tying the journal into the verification layer's
evidence.

Inspect:

- `GET /ambient/runs/{run_id}` returns the checkpoint, the full journal, the
  run's claims, and linked execution summaries.
- `python -m shadow_node.cli journal show <run_id>`

## 3. Claims about world state

Agents register claims ("the notes index is readable", "service Z is up").
A claim starts `unconfirmed`. Later observations confirm or refute it, each
carrying evidence text. Decided claims are final; this keeps the record
honest instead of letting verdicts flip with the wind.

Claims can be registered explicitly (`POST /claims`) or declared on a run
step (`{"tool": ..., "claim": "..."}`). A step-level claim is decided
automatically by the step's verification verdict: `verified` confirms it,
`failed`/`conflicting` refutes it, with the verdict reason as evidence.

Inspect and decide:

- `GET /claims?status=unconfirmed|confirmed|refuted`
- `POST /claims/{id}/confirm` and `/refute` with `{"evidence": "..."}`
- `python -m shadow_node.cli claims list|confirm|refute`

## 4. Ambient scheduler

`AmbientScheduler` runs periodic background tasks. Configuration:

- `GET /ambient/status`, `POST /ambient/config`
- `python -m shadow_node.cli ambient on|off|status`

Fields: `enabled` (default false), `interval_seconds` (minimum 60),
`stealth_mode` (default false), `tasks` (default `["morning_brief"]`).

Built-in tasks (see `apps/shadow-node/shadow_node/ambient_tasks.py`):

- `morning_brief`: pending approvals, 24h execution verdict counts,
  unconfirmed claims, paired device count.
- `memory_digest`: memory inventory by category and type, items expiring
  within 7 days. Ingest already dedupes by content hash, so this reports
  rather than merges.

Contract for built-in tasks: read-only observers. They never change world
state beyond their own journal entries and checkpoints. They write no files,
make no network requests, and touch no credentials. Each tick is journaled
and checkpointed (`kind: "ambient"`) and appears in `GET /ambient/runs`.

SSE events (suppressed in stealth mode): `ambient.tick`,
`ambient.task.completed`, `ambient.config.changed`. The mobile app can
subscribe to these on `/agent/stream` to show ambient activity.

## 5. Stealth Mode: exact definition

Stealth Mode is a scheduler setting (`stealth_mode: true`), not a separate
system. When enabled:

What it captures:

- Scheduled task runs, exactly as in normal mode.
- Journal entries for every attempt, observation, and decision.
- Checkpoint records for every tick.
- Audit log lines (`ambient.tick`, `ambient.config.changed`).

What it never captures:

- The node has no microphone, camera, location, or keystroke inputs at all,
  so there is nothing ambient that could capture them. Stealth Mode does not
  add hidden inputs; it only changes surfacing.
- No network egress: built-in tasks make no HTTP requests.
- No credentials: tasks never see vault contents.

What changes: no `ambient.*` SSE events are emitted and no push
notifications are sent for ambient activity. The work still happens and is
still recorded; it is simply not announced.

How to verify:

1. `python -m shadow_node.cli ambient status` shows `stealth_mode: True`.
2. Subscribe to `/agent/stream`: during a tick you see no `ambient.*`
   events (you will still see a user-initiated `ambient.config.changed`).
3. `python -m shadow_node.cli journal show <run_id>` shows the tick's
   entries; the audit chain shows the tick. The work happened; it was not
   announced.

## 6. Security notes

- Every run step passes the Sentinel-lite policy engine. Blocked tools stay
  blocked even in approved runs; destructive tools still need double
  confirmation. Ambient tasks themselves are read-only and need no policy
  bypass.
- Journal, checkpoint, claim, and config records live in the encrypted
  runtime DB when `SHADOW_RUNTIME_DB` is set, plaintext-in-memory otherwise.
- The scheduler thread is a daemon; it can never take the node down. A
  failing task is journaled and the tick continues.
- Enabling ambient is an explicit operator action and is itself audit-logged.

## 7. Always-on loop ("o"-pattern, local-first)

`AmbientLoop` (`packages/agent-core/agent_core/always_on.py`) is the node's
always-on background loop. One daemon thread drives `AmbientScheduler.tick()`
with an explicit lifecycle:

- Steady states: `SLEEPING` (idle: the thread blocks on an event, no
  busy-wait) and `AWAKE` (processing wake events and running the tick).
  Transients `STARTING`, `STOPPING`, `STOPPED` make every transition
  observable in the journal and as `ambient.loop.state` events.
- Idle resource behavior: while `SLEEPING` the thread waits with a timeout
  of `min(idle_poll_seconds, seconds_until_next_tick)`. An enabled node with
  an hourly tick wakes at most once an hour plus on real events; a disabled
  node sleeps the full idle poll and does no work.
- Clean shutdown: `stop()` signals, joins the thread, persists a loop
  record (`ambient_loop` collection), and journals it. The ASGI lifespan in
  `main.py` calls `stop()` on server shutdown. A restart that finds a loop
  record not marked clean journals "previous loop did not shut down
  cleanly".

Wake sources (all local, no cloud services):

- `PushWakeTrigger`: the companion app calls `POST /ambient/wake` with
  source `push` when the user taps a notification.
- `MessageWakeTrigger`: the ask pipeline (`/agent/ask`, `/agent/ask_stream`)
  delivers a wake on every inbound message; `POST /ambient/wake` with source
  `message` covers other local message bridges.
- `CalendarWakeTrigger`: polls the node's own reminder store; a pending
  reminder entering its 5-minute lead window wakes the loop once per
  (reminder, due_at).

Opt-in rule preserved: the loop does no work until ambient is enabled.
Wake events received while disabled are journaled as held and the loop
stays `SLEEPING`.

## 8. Durable sessions and automatic compaction

`SessionStore` keeps conversation sessions in the runtime store
(`agent_sessions` collection, encrypted when `SHADOW_RUNTIME_DB` is set),
so they survive process restarts. `rehydrate()` runs on boot: open sessions
whose last message is from the user (the assistant never answered) are
flagged `response_interrupted` in metadata instead of silently resuming.

`SessionCompactor` compacts automatically on append past the token budget
(default 8000 estimated tokens, estimates are `len//4`): messages older
than the recent window fold into one deterministic system summary (message
count, time span, opening user intent, extracted key facts); the recent
window is kept verbatim. The folded summary is ingested into the
user-owned memory engine (source kind `session`), so memory stays the
source of truth and sessions stay the working set.

HTTP surface:

- `POST /agent/sessions`, `GET /agent/sessions`,
  `GET /agent/sessions/{id}`, `POST /agent/sessions/{id}/close`
- `POST /agent/ask` accepts an optional `session_id` and appends the turn
  (user + assistant) to that session; the response echoes `session_id`.
- `POST /ambient/wake` with `{"source": "push"|"message"|"calendar"|"operator",
  "reason": ..., "payload": {...}}`
- `GET /ambient/status` now also reports `loop` state, wake count, and open
  session count.
