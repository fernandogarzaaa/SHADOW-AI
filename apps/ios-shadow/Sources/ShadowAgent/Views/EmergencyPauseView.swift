import SwiftUI

struct EmergencyPauseView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        Form {
            Section {
                EmergencyPauseToggle()
            } footer: {
                Text("Blocks every action on the node and records an audit event. Any paired device can pause or resume.")
            }
        }
        .navigationTitle("Emergency pause")
        .task { await state.refreshHealth() }
    }
}
