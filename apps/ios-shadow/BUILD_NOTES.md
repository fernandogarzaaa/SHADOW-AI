# iOS Build Notes

## Build and run
1. Open `apps/ios-shadow/ShadowAgent.xcodeproj` in Xcode (verified with the current Xcode on macOS).
2. Select the `ShadowAgentApp` scheme and an iOS 17+ simulator.
3. Optional: set `SHADOW_NODE_URL` in the scheme's environment to pre-fill the node address.
4. Build and run. To pair from a phone, start the node with `SHADOW_HOST=0.0.0.0` and use the computer's LAN address.

Command line (no signing):
```bash
xcodebuild -project ShadowAgent.xcodeproj -scheme ShadowAgentApp \
  -destination 'platform=iOS Simulator,name=iPhone 18 Pro' build CODE_SIGNING_ALLOWED=NO
```

## Pairing
- First device on a new node: enter the setup code printed in the node's terminal (`SHADOW BOOTSTRAP CODE`). The device becomes the owner.
- Later devices: leave the code empty; the app shows a 6-character code and waits until you approve it from a paired device (dashboard → Devices).
- Requests are signed with signature v2 (`ShadowRequestSigner`), which also covers the query string.

## Tests
`swift test` runs the signer against the node's shared vectors (`tests/fixtures/sig_v2_vectors.json`). It compiles `Services/DeviceIdentityStore.swift` directly, so the tested code is the app's code. CryptoKit and Security are Apple-only, so this needs macOS.

## Mock mode
Debug builds only, and only with `SHADOW_MOCK_MODE=true` in the scheme environment. Release builds always talk to a real node.

## Not done yet
- Signing team, entitlements, privacy manifest and app icons for device/TestFlight builds.
- Share Extension, App Intents and background refresh (see `Intents/ShadowAppIntentPlan.swift`).
