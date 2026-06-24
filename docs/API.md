# API

Shadow Agent RC1 is local-first and privacy-sensitive. The production baseline keeps health and pairing public; all personal-data and execution routes require Ed25519 signed requests from a trusted paired device. Signatures cover method, path, body, nonce, and timestamp; replayed nonces, expired timestamps, invalid signatures, and revoked devices are rejected and audited.

## RC behavior
- Local mock provider is default; cloud providers require consent plus explicit per-request approval.
- Memory ingestion supports manual text and text-like documents (, , , ) through user-approved flows.
- Retrieved memory is treated as untrusted context and cannot override policy.
- Emergency pause blocks ingestion and execution handoff.
- Audit records are append-only by API semantics.

## Validation
Run Requirement already satisfied: fastapi>=0.111 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from -r requirements.txt (line 1)) (0.138.0)
Requirement already satisfied: uvicorn>=0.30 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from uvicorn[standard]>=0.30->-r requirements.txt (line 2)) (0.49.0)
Requirement already satisfied: pydantic>=2.7 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from -r requirements.txt (line 3)) (2.13.4)
Requirement already satisfied: cryptography>=42 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from -r requirements.txt (line 4)) (49.0.0)
Requirement already satisfied: pytest>=8 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from -r requirements.txt (line 5)) (9.0.3)
Requirement already satisfied: httpx>=0.27 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from -r requirements.txt (line 6)) (0.28.1)
Requirement already satisfied: aiosqlite>=0.19 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from -r requirements.txt (line 7)) (0.22.1)
Requirement already satisfied: pytest-asyncio>=0.23 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from -r requirements.txt (line 8)) (1.4.0)
Requirement already satisfied: starlette>=0.46.0 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from fastapi>=0.111->-r requirements.txt (line 1)) (1.3.1)
Requirement already satisfied: typing-extensions>=4.8.0 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from fastapi>=0.111->-r requirements.txt (line 1)) (4.15.0)
Requirement already satisfied: typing-inspection>=0.4.2 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from fastapi>=0.111->-r requirements.txt (line 1)) (0.4.2)
Requirement already satisfied: annotated-doc>=0.0.2 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from fastapi>=0.111->-r requirements.txt (line 1)) (0.0.4)
Requirement already satisfied: click>=7.0 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from uvicorn>=0.30->uvicorn[standard]>=0.30->-r requirements.txt (line 2)) (8.3.3)
Requirement already satisfied: h11>=0.8 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from uvicorn>=0.30->uvicorn[standard]>=0.30->-r requirements.txt (line 2)) (0.16.0)
Requirement already satisfied: annotated-types>=0.6.0 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from pydantic>=2.7->-r requirements.txt (line 3)) (0.7.0)
Requirement already satisfied: pydantic-core==2.46.4 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from pydantic>=2.7->-r requirements.txt (line 3)) (2.46.4)
Requirement already satisfied: cffi>=2.0.0 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from cryptography>=42->-r requirements.txt (line 4)) (2.0.0)
Requirement already satisfied: iniconfig>=1.0.1 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from pytest>=8->-r requirements.txt (line 5)) (2.3.0)
Requirement already satisfied: packaging>=22 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from pytest>=8->-r requirements.txt (line 5)) (26.2)
Requirement already satisfied: pluggy<2,>=1.5 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from pytest>=8->-r requirements.txt (line 5)) (1.6.0)
Requirement already satisfied: pygments>=2.7.2 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from pytest>=8->-r requirements.txt (line 5)) (2.20.0)
Requirement already satisfied: anyio in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from httpx>=0.27->-r requirements.txt (line 6)) (4.14.0)
Requirement already satisfied: certifi in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from httpx>=0.27->-r requirements.txt (line 6)) (2026.6.17)
Requirement already satisfied: httpcore==1.* in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from httpx>=0.27->-r requirements.txt (line 6)) (1.0.9)
Requirement already satisfied: idna in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from httpx>=0.27->-r requirements.txt (line 6)) (3.18)
Requirement already satisfied: pycparser in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from cffi>=2.0.0->cryptography>=42->-r requirements.txt (line 4)) (3.0)
Requirement already satisfied: httptools>=0.8.0 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from uvicorn[standard]>=0.30->-r requirements.txt (line 2)) (0.8.0)
Requirement already satisfied: python-dotenv>=0.13 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from uvicorn[standard]>=0.30->-r requirements.txt (line 2)) (1.2.2)
Requirement already satisfied: pyyaml>=5.1 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from uvicorn[standard]>=0.30->-r requirements.txt (line 2)) (6.0.3)
Requirement already satisfied: uvloop>=0.15.1 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from uvicorn[standard]>=0.30->-r requirements.txt (line 2)) (0.22.1)
Requirement already satisfied: watchfiles>=0.20 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from uvicorn[standard]>=0.30->-r requirements.txt (line 2)) (1.2.0)
Requirement already satisfied: websockets>=10.4 in /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages (from uvicorn[standard]>=0.30->-r requirements.txt (line 2)) (16.0), ...............................................F........................ [ 47%]
........................................................................ [ 95%]
.......                                                                  [100%]
=================================== FAILURES ===================================
___________________ test_memory_ingest_search_ask_and_audit ____________________

    def test_memory_ingest_search_ask_and_audit():
        d,i=pair(); payload={'text':'Project Alpha launch notes mention privacy first local memory','source_title':'alpha.md'}
        assert request('POST','/memory/ingest',d,i,payload).status_code==200
        assert request('GET','/memory/search?q=Alpha',d,i).status_code==200
        ask=request('POST','/agent/ask',d,i,{'prompt':'Alpha privacy','provider':'local_mock'}).json()
