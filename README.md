# Shadow Agent

Local-first personal AI agent foundation for iOS, desktop Shadow Node, encrypted memory, consent-ledger policy, AXIOM-AETHER context routing adapters, and GHOST-Chimera action adapters.

## What works now
- **Minimalist web dashboard** served at `/` (Ask, Memory, Actions, Approvals, Audit, emergency pause) — no build step.
- FastAPI Shadow Node with health, pairing, memory, agent, approvals, devices, audit, tools, and WebSocket task endpoints.
- Encrypted SQLite/FTS5 memory engine with chunking, attribution, confidence scoring, deletion/revocation — **persists across restarts** with a stable key.
- **Real model**: local mock by default; a real Claude (`AnthropicProvider`) is used when cloud consent + explicit approval + an API key are all present.
- **Real, sandboxed actions** behind the approval gate: `note.create/append/list`, `reminder.create`, and SSRF-guarded `http.get` (file actions confined to the workspace).
- **Persistent encrypted runtime state** (audit, consents, devices) via `SHADOW_RUNTIME_DB`.
- Agent Core with autonomy modes, risk classification, approval gates, cloud-escalation policy, prompt-injection defenses, audit events, and a tool registry.
- AXIOM adapter for redaction, compression, semantic skeletons, fingerprinting, token budgets.
- SwiftUI iOS command-center app (validate the simulator build locally — Xcode isn't available in CI).

See `docs/PRODUCTION_RUNBOOK.md` to deploy and `docs/PROJECT_AUDIT_2026-06.md` for the verified state of every component.

## Run
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn shadow_node.main:app --app-dir apps/shadow-node --reload --port 8787
```

## Test
```bash
pytest
```

## Repository tree
- `apps/native` — React Native (Expo) iOS/Android app (this branch); store-ready.
- `apps/ios-shadow` — SwiftUI iOS app foundation.
- `apps/shadow-node` — local desktop/server runtime.
- `packages/memory-engine` — encrypted personal memory and local RAG baseline.
- `packages/agent-core` — planner, policy, consent, approval workflow, audit models.
- `packages/axiom-adapter` — AXIOM-AETHER-compatible context layer.
- `packages/ghost-adapter` — GHOST-Chimera-compatible action layer.
- `docs` — product, security, architecture, API, and delivery docs.

## Beta demo flow
```bash
make demo
```The demo grants local-only consent, ingests `examples/sample_project_context.md`, asks a memory-backed question, creates approvals as needed, and prints audit counts.

## Secure pairing/auth testing
Pair with `POST /pair/start` then `POST /pair/confirm`. Authenticated mode validates `x-shadow-device-id`, `x-shadow-signature`, `x-shadow-nonce`, and `x-shadow-timestamp` using per-device session secrets, timestamp skew checks, replay protection, revocation, and audit logging.

## Phase 4 iOS-to-node beta
A real tester can now run the node, open the iOS app project, pair with the node, store session identity in Keychain, send signed requests, ingest pasted memory, ask questions, review sources/why explanations, approve or deny actions, execute safe mock/GHOST actions, view audit logs, and toggle emergency pause.

Xcode is not available in this container; validate the iOS simulator build locally using `apps/ios-shadow/BUILD_NOTES.md`.
