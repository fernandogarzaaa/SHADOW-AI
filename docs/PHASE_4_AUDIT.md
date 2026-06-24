# Phase 4 Repository Audit

## Current baseline inspected
The branch is at commit `634cc95` with a local-first beta foundation: FastAPI Shadow Node, encrypted SQLite/FTS memory, consent and approval policy, signed-device session primitives, local file connector, GHOST/AXIOM adapter seams, and a SwiftUI/Xcode placeholder app.

## What already exists
- Backend endpoints for health, pairing, memory ingest/search/export/source delete, agent ask/plan/execute, approvals, devices, audit, model provider summary, and WebSocket task channel.
- Signed request primitives in Python: HMAC signature over method/path/body/nonce/timestamp, nonce replay protection, timestamp validation, revocation checks, and auth-failure audit events.
- Memory engine with encryption, chunking, FTS5 search, duplicate detection, freshness score, categories, sensitivity flags, source deletion, and export.
- Agent core policy with emergency pause blocking, outbound/cloud approval requirements, destructive double confirmation, spyware/covert monitoring hard blocks, and prompt-injection request detection.
- iOS SwiftUI screen files and a minimal placeholder Xcode project.

## What is compile-ready
- Python backend packages compile and tests pass at baseline.
- Swift source is structured under `apps/ios-shadow/Sources/ShadowAgent`, but the Xcode project file was previously a placeholder and did not reliably reference source files/resources.

## What is only placeholder
- The iOS Xcode project and target membership.
- iOS API client, secure device identity, real pairing flow, memory/ask/approval/audit backend-backed UX.
- Keychain implementation was a placeholder using `UserDefaults`.
- Emergency pause had local UI state but no backend API.

## What blocks real iOS testing
- Missing production-shaped Swift API client and request models.
- Missing iOS signed-request implementation compatible with node HMAC session protocol.
- Missing Keychain-backed storage for device ID/session secret/node metadata.
- Missing backend endpoints for creating approval requests directly and syncing emergency pause state.
- Placeholder Xcode project does not enumerate app sources/resources.
- Screens were mostly static and did not call the backend.

## Implementation plan
1. Add backend endpoints needed by the app: memory list, approval creation, emergency pause get/set, stable error envelope, local CORS, and audit events for approval/emergency flows.
2. Keep auth public surface limited to health and pairing when auth is enabled; apply middleware consistently and test protected endpoint rejection.
3. Replace iOS placeholder client with real `ShadowNodeAPIClient`, codable DTOs, configurable base URL, mock/real modes, timeout/error handling, JSON encode/decode, and signed request headers.
4. Add Keychain-backed `DeviceIdentityStore`, HMAC signing abstraction, key reset/unpair support, and documented CryptoKit path.
5. Wire pairing, memory, ask, approvals, audit, devices, and emergency pause screens through shared `AppState`.
6. Update docs and add build notes/screenshots placeholders.
7. Expand backend tests to at least 85 passing tests.

## Risks
- Xcode cannot be validated in this Linux container; local macOS/Xcode validation is still required.
- The beta protocol uses HMAC session secrets returned after pairing; production should move to mutually authenticated ECDH and key pinning.
- The Xcode project is generated manually and may need Xcode normalization.
- iOS file document-picker integration remains user-selected only and must avoid broad file scanning.

## Files that must be touched
- `apps/shadow-node/shadow_node/main.py`
- `packages/agent-core/agent_core/*`
- `apps/ios-shadow/ShadowAgent.xcodeproj/project.pbxproj`
- `apps/ios-shadow/Sources/ShadowAgent/Models/*`
- `apps/ios-shadow/Sources/ShadowAgent/Services/*`
- `apps/ios-shadow/Sources/ShadowAgent/State/*`
- `apps/ios-shadow/Sources/ShadowAgent/Views/*`
- `apps/ios-shadow/README.md`
- `apps/ios-shadow/BUILD_NOTES.md`
- `docs/*`
- `tests/*`
