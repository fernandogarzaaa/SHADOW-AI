import Foundation

public struct ConsentAuditEntry: Codable, Equatable, Sendable, Identifiable {
    public enum EventType: String, Codable, Sendable {
        case permissionRequested
        case permissionGranted
        case permissionRevoked
        case contextIngested
        case actionProposed
        case actionApproved
        case actionDenied
    }

    public let id: UUID
    public let type: EventType
    public let createdAt: Date
    public let summary: String
    public let scopes: Set<PermissionScope>

    public init(id: UUID = UUID(), type: EventType, createdAt: Date = Date(), summary: String, scopes: Set<PermissionScope> = []) {
        self.id = id
        self.type = type
        self.createdAt = createdAt
        self.summary = summary
        self.scopes = scopes
    }
}

public actor ConsentAuditLog {
    private var entries: [ConsentAuditEntry] = []

    public init() {}

    public func record(_ entry: ConsentAuditEntry) {
        entries.append(entry)
    }

    public func list() -> [ConsentAuditEntry] {
        entries.sorted { $0.createdAt > $1.createdAt }
    }
}
