import SwiftUI

struct OnboardingView: View {
    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    Image(systemName: "shield.lefthalf.filled")
                        .font(.system(size: 40))
                        .foregroundStyle(.tint)
                        .accessibilityHidden(true)
                    Text("Shadow")
                        .font(.largeTitle.bold())
                    Text("Your private agent runs on your own computer. This iPhone pairs with it to ask questions, review approvals, and pause it at any time.")
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 8)
            }
            Section("How it works") {
                Label("Memory stays encrypted on your node.", systemImage: "lock")
                Label("Nothing runs until you approve it.", systemImage: "checkmark.shield")
                Label("Every decision is in the audit log.", systemImage: "list.bullet.rectangle")
            }
            Section {
                NavigationLink {
                    PairDeviceView()
                } label: {
                    Label("Pair with your node", systemImage: "link")
                        .font(.headline)
                }
            }
        }
        .navigationTitle("Welcome")
    }
}
