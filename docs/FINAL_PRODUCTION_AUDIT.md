# Final Production Audit — Shadow Agent RC1

## Current status
The repository contains a FastAPI Shadow Node, encrypted SQLite/FTS memory engine, policy engine, pairing service, model-provider registry, GHOST and AXIOM adapter seams, SwiftUI iOS package, Docker/Make tooling, and tests. This phase hardens it into a release-candidate baseline rather than a fully App-Store-shipped product.

## Fully implemented
- Local node health, pairing, device registry, consent, memory ingest/search, Ask Shadow, approvals, execution handoff, emergency pause, and audit APIs.
- Ed25519 pairing and protected-route signed requests covering method, path, body, nonce, and timestamp.
- Encrypted local memory storage with SQLite FTS5 retrieval and untrusted-context attribution.
- Approval-gated execution with destructive-action double confirmation and emergency-pause blocking.
- Local mock model default, cloud-provider interfaces blocked unless consent and explicit approval are present.
- Deterministic AXIOM context packaging and GHOST task IR handoff.

## Mocked or release-candidate only
- OpenAI/OpenRouter/local model providers are interfaces and do not invoke live external APIs by default.
- GHOST local runtime and AXIOM local runtime are callable adapter paths, but production runtime binaries are not bundled.
- Gmail, Calendar, and Notes connectors are mock metadata connectors only; OAuth is intentionally not faked.
- iOS is a Swift Package app scaffold build-ready for Xcode validation, not validated in this Linux environment.

## Security-sensitive areas
- `apps/shadow-node/shadow_node/auth.py`: signed request verifier and replay protection.
- `apps/shadow-node/shadow_node/pairing.py`: pairing challenge verification and device fingerprinting.
- `packages/memory-engine/memory_engine/engine.py`: encrypted storage, FTS indexing, deletion semantics.
- `apps/shadow-node/shadow_node/model_providers.py`: cloud consent gates and redaction package.
- `packages/agent-core/agent_core/policy.py`: blocked action classes, cloud and destructive action policy.

## App Store blockers
- Xcode project/device build must be validated on macOS.
- Privacy Nutrition Label answers require legal/product review.
- Share Extension, App Intents, notifications, and BackgroundTasks are scaffolds needing entitlement review.

## Backend production blockers
- Replace generated per-process runtime encryption keys with an operator-managed local secret.
- Add persistent nonce/session table if multi-process deployment is used.
- Add production observability and backup/restore workflows.

## Real user testing blockers
- Mac/Xcode simulator and device QA.
- Usability review for pairing and node URL discovery.
- Larger corpus ingestion performance testing.

## Completed in this phase
- Signed transport middleware and tests.
- Demo updated for authenticated requests.
- iOS Keychain device identity and signed Ask request seam.
- RC docs, QA checklist, privacy/security docs, and CI.

## File-level plan
- `apps/shadow-node/shadow_node/auth.py`: request-signing verifier.
- `apps/shadow-node/shadow_node/main.py`: protect APIs, preserve public health/pairing.
- `apps/ios-shadow/Sources/ShadowAgent/Services/`: real HTTP signing seam and Keychain identity.
- `tests/test_production_rc.py`: auth, pairing, memory, consent, emergency, approval coverage.
- `docs/*.md`: release-candidate operational, privacy, and App Store package.
