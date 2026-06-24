# Shadow PWA (React Native + Expo)

A production-ready, installable **Progressive Web App** for the Shadow Node,
built from a single **React Native** codebase via **Expo + react-native-web**.

> Why this stack: a PWA is a web app; React Native targets native. Expo's
> `react-native-web` renderer bridges them — one RN codebase that exports a
> static, installable PWA (manifest + service worker) **and** can also run as a
> native iOS/Android app (`expo run:ios` / `run:android`).

## Features (mirrors the node dashboard)
- **Ask** — query local memory; shows route (on-device vs frontier), sources, token savings, grounding.
- **Memory** — ingest + search encrypted memory.
- **Actions** — run sandboxed actions (note/reminder/http) through the approval gate.
- **Models** — connect frontier providers (Anthropic/OpenAI/Gemini) by API key.
- **Approvals** — approve/deny pending high-impact actions.
- **Audit** — recent decisions.
- Live node status + emergency-pause toggle.

## Develop
```bash
cd apps/pwa
npm install
npx expo start --web      # dev server
```
Point it at your node by setting the base URL (defaults to the serving origin,
else `http://localhost:8787`).

## Build the installable PWA
```bash
npx expo export -p web     # -> dist/ (static, installable)
npx serve dist             # or any static host / the Shadow Node behind a proxy
```
The build emits `dist/` with `index.html`, the JS bundle, `manifest.json`,
`sw.js`, and icons. Visiting it offers "Install app"; the service worker caches
the app shell for offline launch.

## Native (optional)
The same codebase runs natively:
```bash
npx expo run:ios          # or run:android  (needs Xcode / Android SDK)
```

## Notes
- API calls go to the Shadow Node; configure CORS / reverse proxy for production.
- No secrets are bundled — provider API keys are entered at runtime and stored on the node (encrypted).
