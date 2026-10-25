import Foundation

enum ShadowAPIError: Error, LocalizedError {
    case badURL
    case notPaired
    case unreachable
    case server(Int, String)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .badURL: return "That node address isn't a valid URL."
        case .notPaired: return "This iPhone isn't paired with a node yet."
        case .unreachable: return "Can't reach the node. Check the address and that your iPhone is on the same network."
        case .server(let code, let detail): return Self.friendly(code: code, detail: detail)
        case .decoding(let what): return "The node sent a response this app doesn't understand (\(what))."
        }
    }

    /// True when the stored credentials are no longer usable and the user
    /// has to pair again.
    var needsRepair: Bool {
        if case .server(401, let d) = self {
            return ["unknown_device", "revoked_device", "session_expired", "sig_downgrade"].contains(d)
        }
        return false
    }

    private static func friendly(code: Int, detail: String) -> String {
        switch detail {
        case "unknown_device", "revoked_device": return "This iPhone was disconnected from the node. Pair it again."
        case "session_expired": return "This iPhone's session expired. Pair it again."
        case "expired_timestamp": return "Your iPhone's clock is out of sync with the node."
        case "invalid_bootstrap_code": return "That setup code isn't right. Check the code in the node's terminal."
        default: return detail.isEmpty ? "The node returned an error (\(code))." : detail
        }
    }
}

/// Outcome of POST /pair/confirm: credentials, or still waiting for an owner.
enum PairConfirmOutcome {
    case paired(DeviceIdentity, isOwner: Bool)
    case pending
}

final class ShadowNodeAPIClient {
    let baseURL: URL
    let mockMode: Bool
    private let session: URLSession
    private let store: DeviceIdentityStoring
    private let signer = ShadowRequestSigner()
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(baseURL: URL, mockMode: Bool = false, store: DeviceIdentityStoring = KeychainDeviceIdentityStore()) {
        self.baseURL = baseURL
        self.mockMode = mockMode
        self.store = store
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 20
        cfg.waitsForConnectivity = false
        self.session = URLSession(configuration: cfg)
    }

    // MARK: Pairing

    func health() async throws -> HealthResponse {
        if mockMode { return HealthResponse(status: "ok", version: "mock", emergencyPaused: false, authRequired: true, bootstrapOpen: false) }
        return try await request("GET", "/health", auth: false)
    }

    func pairStart(deviceName: String, publicKey: String) async throws -> PairStartResponse {
        if mockMode { return PairStartResponse(pairingId: "mock_pair", code: "MOCK42", expiresInSeconds: 300) }
        struct Body: Encodable { let device_name: String; let public_key: String; let client_kind = "ios" }
        return try await request("POST", "/pair/start", body: Body(device_name: deviceName, public_key: publicKey), auth: false)
    }

    func pairConfirm(pairingId: String, publicKey: String, deviceName: String, bootstrapCode: String?) async throws -> PairConfirmOutcome {
        if mockMode {
            let id = DeviceIdentity(deviceId: "mock_device", sharedSecret: "mock_secret", nodeFingerprint: "mock",
                                    publicKey: publicKey, baseURL: baseURL, deviceName: deviceName)
            store.save(id)
            return .paired(id, isOwner: true)
        }
        struct Body: Encodable { let pairing_id: String; let bootstrap_code: String? }
        struct Response: Decodable {
            let device: Device?
            let secret: String?
            let shared_secret: String?
            let session_expires_at: String?
            let status: String?
        }
        let (resp, code): (Response, Int) = try await requestWithStatus(
            "POST", "/pair/confirm", bodyData: encoder.encode(Body(pairing_id: pairingId, bootstrap_code: bootstrapCode)), auth: false)
        if code == 202 || resp.status == "pending" { return .pending }
        guard let device = resp.device, let secret = resp.secret ?? resp.shared_secret else {
            throw ShadowAPIError.decoding("pairing response")
        }
        let identity = DeviceIdentity(deviceId: device.id, sharedSecret: secret, nodeFingerprint: device.fingerprint ?? "",
                                      publicKey: publicKey, baseURL: baseURL, deviceName: device.name,
                                      sessionExpiresAt: resp.session_expires_at)
        store.save(identity)
        return .paired(identity, isOwner: device.isOwner == true)
    }

    // MARK: Memory & ask

    func ingestMemory(text: String, sourceTitle: String) async throws -> [MemoryItem] {
        if mockMode {
            return [MemoryItem(id: UUID().uuidString, category: "note", text: text,
                               source: MemorySource(id: "mock", kind: "manual", title: sourceTitle), confidence: 0.9)]
        }
        struct Body: Encodable { let text: String; let source_kind = "ios_manual"; let source_title: String }
        struct Response: Decodable { let items: [MemoryItem] }
        let r: Response = try await request("POST", "/memory/ingest", body: Body(text: text, source_title: sourceTitle), auth: true)
        return r.items
    }

    func searchMemory(_ query: String) async throws -> [MemorySearchResult] {
        if mockMode { return [] }
        var comps = URLComponents()
        comps.path = "/memory/search"
        comps.queryItems = [URLQueryItem(name: "q", value: query), URLQueryItem(name: "limit", value: "10")]
        return try await request("GET", comps.string ?? "/memory/search", auth: true)
    }

