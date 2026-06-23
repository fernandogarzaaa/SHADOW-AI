import SwiftUI
struct ConnectorSettingsView: View { var body: some View { List { Text("Connector Settings").font(.title.bold()); Text("Manual file import is enabled. OAuth connectors are future gated integrations.") }.navigationTitle("Connectors") } }
