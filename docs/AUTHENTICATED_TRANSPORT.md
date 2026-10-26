# Authenticated transport

How clients pair with a Shadow node and sign their requests. This is the contract the dashboard (`web/signer.js`), the Expo app (`shadowSigner.ts`) and the iOS app (`ShadowRequestSigner`) implement; a new client following it should interoperate first time.

When `SHADOW_AUTH_REQUIRED=true` (the default), every request needs a signature except: `OPTIONS` (CORS preflight), `/`, `/web/*` (dashboard assets), `/health`, `/ready`, `/pair/start`, `/pair/confirm`, and the API docs (`/docs*`, `/openapi*`, which describe routes but return no data). `GET /health` reports `auth_required` and `bootstrap_open` so clients can tell which mode a node is in.

**Transport security.** Pairing returns the device secret in a response body, and responses are not signed. Use HTTPS (or `localhost`) whenever the node is reachable beyond the local machine.

All timestamps in responses are ISO 8601 in UTC. Request and response bodies are JSON.

## Roles

- **Trusted**: every paired device. **Active**: trusted, not revoked, session not expired.
- **Owner**: a device paired with the bootstrap code. Devices approved by an owner, or added with `/devices/register`, are not owners.
- **Owner-only**: `POST /pair/approve`, `GET /pair/pending`, `POST /devices/register`, and revoking or renewing *another* device (including reviving an expired one). Any device may revoke or renew itself and toggle the emergency pause. A non-owner gets `403 "owner device required"`.
- **Legacy nodes** that have devices but no owner: any trusted device passes the owner check until an owner exists.

## Pairing

1. The new device calls `POST /pair/start` with:
   - `device_name`: a display name.
   - `public_key`: an opaque per-install identifier. Send 32 random bytes as hex; it does not need to be a real public key or be kept secret. The node stores it and shows its fingerprint (`sha256(public_key)[:32]`) so people can recognise devices. It is not used in signing today; the field is reserved for device-held asymmetric keys.
   - `client_kind` (optional): a free-form label such as `web`, `ios` or `mobile`. Only `web` changes behaviour: those devices start on signature v2. Omitted means no label.
2. The device polls `POST /pair/confirm` with `{pairing_id, bootstrap_code?}`. Poll every 2 s and stop on `200`, `403`, `404` or `410`, or after `expires_in_seconds`.
3. Approval comes from one of:
   - **An owner device**: it lists `GET /pair/pending` and calls `POST /pair/approve {pairing_id}` (idempotent). The person approving checks that the code shown on both devices matches.
   - **The bootstrap code** (see below), sent as `bootstrap_code` in `/pair/confirm`. The device becomes the owner.
   - **Dev mode** (`SHADOW_AUTH_REQUIRED=false`): the first device on an empty node pairs without a code.
4. On `200` the device stores `device.id` and `secret`. A pairing is single use: a confirm retried after a lost `200` gets `404`, so start pairing again.

| Endpoint | Request | Success | Errors |
|---|---|---|---|
| `POST /pair/start` | `{device_name, public_key, client_kind?}` | `200 {pairing_id, code, expires_in_seconds, bootstrap_required}` | `422` invalid body, `429` more than 20 pairings pending |
| `POST /pair/confirm` | `{pairing_id, bootstrap_code?}` | `200 {device, secret, shared_secret, session_expires_at}`, or `202 {pairing_id, status: "pending", bootstrap_required}` | `403 {"detail": "invalid_bootstrap_code", ...}`, `404` unknown or already used, `410` expired |
| `GET /pair/pending` (owner) | | `200 {items: [{pairing_id, code, device_name, client_kind, created_at, expires_in_seconds}], count, next_cursor}` | `403` |
| `POST /pair/approve` (owner) | `{pairing_id}` | `200 {pairing_id, status: "approved"}` | `403`, `404`, `410` |
| `POST /devices/register` (owner) | `{name, public_key}` | `200 {pairing_id, code, expires_in_seconds}` (already approved) | `403`, `429` |

- `code` is the last 6 characters of `pairing_id`, uppercased. Pairings expire after 300 s.
- `secret` is 64 lowercase hex characters. `shared_secret` is the same value under the name older clients read.
- `device` has: `id`, `name`, `public_key`, `fingerprint`, `trusted`, `revoked`, `is_owner`, `session_expires_at`, `registered_at`, `credential_scheme`, `min_sig_version`, `client_kind`.
- `/pair/confirm` runs as one critical section, so concurrent confirms of a pairing mint exactly one device; the others get `404`.

### Owner-initiated pairing ("Add a phone")

1. The owner calls `POST /devices/register {name, public_key}` and gets an already-approved `pairing_id`.
2. The owner hands the new device this payload, as a QR code or by manual entry: `{"v": 1, "url": "<node base URL>", "pairing_id": "<id>"}`.
3. Within 300 s, the new device calls `POST /pair/confirm {pairing_id}` (it skips `/pair/start`). It is not an owner, and it starts on v1 until it first signs with v2.

