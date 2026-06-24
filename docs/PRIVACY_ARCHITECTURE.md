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
