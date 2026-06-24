# Shadow Agent iOS

Open `ShadowAgent.xcodeproj` in Xcode. The required target is `ShadowAgentApp` for iOS 17+ simulator testing.

## Tester flow
1. Start Shadow Node with `make run` from the repo root.
2. Open the app and set the node URL to `http://127.0.0.1:8787`.
3. Disable mock mode.
4. Pair from Devices / Pair.
5. Ingest user-approved pasted text from Memory.
6. Ask a question from Ask Shadow.
7. Review sources and why explanations.
8. Create/approve/deny/execute proposals from Approvals.
9. Toggle Emergency Pause and confirm execution is blocked.
10. Review Audit Log.

## Modes
- Local mock mode is available for screenshots and offline testing.
- Real node mode signs requests with the paired device session secret.

## Secure identity
The app stores device ID, node fingerprint, public key metadata, and HMAC session secret in `KeychainDeviceIdentityStore`. Requests include `x-shadow-device-id`, `x-shadow-signature`, `x-shadow-nonce`, and `x-shadow-timestamp`.

## Build notes
See `BUILD_NOTES.md`. Xcode is not available in the CI/container environment used by this agent, so local macOS validation is required before TestFlight.
