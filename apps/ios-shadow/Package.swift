// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "ShadowAgent", platforms: [.iOS(.v17)], products: [.library(name: "ShadowAgent", targets: ["ShadowAgent"])], targets: [.target(name: "ShadowAgent", path: "Sources/ShadowAgent")])
