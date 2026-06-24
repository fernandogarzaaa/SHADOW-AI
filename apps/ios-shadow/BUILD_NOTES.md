# iOS Build Notes

Open `Package.swift` in Xcode on macOS. Select the ShadowAgent executable target, choose an iOS simulator or signed physical-device destination, and build. The Linux CI environment cannot validate Xcode builds. Configure the node URL in settings; local HTTP node usage may require App Transport Security exceptions for development LAN hosts. Device signing keys are generated and stored in Keychain.
