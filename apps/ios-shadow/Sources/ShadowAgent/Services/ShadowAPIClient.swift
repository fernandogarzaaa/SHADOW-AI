import Foundation

protocol ShadowAPIClient {
    func health() async throws -> Bool
    func ask(_ prompt: String) async throws -> String
    func pair(code: String) async throws
    func approvals() async throws -> [ApprovalRequest]
}

struct ShadowNodeSettings: Codable {
    var baseURL: URL = URL(string: "http://127.0.0.1:8787")!
    var localMockMode: Bool = true
}

struct LocalMockShadowAPIClient: ShadowAPIClient {
    func health() async throws -> Bool { true }
    func ask(_ prompt: String) async throws -> String { "Local-first response for: \(prompt)" }
    func pair(code: String) async throws {}
    func approvals() async throws -> [ApprovalRequest] { [] }
}

struct HTTPShadowAPIClient: ShadowAPIClient {
    var settings: ShadowNodeSettings

    func health() async throws -> Bool {
        let (_, response) = try await URLSession.shared.data(from: settings.baseURL.appending(path: "health"))
        return (response as? HTTPURLResponse)?.statusCode == 200
    }

    func pair(code: String) async throws {
        let startURL = settings.baseURL.appending(path: "pair/start")
        var startRequest = URLRequest(url: startURL); startRequest.httpMethod = "POST"; startRequest.httpBody = Data("{}".utf8); startRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let (startData, _) = try await URLSession.shared.data(for: startRequest)
        let challenge = try JSONDecoder.shadow.decode(PairingChallenge.self, from: startData)
        let identity = KeychainDeviceIdentity.shared
        let signature = try identity.signPairingConfirmation(pairingID: challenge.pairingID, challenge: challenge.challenge, nonce: challenge.nonce)
        let confirm = PairConfirm(pairingID: challenge.pairingID, deviceName: code.isEmpty ? "iOS Device" : code, publicKey: try identity.publicKeyBase64URL(), signature: signature, nonce: challenge.nonce)
        var confirmRequest = URLRequest(url: settings.baseURL.appending(path: "pair/confirm")); confirmRequest.httpMethod = "POST"; confirmRequest.httpBody = try JSONEncoder.shadow.encode(confirm); confirmRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let (deviceData, _) = try await URLSession.shared.data(for: confirmRequest)
        let device = try JSONDecoder.shadow.decode(PairedDeviceResponse.self, from: deviceData)
        identity.storeDeviceID(device.id)
    }

    func ask(_ prompt: String) async throws -> String {
        let path = "/agent/ask"
        let body = try JSONEncoder.shadow.encode(AskPayload(prompt: prompt, provider: "local_mock"))
        var request = URLRequest(url: settings.baseURL.appending(path: path)); request.httpMethod = "POST"; request.httpBody = body; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let signed = try KeychainDeviceIdentity.shared.sign(method: "POST", path: path, body: body)
        request.setValue(signed.deviceID, forHTTPHeaderField: "X-Shadow-Device-Id"); request.setValue(signed.nonce, forHTTPHeaderField: "X-Shadow-Nonce"); request.setValue(signed.timestamp, forHTTPHeaderField: "X-Shadow-Timestamp"); request.setValue(signed.signature, forHTTPHeaderField: "X-Shadow-Signature")
        let (data, _) = try await URLSession.shared.data(for: request)
        let obj = try JSONDecoder.shadow.decode(AskResponse.self, from: data)
        return obj.answer
    }

    func approvals() async throws -> [ApprovalRequest] { [] }
}

private struct AskPayload: Encodable { let prompt: String; let provider: String }
private struct AskResponse: Decodable { let answer: String }
private struct PairingChallenge: Decodable { let pairingID: String; let challenge: String; let nonce: String; enum CodingKeys: String, CodingKey { case pairingID = "pairing_id", challenge, nonce } }
private struct PairConfirm: Encodable { let pairingID: String; let deviceName: String; let publicKey: String; let signature: String; let nonce: String; enum CodingKeys: String, CodingKey { case pairingID = "pairing_id", deviceName = "device_name", publicKey = "public_key", signature, nonce } }
private struct PairedDeviceResponse: Decodable { let id: String }

private extension JSONEncoder { static var shadow: JSONEncoder { JSONEncoder() } }
private extension JSONDecoder { static var shadow: JSONDecoder { JSONDecoder() } }
