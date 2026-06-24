# Shadow Agent Alpha

Production-shaped local-first personal AI agent alpha for iOS + desktop Shadow Node + encrypted personal memory.

## Demoable end-to-end flow
1. Pair a demo iOS/device identity with Shadow Node.
2. Ingest approved text into encrypted memory.
3. Ask Shadow a question.
4. Retrieve memory and package context through AXIOM redaction/compression.
5. Generate an action and approval request.
6. Approve/deny the action.
7. Execute a safe local mock task through the Ghost adapter.
8. Inspect durable audit, device, approval, task, consent, and memory state.

## Run backend
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
make run
```

## Run demo
```bash
make run   # terminal 1
make demo  # terminal 2
```

## Test
```bash
pytest -q
```

## Key paths
- `apps/shadow-node` FastAPI runtime, durable stores, pairing, connectors, model providers.
- `apps/ios-shadow` SwiftUI command-center package and Xcode-ready README.
- `packages/memory-engine` encrypted memory with SQLite/FTS5.
- `packages/agent-core` policy, autonomy, approval, task, audit models.
- `packages/axiom-adapter` redaction/compression/fingerprint/skeleton context packaging.
- `packages/ghost-adapter` approval-gated safe mock execution and telemetry.
- `docs/` alpha specifications and demo documentation.
