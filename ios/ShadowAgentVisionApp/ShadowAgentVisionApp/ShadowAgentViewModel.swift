#if canImport(SwiftUI)
import Foundation
import ShadowAgentCore

@MainActor
final class ShadowAgentViewModel: ObservableObject {
    @Published private(set) var configuration = AgentConfiguration()
    @Published private(set) var auditEntries: [ConsentAuditEntry] = []
    @Published var latestRecommendation: AgentRecommendation?
    @Published var latestDecision: AgentDecision?

    private let auditLog = ConsentAuditLog()
    private let agent: ShadowAgent

    init() {
        let memory = FileAgentMemoryStore(fileURL: URL.documentsDirectory.appending(path: "shadow-agent-memory.json"))
        self.agent = ShadowAgent(memory: memory)
    }

    func grant(scope: PermissionScope, read: Bool, write: Bool) async {
        await agent.grant(PermissionGrant(scope: scope, readAllowed: read, writeAllowed: write))
        await auditLog.record(ConsentAuditEntry(type: .permissionGranted, summary: "Granted \(scope.rawValue)", scopes: [scope]))
        auditEntries = await auditLog.list()
    }

    func ingestDemoContext() async throws {
        let event = UserContextEvent(scope: .notes, content: "User prefers short morning briefs with calendar risks first.")
        try await agent.ingest(event)
        await auditLog.record(ConsentAuditEntry(type: .contextIngested, summary: "Stored approved notes context", scopes: [.notes]))
        auditEntries = await auditLog.list()
    }

    func recommendMorningBrief() async throws {
        latestRecommendation = try await agent.recommend(for: "prepare morning brief")
    }

    func approveCalendarAction() async throws {
        latestDecision = try await agent.decide(action: "schedule meeting with product team", scopes: [.calendar])
        await auditLog.record(ConsentAuditEntry(type: .actionProposed, summary: latestDecision?.message ?? "Action evaluated", scopes: [.calendar]))
        auditEntries = await auditLog.list()
    }
}
#endif
