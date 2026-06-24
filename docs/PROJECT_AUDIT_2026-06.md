# Shadow Agent — Project Audit (June 2026)

This is a verified, evidence-based snapshot of the repository state. Every "✅"
below was confirmed by running the code, not by reading documentation.

## Verification method
- `pip install -r requirements.txt` + `python -m compileall apps/shadow-node packages` — clean.
- `pytest -q` — **94 passed** (88 baseline + 6 new RC tests).
- App import — boots, 29 routes.
- `make demo` — full pairing → consent → ingest → ask → approval → audit flow runs.

## What is real

| Area | State | Notes |
|---|---|---|
| FastAPI Shadow Node | ✅ Real | 29 routes, boots clean |
| Encrypted memory (SQLite + FTS5 + Fernet) | ✅ Real | AES via Fernet; chunking, attribution, dedup, revocation |
| **Persistent memory across restarts** | ✅ **New** | Stable key via `SHADOW_MEMORY_KEY[_FILE]`; set `SHADOW_MEMORY_DB` |
| Signed-request transport auth | ✅ Real | HMAC signature, nonce replay protection, timestamp skew, revocation, auth-failure audit (`agent_core/security.py`) |
| Prompt-injection / exfiltration defense | ✅ Real | `is_suspicious_user_request`, `mark_untrusted` on retrieved context |
| Consent + cloud-escalation policy | ✅ Real | Cloud blocked without active grant **and** explicit approval |
| Approval workflow + emergency pause | ✅ Real | Double-confirm gate for critical actions |
| **Real Claude model provider** | ✅ **New** | `AnthropicProvider` (httpx) gated behind cloud consent + API key; local mock fallback |
| Audit log | ✅ Real | Append-only event stream surfaced at `/audit` |

## What is still scaffolding (known gaps)

| Area | State | Impact |
|---|---|---|
| GHOST action execution | ⚠️ Mock | `mode=mock` returns simulated results; no real desktop actions yet |
| AXIOM context adapter | ⚠️ Thin | Deterministic packaging seam, not a full context router |
| Runtime state (devices/consents/approvals) | ⚠️ In-memory | Lost on node restart; memory itself now persists. Encrypted SQLite stores are designed but not yet the default runtime backend |
| iOS app | ⚠️ Unverified here | Cannot build without Xcode; validate per `apps/ios-shadow/BUILD_NOTES.md` |
| Ed25519 device keys | ⚠️ Enhancement | Transport auth uses HMAC today; asymmetric keys are a follow-up |

## Production posture
- **Auth is off by default** (`SHADOW_AUTH_REQUIRED=false`). Set `true` for any networked deployment.
- CORS is restricted to localhost origins — widen deliberately if serving a real client.
- Cloud model is **opt-in** and key-gated; the node is fully functional offline.

## Honest bottom line
The node is a genuinely working, well-tested local-first service with real
encryption, real authenticated transport, real privacy controls, and now a real
model seam and persistence. The remaining gap to a *complete* product is real
action execution (GHOST) and durable runtime state. It is deployable today as a
private personal-memory + Q&A node with `SHADOW_AUTH_REQUIRED=true`; it is not
yet an autonomous action-taking agent.

## Recommended next steps (priority order)
1. Make encrypted SQLite the default runtime store (devices/consents/approvals/audit).
2. Implement one real GHOST action end-to-end behind the approval gate.
3. Promote transport auth to Ed25519 device keys (Keychain-backed on iOS).
4. Add rate limiting + structured request logging for the networked deployment.
