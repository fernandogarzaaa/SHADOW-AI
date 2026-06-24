# Phase 2 Repository Audit

## Existing foundation
- FastAPI `apps/shadow-node` exposes health, pairing, memory, agent, approvals, devices, audit, and WebSocket routes.
- `packages/memory-engine` provides encrypted SQLite rows with FTS5 search, chunking, confidence, and revocation.
- `packages/agent-core` defines typed models, policy engine, planner, approvals, audit events, and tool registry.
- `packages/axiom-adapter` implements deterministic redaction/compression/fingerprinting seams.
- `packages/ghost-adapter` contains an approval-gated task IR seam.
- `apps/ios-shadow` contains a SwiftUI package skeleton and required screen names.
- Docs and scripts exist, but several files were skeletal.

## Missing pieces before Phase 2
- Approvals, audit, devices, consents, and tasks were in process memory only.
- Pairing was code-only: no signatures, replay protection, expiration enforcement, revocation, or key pinning.
- Agent execution did not persist approval/task/audit state and Ghost was not wired into execution flow.
- AXIOM was callable but not consistently integrated into model/cloud context flow.
- There was no connector registry, model provider abstraction, deterministic demo, or end-to-end test coverage.
- iOS lacked an Xcode-ready README, settings for a real node URL, audit screen, and implementation scaffolds.

## Fragile/stubbed areas
- SQLite encryption uses encrypted JSON payloads with searchable plaintext indexes; production should use SQLCipher or encrypted indexes where feasible.
- Pairing v1 signs challenges but still needs transport-level mTLS/session encryption in the next phase.
- Ghost execution is a safe deterministic mock executor rather than real desktop control.
- OpenAI/OpenRouter providers are interfaces only unless explicit secrets are configured and consent is granted.
- Swift package structure is Xcode-ready, but not a fully signed `.xcodeproj`.

## Hardening plan
1. Durable encrypted SQLite stores for devices, approvals, audit, consent, and tasks.
2. Pairing v1 with Ed25519 identity keys, challenge signatures, nonces, expiration, key pinning, revocation, and tests.
3. End-to-end API/demo flow covering ingestion, retrieval, approval, Ghost execution, and audit.
4. Connector registry and model provider abstractions with explicit consent checks.
5. iOS command center structure with API client, settings, audit, and extension scaffolds.
6. Security docs covering emergency pause, destructive double confirmation, cloud consent, and audit immutability.

## Risks and priorities
- P0: never execute blocked/destructive/cloud actions without policy approval.
- P0: persist audit records and never log secrets.
- P1: make pairing replay/expiration/revocation testable.
- P1: keep demo deterministic and local-only by default.
- P2: replace mock Ghost/model providers with real upstream integrations.