>       assert ask['sources'] and ask['model']['cloud_used'] is False
E       assert ([])

tests/test_production_rc.py:66: AssertionError
=============================== warnings summary ===============================
../../root/.pyenv/versions/3.12.13/lib/python3.12/site-packages/fastapi/testclient.py:1
  /root/.pyenv/versions/3.12.13/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_production_rc.py::test_memory_ingest_search_ask_and_audit
1 failed, 150 passed, 1 warning in 3.73s, Listing 'apps/shadow-node'...
Listing 'apps/shadow-node/shadow_node'...
Listing 'packages'...
Listing 'packages/agent-core'...
Listing 'packages/agent-core/agent_core'...
Listing 'packages/axiom-adapter'...
Listing 'packages/axiom-adapter/axiom_adapter'...
Listing 'packages/ghost-adapter'...
Listing 'packages/ghost-adapter/ghost_adapter'...
Listing 'packages/memory-engine'...
Listing 'packages/memory-engine/memory_engine'..., and PYTHONPATH=apps/shadow-node:packages/agent-core:packages/memory-engine:packages/axiom-adapter:packages/ghost-adapter python scripts/demo_e2e.py
1 health {'status': 'ok', 'version': '0.2.0-alpha', 'local_first': True, 'emergency_paused': False}
2 paired dev_672c1efd8ece437e9627eb6d192f3eb5
3 ingest 1
4 answer Local answer based on approved context: 
5 approval apr_23f8b51d58c0490bbf0b9a8e4e3bb500
6 execute {'ok': True, 'ghost': {'status': 'completed', 'result': 'Safe mock local task executed by Ghost adapter.', 'ir': {'objective': 'Demo safe local action', 'steps': [{'tool': 'create_local_reminder', 'risk': 'RiskClass.LOW', 'description': 'Create a safe local reminder draft for Project Alpha Friday review', 'params': {'title': 'Review Project Alpha', 'due': 'Friday'}}], 'safety_profile': 'approval_gated'}, 'telemetry': {'status': 'completed', 'backend': 'mock-ghost', 'started_at': '2026-06-24T05:50:45.908140+00:00', 'finished_at': '2026-06-24T05:50:45.908153+00:00', 'steps_executed': 1, 'error': None}}}
7 audit events 6
[
  {
    "id": "aud_7cd366e01e93414689b579c0e5f8fa2d",
    "actor": "user",
    "event_type": "memory_ingest",
    "data_used": [
      "Project Alpha Brief"
    ],
    "model_used": null,
    "permission_checked": null,
    "proposed_action": null,
    "status": "stored",
    "result": null,
    "timestamp": "2026-06-24T05:50:45.833180Z"
  },
  {
    "id": "aud_58367630f91a4750859505327aa38b82",
    "actor": "shadow_node",
    "event_type": "agent_ask",
    "data_used": [],
    "model_used": "local_mock",
    "permission_checked": null,
    "proposed_action": null,
    "status": "answered",
    "result": null,
    "timestamp": "2026-06-24T05:50:45.846425Z"
  },
  {
    "id": "aud_27203b6fbfaf4cff8086f84f26b02829",
    "actor": "shadow_node",
    "event_type": "approval_requested",
    "data_used": [],
    "model_used": null,
    "permission_checked": "RiskClass.LOW",
    "proposed_action": "Create a safe local reminder draft for Project Alpha Friday review",
    "status": "recorded",
    "result": null,
    "timestamp": "2026-06-24T05:50:45.879558Z"
  },
  {
    "id": "aud_4d3fdbdc20604680a65dbb64da7e3f67",
    "actor": "shadow_node",
    "event_type": "approval_decided",
    "data_used": [],
    "model_used": null,
    "permission_checked": null,
    "proposed_action": "Create a safe local reminder draft for Project Alpha Friday review",
    "status": "approved",
    "result": null,
    "timestamp": "2026-06-24T05:50:45.897184Z"
  },
  {
    "id": "aud_2d86fdc5dc6c4f718389def6a7ceb288",
    "actor": "shadow_node",
    "event_type": "ghost_execute",
    "data_used": [],
    "model_used": null,
    "permission_checked": null,
    "proposed_action": "Create a safe local reminder draft for Project Alpha Friday review",
    "status": "completed",
    "result": "{'status': 'completed', 'backend': 'mock-ghost', 'started_at': '2026-06-24T05:50:45.908140+00:00', 'finished_at': '2026-06-24T05:50:45.908153+00:00', 'steps_executed': 1, 'error': None}",
    "timestamp": "2026-06-24T05:50:45.908277Z"
  }
]. iOS validation must be completed on macOS by opening  in Xcode, selecting an iOS simulator or device, and building/running the ShadowAgent target.

## Release notes
This document is part of the production release-candidate package. Mock OAuth, live cloud models, and real GHOST/AXIOM runtime binaries remain post-RC integration tasks unless explicitly configured by the operator.
