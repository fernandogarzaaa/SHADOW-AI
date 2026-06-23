import Foundation
protocol ShadowAPIClient { func health() async throws -> Bool; func ask(_ prompt: String) async throws -> String; func pair(code: String) async throws; func approvals() async throws -> [ApprovalRequest] }
struct ShadowNodeSettings: Codable { var baseURL: URL = URL(string: "http://127.0.0.1:8787")!; var localMockMode: Bool = true }
struct LocalMockShadowAPIClient: ShadowAPIClient {
    func health() async throws -> Bool { true }
    func ask(_ prompt: String) async throws -> String { "Local-first response for: \(prompt)" }
    func pair(code: String) async throws {}
    func approvals() async throws -> [ApprovalRequest] { [] }
}
struct HTTPShadowAPIClient: ShadowAPIClient {
    var settings: ShadowNodeSettings
    func health() async throws -> Bool { let (_, response) = try await URLSession.shared.data(from: settings.baseURL.appending(path: "health")); return (response as? HTTPURLResponse)?.statusCode == 200 }
    func ask(_ prompt: String) async throws -> String { "HTTP client scaffold ready for /agent/ask" }
    func pair(code: String) async throws {}
    func approvals() async throws -> [ApprovalRequest] { [] }
}
