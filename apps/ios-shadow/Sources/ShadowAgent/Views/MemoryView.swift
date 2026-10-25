import SwiftUI

struct MemoryView: View {
    @EnvironmentObject var state: AppState
    @State private var text = ""
    @State private var title = ""
    @State private var query = ""
    @State private var saving = false

    var body: some View {
        List {
            Section {
                TextField("Source title", text: $title)
                TextField("Text to remember", text: $text, axis: .vertical)
                    .lineLimit(3...10)
                Button {
                    Task {
                        saving = true
                        if await state.ingest(text: text, title: title) { text = "" }
                        saving = false
                    }
                } label: {
                    HStack { Text("Save to memory"); if saving { Spacer(); ProgressView() } }
                }
                .disabled(saving || text.trimmingCharacters(in: .whitespaces).isEmpty)
            } header: {
                Text("Add")
            } footer: {
                Text("Stored encrypted on your node. Shadow never scans your files on its own.")
            }

            Section("Results") {
                if state.searchResults.isEmpty {
                    Text(query.isEmpty ? "Search to see what Shadow remembers." : "No matches.")
                        .foregroundStyle(.secondary)
                }
                ForEach(state.searchResults) { r in
                    NavigationLink { MemoryDetailView(result: r) } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(r.attribution).font(.subheadline.weight(.medium))
                            Text(r.item.text).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                        }
                    }
                }
            }
        }
        .navigationTitle("Memory")
        .searchable(text: $query, prompt: "Search memory")
        .onSubmit(of: .search) { Task { await state.search(query) } }
        .onChange(of: query) { _, newValue in
            if newValue.isEmpty { state.searchResults = [] }
        }
    }
}
