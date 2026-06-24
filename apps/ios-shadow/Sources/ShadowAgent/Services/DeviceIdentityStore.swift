import Foundation
import Security
import CryptoKit

struct DeviceIdentity: Codable { var deviceId: String; var sharedSecret: String; var nodeFingerprint: String; var publicKey: String; var baseURL: URL }
protocol DeviceIdentityStoring { func load() -> DeviceIdentity?; func save(_ identity: DeviceIdentity); func reset() }
final class KeychainDeviceIdentityStore: DeviceIdentityStoring {
    private let service = "ai.shadow.agent.deviceIdentity"; private let account = "pairedNode"
    func load() -> DeviceIdentity? { guard let data = readData() else { return nil }; return try? JSONDecoder().decode(DeviceIdentity.self, from: data) }
    func save(_ identity: DeviceIdentity) { if let data = try? JSONEncoder().encode(identity) { writeData(data) } }
    func reset() { let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account]; SecItemDelete(query as CFDictionary) }
    private func readData() -> Data? { let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]; var item: CFTypeRef?; SecItemCopyMatching(query as CFDictionary, &item); return item as? Data }
    private func writeData(_ data: Data) { reset(); let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account, kSecValueData as String: data, kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]; SecItemAdd(query as CFDictionary, nil) }
}
struct ShadowRequestSigner {
    func headers(identity: DeviceIdentity, method: String, path: String, body: Data) -> [String: String] {
        let nonce = UUID().uuidString; let ts = String(Int(Date().timeIntervalSince1970)); let bodyString = String(data: body, encoding: .utf8) ?? ""; let message = [method.uppercased(), path, bodyString, nonce, ts].joined(separator: "\n")
        let key = SymmetricKey(data: Data(identity.sharedSecret.utf8)); let mac = HMAC<SHA256>.authenticationCode(for: Data(message.utf8), using: key); let signature = mac.map { String(format: "%02x", $0) }.joined()
        return ["x-shadow-device-id": identity.deviceId, "x-shadow-nonce": nonce, "x-shadow-timestamp": ts, "x-shadow-signature": signature]
    }
}
