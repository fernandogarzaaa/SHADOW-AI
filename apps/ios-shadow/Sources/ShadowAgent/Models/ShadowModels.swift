import Foundation

// Wire models for the Shadow node API. Field names follow the node's JSON
// (snake_case) via CodingKeys. Optional fields are optional here too so a
// newer node never breaks decoding.

/// Arbitrary JSON, so action params round-trip to the node unchanged (the
/// node re-hashes the action envelope at execution time; any change to the
/// params would fail the approval binding).
enum JSONValue: Codable, Hashable, CustomStringConvertible {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .number(let n):
            if n.rounded() == n, abs(n) < 1e15 { try c.encode(Int64(n)) } else { try c.encode(n) }
        case .bool(let b): try c.encode(b)
        case .object(let o): try c.encode(o)
        case .array(let a): try c.encode(a)
        case .null: try c.encodeNil()
        }
    }

    var description: String {
        switch self {
        case .string(let s): return s
        case .number(let n): return n.rounded() == n ? String(Int64(n)) : String(n)
        case .bool(let b): return String(b)
        case .null: return "null"
        case .array(let a): return "[" + a.map(\.description).joined(separator: ", ") + "]"
        case .object(let o): return "{" + o.keys.sorted().map { "\($0): \(o[$0]!.description)" }.joined(separator: ", ") + "}"
        }
    }
}

enum RiskClass: String, Codable { case low, medium, high, blocked }
enum ApprovalStatus: String, Codable { case pending, approved, denied, expired, consumed }

/// Parses the node's ISO-8601 timestamps (with or without fractional
/// seconds / offset). Kept as strings on the wire models.
enum NodeDate {
    private static let withFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let plain = ISO8601DateFormatter()

    static func parse(_ s: String?) -> Date? {
        guard var s, !s.isEmpty else { return nil }
        // Python emits microseconds; ISO8601DateFormatter wants milliseconds.
        if let dot = s.firstIndex(of: "."), let end = s[dot...].firstIndex(where: { !$0.isNumber && $0 != "." }) {
            let frac = s[s.index(after: dot)..<end]
            if frac.count > 3 { s.replaceSubrange(s.index(after: dot)..<end, with: frac.prefix(3)) }
        }
        if !s.hasSuffix("Z") && !s.contains("+") && s.filter({ $0 == "-" }).count < 3 { s += "Z" }
        return withFraction.date(from: s) ?? plain.date(from: s)
    }
}

struct PairStartResponse: Codable {
    var pairingId: String
    var code: String
    var expiresInSeconds: Int
    var bootstrapRequired: Bool?
    enum CodingKeys: String, CodingKey {
        case code
        case pairingId = "pairing_id", expiresInSeconds = "expires_in_seconds", bootstrapRequired = "bootstrap_required"
    }
}

struct Device: Identifiable, Codable {
    var id: String
    var name: String
    var fingerprint: String?
    var trusted: Bool
    var revoked: Bool?
    var isOwner: Bool?
    var clientKind: String?
    var sessionExpiresAt: String?
    enum CodingKeys: String, CodingKey {
        case id, name, trusted, revoked, fingerprint
        case isOwner = "is_owner", clientKind = "client_kind", sessionExpiresAt = "session_expires_at"
    }
}

struct MemorySource: Identifiable, Codable {
    var id: String
    var kind: String
    var title: String
}

struct MemoryItem: Identifiable, Codable {
    var id: String
    var category: String?
    var text: String
    var source: MemorySource
    var confidence: Double
    var sensitive: Bool?
    var doNotSendToCloud: Bool?
    enum CodingKeys: String, CodingKey {
        case id, category, text, source, confidence, sensitive
        case doNotSendToCloud = "do_not_send_to_cloud"
    }
}

struct MemorySearchResult: Identifiable, Codable {
    var id: String { item.id }
    var item: MemoryItem
    var score: Double
    var freshness: Double
    var attribution: String
    var explanation: String
}

struct AgentAction: Identifiable, Codable {
    var id: String
    var toolName: String
    var description: String
    var params: [String: JSONValue]?
    var risk: RiskClass?
    var requiresApproval: Bool?
    var destructive: Bool?
    var destination: String?
    var dataUsed: [String]?
    var modelUsed: String?
    enum CodingKeys: String, CodingKey {
        case id, description, params, risk, destructive, destination
        case toolName = "tool_name", requiresApproval = "requires_approval", dataUsed = "data_used", modelUsed = "model_used"
    }
}

struct AgentPlan: Codable {
    var userIntent: String
    var actions: [AgentAction]
    enum CodingKeys: String, CodingKey { case actions, userIntent = "user_intent" }
}

struct AgentAskResponse: Codable {
    var answer: String
    var sources: [MemorySearchResult]
    var why: [String]
    var modelUsed: String?
    var cloudAllowed: Bool?
    var route: String?
    var degraded: Bool?
    var plan: AgentPlan?
    enum CodingKeys: String, CodingKey {
        case answer, sources, why, plan, route, degraded
        case modelUsed = "model_used", cloudAllowed = "cloud_allowed"
    }
}

struct ApprovalRequest: Identifiable, Codable {
    var id: String
    var action: AgentAction
    var reason: String
    var actionPreview: String?
    var dataUsedPreview: [String]?
    var modelUsedPreview: String?
    var destinationPreview: String?
    var riskLabel: RiskClass?
    var requiresDoubleConfirmation: Bool?
    var consequence: String?
    var status: ApprovalStatus
    var denyReason: String?
    var expiresAt: String?
    enum CodingKeys: String, CodingKey {
        case id, action, reason, status, consequence
        case actionPreview = "action_preview", dataUsedPreview = "data_used_preview"
        case modelUsedPreview = "model_used_preview", destinationPreview = "destination_preview"
        case riskLabel = "risk_label", requiresDoubleConfirmation = "requires_double_confirmation"
        case denyReason = "deny_reason", expiresAt = "expires_at"
    }
}

/// Typed result of POST /agent/execute.
struct ExecutionResult: Codable {
    var ok: Bool?
    var status: String?
    var reason: String?
    var verification: String?
    var verificationReason: String?
    var executionId: String?
    enum CodingKeys: String, CodingKey {
        case ok, status, reason, verification
        case verificationReason = "verification_reason", executionId = "execution_id"
    }

    var summary: String {
        if ok == false { return "Didn't run: \(reason ?? status ?? "blocked by policy")" }
        if let v = verification { return "Done · \(v)" }
        return "Done"
    }
}

struct AuditEvent: Identifiable, Codable {
    var id: String
    var actor: String
    var eventType: String
    var status: String
    var result: String?
    var timestamp: String?
    var proposedAction: String?
    enum CodingKeys: String, CodingKey {
        case id, actor, status, result, timestamp
        case eventType = "event_type", proposedAction = "proposed_action"
    }
}

struct HealthResponse: Codable {
    var status: String
    var version: String
    var emergencyPaused: Bool
    var authRequired: Bool?
    var bootstrapOpen: Bool?
    enum CodingKeys: String, CodingKey {
        case status, version
        case emergencyPaused = "emergency_paused", authRequired = "auth_required", bootstrapOpen = "bootstrap_open"
    }
}

struct EmergencyPauseState: Codable { var paused: Bool }

/// Uniform list envelope returned by node list endpoints.
struct Page<T: Decodable>: Decodable {
    var items: [T]
    var count: Int
}
