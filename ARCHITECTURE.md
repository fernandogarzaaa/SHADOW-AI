# Shadow Agent Alpha Architecture

```text
iOS Shadow App -> Pairing v1 / HTTP / WS -> Shadow Node
Shadow Node -> Durable Stores | Agent Core | Memory Engine | AXIOM Adapter | Ghost Adapter | Connectors | Model Providers
```

## Alpha boundaries
- iOS remains the consent command center with pairing, node URL settings, memory, approvals, devices, audit, privacy, autonomy, and emergency pause screens.
- Shadow Node owns local API, durable runtime stores, pairing, task planning, approval state, audit, model-provider policy, and Ghost execution handoff.
- Memory Engine owns encrypted memory payloads and SQLite FTS5 retrieval.
- Agent Core owns risk classification, autonomy enforcement, approval decisions, cloud gating, and audit models.
- AXIOM packages retrieved personal context using redaction, compression, skeletons, fingerprints, and token estimates.
- GHOST receives approved AgentPlan-derived task IR and returns telemetry from a safe mock executor.

## End-to-end flow
Pair device, ingest approved memory, search/ask, package context, propose action, persist approval, user approves/denies, execute approved safe task, append audit events.

## Durable state
`DeviceStore`, `ApprovalStore`, `AuditStore`, `ConsentStore`, and `TaskStore` use SQLite with encrypted JSON payloads. The audit store is append-only at the repository layer.

## Security defaults
Emergency pause, blocked action classes, critical double confirmation, outbound approval, cloud consent, redaction, device revocation, and no-secret logging are enforced in the node flow.
