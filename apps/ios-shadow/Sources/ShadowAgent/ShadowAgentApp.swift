import SwiftUI
@main struct ShadowAgentApp: App {
    @StateObject private var state = AppState()
    var body: some Scene { WindowGroup { NavigationStack { HomeView() }.environmentObject(state) } }
}
