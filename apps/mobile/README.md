# SHADOW Mobile

SHADOW mobile is the approval-first ambient agent app. Your phone supervises
your Shadow Node: it receives approval requests as push notifications, lets
you approve or reject them (gated behind Face ID), and keeps you paired to
your node over an authenticated HMAC channel.

The client lives in `apps/mobile` of the SHADOW-AI repo. Work on the mobile
client happens on feature branches (for example `claude/expo-client`); the
coordinator merges after review.

## Prerequisites

- Node 20+
- bun or npm
- EAS CLI (`npm i -g eas-cli`)
- An Expo account (needed for builds and push notifications)

## Install

```bash
cd apps/mobile
bun install
```

## Run (development)

```bash
bunx expo start
```

Scan the QR code with Expo Go, or open the onboarding flow in the app at
`app/onboarding/scan` and pair against your Shadow Node.

## Pairing contract

The node exposes its pairing payload as JSON for the QR code:

```json
{"v":1,"url":"http://<node-host>:8000","pairing_id":"<code from POST /pair/start>"}
```

Manual entry works too: type the node URL and the pairing code shown after
calling `POST /pair/start` on the node.

### Auth scheme

Every node endpoint except `/pair/*` and `/health` requires HMAC-SHA256
headers: `x-shadow-device-id`, `x-shadow-signature`, `x-shadow-nonce`,
`x-shadow-timestamp`. The signature is
`hex(HMAC-SHA256(secret, "METHOD\npath\nbody\nnonce\ntimestamp"))`.
The device secret lives in SecureStore under `shadow_device_secret` and is
never logged or pasted into docs. See `src/lib/shadowSigner.ts` for the
signing implementation.

## Push notifications

Push is how approval alerts reach you. Setup steps:

1. Replace `TODO-inan-eas-project-id` in `app.config.js` (field
   `extra.eas.projectId`) with the EAS project id from the Expo dashboard.
2. In the Expo dashboard, configure FCM (Android) and APNs (iOS) credentials
   for the project.
3. Build the app with `eas build` (Expo Go cannot receive real push tokens).
4. After pairing, the app registers its Expo push token at
   `POST /devices/{id}/push-token` automatically. Tokens must start with
   `ExponentPushToken[` or the node rejects them.

The implementation lives in `src/lib/notifications.ts`. Registration is
defensive: it silently returns `false` when not paired, when permission is
denied, when no project id is configured, or when the network call fails,
so pairing never breaks because push is unavailable.

## Build commands

```bash
eas build --profile development --platform ios   # dev client, internal
eas build --profile preview                      # internal test build (ios + android)
eas build --profile production --platform all    # store build (ios + android)
```

Profiles are defined in `eas.json`. Android builds produce an APK for
development/preview and an app bundle (AAB) for production.

## TestFlight / Play submission

Inan handles the Apple Developer Program and Play Console accounts, signing
certificates, and the actual store submissions. Privacy policy ownership is
his as well. The `eas submit` command uses the `production` profile defined
in `eas.json`.

## Project layout

- `app/` : Expo Router screens (`onboarding/`, tabs, settings)
- `src/lib/notifications.ts` : push permission, token, node registration
- `src/lib/shadowSigner.ts` : HMAC request signing
- `src/api/shadow.ts` : node API client
- `src/stores/useConnectionStore.ts` : pairing state (device id, node URL)
- `assets/` : SHADOW-branded icons, splash, notification icon
