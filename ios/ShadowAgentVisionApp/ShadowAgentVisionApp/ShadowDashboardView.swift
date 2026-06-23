#if canImport(SwiftUI)
import SwiftUI
import ShadowAgentCore

struct ShadowDashboardView: View {
    @ObservedObject var viewModel: ShadowAgentViewModel

    var body: some View {
        NavigationStack {
            List {
                Section("Vision") {
                    Label("Always-on personal AI agent", systemImage: "sparkles")
                    Label("Permissioned context collection", systemImage: "hand.raised")
                    Label("Hybrid local RAG + frontier reasoning", systemImage: "lock.shield")
                }

                Section("Consent") {
                    Button("Grant Notes Read Access") {
                        Task { await viewModel.grant(scope: .notes, read: true, write: false) }
                    }
                    Button("Grant Calendar Write Access") {
                        Task { await viewModel.grant(scope: .calendar, read: true, write: true) }
                    }
                }

                Section("Agent") {
                    Button("Ingest Demo Context") {
                        Task { try? await viewModel.ingestDemoContext() }
                    }
                    Button("Recommend Morning Brief") {
                        Task { try? await viewModel.recommendMorningBrief() }
                    }
                    Button("Evaluate Calendar Action") {
                        Task { try? await viewModel.approveCalendarAction() }
                    }

                    if let recommendation = viewModel.latestRecommendation {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(recommendation.title).font(.headline)
                            Text(recommendation.rationale).font(.caption)
                        }
                    }

                    if let decision = viewModel.latestDecision {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(decision.outcome.rawValue).font(.headline)
                            Text(decision.message).font(.caption)
                        }
                    }
                }

                Section("Audit Log") {
                    ForEach(viewModel.auditEntries) { entry in
                        VStack(alignment: .leading) {
                            Text(entry.type.rawValue).font(.headline)
                            Text(entry.summary).font(.caption)
                        }
                    }
                }
            }
            .navigationTitle("Shadow Agent")
        }
    }
}
#endif
