import SwiftUI
struct HomeView: View {
 @EnvironmentObject var state: AppState
 var body: some View { List {
  if state.emergencyPaused { Section { Text("🚨 Emergency pause is ON. All execution is blocked.").foregroundStyle(.red) } }
  Section("Node") { Toggle("Local mock mode", isOn: $state.mockMode).onChange(of: state.mockMode) { _, _ in state.refreshClient() }; TextField("Node URL", text: $state.baseURLText).textInputAutocapitalization(.never); Button("Sync emergency pause") { Task { await state.setEmergencyPause(!state.emergencyPaused) } }; Text(state.statusMessage).font(.footnote) }
  Section("Command Center") { NavigationLink("Ask Shadow", destination: AskShadowView()); NavigationLink("Memory", destination: MemoryView()); NavigationLink("Approvals", destination: ApprovalsView()); NavigationLink("Devices / Pair", destination: DevicesView()); NavigationLink("Audit Log", destination: AuditLogView()) }
  Section("Trust") { NavigationLink("Privacy Dashboard", destination: PrivacyDashboardView()); NavigationLink("Autonomy Settings", destination: AutonomySettingsView()); NavigationLink("Connector Settings", destination: ConnectorSettingsView()); NavigationLink("Model Provider Settings", destination: ModelProviderSettingsView()); NavigationLink("Emergency Pause", destination: EmergencyPauseView()) }
 }.navigationTitle("Shadow Agent") }
}
