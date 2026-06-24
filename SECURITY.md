# Security and Privacy

Shadow Agent defaults to local-first, explicit consent, auditability, emergency pause, and revocable devices/memory.

## Enforced controls
- Emergency pause blocks ingestion and execution-sensitive flows.
- Keylogging, covert monitoring, iOS sandbox bypass, silent microphone, and silent camera classes are hard-blocked.
- Critical/destructive actions require approval and double confirmation at execution.
- Outbound message/email actions are critical and require approval.
- Cloud model providers require explicit request approval plus active non-local consent.
- AXIOM redacts private data before cloud-safe context packaging.
- Device revocation marks devices untrusted and blocks trusted-device checks.
- Audit store is append-only at the repository API layer.
- Secrets are not logged; `.env` is ignored.

## Remaining hardening
Use SQLCipher/encrypted indexes, transport mTLS, OS keychains, signed iOS app groups, prompt-injection filters, and real sandboxed desktop execution in the next phase.

## RC1 transport and privacy hardening

Protected node endpoints require Ed25519 signed requests from a trusted paired device. Signatures cover method, path, body, nonce, and timestamp; replay, clock-skew, invalid-signature, and revoked-device failures are audited without logging secrets. Emergency pause blocks execution and ingestion paths, and cloud model routing remains disabled unless a consent grant and explicit request approval are both present.
