# Threat model

Shadow runs on hardware the user owns and is reached from the user's own devices. Its assets are the memory store, the provider API keys, the ability to take actions (notes, calendar, email drafts, web fetches) and the audit trail.

## Trust boundaries

| Boundary | Crossed by | Control |
|---|---|---|
| Network → node | Every HTTP/WS request | Signed requests (v2 binds method, path, query, body digest, device), nonce replay ledger, timestamp skew, body cap (streamed, so chunked uploads are included), rate limits |
| New device → enrolled device | Pairing | Owner approval with a matching code, or the single-use bootstrap code from the node's own terminal |
| Agent → action | `/agent/execute`, ghost runs | Policy engine, server-side approval bound to the action envelope hash, one-shot consumption, second confirmation for irreversible actions, emergency pause |
| Action → consent-gated tool | calendar, email | Explicit consent only from a verified approval for that exact action, never from autonomous execution |
| Node → cloud model | `/agent/ask` with cloud allowed | Consent grant + per-request approval, per-item egress manifest, `do_not_send_to_cloud` items never leave, AXIOM redaction (also on the expanded retry), audited egress |
| Node → internet | `http.get`, `web.search` | Public addresses only (`is_global`: blocks private, loopback, link-local, CGNAT, ULA, mapped and 6to4 forms), every redirect re-validated, DNS pinned per thread for the connect, ports 80/443, no proxies, 1 MiB cap |
| Browser → dashboard | Script execution | Strict CSP (`script-src 'self'`, no inline script or handlers), `frame-ancestors 'none'`, all node text HTML-escaped, signing key non-extractable |

## Threats and mitigations

| Threat | Mitigation | Residual risk |
|---|---|---|
| Someone on the LAN claims the node first | First owner needs the bootstrap code printed on the node's terminal; the node binds 127.0.0.1 by default | Anyone who can read the node's logs can enrol while no owner exists |
| Stolen or lost phone | Revoke from any owner device; sessions expire after 30 days unused; emergency pause from any device | A stolen unlocked phone can act until revoked |
| Replayed or altered request | Nonce ledger (persistent with `SHADOW_RUNTIME_DB`), ±300 s skew, v2 signs the query and body digest | v1 clients leave the query unsigned until upgraded (`SHADOW_REQUIRE_SIG_V2` closes this) |
| Prompt injection via memory or fetched pages | Retrieved text is fenced as untrusted; the planner can't approve its own actions; consent and approvals are server-side | A model can still produce a misleading answer |
| Over-sharing with a cloud provider | Default local; per-item egress authorization; redaction; manifest in the audit chain | Redaction is pattern-based and can miss unusual identifiers |
| SSRF to internal services | See the network boundary above | DNS pinning relies on the sync HTTP client resolving in the calling thread |
| Secrets leaking from images or disks | `.dockerignore` excludes `data/`, `.env`, `.venv`; key files are created 0600 atomically under `SHADOW_DATA_DIR`; the container runs unprivileged | Memory "delete" is a soft delete: ciphertext remains until compaction |
| Malicious approval by a compromised device | Every decision records the deciding device; only owners can approve pairings or manage other devices | Any trusted device can approve actions (phones are the main approval surface) |
| Loss of audit evidence | Core events are moved into the persistent list before `/audit` returns; tamper-evident Sentinel chain | The legacy audit list is append-only but not hash-chained |

## Out of scope

Malware with root on the node host, physical attacks on an unlocked device, and compromise of a cloud provider's own infrastructure.
