# Shadow Node — Production Runbook

Minimal, accurate steps to run the node in a real deployment.

## 1. Configure
Copy `.env.example` to `.env` and set, at minimum:

```bash
SHADOW_AUTH_REQUIRED=true                 # enforce signed requests on protected routes
SHADOW_DATA_DIR=/var/lib/shadow           # key files go to $SHADOW_DATA_DIR/keys (created 0600)
SHADOW_MEMORY_DB=/var/lib/shadow/memory.db
SHADOW_RUNTIME_DB=/var/lib/shadow/runtime.db   # devices, approvals, audit, nonces survive restarts
# SHADOW_BOOTSTRAP_CODE=...               # optional: pin the first-owner setup code (headless installs)
# SHADOW_REQUIRE_SIG_V2=true              # once every client signs with v2
```

To enable real Claude answers (optional — node works fully offline without this):

```bash
SHADOW_CLOUD_ENABLED=true
SHADOW_MODEL_PROVIDER=anthropic
SHADOW_MODEL_NAME=claude-opus-5-5
ANTHROPIC_API_KEY=sk-ant-...              # never commit this
```

Cloud answers are still gated **per request** by an active `cloud_redacted`
consent grant **and** explicit `cloud_approval`. Without those the node stays local.

## 2. Run

```bash
docker compose up --build        # or, from a checkout:
pip install .
uvicorn shadow_node.main:app --host 0.0.0.0 --port 8787
```

Mount a persistent volume for `SHADOW_DATA_DIR` (the Docker image uses `/data`)
so memory, devices and the keys survive restarts and rebuilds. The image runs as
an unprivileged user and contains no key material.

## 2b. Pair the first device
On a fresh node the log shows a single-use setup code:

```
SHADOW BOOTSTRAP CODE: 1A2B-3C4D  (single use; pair your first device with it)
```

Open the dashboard (`http://<node>:8787/`) and enter it, or use it from the iOS
app. That device becomes the owner; later devices are approved from Devices.

## 3. Verify
- `GET /health` → liveness `{"auth_required": true, "version": "0.1.0", "bootstrap_open": false}`.
- `GET /ready` → readiness probe (200 ready / 503 degraded) with effective config:
  `rate_limit_rpm`, `grounding_verify`, `providers_ready`. Wire this to your
  orchestrator's readiness check (the Docker image also ships a `HEALTHCHECK`).
- `GET /model/providers` → confirm `cloud_model_ready` matches intent.
- With auth on, unsigned requests to protected routes return `401`.

## Operational hardening (built in)
- **Rate limiting:** `SHADOW_RATE_LIMIT_RPM` (per-client token bucket; `/health`
  and `/ready` exempt). Over-limit requests get `429`.
- **Structured logging:** every request logs one JSON line (`method`, `path`,
  `status`, `ms`, `client`) to stdout — scrape with your log pipeline.
- **Draft-then-verify:** `SHADOW_GROUNDING_VERIFY=true` retries a poorly-grounded
  frontier answer once against the full context before returning it.

## 4. Security checklist before exposing publicly
- [ ] `SHADOW_AUTH_REQUIRED=true`
- [ ] Persistent `SHADOW_DATA_DIR` (keys, memory and runtime DBs) on a backed-up volume
- [ ] First owner paired (`/health` reports `bootstrap_open: false`)
- [ ] CORS origins reviewed (defaults to localhost only)
- [ ] API key supplied via secret manager / env, never in the image
- [ ] TLS terminated by a reverse proxy in front of the node
- [ ] Reverse-proxy rate limiting enabled

## Known limitations (see PROJECT_AUDIT_2026-06.md)
- GHOST action execution is still mocked.
- Device/consent/approval runtime state is in-memory (lost on restart); memory persists.
