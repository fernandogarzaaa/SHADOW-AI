import SwiftUI
struct ConnectorSettingsView: View { var body: some View { List { Text("Connector Settings").font(.title.bold()); Text("Manual paste and user-selected text files are supported. Shadow does not scan files covertly."); Text("Future: Share Extension and security-scoped document picker upload for .txt, .md, .markdown, and .json.") }.navigationTitle("Connectors") } }
