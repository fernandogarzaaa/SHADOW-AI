// swift-tools-version: 5.9
import PackageDescription

// This package intentionally builds a tiny cross-platform shim so Linux CI can
// validate the repository without attempting to compile UIKit/SwiftUI/Security
// iOS app sources. Open `ShadowAgent.xcodeproj` for the real iOS app target.
let package = Package(
    name: "ShadowAgent",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [.library(name: "ShadowAgentPackageShim", targets: ["ShadowAgentPackageShim"])],
    targets: [.target(name: "ShadowAgentPackageShim", path: "PackageSupport")]
)
