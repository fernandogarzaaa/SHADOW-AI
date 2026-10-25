import SwiftUI

struct MemoryDetailView: View {
    let result: MemorySearchResult

    var body: some View {
        List {
            Section("Text") {
                Text(result.item.text).textSelection(.enabled)
            }
            Section("Where it came from") {
                LabeledContent("Source", value: result.attribution)
                LabeledContent("Confidence", value: String(format: "%.2f", result.item.confidence))
                LabeledContent("Freshness", value: String(format: "%.2f", result.freshness))
                Text(result.explanation).font(.caption).foregroundStyle(.secondary)
            }
            Section("Privacy") {
                LabeledContent("Sensitive", value: result.item.sensitive == true ? "Yes" : "No")
                LabeledContent("Sent to cloud models", value: result.item.doNotSendToCloud == true ? "Never" : "Only with your consent")
            }
        }
        .navigationTitle("Memory")
        .navigationBarTitleDisplayMode(.inline)
    }
}
