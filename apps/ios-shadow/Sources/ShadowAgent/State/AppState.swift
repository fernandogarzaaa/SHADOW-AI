import Foundation
import SwiftUI
@MainActor final class AppState: ObservableObject {
    @Published var autonomyMode: AutonomyMode = .suggestOnly
    @Published var emergencyPaused = false
    @Published var memories = [MemoryItem(id: UUID(), title: "Welcome memory", snippet: "Approved memories appear here and can be deleted.", confidence: 0.9, source: "onboarding")]
    @Published var approvals = [ApprovalRequest(id: UUID(), title: "Draft email reply", reason: "External communication requires approval.", risk: .critical, createdAt: Date())]
    @Published var devices = [Device(id: UUID(), name: "Local Shadow Node", trusted: false, lastSeen: nil)]
}
