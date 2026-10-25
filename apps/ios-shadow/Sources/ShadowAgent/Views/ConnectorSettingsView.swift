import SwiftUI

struct ConnectorSettingsView: View {
    var body: some View {
        List {
            Section("Available now") {
                Label("Paste text into Memory", systemImage: "doc.on.clipboard")
            }
            Section("Coming later") {
                Label("Share sheet: send selected text or files to Shadow", systemImage: "square.and.arrow.up")
                Label("Pick .txt, .md and .json files to import", systemImage: "doc")
            }
            Section {
                Text("Shadow never scans your files or accounts on its own. Everything it knows, you gave it.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Connectors")
    }
}
