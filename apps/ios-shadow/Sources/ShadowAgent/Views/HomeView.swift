import SwiftUI

/// Command center: one tab per job, with the pause state always visible.
struct HomeView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        TabView {
            NavigationStack { AskShadowView() }
                .tabItem { Label("Ask", systemImage: "bubble.left.and.text.bubble.right") }
            NavigationStack { ApprovalsView() }
                .tabItem { Label("Approvals", systemImage: "checkmark.shield") }
                .badge(state.approvals.count)
            NavigationStack { MemoryView() }
                .tabItem { Label("Memory", systemImage: "brain") }
            NavigationStack { SettingsView() }
                .tabItem { Label("Settings", systemImage: "gearshape") }
        }
        .safeAreaInset(edge: .top) {
            if state.emergencyPaused {
                PausedBanner()
            }
        }
        .task { await state.refreshAll() }
    }
}

struct PausedBanner: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "pause.circle.fill").accessibilityHidden(true)
            Text("Emergency pause is on. Shadow won't act.")
                .font(.callout.weight(.medium))
            Spacer()
            Button("Resume") { Task { await state.setEmergencyPause(false) } }
                .font(.callout.bold())
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 16).padding(.vertical, 10)
        .background(.red)
        .accessibilityElement(children: .combine)
    }
}
