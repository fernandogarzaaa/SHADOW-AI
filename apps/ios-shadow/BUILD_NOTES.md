# iOS Build Notes

## Intended local validation
1. Open `apps/ios-shadow/ShadowAgent.xcodeproj` in Xcode 15+.
2. Select the `ShadowAgentApp` target.
3. Choose an iOS 17+ simulator.
4. Set `SHADOW_NODE_URL=http://127.0.0.1:8787` if running against the local node.
5. Build and run.

## Container limitation
This Linux container does not include Xcode or `xcodebuild`, so simulator build/run cannot be truthfully validated here. The Swift source has been organized to be simulator-oriented, but final target membership and signing should be normalized in Xcode on macOS.

## Known Xcode limitations
- The project file is maintained manually in this repository and may be rewritten by Xcode on first open.
- Production signing, entitlements, privacy manifests, and asset catalog icons still require macOS/Xcode validation.
- Document picker upload is described and manual paste ingestion is wired; full security-scoped document picker upload should be validated on simulator/device.
