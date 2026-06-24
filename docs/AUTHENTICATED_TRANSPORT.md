# AUTHENTICATED TRANSPORT

After pairing, the node issues a per-device session secret and stores a device fingerprint. iOS stores device ID, node fingerprint, public key metadata, and the session secret in Keychain.

## Signed request headers
- `x-shadow-device-id`
- `x-shadow-signature`
- `x-shadow-nonce`
- `x-shadow-timestamp`

The signature is HMAC-SHA256 over `METHOD + "\n" + PATH + "\n" + BODY + "\n" + NONCE + "\n" + TIMESTAMP`. The server validates timestamp skew, nonce replay, device trust, revocation, session expiration, and signature equality. Failed attempts create auth-failure audit events.

## Production upgrade path
The beta HMAC session protocol is intentionally simple for local testing. Production should replace pairing secret return with mutually authenticated ECDH, public-key pinning, Secure Enclave-backed keys where available, and explicit key rotation.
