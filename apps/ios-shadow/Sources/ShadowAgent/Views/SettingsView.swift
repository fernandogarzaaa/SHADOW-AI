import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var state: AppState
    @State private var confirmDisconnect = false

    var body: some View {
        List {
            Section("Node") {
                LabeledContent("Address", value: state.pairedIdentity?.baseURL.absoluteString ?? state.baseURLText)
                LabeledContent("Version", value: state.health?.version ?? "unknown")
                if let name = state.pairedIdentity?.deviceName { LabeledContent("This iPhone", value: name) }
            }
            Section {
                EmergencyPauseToggle()
            } footer: {
                Text("Stops the agent from taking any action until you resume it, on every device.")
            }
            Section("Trust") {
                NavigationLink("Privacy") { PrivacyDashboardView() }
                NavigationLink("Autonomy") { AutonomySettingsView() }
                NavigationLink("Model providers") { ModelProviderSettingsView() }
                NavigationLink("Connectors") { ConnectorSettingsView() }
            }
            Section("Activity") {
                NavigationLink("Devices") { DevicesView() }
                NavigationLink("Audit log") { AuditLogView() }
            }
            Section {
                Button("Disconnect this iPhone", role: .destructive) { confirmDisconnect = true }
            }
        }
        .navigationTitle("Settings")
        .refreshable { await state.refreshHealth() }
        .confirmationDialog("Disconnect this iPhone?", isPresented: $confirmDisconnect, titleVisibility: .visible) {
            Button("Disconnect", role: .destructive) { Task { await state.disconnect() } }
        } message: {
            Text("The node revokes this iPhone's key. You'll need to pair again.")
        }
    }
}

/// The node's emergency pause. The toggle shows the node's state and
/// only changes once the node confirms.
struct EmergencyPauseToggle: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        Toggle("Emergency pause", isOn: Binding(
            get: { state.emergencyPaused },
            set: { newValue in Task { await state.setEmergencyPause(newValue) } }
        ))
        .tint(.red)
    }
}
