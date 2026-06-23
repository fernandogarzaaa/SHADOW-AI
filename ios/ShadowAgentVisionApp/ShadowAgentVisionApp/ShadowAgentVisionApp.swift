#if canImport(SwiftUI)
import SwiftUI
import ShadowAgentCore

@main
struct ShadowAgentVisionApp: App {
    @StateObject private var viewModel = ShadowAgentViewModel()

    var body: some Scene {
        WindowGroup {
            ShadowDashboardView(viewModel: viewModel)
        }
    }
}
#endif
