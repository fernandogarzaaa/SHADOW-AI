import SwiftUI

struct AskShadowView: View {
    @EnvironmentObject var state: AppState
    @State private var prompt = ""
    @State private var allowCloud = false
    @State private var asking = false

    var body: some View {
        List {
            Section {
                TextField("What did I note about Aurora?", text: $prompt, axis: .vertical)
                    .lineLimit(2...6)
                Toggle("Use the cloud model", isOn: $allowCloud)
                Button {
                    Task {
                        asking = true
                        await state.ask(prompt, allowCloud: allowCloud)
                        asking = false
                    }
                } label: {
                    HStack {
                        Text("Ask")
                        if asking { Spacer(); ProgressView() }
                    }
                }
                .disabled(asking || prompt.trimmingCharacters(in: .whitespaces).isEmpty)
            } footer: {
                Text("The cloud model needs a cloud consent grant on the node. Without it, answers stay on your node.")
            }

            if let answer = state.lastAnswer {
                Section("Answer") {
                    Text(answer.answer)
                        .textSelection(.enabled)
                        .foregroundStyle(answer.degraded == true ? .red : .primary)
                    LabeledContent("Answered by", value: answer.route == "frontier" ? "Cloud · \(answer.modelUsed ?? "")" : "On-device · \(answer.modelUsed ?? "local")")
                    if answer.modelUsed == "local_mock" {
                        Text("This came from the placeholder model, not a real one. Connect a provider on the node's dashboard for real answers.")
                            .font(.footnote)
                            .foregroundStyle(.orange)
                    }
                }
                if !answer.sources.isEmpty {
                    Section("Sources") {
                        ForEach(answer.sources) { r in
                            NavigationLink { MemoryDetailView(result: r) } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(r.attribution).font(.subheadline.weight(.medium))
                                    Text(r.item.text).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                                }
                            }
                        }
                        Text("Retrieved text is treated as untrusted and can't override policy.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle("Ask Shadow")
    }
}
