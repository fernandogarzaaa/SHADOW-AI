import Foundation

public struct AgentGuardrails: Sendable {
    public var blockedPhrases: Set<String>
    public var requiresConfirmationPhrases: Set<String>

    public init(
        blockedPhrases: Set<String> = [
            "transfer money",
            "delete account",
            "share password",
            "disable security",
            "exfiltrate"
        ],
        requiresConfirmationPhrases: Set<String> = [
            "send email",
            "send message",
            "purchase",
            "schedule meeting",
            "remote control"
        ]
    ) {
        self.blockedPhrases = blockedPhrases
        self.requiresConfirmationPhrases = requiresConfirmationPhrases
    }

    public func isActionAllowed(_ action: String) -> Bool {
        let normalized = action.lowercased()
        return !blockedPhrases.contains { normalized.contains($0) }
    }

    public func requiresConfirmation(_ action: String) -> Bool {
        let normalized = action.lowercased()
        return requiresConfirmationPhrases.contains { normalized.contains($0) }
    }
}