### Bootstrap code

Used only while the node has no active owner: a fresh node, or every owner revoked or expired.

- **Format:** `XXXX-XXXX` (8 hex characters). Compared ignoring case, dashes and spaces.
- **When it's printed:** to the node's terminal at startup, and again on `/pair/start` while bootstrap is open (`SHADOW BOOTSTRAP CODE: XXXX-XXXX`). It is never written to log sinks.
- **Random code:** single use. After 5 wrong attempts a new code is printed.
- **Pinned code** (`SHADOW_BOOTSTRAP_CODE`, for headless deployments): at least 8 characters ignoring dashes, or the node refuses to start. Single use: once consumed, later reopenings print a random code. After 5 wrong attempts it is locked until the node restarts.
- A code sent while bootstrap is closed gets `403 invalid_bootstrap_code` and does not count as a failure.

## Signed request headers

| Header | Value |
|---|---|
| `x-shadow-device-id` | `device.id` from pairing |
| `x-shadow-signature-version` | `2`. Omitting it means legacy v1; a non-integer is rejected as `unsupported_signature_version`. |
| `x-shadow-nonce` | at least 16 bytes from a secure random generator, lowercase hex, never reused |
| `x-shadow-timestamp` | Unix seconds as a decimal integer; must be within ±300 s of the node's clock |
| `x-shadow-signature` | lowercase hex of HMAC-SHA256 over the canonical string, keyed with **the ASCII bytes of the `secret` string** (do not hex-decode it) |

### Signature v2 (current)

The canonical string is these eight lines joined with `\n`, with no trailing newline:

```
SHADOW-SIG-v2
METHOD
/path
canonical_query
sha256_hex(body)
nonce
timestamp
device_id
```

- **METHOD**: uppercase.
- **/path**: the request path exactly as sent on the wire. Percent-encoding is preserved (uppercase escapes), the query and fragment are excluded, and any prefix the node sees behind a proxy is included. For example, `/scheduled-tasks/ambient%3Afeed_digest` is signed as written.
- **canonical_query**:
  1. Drop a leading `?`. An empty query gives an empty line.
  2. Split on `&` and decode each pair (`+` is a space). A bare `k` and `k=` both mean key `k` with an empty value.
  3. Re-encode each key and value, keeping only `A-Z a-z 0-9 - _ . ~` and writing every other byte of the UTF-8 encoding as uppercase `%XX`.
  4. Sort pairs by encoded key, then encoded value, comparing bytes. Sorting the encoded form matters: `%C3%A9` (é) sorts before `a`.
  5. Join as `k=v` with `&`.
- **sha256_hex(body)**: lowercase hex SHA-256 of the exact bytes sent. With no body, it's the digest of empty input: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

#### Worked example

Secret `7f3c9a1e5b2d4f6081a3c5e7f9b1d3e5a7c9e1f3b5d7f9a1c3e5b7d9f1a3c5e7`, device `dev_test123`, nonce `n0nce`, timestamp `1760000000`, request `GET /approvals?status=pending&limit=10` with no body. The canonical string is:

```
SHADOW-SIG-v2
GET
/approvals
limit=10&status=pending
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
n0nce
1760000000
dev_test123
```

The signature is `f87b51ecbd6c628095a5ddf53f562d7ca5832a10b20b55ff68c87af8b9c69f02`.

#### Test vectors

`tests/fixtures/sig_v2_vectors.json` holds `secret`, `device_id`, `nonce`, `timestamp`, and `cases[]`, each with `name`, `method`, `path`, `query`, `body`, `canonical_query` and `signature`. The cases cover sorting, repeated keys, `+` and spaces, unicode, reserved characters, blank values, a bare key, non-ASCII key ordering, an encoded path and a JSON body. The Python node, the dashboard, the Expo app and the iOS app (`swift test` in `apps/ios-shadow`) all check every case.

A client should also check these failures against a live node:

| Case | Expected |
|---|---|
| clock off by more than 300 s | `expired_timestamp` |
| reused nonce | `replayed_nonce` |
| v1 after the device has used v2 | `sig_downgrade` |
| query or body changed after signing | `invalid_signature` |

### Legacy v1

New clients MUST sign with v2. v1 is documented only for clients paired before v2 existed.

The v1 canonical string is `METHOD\npath\nbody\nnonce\ntimestamp`:
- **path** is the decoded path, without the query string, so query parameters are **not** signed.
- **body** is the raw UTF-8 text. For `multipart/form-data` it is the literal `sha256:<hex digest of the raw body>` instead. Other non-UTF-8 bodies can't be signed with v1.

