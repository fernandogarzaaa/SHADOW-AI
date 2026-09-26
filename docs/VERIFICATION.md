# Verification: evidence-based completion

The node never equates tool execution with success. Every call through
`POST /agent/execute` (and therefore `AgentCore.execute`) produces an
**execution record**: intent, plan, policy decision, tool observation,
before/after world-state snapshots, attached evidence, and one final
deterministic verdict.

## The verdict

Exactly one of:

| Status | Meaning |
|---|---|
| `verified` | Evidence confirms the intended world-state change happened. |
| `failed` | The action clearly did not achieve its intent. |
| `uncertain` | The outcome cannot be determined from the available evidence. |
| `conflicting` | The observed state contradicts the intended change. |

There is no `success` status. A tool reporting `ok: true` is an observation,
not proof.

## How the verdict is decided

The verifier (`agent_core.verification.verify_execution`) is a pure,
deterministic function. No LLM acts as judge. The rules, in order:

1. Policy blocked the action -> `failed`.
2. The tool raised an exception -> `failed`.
3. The tool returned no result, or reported `ok: false` -> `failed`.
4. The tool has no registered handler (mock run) -> `uncertain`: there is
   no observable world-state effect to check.
5. Read-only tools (`note.list`, `http.get`) -> `verified` when the
   observation has the expected shape, else `uncertain`.
6. State-changing tools (`note.create`, `note.append`, `reminder.create`,
   `calendar.create`, `email.draft`):
   - world state unchanged despite the tool claiming success -> `failed`
     (this is the deliberate false-success case: a lying tool is caught).
   - the observed diff matches the stated intent (checked by reading the
     actual files back, never by trusting the tool's report) -> `verified`.
   - the observed diff contradicts the intent -> `conflicting`.
7. Any other registered tool -> `uncertain`: intent could not be checked.

## World-state tracking

Before and after each execution the node snapshots the workspace directory
(`SHADOW_WORKSPACE_DIR`): file paths with SHA-256 and size. The diff lists
added, modified, and removed files and is stored on the record as evidence.
Snapshots are read-only and bounded (5000 files max).

## Approval cards carry the verdict

Pass `approval_id` when executing an approved action:

    POST /agent/execute  {"action": {...}, "approved": true, "approval_id": "apr_..."}

After the run, the approval card gains `execution_id` and
`verification_status`, and an `approval.updated` event goes out over the SSE
stream (`GET /agent/stream`) so the mobile Approvals tab updates live.

## API

- `GET /executions?status=verified&limit=50` - execution summaries, newest first.
- `GET /executions/{id}` - full detail: intent, action, policy decision,
  tool observation, evidence items, world-state diff, verdict and reason.

## CLI

With `SHADOW_RUNTIME_DB` set (persistent node), inspect history directly:

    PYTHONPATH=apps/shadow-node python -m shadow_node.cli executions list --status failed
    PYTHONPATH=apps/shadow-node python -m shadow_node.cli executions show exec_<id>

Without `SHADOW_RUNTIME_DB` the node keeps executions in memory only and the
CLI explains that instead of failing silently.

## Persistence

Execution records live in the encrypted runtime DB (`SHADOW_RUNTIME_DB`) under
the `executions` collection, alongside approvals, audit events, and devices.
They are loaded back into memory on node start.

## Scope notes

- The `ghost_handoff` tool path (`GhostAdapter.execute`) has its own execution
  semantics and is not yet wrapped in execution records; that is follow-up work.
- Intent checks cover the node's sandboxed local tools. New tools need a rule
  in `agent_core.verification` (an intent check plus read-only/mutating
  classification) before their executions can be `verified`.
