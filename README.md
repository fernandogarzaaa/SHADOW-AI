# Shadow Agent

Local-first personal AI agent foundation for iOS, desktop Shadow Node, encrypted memory, consent-ledger policy, AXIOM-AETHER context routing adapters, and GHOST-Chimera action adapters.

## What works now
- FastAPI Shadow Node with health, pairing, memory, agent, approvals, devices, audit, and WebSocket task endpoints.
- Encrypted SQLite/FTS5 memory engine with chunking, attribution, confidence scoring, deletion/revocation.
- Agent Core with autonomy modes, risk classification, approval gates, cloud escalation policy, audit events, and tool registry.
- AXIOM adapter seam for redaction, compression, semantic skeletons, fingerprinting, drift detection, token budgets.
- GHOST adapter seam for task IR, execution policy, desktop action, safety profile, telemetry.
- SwiftUI iOS command-center skeleton with required screens and App Intents/Share Extension/BackgroundTasks seams.

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
```
The demo grants local-only consent, ingests `examples/sample_project_context.md`, asks a memory-backed question, creates approvals as needed, and prints audit counts.

## Secure pairing/auth testing
Pair with `POST /pair/start` then `POST /pair/confirm`. Authenticated mode validates `x-shadow-device-id`, `x-shadow-signature`, `x-shadow-nonce`, and `x-shadow-timestamp` using per-device session secrets, timestamp skew checks, replay protection, revocation, and audit logging.
