import SwiftUI
import ThinkingOrbsKit

struct PairDeviceView: View {
    @EnvironmentObject var state: AppState
    @State private var deviceName = UIDevice.current.name
    @State private var setupCode = ""

    var body: some View {
        Form {
            switch state.pairingPhase {
            case .waitingForApproval(let code):
                Section {
                    VStack(spacing: 12) {
                        ThinkingOrb(state: .connecting, size: .px64)
                            .accessibilityHidden(true)
                        Text("Waiting for approval")
                            .font(.headline)
                        Text(code)
                            .font(.system(.largeTitle, design: .monospaced).bold())
                            .accessibilityLabel("Pairing code \(code.map(String.init).joined(separator: " "))")
                        Text("On a device that's already paired (for example the dashboard in your browser), open Devices and approve this code.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
                Section {
                    Button("Cancel", role: .cancel) { state.cancelPairing() }
                }
            default:
                Section {
                    TextField("http://192.168.1.10:8787", text: $state.baseURLText)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textContentType(.URL)
                } header: {
                    Text("Node address")
                } footer: {
                    Text("Start the node with SHADOW_HOST=0.0.0.0 so your iPhone can reach it, and use your computer's local network address.")
                }
                Section("This iPhone") {
                    TextField("Name", text: $deviceName)
                }
                Section {
                    TextField("XXXX-XXXX", text: $setupCode)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .textContentType(.oneTimeCode)
                } header: {
                    Text("Setup code (first device only)")
                } footer: {
                    Text("Only needed if this is the first device for a new node. The code is printed in the terminal where the node is running. Otherwise leave it empty and approve this iPhone from a paired device.")
                }
                Section {
                    Button {
                        state.startPairing(deviceName: deviceName, bootstrapCode: setupCode)
                    } label: {
                        HStack {
                            Text("Pair")
                            if state.pairingPhase == .working {
                                Spacer()
                                ProgressView()
                            }
                        }
                    }
                    .disabled(state.pairingPhase == .working || state.baseURLText.isEmpty)
                }
            }
        }
        .navigationTitle("Pair")
        .task { await state.checkNode() }
    }
}
