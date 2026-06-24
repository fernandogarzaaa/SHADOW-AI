# Shadow Agent iOS

Xcode-ready Swift Package layout for the Shadow Agent command center.

## Run in Xcode
1. Open Xcode 15+.
2. Choose **File > Open Package** and select `apps/ios-shadow/Package.swift`.
3. Create an iOS app scheme if Xcode prompts, using `ShadowAgentApp` as the app entry point.
4. Set the Shadow Node base URL in Settings to `http://127.0.0.1:8787` for simulator-to-Mac demos.

## Screens
Home, Ask Shadow, Memory, Memory Detail, Approvals, Approval Detail, Devices, Pair Device, Audit, Privacy Dashboard, Autonomy Settings, Settings, Onboarding.

## Extension scaffolds
- App Intents: approved ask, emergency pause, memory import.
- Share Extension: user-selected text/file ingestion only.
- BackgroundTasks: heartbeat and approval notifications only.

Screenshots should be placed in `Screenshots/` after simulator capture.
