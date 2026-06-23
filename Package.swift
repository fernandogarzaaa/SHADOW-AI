// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "SHADOW-AI",
    platforms: [
        .iOS(.v17),
        .macOS(.v14)
    ],
    products: [
        .library(name: "ShadowAgentCore", targets: ["ShadowAgentCore"])
    ],
    targets: [
        .target(name: "ShadowAgentCore"),
        .testTarget(name: "ShadowAgentCoreTests", dependencies: ["ShadowAgentCore"])
    ]
)
