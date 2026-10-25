import CryptoKit
import Foundation
import Security

/// Credentials issued by the node at pairing. Stored in the Keychain only.
struct DeviceIdentity: Codable {
    var deviceId: String
    var sharedSecret: String
    var nodeFingerprint: String
    var publicKey: String
    var baseURL: URL
    var deviceName: String?
    var sessionExpiresAt: String?
}

protocol DeviceIdentityStoring {
    func load() -> DeviceIdentity?
    func save(_ identity: DeviceIdentity)
    func reset()
}

final class KeychainDeviceIdentityStore: DeviceIdentityStoring {
    private let service = "ai.shadow.agent.deviceIdentity"
    private let account = "pairedNode"

    private var baseQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    func load() -> DeviceIdentity? {
        var q = baseQuery
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
        return try? JSONDecoder().decode(DeviceIdentity.self, from: data)
    }

    func save(_ identity: DeviceIdentity) {
        guard let data = try? JSONEncoder().encode(identity) else { return }
        reset()
        var q = baseQuery
        q[kSecValueData as String] = data
        q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(q as CFDictionary, nil)
    }

    func reset() {
        SecItemDelete(baseQuery as CFDictionary)
    }
}

/// 32 random bytes from the system CSPRNG, hex encoded. Proposed to the node
/// at pairing as this install's identity (the node fingerprints it).
enum DevicePublicKey {
    static func generate() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        precondition(status == errSecSuccess, "secure random generator unavailable")
        return bytes.map { String(format: "%02x", $0) }.joined()
    }
}

/// Request signer, signature v2 (must match agent_core.security):
///   HMAC-SHA256(secret, "SHADOW-SIG-v2\nMETHOD\npath\ncanonical_query\nsha256hex(body)\nnonce\ntimestamp\ndevice_id")
/// canonical_query: decoded pairs, RFC 3986 re-encoded, sorted by (key, value),
/// joined with "&". Shared vectors: tests/fixtures/sig_v2_vectors.json.
struct ShadowRequestSigner {
    private static let unreserved = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~")

    static func rfc3986(_ s: String) -> String {
        s.addingPercentEncoding(withAllowedCharacters: unreserved) ?? s
    }

    static func canonicalQuery(_ query: String?) -> String {
        guard let query, !query.isEmpty else { return "" }
        let pairs: [(String, String)] = query.split(separator: "&", omittingEmptySubsequences: true).map { part in
            let kv = part.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            func decode(_ s: Substring) -> String {
                (String(s).replacingOccurrences(of: "+", with: " ").removingPercentEncoding) ?? String(s)
            }
            return (rfc3986(decode(kv[0])), rfc3986(kv.count > 1 ? decode(kv[1]) : ""))
        }
        return pairs.sorted { $0.0 != $1.0 ? $0.0 < $1.0 : $0.1 < $1.1 }
            .map { "\($0.0)=\($0.1)" }
            .joined(separator: "&")
    }

    static func hex<D: Sequence>(_ bytes: D) -> String where D.Element == UInt8 {
        bytes.map { String(format: "%02x", $0) }.joined()
    }

    static func signature(secret: String, method: String, path: String, query: String?, body: Data,
                          nonce: String, timestamp: String, deviceId: String) -> String {
        let message = [
            "SHADOW-SIG-v2", method.uppercased(), path, canonicalQuery(query),
            hex(SHA256.hash(data: body)), nonce, timestamp, deviceId,
        ].joined(separator: "\n")
        let mac = HMAC<SHA256>.authenticationCode(for: Data(message.utf8), using: SymmetricKey(data: Data(secret.utf8)))
        return hex(mac)
    }

    func headers(identity: DeviceIdentity, method: String, url: URL, body: Data) -> [String: String] {
        var nonceBytes = [UInt8](repeating: 0, count: 16)
        _ = SecRandomCopyBytes(kSecRandomDefault, nonceBytes.count, &nonceBytes)
        let nonce = Self.hex(nonceBytes)
        let ts = String(Int(Date().timeIntervalSince1970))
        let comps = URLComponents(url: url, resolvingAgainstBaseURL: true)
        let sig = Self.signature(secret: identity.sharedSecret, method: method, path: comps?.path ?? url.path,
                                 query: comps?.percentEncodedQuery, body: body, nonce: nonce, timestamp: ts,
                                 deviceId: identity.deviceId)
        return [
            "x-shadow-device-id": identity.deviceId,
            "x-shadow-signature-version": "2",
            "x-shadow-nonce": nonce,
            "x-shadow-timestamp": ts,
            "x-shadow-signature": sig,
        ]
    }
}
