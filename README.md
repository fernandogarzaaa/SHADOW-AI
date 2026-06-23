# SHADOW-AI

SHADOW-AI is an iOS-first personal AI agent implementation. It combines an always-on product vision with a production-oriented Swift core that enforces consent, app allow-lists, memory isolation, audit logging, and autonomous-action guardrails.

## What is implemented

- `ShadowAgentCore`, a Swift Package Manager library for the agent domain model and runtime policy engine.
- Permission grants for read/write access across email, chat, calendar, notes, photos, voice, keystrokes, work apps, and device control.
- Configurable modes: observe-only, recommend, confirm-before-action, and autonomous.
- Watched-application allow-list enforcement before context ingestion.
- Local memory stores for approved user context, including in-memory and file-backed implementations.
- Recommendation generation from approved local context.
- Autonomous decisioning that checks write permissions and safety guardrails before approving an action.
- Consent audit logging for permission, ingestion, proposal, approval, and denial events.
- A SwiftUI iOS app shell under `ios/ShadowAgentVisionApp` that demonstrates consent, local context ingestion, recommendations, action evaluation, and audit history.

## Product vision

Shadow Agent Vision is designed to be always on by default, similar in spirit to a next-generation mobile assistant but more personal, contextual, and proactive. The agent notifies the user before requesting read or write permissions, gathers approved context, asks again before sensitive actions, and learns from user-approved data so it can work on behalf of the user inside clear boundaries.

## Startup concept

The agent is built around a quantized personal hybrid RAG idea:

- Mobile-first operation.
- Always-on mode that can be scoped to designated apps.
- Approved app activity learning from signals such as typing behavior, user behavior patterns, photos, voice, notes, messages, and work context.
- Local memory retrieval for personal context.
- Optional frontier-model reasoning for higher-quality planning and generation.

## User value

The agent can help the user by:

- Recommending actions and giving advice.
- Running in autonomous mode after permissions, guardrails, and learned workflow context are in place.
- Speaking on behalf of the user only when explicitly authorized.
- Connecting to approved devices and local computers for autonomous remote-control workflows.

## Key integrations

- [Axiom Aether](https://github.com/fernandogarzaaa/AXIOM-AETHER)
- [Ghost Chimera](https://github.com/fernandogarzaaa/GHOST-Chimera)

## Safety and privacy model

SHADOW-AI treats user data as permissioned local context. The core enforces:

- Read permission before context ingestion.
- Write permission before action approval.
- Expiring permission grants.
- Watched-app allow lists.
- Guardrails for dangerous actions such as sharing passwords, deleting accounts, disabling security, or moving money.
- Audit logs for user-visible traceability.

## Cloud and local hybrid model

The intended architecture combines local RAG with cloud-based frontier reasoning. Private context should remain fingerprinted, encrypted, minimized, and policy-filtered before any remote reasoning request. The current repository implements the local consent, memory, and decisioning foundation needed for that architecture.

## Development

Run the test suite:

```bash
swift test
```
