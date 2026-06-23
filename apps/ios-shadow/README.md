# Shadow Agent iOS

Open `ShadowAgent.xcodeproj` in Xcode. The `ShadowAgentApp` target is intended for iOS 17+ simulator runs.

## Modes
- Local mock mode is default.
- Real node mode points to `SHADOW_NODE_URL` or `http://127.0.0.1:8787`.

## Screens
Home, Ask Shadow, Memory, Memory Detail, Approvals, Approval Detail, Devices, Pair Device, Audit Log, Privacy Dashboard, Autonomy Settings, Connector Settings, Model Provider Settings, Emergency Pause.

## Secrets
`KeychainSecretStore` is the Keychain-backed seam for pairing/session secrets; the beta placeholder uses app-local persistence in this repo and must be swapped for full Keychain item attributes before distribution.
