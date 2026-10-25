# Shadow Agent

Local-first personal AI agent foundation for iOS, desktop Shadow Node, encrypted memory, consent-ledger policy, AXIOM-AETHER context routing adapters, and GHOST-Chimera action adapters.

## What works now
- **Web dashboard** at `/`, no build step: Overview, Ask, Approvals, Actions, Memory, Goals, Schedule, Feed, custom Panels, Devices, Models, Audit, and the emergency pause. The browser pairs as a device and signs every request.
- FastAPI Shadow Node: pairing, memory, agent, approvals, devices, goals, reminders, scheduled tasks, feed, panels, audit, tools, SSE and WebSocket endpoints (reference in `docs/API.md`).
- Encrypted SQLite/FTS5 memory with attribution, confidence, sensitivity flags and deletion. It persists across restarts.
- **Models**: an on-device placeholder by default. With a provider connected (Anthropic `claude-opus-5-5` by default, OpenAI or Gemini) plus cloud consent and per-request approval, questions go to the cloud model with redacted, compressed context.
- **Real, sandboxed actions** behind the approval gate: notes, reminders, calendar events and email drafts (written to the workspace), SSRF-guarded `http.get`, and web search.
- Signed requests (signature v2), first-owner bootstrap code, sliding 30-day sessions, and persistent encrypted runtime state (`SHADOW_RUNTIME_DB`).
- Clients: the SwiftUI iOS app (`apps/ios-shadow`) and the Expo app (`apps/mobile`).

See `docs/PRODUCTION_RUNBOOK.md` to deploy, `docs/THREAT_MODEL.md` for the security model, and `docs/AUTHENTICATED_TRANSPORT.md` for pairing and signing.

## Run
```bash
make setup     # venv + dev dependencies + the 5 local packages
make run       # http://127.0.0.1:8787, state kept in ./data
```
On first start the terminal prints a one-time setup code:
```
SHADOW BOOTSTRAP CODE: 1A2B-3C4D  (single use; pair your first device with it)
```
Open http://127.0.0.1:8787, enter the code, and that browser becomes the node's owner. Approve further devices (phones, other browsers) from **Devices**.

To reach the node from a phone on your network: `SHADOW_HOST=0.0.0.0 python apps/shadow-node/run.py`. Plain-http LAN addresses can't use WebCrypto, so the dashboard warns that its key is stored less securely. Use localhost or put HTTPS in front for browsers.

For real answers, connect a provider in **Models** (or set `ANTHROPIC_API_KEY`, `SHADOW_CLOUD_ENABLED=true`, `SHADOW_MODEL_PROVIDER=anthropic`), add a cloud consent grant, then tick "Use the cloud model" when asking.

Docker: `docker compose up --build`. The setup code appears in `docker compose logs shadow-node`.

## Test
```bash
make test                           # Python suite
node tests/js/sig_v2_vectors.test.mjs   # dashboard signer vs shared vectors
(cd apps/ios-shadow && swift test)  # iOS signer vs shared vectors (macOS)
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
The demo grants local-only consent, ingests `examples/sample_project_context.md`, asks a memory-backed question, and prints approval and audit counts.

## iOS app
Open `apps/ios-shadow/ShadowAgent.xcodeproj`, run the `ShadowAgentApp` scheme on an iOS 17+ simulator, and pair: with the setup code on a fresh node, or by approving the code it shows from the dashboard's Devices view. See `apps/ios-shadow/BUILD_NOTES.md`.
