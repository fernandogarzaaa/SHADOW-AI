import Foundation
import CryptoKit
import Security

struct SignedShadowRequest {
    let deviceID: String
    let nonce: String
    let timestamp: String
    let signature: String
}

final class KeychainDeviceIdentity {
    static let shared = KeychainDeviceIdentity()
    private let service = "ai.shadow.device.identity"

    func storedDeviceID() -> String? { UserDefaults.standard.string(forKey: "shadow.deviceID") }
    func storeDeviceID(_ id: String) { UserDefaults.standard.set(id, forKey: "shadow.deviceID") }

    func signingKey() throws -> Curve25519.Signing.PrivateKey {
        if let data = read(account: "signingKey") { return try Curve25519.Signing.PrivateKey(rawRepresentation: data) }
        let key = Curve25519.Signing.PrivateKey()
        try write(key.rawRepresentation, account: "signingKey")
        return key
    }

    func publicKeyBase64URL() throws -> String { try signingKey().publicKey.rawRepresentation.base64URLEncodedString() }

    func signPairingConfirmation(pairingID: String, challenge: String, nonce: String) throws -> String {
        let payload = "\(pairingID):\(challenge):\(nonce)"
        return try signingKey().signature(for: Data(payload.utf8)).base64URLEncodedString()
    }

    func sign(method: String, path: String, body: Data) throws -> SignedShadowRequest {
        guard let deviceID = storedDeviceID() else { throw URLError(.userAuthenticationRequired) }
        let nonce = UUID().uuidString.replacingOccurrences(of: "-", with: "")
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let payload = [method.uppercased(), path, String(data: body, encoding: .utf8) ?? "", nonce, timestamp].joined(separator: "\n")
        let sig = try signingKey().signature(for: Data(payload.utf8)).base64URLEncodedString()
        return SignedShadowRequest(deviceID: deviceID, nonce: nonce, timestamp: timestamp, signature: sig)
    }

    private func read(account: String) -> Data? {
        let q: [String: Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:service, kSecAttrAccount as String:account, kSecReturnData as String:true]
        var item: CFTypeRef?; return SecItemCopyMatching(q as CFDictionary, &item) == errSecSuccess ? item as? Data : nil
    }
    private func write(_ data: Data, account: String) throws {
        let q: [String: Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:service, kSecAttrAccount as String:account]
        SecItemDelete(q as CFDictionary)
        var item = q; item[kSecValueData as String] = data; item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(item as CFDictionary, nil); if status != errSecSuccess { throw URLError(.cannotCreateFile) }
    }
}

private extension Data { func base64URLEncodedString() -> String { self.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") } }
