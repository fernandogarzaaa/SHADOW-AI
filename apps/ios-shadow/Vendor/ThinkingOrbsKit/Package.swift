// swift-tools-version: 5.9
import PackageDescription

// Vendored from https://github.com/Jakubantalik/Libraries.dev
// (packages/thinking-orbs/ports/ios/ThinkingOrbsKit) at commit
// ea001e3469e810e8a3e42df072cdb61e4a10c5ef. MIT, see LICENSE.
// Pinned by vendoring because upstream only offers a branch-tracking package.
let package = Package(
    name: "ThinkingOrbsKit",
    platforms: [.iOS(.v15), .macOS(.v12)],
    products: [
        .library(name: "ThinkingOrbsKit", targets: ["ThinkingOrbsKit"])
    ],
    targets: [
        .target(name: "ThinkingOrbsKit")
    ]
)
