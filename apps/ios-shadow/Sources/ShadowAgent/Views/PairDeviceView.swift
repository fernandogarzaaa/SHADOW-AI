import SwiftUI

struct PairDeviceView: View {
    @EnvironmentObject var state: AppState
    @State private var nodeURL = "http://127.0.0.1:8787"
    @State private var deviceName = "iOS Device"
    @State private var status = "Enter your local Shadow Node URL, check health, then pair."
    @State private var isLoading = false

    var body: some View {
        Form {
            Section("Shadow Node") {
                TextField("Node URL", text: $nodeURL)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
                TextField("Device name", text: $deviceName)
                Button(isLoading ? "Working…" : "Check node health") { Task { await checkHealth() } }
                    .disabled(isLoading)
                Button("Pair this device") { Task { await pairDevice() } }
                    .disabled(isLoading)
            }
            Section("Status") {
                Text(status)
                if state.emergencyPaused { Text("Emergency pause is enabled. Pairing is allowed, but execution remains blocked.").foregroundStyle(.orange) }
            }
            Section("Safety") {
                Text("Pairing pins this device public key on your local node. Protected memory, consent, approval, and execution APIs require signed requests after pairing.")
                    .font(.footnote)
            }
        }
        .navigationTitle("Pair Device")
    }

    private func client() throws -> HTTPShadowAPIClient {
        guard let url = URL(string: nodeURL) else { throw URLError(.badURL) }
        return HTTPShadowAPIClient(settings: ShadowNodeSettings(baseURL: url, localMockMode: false))
    }

    private func checkHealth() async {
        await runStatusTask(success: "Node is reachable.") { try await client().health() ? nil : "Node returned an unhealthy response." }
    }

    private func pairDevice() async {
        await runStatusTask(success: "Device paired. Signed requests are active.") { try await client().pair(code: deviceName); return nil }
    }

    private func runStatusTask(success: String, operation: () async throws -> String?) async {
        isLoading = true; defer { isLoading = false }
        do { if let message = try await operation() { status = message } else { status = success } }
        catch { status = "Unable to complete request: \(error.localizedDescription)" }
    }
}
