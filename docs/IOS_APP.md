# IOS APP

Phase 4 wires the SwiftUI app to the local Shadow Node. The app includes a configurable node URL, local mock mode, real node mode, Keychain-backed device identity storage, HMAC signed requests, pairing UX, memory ingestion/search, Ask Shadow, approvals, safe execution, audit log, and emergency pause controls.

## Screens
Home, Ask Shadow, Memory, Memory Detail, Approvals, Approval Detail, Devices, Pair Device, Audit Log, Privacy Dashboard, Autonomy Settings, Connector Settings, Model Provider Settings, Emergency Pause.

## Build validation
The container does not include Xcode. Open `apps/ios-shadow/ShadowAgent.xcodeproj`, select `ShadowAgentApp`, and run on an iOS 17+ simulator to validate target membership, signing, assets, and launch screen.
