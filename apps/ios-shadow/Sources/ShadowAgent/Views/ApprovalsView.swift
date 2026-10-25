import SwiftUI
import ThinkingOrbsKit

struct ApprovalsView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        List {
            Section("Waiting for you") {
                if state.approvals.isEmpty {
                    HStack(spacing: 12) {
                        ThinkingOrb(state: .breathing, size: .px20, paused: true)
                            .accessibilityHidden(true)
                        Text("Nothing waiting.").foregroundStyle(.secondary)
                    }
                }
                ForEach(state.approvals) { approval in
                    NavigationLink { ApprovalDetailView(approval: approval) } label: { ApprovalRow(approval: approval) }
                }
            }
            if !state.readyToRun.isEmpty {
                Section("Approved, not run yet") {
                    ForEach(state.readyToRun) { approval in
                        NavigationLink { ApprovalDetailView(approval: approval) } label: { ApprovalRow(approval: approval) }
                    }
                }
            }
        }
        .navigationTitle("Approvals")
        .refreshable { await state.loadApprovals() }
        .task { await state.loadApprovals() }
    }
}

struct ApprovalRow: View {
    let approval: ApprovalRequest

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(approval.actionPreview ?? approval.action.description)
                .font(.subheadline.weight(.medium))
            HStack(spacing: 6) {
                RiskBadge(risk: approval.riskLabel)
                Text(approval.action.toolName).font(.caption).foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

struct RiskBadge: View {
    let risk: RiskClass?

    var body: some View {
        let color: Color = switch risk {
        case .low: .green
        case .medium: .orange
        case .high, .blocked: .red
        case nil: .gray
        }
        Text("\(risk?.rawValue ?? "unknown") risk")
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }
}
