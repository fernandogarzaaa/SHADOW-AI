import SwiftUI

struct AuditLogView: View {
    @EnvironmentObject var state: AppState
    @State private var filter = ""

    private var filtered: [AuditEvent] {
        filter.isEmpty ? state.auditEvents : state.auditEvents.filter { $0.eventType.localizedCaseInsensitiveContains(filter) }
    }

    var body: some View {
        List {
            if filtered.isEmpty {
                Text(state.auditEvents.isEmpty ? "No events yet." : "No events match.").foregroundStyle(.secondary)
            }
            ForEach(filtered) { e in
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(e.eventType).font(.subheadline.weight(.medium))
                        Spacer()
                        Text(e.status).font(.caption).foregroundStyle(color(for: e.status))
                    }
                    if let detail = e.proposedAction ?? e.result { Text(detail).font(.caption).foregroundStyle(.secondary) }
                    if let date = NodeDate.parse(e.timestamp) {
                        Text(date, format: .dateTime.month().day().hour().minute().second())
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                }
                .accessibilityElement(children: .combine)
            }
        }
        .navigationTitle("Audit log")
        .searchable(text: $filter, prompt: "Filter by event")
        .refreshable { await state.loadAudit() }
        .task { await state.loadAudit() }
    }

    private func color(for status: String) -> Color {
        switch status {
        case "blocked", "denied", "revoked": return .red
        case "pending", "fallback_local": return .orange
        case "answered", "allowed", "stored", "approved", "trusted", "ok": return .green
        default: return .secondary
        }
    }
}
