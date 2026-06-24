# Shadow Node — Production Runbook

Minimal, accurate steps to run the node in a real deployment.

## 1. Configure
Copy `.env.example` to `.env` and set, at minimum:

```bash
SHADOW_AUTH_REQUIRED=true                 # enforce signed requests on protected routes
SHADOW_MEMORY_DB=/var/lib/shadow/memory.db
SHADOW_MEMORY_KEY_FILE=/var/lib/shadow/keys/memory.key   # generated 0600 if absent
```

To enable real Claude answers (optional — node works fully offline without this):

```bash
SHADOW_CLOUD_ENABLED=true
SHADOW_MODEL_PROVIDER=anthropic
SHADOW_MODEL_NAME=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...              # never commit this
```

Cloud answers are still gated **per request** by an active `cloud_redacted`
consent grant **and** explicit `cloud_approval`. Without those the node stays local.

## 2. Run

```bash
docker compose up --build        # or:
uvicorn shadow_node.main:app --app-dir apps/shadow-node --host 0.0.0.0 --port 8787
```

Mount a persistent volume for `SHADOW_MEMORY_DB` and the key file so memory and
the encryption key survive restarts.

## 3. Verify
- `GET /health` → `{"auth_required": true, "version": "1.0.0-rc"}`.
- `GET /model/providers` → confirm `cloud_model_ready` matches intent.
- With auth on, unsigned requests to protected routes return `401`.

## 4. Security checklist before exposing publicly
- [ ] `SHADOW_AUTH_REQUIRED=true`
- [ ] Persistent `SHADOW_MEMORY_DB` + key file on a backed-up volume
- [ ] CORS origins reviewed (defaults to localhost only)
- [ ] API key supplied via secret manager / env, never in the image
- [ ] TLS terminated by a reverse proxy in front of the node
- [ ] Reverse-proxy rate limiting enabled

## Known limitations (see PROJECT_AUDIT_2026-06.md)
- GHOST action execution is still mocked.
- Device/consent/approval runtime state is in-memory (lost on restart); memory persists.
