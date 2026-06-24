import Foundation
import SwiftUI

@MainActor final class AppState: ObservableObject {
    @Published var baseURLText = "http://127.0.0.1:8787"
    @Published var mockMode = true
    @Published var pairedIdentity: DeviceIdentity?
    @Published var emergencyPaused = false
    @Published var memories: [MemoryItem] = []
    @Published var searchResults: [MemorySearchResult] = []
    @Published var approvals: [ApprovalRequest] = []
    @Published var devices: [Device] = []
    @Published var auditEvents: [AuditEvent] = []
    @Published var lastAnswer: AgentAskResponse?
    @Published var lastExecutionResult: String?
    @Published var statusMessage = "Local mock mode is enabled."
    @Published var autonomyMode: AutonomyMode = .suggestOnly
    private let identityStore = KeychainDeviceIdentityStore()
    lazy var api: ShadowNodeAPIClient = makeClient()
    init() { pairedIdentity = identityStore.load() }
    func makeClient() -> ShadowNodeAPIClient { ShadowNodeAPIClient(baseURL: URL(string: baseURLText) ?? URL(string: "http://127.0.0.1:8787")!, mockMode: mockMode, store: identityStore) }
    func refreshClient() { api = makeClient(); pairedIdentity = identityStore.load() }
    func pair() async { do { refreshClient(); _ = try await api.health(); let challenge = try await api.pairStart(); let publicKey = "ios-\(UUID().uuidString)"; let identity = try await api.pairConfirm(challenge: challenge, deviceName: "iOS Simulator", publicKey: publicKey); pairedIdentity = identity; statusMessage = "Paired with node. Code: \(challenge.code)" } catch { statusMessage = "Pairing failed: \(error.localizedDescription)" } }
    func unpair() { identityStore.reset(); pairedIdentity = nil; statusMessage = "Device unpaired and local session keys removed." }
    func ingest(text: String, title: String) async { do { let items = try await api.ingestMemory(text: text, sourceTitle: title); memories = items + memories; statusMessage = "Stored \(items.count) memory chunk(s)." } catch { statusMessage = "Ingestion failed: \(error.localizedDescription)" } }
    func search(_ query: String) async { do { searchResults = try await api.searchMemory(query); statusMessage = "Retrieved \(searchResults.count) result(s)." } catch { statusMessage = "Search failed: \(error.localizedDescription)" } }
    func ask(_ prompt: String) async { do { lastAnswer = try await api.ask(prompt); searchResults = lastAnswer?.sources ?? []; statusMessage = "Shadow answered using \(searchResults.count) retrieved memories." } catch { statusMessage = "Ask failed: \(error.localizedDescription)" } }
    func loadApprovals() async { do { approvals = try await api.approvals() } catch { statusMessage = "Approval load failed: \(error.localizedDescription)" } }
    func createApproval(from action: AgentAction) async { do { let approval = try await api.createApproval(action: action, reason: "Created from iOS proposal"); approvals.insert(approval, at: 0); statusMessage = "Approval created." } catch { statusMessage = "Approval create failed: \(error.localizedDescription)" } }
    func approve(_ approval: ApprovalRequest) async { do { let updated = try await api.approve(id: approval.id); replaceApproval(updated); statusMessage = "Approved once." } catch { statusMessage = "Approve failed: \(error.localizedDescription)" } }
    func deny(_ approval: ApprovalRequest, reason: String) async { do { let updated = try await api.deny(id: approval.id, reason: reason); replaceApproval(updated); statusMessage = "Denied: \(reason)" } catch { statusMessage = "Deny failed: \(error.localizedDescription)" } }
    func execute(_ approval: ApprovalRequest, doubleConfirmed: Bool = false) async { do { lastExecutionResult = try await api.execute(action: approval.action, approved: approval.status == .approved, doubleConfirmed: doubleConfirmed); statusMessage = lastExecutionResult ?? "Executed." } catch { statusMessage = "Execution blocked/failed: \(error.localizedDescription)" } }
    func loadAudit() async { do { auditEvents = try await api.audit() } catch { statusMessage = "Audit load failed: \(error.localizedDescription)" } }
    func loadDevices() async { do { devices = try await api.devices() } catch { statusMessage = "Device load failed: \(error.localizedDescription)" } }
    func setEmergencyPause(_ paused: Bool) async { do { let state = try await api.setEmergencyPause(paused, reason: paused ? "Enabled from iOS" : "Resumed from iOS"); emergencyPaused = state.paused; statusMessage = paused ? "Emergency pause enabled. Execution is blocked." : "Emergency pause disabled." } catch { statusMessage = "Pause sync failed: \(error.localizedDescription)" } }
    private func replaceApproval(_ updated: ApprovalRequest) { if let i = approvals.firstIndex(where: { $0.id == updated.id }) { approvals[i] = updated } else { approvals.insert(updated, at: 0) } }
}
