import SwiftUI

/// How much Shadow may do on its own. The policy lives on the node; this
/// screen explains it rather than offering switches the node doesn't read.
struct AutonomySettingsView: View {
    var body: some View {
        List {
            Section {
                Label("Suggest only", systemImage: "hand.raised")
                    .font(.headline)
                Text("Shadow proposes actions and waits for your approval. Irreversible actions (sending, deleting, paying) always need a second confirmation, whatever the mode.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } header: {
                Text("Current mode")
            }
            Section("Always true") {
                Label("Nothing runs without an approval you can see.", systemImage: "checkmark.shield")
                Label("An approval covers one run of exactly the action shown.", systemImage: "1.circle")
                Label("Emergency pause stops everything immediately.", systemImage: "pause.circle")
            }
            Section {
                Text("To change the policy, edit policy.yaml on the node.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Autonomy")
    }
}
