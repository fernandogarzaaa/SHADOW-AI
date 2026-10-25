import SwiftUI

struct ApprovalDetailView: View {
    @EnvironmentObject var state: AppState
    @Environment(\.dismiss) private var dismiss
    let approval: ApprovalRequest
    @State private var denyReason = ""
    @State private var doubleConfirm = false
    @State private var result: ExecutionResult?
    @State private var busy = false

    private var needsSecondConfirmation: Bool { approval.requiresDoubleConfirmation == true }

    var body: some View {
        Form {
            Section("Action") {
                Text(approval.actionPreview ?? approval.action.description)
                LabeledContent("Tool", value: approval.action.toolName)
                LabeledContent("Risk") { RiskBadge(risk: approval.riskLabel) }
                if let dest = approval.destinationPreview { LabeledContent("Destination", value: dest) }
                if let model = approval.modelUsedPreview { LabeledContent("Model", value: model) }
                ForEach(approval.dataUsedPreview ?? [], id: \.self) { Text("Uses: \($0)").font(.caption) }
                if let consequence = approval.consequence {
                    Text(consequence).foregroundStyle(.orange)
                }
            }
            if let params = approval.action.params, !params.isEmpty {
                Section("Details") {
                    ForEach(params.keys.sorted(), id: \.self) { key in
                        LabeledContent(key, value: params[key]?.description ?? "")
                    }
                }
            }

            switch approval.status {
            case .pending:
                Section {
                    Button("Approve once") { act { await state.approve(approval) } }
                    TextField("Reason (optional)", text: $denyReason)
                    Button("Deny", role: .destructive) { act { await state.deny(approval, reason: denyReason) } }
                } header: {
                    Text("Decision")
                } footer: {
                    Text("Approving lets this action run once, exactly as shown.")
                }
            case .approved:
                Section {
                    if needsSecondConfirmation {
                        Toggle("I understand this can't be undone", isOn: $doubleConfirm)
                    }
                    Button("Run now") {
                        Task {
                            busy = true
                            result = await state.run(approval, doubleConfirmed: doubleConfirm)
                            busy = false
                        }
                    }
                    .disabled(busy || (needsSecondConfirmation && !doubleConfirm))
                } header: {
                    Text("Approved")
                }
            default:
                Section { Text("This approval is \(approval.status.rawValue).").foregroundStyle(.secondary) }
            }

            if let result {
                Section("Result") {
                    Text(result.summary)
                    if let reason = result.verificationReason { Text(reason).font(.caption).foregroundStyle(.secondary) }
                }
            }
        }
        .disabled(busy)
        .navigationTitle("Approval")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func act(_ work: @escaping () async -> Void) {
        Task {
            busy = true
            await work()
            busy = false
            dismiss()
        }
    }
}
