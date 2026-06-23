import SwiftUI
struct HomeView: View {
 @EnvironmentObject var state: AppState
 var body: some View { List {
  Section("Command Center") { NavigationLink("Ask Shadow", destination: AskShadowView()); NavigationLink("Memory", destination: MemoryView()); NavigationLink("Approvals", destination: ApprovalsView()); NavigationLink("Devices", destination: DevicesView()); NavigationLink("Audit Log", destination: AuditLogView()) }
  Section("Trust") { NavigationLink("Privacy Dashboard", destination: PrivacyDashboardView()); NavigationLink("Autonomy Settings", destination: AutonomySettingsView()); NavigationLink("Connector Settings", destination: ConnectorSettingsView()); NavigationLink("Model Provider Settings", destination: ModelProviderSettingsView()); NavigationLink("Emergency Pause", destination: EmergencyPauseView()) }
 }.navigationTitle("Shadow Agent") }
}
