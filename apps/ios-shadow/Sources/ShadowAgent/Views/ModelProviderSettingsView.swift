import SwiftUI
struct ModelProviderSettingsView: View { var body: some View { List { Text("Model Provider Settings").font(.title.bold()); Text("Local mock is default. Cloud providers require consent, redaction, and per-request escalation approval.") }.navigationTitle("Models") } }
