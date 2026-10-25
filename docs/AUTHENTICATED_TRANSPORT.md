# Authenticated transport

Every route except `/`, `/web/*`, `/health`, `/ready`, `/pair/start` and `/pair/confirm` requires a signed request when `SHADOW_AUTH_REQUIRED=true` (the default).

## Pairing

1. The new device calls `POST /pair/start` with `device_name`, `public_key` (32 random bytes, hex) and optionally `client_kind` (`web`, `ios`, `mobile`). It gets a `pairing_id` and a 6-character `code`.
2. It polls `POST /pair/confirm` with the `pairing_id`. The node answers `202 {"status": "pending"}` until the pairing is approved.
3. Approval comes from one of:
   - **An owner device**: `POST /pair/approve` (the dashboard's Devices view lists `GET /pair/pending`). The person approving checks that the code matches the one on the new device.
   - **An owner-initiated pairing**: `POST /devices/register` creates a pairing that is already approved (the dashboard's "Add a phone").
   - **The bootstrap code**, only while the node has no *active* owner (a fresh node, or every owner revoked or expired). The node prints a single-use code to its terminal at startup (`SHADOW BOOTSTRAP CODE: XXXX-XXXX`). The device sends it as `bootstrap_code` in `/pair/confirm` and becomes the owner. After 5 wrong attempts the code rotates. `SHADOW_BOOTSTRAP_CODE` pins a code for headless deployments. In dev mode (`SHADOW_AUTH_REQUIRED=false`) the first device on an empty node pairs without a code.
4. The `200` response carries `device`, `secret` (also as `shared_secret` for older clients) and `session_expires_at`.

`/pair/confirm` is a single critical section, so concurrent confirms of one pairing mint exactly one device.

## Signed request headers

| Header | Value |
|---|---|
| `x-shadow-device-id` | device id from pairing |
| `x-shadow-signature-version` | `2` (omit for legacy v1) |
| `x-shadow-nonce` | random hex, single use |
| `x-shadow-timestamp` | unix seconds (±300 s skew allowed) |
| `x-shadow-signature` | lowercase hex HMAC-SHA256 with the device secret |

### Signature v2 (current)

```
SHADOW-SIG-v2
METHOD
/path
canonical_query
sha256_hex(raw_body)
nonce
timestamp
device_id
```

Lines joined with `\n`. `canonical_query` is the query string decoded into pairs (`+` is a space), each key and value re-encoded per RFC 3986 (unreserved characters `A-Z a-z 0-9 - _ . ~` kept), sorted by key then value, and joined with `&`. An empty query is an empty line. The body digest covers the exact bytes sent, so JSON and binary bodies are handled the same way.

Shared test vectors: `tests/fixtures/sig_v2_vectors.json`. They are checked by the Python node, the dashboard (`web/signer.js`), the Expo app (`shadowSigner.ts`) and the iOS app (`swift test` in `apps/ios-shadow`).

### Legacy v1

`METHOD\npath\nbody\nnonce\ntimestamp`, where the path excludes the query string, so query parameters are **not** signed. v1 is still accepted, but:
- a device that has authenticated once with v2 can no longer use v1 (`sig_downgrade`);
- browser devices start at v2;
- v1 requests with a query string get a `Deprecation: true` response header;
- `SHADOW_REQUIRE_SIG_V2=true` rejects v1 everywhere.

## Sessions

Sessions last 30 days. A device that authenticates with less than 7 days left is renewed automatically, so devices in regular use never expire. `POST /devices/{id}/renew` renews explicitly: a device may renew itself, and an owner can revive an expired device. Every signed response carries `X-Shadow-Session-Expires`. If every owner has expired, the bootstrap code reopens, so the node can't be permanently locked.

## Server checks

In order: known device, then signature present (both before the body is read), then not revoked, trusted, session valid, nonce present, version allowed, timestamp within skew, signature equality (constant time), nonce claimed atomically (replays are rejected, including across restarts with `SHADOW_RUNTIME_DB`). Failures are audited. Rate limiting is keyed by the verified device id, or the client IP for unauthenticated requests.

## Key storage

| Client | Where the device secret lives |
|---|---|
| Dashboard | Non-extractable WebCrypto key in IndexedDB (https or localhost). On a plain-http LAN address there is no WebCrypto, so it falls back to localStorage and shows a warning. |
| iOS | Keychain, `AfterFirstUnlockThisDeviceOnly` |
| Expo app | `expo-secure-store` |
| Node | Derived from the master secret (`$SHADOW_DATA_DIR/keys/master.key`, created 0600). Nothing per device is stored. |

## Next steps

Replace the returned shared secret with device-held asymmetric keys (Ed25519 support exists behind `SHADOW_ED25519_KEYS`, and Secure Enclave keys on iOS), pin the node's key on clients, and add explicit key rotation.
