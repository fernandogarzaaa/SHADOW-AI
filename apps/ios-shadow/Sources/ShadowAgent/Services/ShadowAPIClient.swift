import Foundation
protocol ShadowAPIClient { func health() async throws -> Bool; func ask(_ prompt: String) async throws -> String; func approve(id: UUID) async throws }
struct LocalMockShadowAPIClient: ShadowAPIClient {
    func health() async throws -> Bool { true }
    func ask(_ prompt: String) async throws -> String { "Local-first response for: \(prompt)" }
    func approve(id: UUID) async throws {}
}
