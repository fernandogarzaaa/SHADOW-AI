/// SwiftPM shim used by non-Xcode CI environments.
/// The runnable iOS application target is `ShadowAgentApp` in `ShadowAgent.xcodeproj`.
public enum ShadowAgentPackageShim {
    public static let target = "ShadowAgentApp"
}
