import Foundation
import SwiftUI

@MainActor
final class AppState: ObservableObject {
    enum PairingPhase: Equatable {
        case idle
        case working
        case waitingForApproval(code: String)
    }

    @Published var baseURLText: String {
        didSet { UserDefaults.standard.set(baseURLText, forKey: "nodeURL") }
    }
    @Published private(set) var pairedIdentity: DeviceIdentity?
    @Published var pairingPhase: PairingPhase = .idle
    @Published var health: HealthResponse?
    @Published var emergencyPaused = false
    @Published var searchResults: [MemorySearchResult] = []
    @Published var approvals: [ApprovalRequest] = []
    @Published var readyToRun: [ApprovalRequest] = []
    @Published var devices: [Device] = []
    @Published var auditEvents: [AuditEvent] = []
    @Published var lastAnswer: AgentAskResponse?
    @Published var errorMessage: String?
    @Published var notice: String?

    let environment = ShadowEnvironment()
    private let identityStore = KeychainDeviceIdentityStore()
    private(set) var api: ShadowNodeAPIClient
    private var pairingTask: Task<Void, Never>?

    var isPaired: Bool { pairedIdentity != nil }

    init() {
        let stored = KeychainDeviceIdentityStore().load()
        let url = stored?.baseURL.absoluteString
            ?? UserDefaults.standard.string(forKey: "nodeURL")
            ?? ShadowEnvironment().apiBaseURL.absoluteString
        baseURLText = url
        pairedIdentity = stored
        api = ShadowNodeAPIClient(baseURL: URL(string: url) ?? ShadowEnvironment().apiBaseURL,
                                  mockMode: ShadowEnvironment().mockMode, store: identityStore)
    }

    /// Rebuild the client for the current address (paired nodes keep theirs).
    private func rebuildClient() throws {
        let text = baseURLText.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalized = text.hasPrefix("http://") || text.hasPrefix("https://") ? text : "http://\(text)"
        guard let url = URL(string: normalized.hasSuffix("/") ? String(normalized.dropLast()) : normalized),
              url.host != nil else { throw ShadowAPIError.badURL }
        baseURLText = url.absoluteString
        api = ShadowNodeAPIClient(baseURL: url, mockMode: environment.mockMode, store: identityStore)
    }

    private func report(_ error: Error) {
        if let e = error as? ShadowAPIError, e.needsRepair {
            unpair(message: e.localizedDescription)
            return
        }
        errorMessage = error.localizedDescription
    }

    // MARK: Pairing

    func checkNode() async {
        do {
            try rebuildClient()
            health = try await api.health()
            emergencyPaused = health?.emergencyPaused ?? false
        } catch {
            health = nil
            errorMessage = error.localizedDescription
        }
    }

    func startPairing(deviceName: String, bootstrapCode: String) {
        pairingTask?.cancel()
        pairingTask = Task { await pair(deviceName: deviceName, bootstrapCode: bootstrapCode) }
    }

    private func pair(deviceName: String, bootstrapCode: String) async {
        pairingPhase = .working
        do {
            try rebuildClient()
            health = try await api.health()
            let publicKey = DevicePublicKey.generate()
            let name = deviceName.trimmingCharacters(in: .whitespaces).isEmpty ? "iPhone" : deviceName
            let start = try await api.pairStart(deviceName: name, publicKey: publicKey)
            let code = bootstrapCode.trimmingCharacters(in: .whitespaces)
            try await confirm(start: start, publicKey: publicKey, name: name, bootstrapCode: code.isEmpty ? nil : code)
        } catch {
            pairingPhase = .idle
            report(error)
        }
    }

    private func confirm(start: PairStartResponse, publicKey: String, name: String, bootstrapCode: String?) async throws {
        let deadline = Date().addingTimeInterval(TimeInterval(start.expiresInSeconds))
        while Date() < deadline {
            switch try await api.pairConfirm(pairingId: start.pairingId, publicKey: publicKey,
                                             deviceName: name, bootstrapCode: bootstrapCode) {
            case .paired(let identity, let isOwner):
                pairedIdentity = identity
                pairingPhase = .idle
                notice = isOwner ? "Paired. This iPhone is the owner of the node." : "Paired."
                await refreshAll()
                return
            case .pending:
                pairingPhase = .waitingForApproval(code: start.code)
                try await Task.sleep(nanoseconds: 2_000_000_000)
                if Task.isCancelled || pairingPhase == .idle { return }
            }
        }
        pairingPhase = .idle
        errorMessage = "The pairing request expired. Try again."
    }

