import SwiftUI
struct DevicesView: View {
    @EnvironmentObject var state: AppState
    var body: some View {
        List {
            Text("DevicesView").font(.title.bold())
            Text("Consent-based, local-first Shadow Agent command center.")
            Toggle("Emergency pause", isOn: $state.emergencyPaused)
            if "DevicesView" == "AutonomySettingsView" { Picker("Autonomy", selection: $state.autonomyMode) { ForEach(AutonomyMode.allCases) { Text($0.rawValue).tag($0) } } }
        }.navigationTitle("Shadow")
    }
}
