import Foundation
import Security

protocol SecretStore {
    func set(_ value: String, for key: String) throws
    func get(_ key: String) throws -> String?
    func delete(_ key: String) throws
}

enum KeychainError: Error {
    case encodeFailed
    case unexpectedData
    case unhandledStatus(OSStatus)
}

/// Real Keychain-backed secret store. Device HMAC secrets and push tokens
/// live in the Keychain (kSecClassGenericPassword, accessible after first
/// unlock on this device only), never in UserDefaults.
struct KeychainSecretStore: SecretStore {
    private let service = "ai.shadow.node"

    private func query(for key: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
    }

    func set(_ value: String, for key: String) throws {
        guard let data = value.data(using: .utf8) else {
            throw KeychainError.encodeFailed
        }
        var q = query(for: key)
        let status = SecItemCopyMatching(q as CFDictionary, nil)
        if status == errSecSuccess {
            let attrs: [String: Any] = [kSecValueData as String: data]
            let updateStatus = SecItemUpdate(q as CFDictionary, attrs as CFDictionary)
            guard updateStatus == errSecSuccess else {
                throw KeychainError.unhandledStatus(updateStatus)
            }
            return
        }
        guard status == errSecItemNotFound else {
            throw KeychainError.unhandledStatus(status)
        }
        q[kSecValueData as String] = data
        q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(q as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw KeychainError.unhandledStatus(addStatus)
        }
    }

    func get(_ key: String) throws -> String? {
        var q = query(for: key)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &item)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else {
            throw KeychainError.unhandledStatus(status)
        }
        guard let data = item as? Data, let value = String(data: data, encoding: .utf8) else {
            throw KeychainError.unexpectedData
        }
        return value
    }

    func delete(_ key: String) throws {
        let status = SecItemDelete(query(for: key) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unhandledStatus(status)
        }
    }
}

struct ShadowEnvironment { var apiBaseURL: URL = URL(string: ProcessInfo.processInfo.environment["SHADOW_NODE_URL"] ?? "http://127.0.0.1:8787")!; var mockMode: Bool = ProcessInfo.processInfo.environment["SHADOW_MOCK_MODE"] != "false" }