    func cancelPairing() {
        pairingTask?.cancel()
        pairingPhase = .idle
    }

    func unpair(message: String? = nil) {
        identityStore.reset()
        pairedIdentity = nil
        approvals = []; readyToRun = []; devices = []; auditEvents = []; lastAnswer = nil
        notice = message ?? "This iPhone was unpaired and its keys were removed."
    }

    func disconnect() async {
        if let id = pairedIdentity?.deviceId {
            try? await api.revoke(deviceId: id)
        }
        unpair()
    }

    // MARK: Data

    func refreshAll() async {
        await refreshHealth()
        await loadApprovals()
    }

    func refreshHealth() async {
        do {
            health = try await api.health()
            emergencyPaused = health?.emergencyPaused ?? false
        } catch { report(error) }
    }

    func ingest(text: String, title: String) async -> Bool {
        do {
            let items = try await api.ingestMemory(text: text, sourceTitle: title.isEmpty ? "iPhone note" : title)
            notice = "Saved \(items.count) memory item\(items.count == 1 ? "" : "s")."
            return true
        } catch { report(error); return false }
    }

    func search(_ query: String) async {
        guard !query.trimmingCharacters(in: .whitespaces).isEmpty else { searchResults = []; return }
        do { searchResults = try await api.searchMemory(query) } catch { report(error) }
    }

    func ask(_ prompt: String, allowCloud: Bool) async {
        do { lastAnswer = try await api.ask(prompt, allowCloud: allowCloud) } catch { report(error) }
    }

    func loadApprovals() async {
        do {
            async let pending = api.approvals(status: .pending)
            async let approved = api.approvals(status: .approved)
            (approvals, readyToRun) = try await (pending, approved)
        } catch { report(error) }
    }

    func requestApproval(for action: AgentAction) async {
        do {
            _ = try await api.createApproval(action: action, reason: "Requested from iPhone")
            notice = "Approval requested. Review it in Approvals."
            await loadApprovals()
        } catch { report(error) }
    }

    func approve(_ approval: ApprovalRequest) async {
        do {
            _ = try await api.approve(id: approval.id)
            notice = "Approved. Run it when you're ready."
            await loadApprovals()
        } catch { report(error) }
    }

    func deny(_ approval: ApprovalRequest, reason: String) async {
        do {
            _ = try await api.deny(id: approval.id, reason: reason.isEmpty ? "Denied on iPhone" : reason)
            notice = "Denied."
            await loadApprovals()
        } catch { report(error) }
    }

    func run(_ approval: ApprovalRequest, doubleConfirmed: Bool) async -> ExecutionResult? {
        do {
            let result = try await api.execute(approval: approval, doubleConfirmed: doubleConfirmed)
            notice = result.summary
            await loadApprovals()
            return result
        } catch { report(error); return nil }
    }

    func loadAudit() async {
        do { auditEvents = try await api.audit() } catch { report(error) }
    }

    func loadDevices() async {
        do { devices = try await api.devices() } catch { report(error) }
    }

    func renew(_ device: Device) async {
        do {
            try await api.renew(deviceId: device.id)
            notice = "Renewed for 30 days."
            await loadDevices()
        } catch { report(error) }
    }

    func revoke(_ device: Device) async {
        do {
            try await api.revoke(deviceId: device.id)
            if device.id == pairedIdentity?.deviceId { unpair(); return }
            await loadDevices()
        } catch { report(error) }
    }

    /// Sets the node's emergency pause and reflects the node's answer.
    func setEmergencyPause(_ paused: Bool) async {
        do {
            let state = try await api.setEmergencyPause(paused, reason: paused ? "Paused from iPhone" : "Resumed from iPhone")
            emergencyPaused = state.paused
            notice = state.paused ? "Paused. Shadow won't act until you resume." : "Resumed."
        } catch {
            report(error)
            await refreshHealth()
        }
    }
}
