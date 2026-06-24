# Shadow — Native app (React Native + Expo)

Production-ready native iOS/Android app for the Shadow Node, built with React
Native (Expo) and `@react-navigation`. Same minimalist design as the web/PWA
clients; same local-first privacy model.

## Features
- **Ask** — query local memory; shows route (on-device vs frontier), sources, token savings, grounding.
- **Memory** — ingest + search encrypted memory.
- **Actions** — run sandboxed actions (note/reminder/http) through the approval gate.
- **Models** — connect frontier providers (Anthropic/OpenAI/Gemini) by API key.
- **Approvals** — approve/deny pending high-impact actions.
- **Audit** — recent decisions.
- **Settings** — point the app at your node (LAN address), test connection.
- Live node status + emergency-pause toggle.

## Develop
```bash
cd apps/native
npm install
npx expo start            # press i (iOS sim) / a (Android) / scan QR with Expo Go
```
On a physical device, open **Settings** in the app and set your node's LAN URL
(e.g. `http://192.168.1.20:8787`) — `localhost` only works in a simulator.

## Production builds (App Store / Play Store)
Uses [EAS Build](https://docs.expo.dev/build/introduction/):
```bash
npm i -g eas-cli
eas login
eas init                      # sets the EAS projectId in app.json
eas build -p ios --profile production
eas build -p android --profile production
eas submit -p ios             # or -p android
```
Bundle identifiers: `ai.shadowagent.app` (iOS & Android). Bump `ios.buildNumber`
/ `android.versionCode` (or use the `autoIncrement` production profile).

## Store submission
- Privacy: see `store/PRIVACY_POLICY.md` (host it and link it in the listings).
- Listing copy + data-collection answers: `store/STORE_LISTING.md`.
- Pre-flight: `store/RELEASE_CHECKLIST.md`.

## Privacy & security posture
- No analytics, no trackers, no ad SDKs. The only network egress is to the Shadow
  Node URL the user configures.
- No secrets are bundled. Provider API keys are entered at runtime and stored
  **on the node** (encrypted), never in the app binary.
- iOS `ITSAppUsesNonExemptEncryption=false` (uses only standard HTTPS).
