# Sentinel-lite: unified policy, credential vault, audit log

The SHADOW node runs one independent policy authority. Every agent action,
every device-auth decision, and every secret use flows through it. The design
follows the Personal Agent OS spec (Sentinel, credential system) adapted to
our self-hosted reality: one node, one owner, no hosted per-user VMs.

Three components, all deterministic and explainable. No LLM acts as judge.

## 1. Unified policy engine

`agent_core.policy.PolicyEngine` is the single policy path. It receives the
action, the user profile, and the approval state, and returns exactly one of:

| Outcome | Meaning |
|---|---|
| `allow` | The action may execute. |
| `deny` | The action must not execute. |
| `require_approval` | The action may execute only after the user approves it (the spec's ASK). |

Every decision carries a `rule_id` and a human-readable `reason`, and is
written to the audit chain as a `policy.decision` event.

### Rules are data, not code

The rule sets live in `apps/shadow-node/shadow_node/policy.yaml`
(override with `SHADOW_POLICY_FILE`):

- `blocked_tools` / `blocked_description_patterns`: always denied
  (keyloggers, covert monitoring, sandbox bypasses, secret leaks).
- `destructive_tools`: denied unless double-confirmed at execution time.
- `sensitive_tools`: always require explicit user approval
  (outbound messages, file writes, device control, cloud escalation...).
- `approval_required_risks`: risk classes that need approval.

Evaluation order is fixed: emergency pause -> blocked -> destructive without
double confirmation -> per-tool tier -> approval required -> allow. The same
inputs always produce the same decision.

### Per-tool approval tiers

`tool_tiers` (default `{}`) lets the operator set Always Ask / Auto Approve /
Always Allow per tool, so routine reads run silent while writes still pause:

```yaml
tool_tiers:
  web_search: auto_approve
  memory.recall: always_allow
  send_email: always_ask
```

Safety properties, all enforced in `decide()` and covered by tests:

- Tiers are evaluated **after** the hard gates, so a tier can never
  override emergency pause, a blocked tool, or destructive double
  confirmation.
- `auto_approve` waives approval only for low/medium-risk, non-sensitive,
  non-destructive uses. A tiered `send_email` (high risk, sensitive) still
  requires approval.
- `always_allow` is standing pre-approval for routine **low-risk,
  non-sensitive, non-destructive** uses only (e.g. `memory.recall`).
  Medium/high-risk, sensitive, or destructive uses of a tiered tool fall
  through to the normal approval path. Tiering a sensitive tool
  `always_allow` (e.g. `send_email`) is a hard startup error, not a silent
  waiver.
- An unknown tier name is a hard startup error, not a silent default.
- Every tier decision is written to the audit chain with its own
  `rule_id` (`tool_tier_always_ask`, `tool_tier_auto_approve`,
  `tool_tier_always_allow`), so tier usage is explainable.
- With no tiers configured, behavior is byte-for-byte identical to before.

The engine falls back to built-in defaults only when no policy file is
configured. An explicitly configured file that is missing or invalid is a
hard startup error: silently running on defaults would hide operator mistakes.

### What the agent cannot do

Per the spec, the agent has no path to modify policy, disable the engine,
grant itself permissions, read vault contents, or bypass the decision path.
Policy changes require operator access to the node host and a node restart.
`AgentCore.execute` cannot run an action without a policy decision; the
decision is attached to the execution record as evidence (see
docs/VERIFICATION.md).

## 2. Credential vault and surrogate credentials

`agent_core.vault.CredentialVault` owns every secret the node holds:
provider keys, webhook secrets, connector tokens.

- Secrets are encrypted at rest in the runtime DB (Fernet, collection
  `vault_credentials`) or in process memory when no DB is configured.
- Tools and workers never see raw secrets. They receive short-lived
  surrogate tokens (`shv_...`, default TTL 5 minutes, optional scopes).
- At the execution boundary (`AgentCore.execute`), surrogates in the action
  params are resolved just-in-time into a copy of the params. The stored
  execution record keeps the surrogates; only the live tool call sees values.
- Every resolution, denial (unknown/expired/revoked/scope-mismatch), mint,
  rotation, and revocation is recorded in the audit chain. The value itself
  never appears in payloads.
- Stored tool results and returned API responses are scrubbed: surrogate
  tokens and known secret values are replaced with `[redacted]`.
- Rotating or revoking a credential revokes its outstanding surrogates.

Real secrets never go into prompts, model context, logs, tool results,
evidence, or audit payloads.

### Operator usage

    PYTHONPATH=apps/shadow-node python -m shadow_node.cli vault list
    PYTHONPATH=apps/shadow-node python -m shadow_node.cli vault store NAME [--scopes a,b]
    PYTHONPATH=apps/shadow-node python -m shadow_node.cli vault rotate NAME
    PYTHONPATH=apps/shadow-node python -m shadow_node.cli vault revoke NAME
    PYTHONPATH=apps/shadow-node python -m shadow_node.cli vault surrogate NAME [--ttl 300]

`vault list` prints names and scopes only. Values are read with a secure
prompt and are never printed.

## 3. Append-only audit log

`agent_core.audit.AuditChain` is a hash-chained, append-only log. Each entry
covers the previous entry's hash plus its own canonical content, so edits,
deletions, and reordering are detectable.

Recorded event types include:

- `policy.decision`: every allow/deny/require-approval with rule id and reason
- `approval.created` / `approval.decided` / `approval.expired`
- `credential.resolved` / `credential.resolve_denied` / `surrogate.minted` /
  `surrogate.revoked` / `credential.stored` / `credential.rotated` /
  `credential.revoked`
- `execution.verdict`: the final VERIFIED/FAILED/UNCERTAIN/CONFLICTING verdict
- `auth.decision`: device-auth denials (per-request successes are not logged;
  they would flood the chain)

Entries persist in the encrypted runtime DB (collection `audit_chain`) when
`SHADOW_RUNTIME_DB` is set, and in memory otherwise.

### Inspect and verify

    PYTHONPATH=apps/shadow-node python -m shadow_node.cli audit list [--limit 20]
    PYTHONPATH=apps/shadow-node python -m shadow_node.cli audit verify

`audit verify` recomputes every link and reports tampering with the entry id
and the specific break (content mismatch, broken predecessor link, sequence
gap). It exits non-zero when the chain is broken.

## Policy inspection

    PYTHONPATH=apps/shadow-node python -m shadow_node.cli policy show

Prints the effective policy: source file, blocked/destructive/sensitive tool
sets, and approval-required risk classes. No secrets.
