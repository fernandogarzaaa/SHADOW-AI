import SwiftUI
struct ModelProviderSettingsView: View { var body: some View { List { Text("Model Provider Settings").font(.title.bold()); Text("Local mock is default. Cloud providers require consent and per-request approval.") }.navigationTitle("Models") } }
