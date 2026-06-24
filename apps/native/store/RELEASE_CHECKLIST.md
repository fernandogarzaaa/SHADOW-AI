# Release checklist (public store submission)

## Identity & versioning
- [ ] `ios.bundleIdentifier` / `android.package` registered (`ai.shadowagent.app`).
- [ ] `version` bumped; `ios.buildNumber` / `android.versionCode` incremented
      (or use the `production` EAS profile's `autoIncrement`).
- [ ] `eas init` run so `extra.eas.projectId` is set.

## Assets
- [ ] App icon 1024×1024 (no alpha for iOS) — `assets/icon.png`.
- [ ] Adaptive icon (Android) — `assets/android-icon-*`.
- [ ] Splash — `assets/splash-icon.png`, background `#0b0c0e`.
- [ ] Screenshots for each required device size (capture from a real build).

## Privacy & compliance
- [ ] Privacy policy hosted; URL added to both stores and `STORE_LISTING.md`.
- [ ] App Privacy answers entered (iOS) — "Data Not Collected".
- [ ] Data Safety form completed (Android) — no collection/sharing.
- [ ] `ITSAppUsesNonExemptEncryption=false` confirmed (standard HTTPS only).
- [ ] Account deletion path documented (handled on the node).

## Build & test
- [ ] `npx tsc --noEmit` clean.
- [ ] `eas build -p ios --profile production` succeeds.
- [ ] `eas build -p android --profile production` succeeds.
- [ ] Smoke test against a real node: Ask, Memory, Actions+approval, Models,
      Audit, emergency pause, Settings (LAN URL).
- [ ] Verify no secrets in the binary and only the configured node is contacted.

## Submit
- [ ] `eas submit -p ios` / `-p android`.
- [ ] TestFlight / internal testing pass before production release.
