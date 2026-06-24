# Architecture

```text
iOS Shadow App -> encrypted API/WebSocket -> Shadow Node
Shadow Node -> Agent Core | Memory Engine | Consent Ledger | Policy Engine | AXIOM Adapter | Ghost Adapter | Connector Registry | Audit Log
```

## Boundaries
The iOS app is the consent command center. Shadow Node is the heavier local runtime. Memory Engine owns encrypted storage and retrieval. Agent Core owns planning, policy, approvals, and audit. AXIOM routes compressed/redacted context. GHOST executes policy-gated desktop/device tasks.

## Data Flow
User-approved content enters via manual import or future Share Extension/connectors, is chunked, scored, encrypted, indexed, and attributed. Queries retrieve local memory, pass through AXIOM redaction/compression when needed, then Agent Core proposes answers/actions.

## Approval Flow
Every action is risk classified. Medium/high/critical/destructive/external-write/cloud actions require approval. Blocked classes never execute. Audit records initiation, data used, permission checked, decision, and result.

## Device Pairing
Node creates one-time pairing code, iOS submits device public key, node registers trusted device. Production hardening will replace MVP code exchange with authenticated ECDH and key pinning.
