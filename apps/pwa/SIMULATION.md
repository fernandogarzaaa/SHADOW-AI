# New-user simulation — verification (not just tests)

We verify production-readiness by **driving a live node with the app's own
pairing + request-signing code** (`src/auth.ts`), exactly as a brand-new user
would, against a node with authentication **enabled**.

## Run it yourself
```bash
# 1) start a node with auth on (from repo root)
SHADOW_AUTH_REQUIRED=true GHOST_RUNTIME_MODE=local \
PYTHONPATH=apps/shadow-node:packages/agent-core:packages/memory-engine:packages/axiom-adapter:packages/ghost-adapter \
python -m uvicorn shadow_node.main:app --app-dir apps/shadow-node --port 8799

# 2) run the simulation
cd apps/pwa && SIM_BASE=http://127.0.0.1:8799 npx tsx sim/new-user-sim.ts
```

## What it exercises (12 checks, all passing)
1. Node reachable, reports `auth_required: true`.
2. **Unsigned protected request → 401** (auth is really enforced).
3. **Pairing** (`/pair/start` + `/pair/confirm`) succeeds.
4. **Signed request accepted** (HMAC over `method\npath\nbody\nnonce\ntimestamp`).
5. Consent granted.
6. Memory ingested.
7. Memory search returns the note (signed GET with query string).
8. Ask answered with routing + token-savings + grounding.
9. **Real action** (`note.create`) executes through the approval gate (file written).
10. **Nonce replay rejected** — reusing a signature returns 401 on the 2nd use.
11. Emergency pause + resume.
12. Audit trail recorded pairing / ask / action.

## Static build (install + load)
`npx expo export -p web` → `dist/` serves `index.html` (title "Shadow"),
the JS bundle, `manifest.json`, and `sw.js` (verified `200`). Installable PWA.

## Honest limits
- The simulation drives the **real client code path** (the same `auth.ts` the app
  ships) against a live node — the network/auth/business logic is genuinely
  exercised.
- It does **not** pixel-click a rendered browser (no headless Chromium available
  in this environment) and does **not** run on a physical iOS/Android device.
  Those require a desktop browser / device or EAS build.
