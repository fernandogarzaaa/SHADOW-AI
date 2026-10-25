import SwiftUI

struct ModelProviderSettingsView: View {
    var body: some View {
        List {
            Section("How answers are produced") {
                Text("Without a cloud provider, answers come from the node's placeholder model. Connect a provider (Anthropic, OpenAI or Gemini) and allow cloud use to get real answers.")
                Text("When a cloud model is used, it receives compressed and redacted context only. Items marked sensitive never leave the node.")
                    .foregroundStyle(.secondary)
            }
            Section {
                Text("Connect providers from the dashboard on your computer: open the node's address in a browser and go to Models.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Model providers")
    }
}
