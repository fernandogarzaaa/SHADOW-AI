# PRD: Shadow Agent Alpha

## Vision
Shadow Agent is a local-first personal AI operating layer with encrypted personal memory, approval-gated action, transparent audit, and replaceable AXIOM/GHOST integrations.

## Phase 2 Alpha Objective
Make the product demoable end-to-end: pair device, ingest approved content, retrieve memory, answer a question, create approval, execute safe Ghost mock task, and inspect durable audit/device/memory/approval state.

## Target users
AI power users, founders, developers, operators, professionals with high context load, students, researchers, assistants, local business owners, and remote workers.

## Alpha features
- Durable encrypted runtime stores.
- Pairing v1 with signed challenge, nonce, expiration, key pinning, replay protection, revocation.
- Connector registry v1 with Gmail, Calendar, Files, Notes/manual text, Desktop Node mocks and consent requirements.
- Model provider abstraction with LocalMock, OpenAI-compatible, OpenRouter-compatible, LocalModel placeholder.
- AXIOM context packaging wired into ask/model flow.
- GHOST task IR and safe approval-gated mock execution.
- iOS Xcode-ready Swift package with command-center screens and extension scaffolds.
- Deterministic `make demo` flow.

## Non-goals
No covert monitoring, hidden keylogging, iOS sandbox bypass, silent chat reading, silent microphone/camera recording, auto-sending messages, or cloud use without explicit consent.

## RC1 acceptance posture

RC1 prioritizes local-first memory, signed iOS-to-node transport, approval-gated actions, auditability, emergency pause, and safe provider routing. Live cloud and OAuth features remain opt-in integration work rather than default behavior.
