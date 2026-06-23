import SwiftUI
struct EmergencyPauseView: View { @EnvironmentObject var state: AppState; var body: some View { VStack(spacing: 20) { Text("Emergency Pause").font(.largeTitle.bold()); Toggle("Block all execution", isOn: $state.emergencyPaused).padding(); Text("When enabled, Shadow refuses every action until you resume.") }.padding().navigationTitle("Pause") } }
