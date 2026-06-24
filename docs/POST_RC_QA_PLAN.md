# Post-RC QA Plan

## Completed in this follow-up
- Added stable local key loading for runtime and memory encryption keys using environment variables or local `data/keys/*.key` files.
- Added persistent SQLite nonce tracking so replay protection survives process-local verifier recreation.
- Added real iOS pairing client flow: health check, pair start, signing challenge confirmation, and Keychain storage of paired device ID.

## Still requires macOS
- Open `apps/ios-shadow/Package.swift` in Xcode.
- Build the ShadowAgent target on an iOS simulator.
- Build on a signed physical device.
- Pair against a node running via `make run` on the same LAN.
- Capture TestFlight/App Store screenshots after the simulator/device QA pass.

## Real-node pairing checklist
1. Start the node with `make run`.
2. Open Pair Device in the iOS app.
3. Enter the node URL.
4. Tap Check node health.
5. Tap Pair this device.
6. Ask Shadow from the app and confirm the request is accepted as signed.
7. Revoke the device from the node and confirm subsequent signed requests are rejected.
