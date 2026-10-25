import SwiftUI

struct DevicesView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        List {
            if state.devices.isEmpty {
                Text("No devices.").foregroundStyle(.secondary)
            }
            ForEach(state.devices) { d in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(d.name).font(.subheadline.weight(.medium))
                        if d.id == state.pairedIdentity?.deviceId { Text("this iPhone").font(.caption).foregroundStyle(.tint) }
                        if d.isOwner == true { Text("owner").font(.caption).foregroundStyle(.secondary) }
                    }
                    Text(status(d)).font(.caption).foregroundStyle(d.revoked == true ? .red : .secondary)
                }
                .swipeActions {
                    if d.revoked != true {
                        Button("Disconnect", role: .destructive) { Task { await state.revoke(d) } }
                        Button("Renew") { Task { await state.renew(d) } }.tint(.blue)
                    }
                }
            }
        }
        .navigationTitle("Devices")
        .refreshable { await state.loadDevices() }
        .task { await state.loadDevices() }
    }

    private func status(_ d: Device) -> String {
        if d.revoked == true { return "Disconnected" }
        guard let expires = NodeDate.parse(d.sessionExpiresAt) else { return "Paired" }
        let days = Int(expires.timeIntervalSinceNow / 86_400)
        return days < 0 ? "Session expired" : "Session renews automatically · \(days) days left"
    }
}
