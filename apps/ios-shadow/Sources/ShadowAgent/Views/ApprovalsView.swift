import SwiftUI
struct ApprovalsView: View {
    @EnvironmentObject var state: AppState
    var body: some View {
        List {
            Text("ApprovalsView").font(.title.bold())
            Text("Consent-based, local-first Shadow Agent command center.")
            Toggle("Emergency pause", isOn: $state.emergencyPaused)
            if "ApprovalsView" == "AutonomySettingsView" { Picker("Autonomy", selection: $state.autonomyMode) { ForEach(AutonomyMode.allCases) { Text($0.rawValue).tag($0) } } }
        }.navigationTitle("Shadow")
    }
}
