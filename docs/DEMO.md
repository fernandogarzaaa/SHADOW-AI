# Demo

## Backend demo
Run `make demo`. The script uses FastAPI TestClient to verify health, create a local-only consent grant, ingest `examples/sample_project_context.md`, ask a memory-backed question, and print approval/audit counts.

## iOS-to-node beta demo
1. Run `make run`.
2. Open `apps/ios-shadow/ShadowAgent.xcodeproj` in Xcode 15+.
3. Select `ShadowAgentApp` and an iOS 17+ simulator.
4. In the app set node URL to `http://127.0.0.1:8787` and disable mock mode.
5. Pair from Devices / Pair.
6. Ingest pasted text from Memory.
7. Ask a question in Ask Shadow and inspect retrieved sources/why explanations.
8. Create an approval, approve/deny, execute safe mock/GHOST action, toggle Emergency Pause, and review Audit Log.

Xcode was not available in the agent container, so simulator validation must be completed locally on macOS.
