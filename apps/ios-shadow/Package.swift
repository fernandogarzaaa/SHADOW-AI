// swift-tools-version: 5.9
import PackageDescription

// The iOS app itself builds from ShadowAgent.xcodeproj (SwiftUI, iOS only).
// This package covers what can be checked without a simulator:
// - ShadowAgentPackageShim: trivial target so Linux CI can resolve the package.
// - ShadowSigning: the request signer, compiled from the app's own source
//   file and tested against the node's shared signature-v2 vectors
//   (`swift test` on macOS; CryptoKit/Security are Apple-only).
let package = Package(
    name: "ShadowAgent",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [.library(name: "ShadowAgentPackageShim", targets: ["ShadowAgentPackageShim"])],
    targets: [
        .target(name: "ShadowAgentPackageShim", path: "PackageSupport"),
        .target(
            name: "ShadowSigning",
            path: "Sources/ShadowAgent/Services",
            sources: ["DeviceIdentityStore.swift"]
        ),
        .testTarget(name: "ShadowSigningTests", dependencies: ["ShadowSigning"], path: "Tests/ShadowSigningTests"),
    ]
)
