# AUTHENTICATED TRANSPORT

Shadow Agent beta keeps local-first defaults and requires explicit consent for sensitive data access, cloud escalation, and execution.

## Signed Requests
After pairing, each protected request includes `x-shadow-device-id`, `x-shadow-signature`, `x-shadow-nonce`, and `x-shadow-timestamp`. The signature covers method, path, body, nonce, and timestamp. The node rejects missing/invalid signatures, replayed nonces, expired timestamps, revoked devices, unknown devices, and expired sessions, and audits failed attempts.
