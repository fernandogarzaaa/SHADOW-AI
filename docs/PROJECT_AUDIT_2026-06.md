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

## Update — production hardening (this branch)
These were the gaps in the first audit; they are now real:

| Area | Was | Now |
|---|---|---|
| GHOST action execution | Mock only | ✅ **Real** sandboxed actions (`note.*`, `reminder.create`, SSRF-guarded `http.get`) behind the approval gate; `local` mode executes, `mock` retained for tests |
| Runtime state (audit/consents/devices) | In-memory, lost on restart | ✅ **Persistent** encrypted SQLite via `SHADOW_RUNTIME_DB` |
| Operator UI | None | ✅ **Minimalist web dashboard** at `/` |

## What is still scaffolding (known gaps)

| Area | State | Impact |
|---|---|---|
| AXIOM context adapter | ⚠️ Thin | Real redaction/compression/fingerprinting, but not a full semantic router |
| Approvals persistence | ⚠️ In-memory | Short-lived by design (15-min expiry); audit/consents/devices now persist |
| iOS app | ⚠️ Unverified here | Cannot build without Xcode; validate per `apps/ios-shadow/BUILD_NOTES.md` |
| Ed25519 device keys | ⚠️ Enhancement | Transport auth uses HMAC today; asymmetric keys are a follow-up |

## Production posture
- **Auth is off by default** (`SHADOW_AUTH_REQUIRED=false`). Set `true` for any networked deployment.
- CORS is restricted to localhost origins — widen deliberately if serving a real client.
- Cloud model is **opt-in** and key-gated; the node is fully functional offline.

## Honest bottom line
The node is a genuinely working, well-tested local-first agent: real encryption,
real authenticated transport, real privacy controls, a real model seam, durable
encrypted memory **and** runtime state, **real sandboxed action execution behind
the approval gate**, and a minimalist web UI. It takes real actions now — it is
no longer just a Q&A node. Deployable with `SHADOW_AUTH_REQUIRED=true`,
`GHOST_RUNTIME_MODE=local`, and persistent volumes (see PRODUCTION_RUNBOOK.md).

## Recommended next steps (priority order)
1. Promote transport auth to Ed25519 device keys (Keychain-backed on iOS).
2. Persist approvals + add expiry sweeping for the durable store.
3. Expand the real action catalog (calendar, email draft) behind per-tool consent.
4. Add rate limiting + structured request logging for networked deployments.
