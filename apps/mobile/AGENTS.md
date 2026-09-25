# Mobile Package - AI Agent Reference

**Role:** SHADOW mobile app (Expo 54, React Native 0.81). Approval-first ambient agent: the phone supervises intelligence running on the Shadow Node. Forked from the opencode-mobile template; rewired to the SHADOW node API (HMAC auth, SSE streams, approvals inbox).

## Overview

Native iOS + Android app built with Expo 54 and React Native 0.81. Connects to the Shadow Node via HMAC-signed HTTP + SSE. Approvals inbox is the primary screen; chat is second.

## Structure

```
app/                       # Expo Router (file-based routing)
├── _layout.tsx           # Root: gesture handler, safe area, theme, app-lock gate
├── index.tsx             # Entry: redirects to onboarding or /(tabs)/approvals
├── (tabs)/               # Tab navigation (Approvals first)
│   ├── _layout.tsx       # Tab container, initialRouteName="approvals"
│   ├── approvals.tsx     # Approvals inbox (the killer screen)
│   ├── chat.tsx          # Streaming chat via /agent/ask_stream
│   ├── diff.tsx          # Diff viewer tab
│   └── files.tsx         # Files tab
├── approvals/[id].tsx    # Approval detail: preview, risk, approve/deny
├── onboarding/           # Node pairing flow
│   ├── scan.tsx          # QR scanner ({"v":1,"url","pairing_id"})
│   └── manual.tsx        # Manual URL + pairing code entry
└── settings/             # Settings: node URL, device info, push, app lock, sign out
    ├── index.tsx
    └── node-url.tsx

src/
├── api/shadow.ts         # Typed node client (shadowFetch, approvals, askAgentStream)
├── lib/
│   ├── shadowSigner.ts   # Pure-TS HMAC-SHA256 signer + x-shadow-* auth headers
│   ├── sseParse.ts       # SSE chunk parser (data: JSON envelopes)
│   └── notifications.ts  # expo-notifications: permission, token, /devices/{id}/push-token
├── hooks/
│   ├── useShadowEventStream.ts  # HMAC-authed GET /agent/stream, backoff reconnect
│   └── useChatStream.ts  # POST /agent/ask_stream progressive deltas
├── stores/
│   ├── useConnectionStore.ts  # nodeUrl, deviceId, deviceSecret (SecureStore)
│   └── useApprovalsStore.ts   # Pending approvals, live SSE apply, optimistic decide
├── components/approvals/ # Inbox list, detail, risk badges, confirm sheets
└── theme/vendor/         # Vendored theme values (no workspace dep)
```

## Node auth contract (do not break)

HMAC-SHA256, required on every endpoint except `/pair/*` and `/health`.
Signature = lowercase hex of HMAC-SHA256(shared_secret, `"METHOD\npath\nbody\nnonce\ntimestamp"`).
METHOD uppercase; **path is the URL path only, no query string** (the node signs `request.url.path`, so `shadowFetch` strips `?...` before signing); body is the raw request body string (`""` for GET); nonce is random hex per request; timestamp is unix seconds (server allows +-300s skew). Headers: `x-shadow-device-id`, `x-shadow-signature`, `x-shadow-nonce`, `x-shadow-timestamp`. Test vector: secret `s3cr3t`, `GET /devices` with nonce `abc123` ts `1700000000` signs the exact string `"GET\n/devices\n\nabc123\n1700000000"`.

## SSE contract

`GET /agent/stream` emits `data: {"type","properties"}` lines; `:heartbeat` comments every ~25s (ignored). Events: `node.hello`, `approval.created`, `approval.updated`. `POST /agent/ask_stream` emits `agent.message.delta` then `agent.message.done`.

## Native modules used

| Module | Purpose |
|--------|---------|
| `expo-secure-store` | device_id + shared_secret (never AsyncStorage) |
| `expo-local-authentication` | App lock gate in `app/_layout.tsx` |
| `expo-notifications` | Approval push; token registered via POST /devices/{id}/push-token |
| `expo-camera` | QR pairing scanner |
| `expo-haptics` | Approve/deny feedback |

## Branding and build

- App name: SHADOW. Deep-link scheme: `shadow://`.
- Bundle IDs: `ai.shadow.app` (iOS + Android); `.dev` / `.preview` variants for dev builds.
- `eas.json` profiles: development / preview / production. `extra.eas.projectId` is `TODO-inan-eas-project-id` until Inan creates the EAS project under his account.
- Web is not a ship target (iOS/Android via EAS).

## Conventions

- Approvals inbox is the primary screen; keep it first in tab order.
- No stubs or TODOs in shipped code; every behavior must be real.
- Secrets in SecureStore only; friendly error strings, no em dashes in user-facing copy.
- Verify with `npx tsc --noEmit` in `apps/mobile` (must be exit 0).
