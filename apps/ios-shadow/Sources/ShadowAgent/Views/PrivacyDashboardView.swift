import SwiftUI
struct PrivacyDashboardView: View {
    @EnvironmentObject var state: AppState
    var body: some View {
        List {
            Text("PrivacyDashboardView").font(.title.bold())
            Text("Consent-based, local-first Shadow Agent command center.")
            Toggle("Emergency pause", isOn: $state.emergencyPaused)
            if "PrivacyDashboardView" == "AutonomySettingsView" { Picker("Autonomy", selection: $state.autonomyMode) { ForEach(AutonomyMode.allCases) { Text($0.rawValue).tag($0) } } }
        }.navigationTitle("Shadow")
    }
}
