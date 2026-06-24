import Foundation
import Security
protocol SecretStore { func set(_ value: String, for key: String) throws; func get(_ key: String) throws -> String? }
struct KeychainSecretStore: SecretStore {
    func set(_ value: String, for key: String) throws { UserDefaults.standard.set(value, forKey: "keychain-placeholder-\(key)") }
    func get(_ key: String) throws -> String? { UserDefaults.standard.string(forKey: "keychain-placeholder-\(key)") }
}
struct ShadowEnvironment { var apiBaseURL: URL = URL(string: ProcessInfo.processInfo.environment["SHADOW_NODE_URL"] ?? "http://127.0.0.1:8787")!; var mockMode: Bool = ProcessInfo.processInfo.environment["SHADOW_MOCK_MODE"] != "false" }
