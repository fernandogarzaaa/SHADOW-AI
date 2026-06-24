# Shadow Agent Production RC Notes

Shadow Agent RC1 is a local-first personal AI release candidate. Health and pairing are the only public node flows; personal data, memory, approvals, execution, consent, devices, connectors, and audit endpoints require a trusted paired device and an Ed25519 signed request.

## Security and privacy baseline
- Signatures cover HTTP method, path, body, nonce, and timestamp.
- Replayed nonces, expired timestamps, invalid signatures, and revoked devices are rejected and audited.
- Local mock model is the default; cloud providers require a consent grant and explicit per-request approval.
- Retrieved memory is treated as untrusted context and cannot override policy.
- Emergency pause blocks ingestion and execution handoff.
- Audit records are append-only by API semantics.
- Supported user-approved ingestion baseline: .txt, .md, .markdown, and .json text content.

## App Store and compliance posture
The app does not covertly monitor other apps, bypass iOS sandboxing, keylog, silently record, or auto-send content. User consent copy must explain local memory, optional cloud escalation, deletion, consent revocation, and emergency pause. Xcode simulator/device validation remains a required QA step before TestFlight.

## Operations
Run `pip install -r requirements.txt`, `pytest -q`, `python -m compileall apps/shadow-node packages`, and `make demo`. Start the node with `make run`, then pair the iOS app using the local node URL. API keys must come only from environment/secure config and must never be logged.

## Release-candidate limitations
Live OAuth, App Store submission, production GHOST/AXIOM runtime binaries, and live cloud model invocation are intentionally post-RC unless explicitly configured and reviewed.

## RC2 replay update

Nonce replay protection is backed by the runtime SQLite database instead of process-only memory. This keeps replay checks intact across verifier recreation in single-node local deployments. Multi-worker deployments should continue to use one shared runtime database or an external nonce store.
