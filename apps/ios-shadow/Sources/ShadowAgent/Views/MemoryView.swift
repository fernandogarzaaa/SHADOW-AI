import SwiftUI
struct MemoryView: View {
    @EnvironmentObject var state: AppState
    var body: some View {
        List {
            Text("MemoryView").font(.title.bold())
            Text("Consent-based, local-first Shadow Agent command center.")
            Toggle("Emergency pause", isOn: $state.emergencyPaused)
            if "MemoryView" == "AutonomySettingsView" { Picker("Autonomy", selection: $state.autonomyMode) { ForEach(AutonomyMode.allCases) { Text($0.rawValue).tag($0) } } }
        }.navigationTitle("Shadow")
    }
}
