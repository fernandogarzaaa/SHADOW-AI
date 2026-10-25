import SwiftUI

@main
struct ShadowAgentApp: App {
    @StateObject private var state = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(state)
        }
    }
}

/// Paired -> the command center; otherwise onboarding and pairing.
struct RootView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        Group {
            if state.isPaired {
                HomeView()
            } else {
                NavigationStack { OnboardingView() }
            }
        }
        .alert("Something went wrong", isPresented: Binding(
            get: { state.errorMessage != nil },
            set: { if !$0 { state.errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(state.errorMessage ?? "")
        }
        .overlay(alignment: .bottom) {
            if let notice = state.notice {
                Text(notice)
                    .font(.callout)
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .background(.regularMaterial, in: Capsule())
                    .padding(.bottom, 24)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .task(id: notice) {
                        try? await Task.sleep(nanoseconds: 2_500_000_000)
                        withAnimation { state.notice = nil }
                    }
                    .accessibilityAddTraits(.updatesFrequently)
            }
        }
        .animation(.default, value: state.notice)
    }
}