    func ask(_ prompt: String, allowCloud: Bool) async throws -> AgentAskResponse {
        if mockMode {
            return AgentAskResponse(answer: "Mock answer (mock mode).", sources: [], why: ["Mock mode"], modelUsed: "mock")
        }
        struct Body: Encodable { let prompt: String; let allow_cloud: Bool; let cloud_approval: Bool }
        return try await request("POST", "/agent/ask", body: Body(prompt: prompt, allow_cloud: allowCloud, cloud_approval: allowCloud), auth: true)
    }

    // MARK: Approvals

    func approvals(status: ApprovalStatus? = nil) async throws -> [ApprovalRequest] {
        if mockMode { return [] }
        let path = status.map { "/approvals?status=\($0.rawValue)" } ?? "/approvals"
        let page: Page<ApprovalRequest> = try await request("GET", path, auth: true)
        return page.items
    }

    func createApproval(action: AgentAction, reason: String) async throws -> ApprovalRequest {
        struct Body: Encodable { let action: AgentAction; let reason: String }
        return try await request("POST", "/approvals", body: Body(action: action, reason: reason), auth: true)
    }

    func approve(id: String) async throws -> ApprovalRequest {
        try await request("POST", "/approvals/\(id)/approve", auth: true)
    }

    func deny(id: String, reason: String) async throws -> ApprovalRequest {
        struct Body: Encodable { let reason: String }
        return try await request("POST", "/approvals/\(id)/deny", body: Body(reason: reason), auth: true)
    }

    /// Runs an approved action. The server derives approval from the
    /// approval record; the action must be the one stored on it.
    func execute(approval: ApprovalRequest, doubleConfirmed: Bool) async throws -> ExecutionResult {
        if mockMode { return ExecutionResult(ok: true, status: "mock") }
        struct Body: Encodable { let action: AgentAction; let approval_id: String; let double_confirmed: Bool }
        return try await request("POST", "/agent/execute",
                                 body: Body(action: approval.action, approval_id: approval.id, double_confirmed: doubleConfirmed), auth: true)
    }

    // MARK: Node

    func devices() async throws -> [Device] {
        if mockMode { return [] }
        let page: Page<Device> = try await request("GET", "/devices", auth: true)
        return page.items
    }

    func renew(deviceId: String) async throws {
        struct R: Decodable { let device_id: String }
        let _: R = try await request("POST", "/devices/\(deviceId)/renew", auth: true)
    }

    func revoke(deviceId: String) async throws {
        struct R: Decodable { let revoked: String }
        let _: R = try await request("POST", "/devices/\(deviceId)/revoke", auth: true)
    }

    func audit(limit: Int = 200) async throws -> [AuditEvent] {
        if mockMode { return [] }
        let page: Page<AuditEvent> = try await request("GET", "/audit?limit=\(limit)", auth: true)
        return page.items.reversed()
    }

    func setEmergencyPause(_ paused: Bool, reason: String?) async throws -> EmergencyPauseState {
        if mockMode { return EmergencyPauseState(paused: paused) }
        struct Body: Encodable { let paused: Bool; let reason: String? }
        return try await request("POST", "/emergency_pause", body: Body(paused: paused, reason: reason), auth: true)
    }

    // MARK: Transport

    private func request<T: Decodable>(_ method: String, _ path: String, auth: Bool) async throws -> T {
        try await requestWithStatus(method, path, bodyData: Data(), auth: auth).0
    }

    private func request<T: Decodable, B: Encodable>(_ method: String, _ path: String, body: B, auth: Bool) async throws -> T {
        try await requestWithStatus(method, path, bodyData: encoder.encode(body), auth: auth).0
    }

    private func requestWithStatus<T: Decodable>(_ method: String, _ path: String, bodyData: Data, auth: Bool) async throws -> (T, Int) {
        guard let url = URL(string: path, relativeTo: baseURL)?.absoluteURL else { throw ShadowAPIError.badURL }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if !bodyData.isEmpty {
            req.httpBody = bodyData
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if auth {
            guard let identity = store.load() else { throw ShadowAPIError.notPaired }
            signer.headers(identity: identity, method: method, url: url, body: bodyData)
                .forEach { req.setValue($0.value, forHTTPHeaderField: $0.key) }
        }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw ShadowAPIError.unreachable
        }
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            throw ShadowAPIError.server(code, Self.errorDetail(data))
        }
        do {
            return (try decoder.decode(T.self, from: data), code)
        } catch {
            throw ShadowAPIError.decoding(String(describing: T.self))
        }
    }

    private static func errorDetail(_ data: Data) -> String {
        struct Envelope: Decodable {
            struct Inner: Decodable { let code: String?; let message: String? }
            let error: Inner?
            let detail: String?
        }
        if let e = try? JSONDecoder().decode(Envelope.self, from: data) {
            return e.error?.code ?? e.detail ?? e.error?.message ?? ""
        }
        return String(data: data, encoding: .utf8) ?? ""
    }
}
