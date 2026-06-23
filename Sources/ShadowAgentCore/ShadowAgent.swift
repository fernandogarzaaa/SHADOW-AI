import Foundation

public enum PermissionScope: String, CaseIterable, Codable, Sendable {
    case email
    case chat
    case calendar
    case notes
    case photos
    case voice
    case keystrokes
    case workApps
    case deviceControl
}

public enum AgentMode: String, Codable, Sendable {
    case observeOnly
    case recommend
    case confirmBeforeAction
    case autonomous
}

public struct PermissionGrant: Codable, Equatable, Sendable {
    public let scope: PermissionScope
    public let grantedAt: Date
    public let expiresAt: Date?
    public let readAllowed: Bool
    public let writeAllowed: Bool

    public init(
        scope: PermissionScope,
        grantedAt: Date = Date(),
        expiresAt: Date? = nil,
        readAllowed: Bool,
        writeAllowed: Bool
    ) {
        self.scope = scope
        self.grantedAt = grantedAt
        self.expiresAt = expiresAt
        self.readAllowed = readAllowed
        self.writeAllowed = writeAllowed
    }

    public func isActive(at date: Date = Date()) -> Bool {
        guard let expiresAt else { return true }
        return date < expiresAt
    }
}

public struct AgentConfiguration: Codable, Equatable, Sendable {
    public var isAlwaysOn: Bool
    public var mode: AgentMode
    public var watchedBundleIdentifiers: Set<String>
    public var allowedDeviceIdentifiers: Set<String>
    public var frontierReasoningEnabled: Bool
    public var localRAGEnabled: Bool

    public init(
        isAlwaysOn: Bool = true,
        mode: AgentMode = .confirmBeforeAction,
        watchedBundleIdentifiers: Set<String> = [],
        allowedDeviceIdentifiers: Set<String> = [],
        frontierReasoningEnabled: Bool = true,
        localRAGEnabled: Bool = true
    ) {
        self.isAlwaysOn = isAlwaysOn
        self.mode = mode
        self.watchedBundleIdentifiers = watchedBundleIdentifiers
        self.allowedDeviceIdentifiers = allowedDeviceIdentifiers
        self.frontierReasoningEnabled = frontierReasoningEnabled
        self.localRAGEnabled = localRAGEnabled
    }
}

public struct UserContextEvent: Codable, Equatable, Sendable, Identifiable {
    public let id: UUID
    public let scope: PermissionScope
    public let sourceBundleIdentifier: String?
    public let occurredAt: Date
    public let content: String
    public let metadata: [String: String]

    public init(
        id: UUID = UUID(),
        scope: PermissionScope,
        sourceBundleIdentifier: String? = nil,
        occurredAt: Date = Date(),
        content: String,
        metadata: [String: String] = [:]
    ) {
        self.id = id
        self.scope = scope
        self.sourceBundleIdentifier = sourceBundleIdentifier
        self.occurredAt = occurredAt
        self.content = content
        self.metadata = metadata
    }
}

public struct AgentRecommendation: Codable, Equatable, Sendable, Identifiable {
    public let id: UUID
    public let title: String
    public let rationale: String
    public let confidence: Double
    public let proposedAction: String?
    public let requiresConfirmation: Bool

    public init(
        id: UUID = UUID(),
        title: String,
        rationale: String,
        confidence: Double,
        proposedAction: String? = nil,
        requiresConfirmation: Bool = true
    ) {
        self.id = id
        self.title = title
        self.rationale = rationale
        self.confidence = min(max(confidence, 0), 1)
        self.proposedAction = proposedAction
        self.requiresConfirmation = requiresConfirmation
    }
}

public struct AgentDecision: Codable, Equatable, Sendable {
    public enum Outcome: String, Codable, Sendable {
        case deniedMissingPermission
        case deniedUnsafeAction
        case recommendationOnly
        case confirmationRequired
        case actionApproved
    }

