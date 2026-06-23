import XCTest
@testable import ShadowAgentCore

final class ShadowAgentCoreTests: XCTestCase {
    func testIngestRequiresReadPermission() async throws {
        let agent = ShadowAgent(memory: InMemoryAgentMemoryStore())
        let event = UserContextEvent(scope: .email, content: "Draft weekly update")

        do {
            try await agent.ingest(event)
            XCTFail("Expected missing permission error")
        } catch ShadowAgentError.missingReadPermission(let scope) {
            XCTAssertEqual(scope, .email)
        }
    }

    func testIngestStoresApprovedContextAndRecommendsFromMemory() async throws {
        let store = InMemoryAgentMemoryStore()
        let agent = ShadowAgent(
            grants: [PermissionGrant(scope: .notes, readAllowed: true, writeAllowed: false)],
            memory: store
        )

        try await agent.ingest(UserContextEvent(scope: .notes, content: "Prefer concise investor updates on Friday"))
        let recommendation = try await agent.recommend(for: "investor update")

        XCTAssertGreaterThan(recommendation.confidence, 0.7)
        XCTAssertTrue(recommendation.rationale.contains("investor"))
    }

    func testWatchedApplicationAllowListIsEnforced() async throws {
        var configuration = AgentConfiguration()
        configuration.watchedBundleIdentifiers = ["com.shadow.mail"]
        let agent = ShadowAgent(
            configuration: configuration,
            grants: [PermissionGrant(scope: .email, readAllowed: true, writeAllowed: false)],
            memory: InMemoryAgentMemoryStore()
        )

        do {
            try await agent.ingest(UserContextEvent(scope: .email, sourceBundleIdentifier: "com.other.mail", content: "Hello"))
            XCTFail("Expected unwatched application error")
        } catch ShadowAgentError.unwatchedApplication(let bundleIdentifier) {
            XCTAssertEqual(bundleIdentifier, "com.other.mail")
        }
    }

    func testAutonomousDecisionRequiresWritePermission() async throws {
        let agent = ShadowAgent(
            configuration: AgentConfiguration(mode: .autonomous),
            grants: [PermissionGrant(scope: .chat, readAllowed: true, writeAllowed: false)],
            memory: InMemoryAgentMemoryStore()
        )

        let decision = try await agent.decide(action: "send message to team", scopes: [.chat])
        XCTAssertEqual(decision.outcome, .deniedMissingPermission)
    }

    func testGuardrailsBlockUnsafeActions() async throws {
        let agent = ShadowAgent(
            configuration: AgentConfiguration(mode: .autonomous),
            grants: [PermissionGrant(scope: .email, readAllowed: true, writeAllowed: true)],
            memory: InMemoryAgentMemoryStore()
        )

        let decision = try await agent.decide(action: "share password by email", scopes: [.email])
        XCTAssertEqual(decision.outcome, .deniedUnsafeAction)
    }

    func testAutonomousModeApprovesSafeGrantedAction() async throws {
        let agent = ShadowAgent(
            configuration: AgentConfiguration(mode: .autonomous),
            grants: [PermissionGrant(scope: .calendar, readAllowed: true, writeAllowed: true)],
            memory: InMemoryAgentMemoryStore()
        )

        let decision = try await agent.decide(action: "schedule meeting with design team", scopes: [.calendar])
        XCTAssertEqual(decision.outcome, .actionApproved)
    }
}
