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
    func ask(_ prompt: String) async throws -> String {
        let path = "/agent/ask"
        let body = try JSONSerialization.data(withJSONObject: ["prompt": prompt, "provider": "local_mock"])
        var request = URLRequest(url: settings.baseURL.appending(path: path)); request.httpMethod = "POST"; request.httpBody = body; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let signed = try KeychainDeviceIdentity.shared.sign(method: "POST", path: path, body: body)
        request.setValue(signed.deviceID, forHTTPHeaderField: "X-Shadow-Device-Id"); request.setValue(signed.nonce, forHTTPHeaderField: "X-Shadow-Nonce"); request.setValue(signed.timestamp, forHTTPHeaderField: "X-Shadow-Timestamp"); request.setValue(signed.signature, forHTTPHeaderField: "X-Shadow-Signature")
        let (data, _) = try await URLSession.shared.data(for: request)
        let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return obj?["answer"] as? String ?? "Shadow Node returned an empty answer."
    }
    func pair(code: String) async throws {}
    func approvals() async throws -> [ApprovalRequest] { [] }
}
