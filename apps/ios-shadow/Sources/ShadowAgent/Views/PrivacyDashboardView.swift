import SwiftUI

struct PrivacyDashboardView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        List {
            Section("Where your data lives") {
                Label("Memory is stored encrypted on your node, not on this iPhone.", systemImage: "externaldrive.badge.checkmark")
                Label("Sensitive items are flagged automatically and never sent to a cloud model.", systemImage: "eye.slash")
                Label("Cloud models only see redacted, compressed context, and only when you allow it.", systemImage: "cloud")
            }
            Section("This iPhone") {
                Label("Its signing key is in the Keychain, available only on this device.", systemImage: "key")
                Label("Every request is signed and can't be replayed.", systemImage: "signature")
            }
            Section {
                EmergencyPauseToggle()
                NavigationLink("Review the audit log") { AuditLogView() }
            }
        }
        .navigationTitle("Privacy")
    }
}