v1 is still accepted, with these limits:
- a device that has authenticated once with v2 can no longer use v1 (`sig_downgrade`);
- devices that paired with `client_kind: "web"` start at v2;
- v1 requests with a query string get `Deprecation: true` and `X-Shadow-Signature-Hint: use signature version 2`;
- `SHADOW_REQUIRE_SIG_V2=true` rejects v1 everywhere.

### WebSocket

`/ws/tasks` authenticates the upgrade request with the same headers, signing `GET` and `/ws/tasks` (plus any query) with an empty body. Browsers can't set these headers on a WebSocket; browser clients can use the SSE stream `GET /agent/stream`, fetched with signed headers, instead. A rejected handshake closes with code `4401` and the reason code as the close reason.

## Sessions

- Sessions last 30 days. A device that authenticates with less than 7 days left is renewed automatically, so devices in regular use never expire.
- Successful authenticated responses carry `X-Shadow-Session-Expires` (ISO 8601 UTC). Clients should store it. Responses are **not** signed: use TLS to authenticate the node.
- `POST /devices/{id}/renew` returns `200 {device_id, session_expires_at}`, `404` for an unknown device, `409` for a revoked one, or `403` when a non-owner renews another device. A device can renew itself only while its session is valid. Once it has expired, an owner has to revive it.
- If every owner has expired, the bootstrap code reopens on the next `/pair/start` or restart, so a node can't be permanently locked.

## Errors

Every authentication failure is `401 {"detail": "<reason>"}`. For allowed CORS origins it also carries `Access-Control-Allow-Origin`. The node checks in this order and returns the first failure:

| `detail` | Meaning | Client action |
|---|---|---|
| `unknown_device` | device id not paired | Forget the credential and pair again |
| `revoked_device` | device was disconnected | Forget the credential and pair again |
| `untrusted_device` | device not trusted | Pair again |
| `session_expired` | 30-day session lapsed | Ask an owner to renew, or pair again |
| `missing_signature`, `missing_nonce` | header absent | Client bug: fix the request |
| `unsupported_signature_version` | version is not 1 or 2 | Client bug: send `2` |
| `sig_downgrade` | v1 from a device that has used v2 | Sign with v2 |
| `replayed_nonce` | nonce already used | Retry with a fresh nonce |
| `invalid_timestamp` | timestamp is not an integer | Client bug |
| `expired_timestamp` | more than 300 s of clock skew | Fix the device clock |
| `invalid_signature` | signature mismatch | Check the key bytes and the canonical string; pair again if it persists |
| `unknown_device_secret` | the node can't resolve this device's secret | Pair again |

The node checks for unknown devices and missing signatures before reading a body that has a `Content-Length`. Chunked bodies are read first, up to `SHADOW_MAX_BODY_BYTES` (25 MB by default; larger bodies get `413`). On success the node raises the device's minimum signature version to 2 if it signed with v2, and may renew its session. Failures are recorded in the audit log.

Nonces are remembered per device for 600 s (twice the allowed clock skew), so a request can't be replayed while its timestamp is still valid. With `SHADOW_RUNTIME_DB` set this survives restarts; without it, a restart forgets them.

Rate limiting is optional and off by default (`SHADOW_RATE_LIMIT_RPM`). It is a per-minute token bucket, per verified device, or per client IP for unauthenticated requests and failed authentication attempts. Requests over the limit get `429`. `/health` and `/ready` are exempt.

## Key storage

| Client | Where the device secret lives |
|---|---|
| Dashboard | Non-extractable WebCrypto key in IndexedDB (https or localhost). On a plain-http LAN address there is no WebCrypto, so it falls back to localStorage and shows a warning. |
| iOS | Keychain, `AfterFirstUnlockThisDeviceOnly` |
| Expo app | `expo-secure-store` |

**Node secrets.** Device secrets are derived, not stored:

```
secret = hex(HMAC-SHA256(master, "shadow-device:v1:<device_id>"))
```

- **Where `master` comes from**, in order: `SHADOW_MASTER_SECRET` (64 hex characters are decoded to bytes; any other value is used as UTF-8), then the file named by `SHADOW_MASTER_SECRET_FILE`, then `$SHADOW_DATA_DIR/keys/master.key` (created 0600 and stored as hex).
- **Fallback:** if the master secret can't be loaded, pairing issues a random secret per device and stores it encrypted in the runtime DB (`credential_scheme: "stored"`).
- **Rotation:** changing the master secret, or bumping its derivation version, invalidates every device; all of them must pair again.

## Next steps

- Replace the returned shared secret with device-held asymmetric keys. The verifier has an experimental Ed25519 path (`SHADOW_ED25519_KEYS`), but no endpoint enrols Ed25519 keys yet, so all devices sign with HMAC today. Secure Enclave keys would come next on iOS.
- Pin the node's key on clients.
- Add explicit key rotation.
