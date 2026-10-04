# Security and Privacy

## Principles
User-owned memory, explicit consent, least privilege, local-first defaults, revocable permissions, transparent audit, no covert collection, no silent cloud context.

## Threat Model
Threats include malicious connectors, prompt injection, stolen node, local malware, cloud over-sharing, automation abuse, replayed pairing codes, and unsafe model/tool output.

## Encryption
Memory rows are encrypted with Fernet in the Python MVP. Production iOS uses Keychain plus CryptoKit-compatible envelope encryption. Node secrets should be stored in OS secure storage. Pairing secrets, API tokens, sync payloads, and sensitive logs must be encrypted.

## Consent Ledger
ConsentGrant records source, scope, purpose, retention, model access, approval, revocation, and last use.

## Cloud Escalation
Default deny. If allowed, policy checks grants, redacts sensitive data, compresses context, discloses payload/model/purpose, logs event, and supports local-only fallback.

## Abuse Prevention
Hard blocks include keylogging, covert monitoring, iOS sandbox bypass, silent microphone/camera capture, and unapproved destructive or external-write actions.

## App Store Notes
The iOS app must be transparent about data access, use App Intents/Share Extension/BackgroundTasks within platform constraints, and avoid claims or behaviors suggesting hidden monitoring.

## Beta Authenticated Transport
Signed device requests add nonce replay protection, timestamp validation, device fingerprint validation, revocation checks, session expiration, and audit events for failed auth attempts.

### Device credential derivation
A device's request-signing secret is derived, not stored: `token = HMAC-SHA256(master, "shadow-device:v<version>:<device_id>")` (hex). The node master secret comes from `SHADOW_MASTER_SECRET` (64 hex chars preferred), then `SHADOW_MASTER_SECRET_FILE` (default `data/keys/master.key`, 0600), else generated once and persisted. The master is never logged and never returned by any API. Request verification recomputes the token and compares with `hmac.compare_digest`; a device whose scheme needs a master that is unavailable fails closed.

Devices enrolled before this scheme carry `credential_scheme: "stored"` and keep their random persisted secrets; they are unaffected by master rotation.

Rotation: replace the master secret AND bump `DEVICE_TOKEN_VERSION` in `device_credentials.py`. The version is part of the derivation input, so every previously derived token stops verifying immediately and each device must complete a fresh pairing ceremony. There is no grace period by design. Authenticated ECDH is the documented upgrade path if the node ever goes remote or multi-user.

## Prompt Injection Defense
Retrieved memory is marked as untrusted context and cannot override system policy. Requests to leak secrets, bypass consent, ignore policy, or auto-send without approval are blocked and audited.