    public let outcome: Outcome
    public let message: String
    public let recommendation: AgentRecommendation?
}

public actor ShadowAgent {
    private var configuration: AgentConfiguration
    private var grants: [PermissionScope: PermissionGrant]
    private let memory: AgentMemoryStore
    private let guardrails: AgentGuardrails

    public init(
        configuration: AgentConfiguration = AgentConfiguration(),
        grants: [PermissionGrant] = [],
        memory: AgentMemoryStore,
        guardrails: AgentGuardrails = AgentGuardrails()
    ) {
        self.configuration = configuration
        self.grants = Dictionary(uniqueKeysWithValues: grants.map { ($0.scope, $0) })
        self.memory = memory
        self.guardrails = guardrails
    }

    public func currentConfiguration() -> AgentConfiguration { configuration }

    public func updateConfiguration(_ configuration: AgentConfiguration) {
        self.configuration = configuration
    }

    public func grant(_ grant: PermissionGrant) {
        grants[grant.scope] = grant
    }

    public func revoke(_ scope: PermissionScope) {
        grants.removeValue(forKey: scope)
    }

    public func ingest(_ event: UserContextEvent, at date: Date = Date()) async throws {
        guard hasReadPermission(for: event.scope, at: date) else {
            throw ShadowAgentError.missingReadPermission(event.scope)
        }

        if let bundleIdentifier = event.sourceBundleIdentifier,
           !configuration.watchedBundleIdentifiers.isEmpty,
           !configuration.watchedBundleIdentifiers.contains(bundleIdentifier) {
            throw ShadowAgentError.unwatchedApplication(bundleIdentifier)
        }

        try await memory.save(event)
    }

    public func recommend(for prompt: String) async throws -> AgentRecommendation {
        let matches = try await memory.search(query: prompt, limit: 5)
        let rationale: String
        if matches.isEmpty {
            rationale = "No matching local memory was found. Ask for more context before acting."
        } else {
            let sources = matches.map { $0.content }.joined(separator: " | ")
            rationale = "Based on approved local context: \(sources)"
        }

        return AgentRecommendation(
            title: "Recommended next step",
            rationale: rationale,
            confidence: matches.isEmpty ? 0.35 : 0.78,
            proposedAction: prompt,
            requiresConfirmation: configuration.mode != .autonomous
        )
    }

    public func decide(action: String, scopes: Set<PermissionScope>, now: Date = Date()) async throws -> AgentDecision {
        for scope in scopes where !hasWritePermission(for: scope, at: now) {
            return AgentDecision(
                outcome: .deniedMissingPermission,
                message: "Write permission is required for \(scope.rawValue).",
                recommendation: nil
            )
        }

        guard guardrails.isActionAllowed(action) else {
            return AgentDecision(
                outcome: .deniedUnsafeAction,
                message: "The proposed action violates configured safety guardrails.",
                recommendation: nil
            )
        }

        let recommendation = try await recommend(for: action)
        switch configuration.mode {
        case .observeOnly, .recommend:
            return AgentDecision(outcome: .recommendationOnly, message: "Autonomous execution is disabled.", recommendation: recommendation)
        case .confirmBeforeAction:
            return AgentDecision(outcome: .confirmationRequired, message: "User confirmation is required before execution.", recommendation: recommendation)
        case .autonomous:
            return AgentDecision(outcome: .actionApproved, message: "Action approved for autonomous execution.", recommendation: recommendation)
        }
    }

    private func hasReadPermission(for scope: PermissionScope, at date: Date) -> Bool {
        guard let grant = grants[scope], grant.isActive(at: date) else { return false }
        return grant.readAllowed
    }

    private func hasWritePermission(for scope: PermissionScope, at date: Date) -> Bool {
        guard let grant = grants[scope], grant.isActive(at: date) else { return false }
        return grant.writeAllowed
    }
}

public enum ShadowAgentError: Error, Equatable, Sendable {
    case missingReadPermission(PermissionScope)
    case unwatchedApplication(String)
}
