"""Live demo of the ambient GHOST capabilities.

Run from the repo root (same PYTHONPATH as `make demo`):

    PYTHONPATH=apps/shadow-node:packages/agent-core:packages/memory-engine:packages/axiom-adapter:packages/ghost-adapter \
        python scripts/demo_ambient.py

Demonstrates, for real against the actual code:
  1. checkpoint save, mid-run interrupt, resume without re-running steps
  2. one ambient scheduler tick producing journal entries
  3. a claim confirmed, then a second claim refuted
"""
import os
import tempfile

os.environ.setdefault("SHADOW_WORKSPACE_DIR", tempfile.mkdtemp(prefix="shadow_demo_ws_"))

from agent_core import (
    AgentCore,
    AmbientScheduler,
    CheckpointStore,
    ClaimRegistry,
    GhostRunSession,
    InMemoryKV,
    RunJournal,
)

calls = []


def probe(params):
    calls.append(params.get("n"))
    return {"ok": True, "n": params.get("n")}


def main():
    store = InMemoryKV()
    core = AgentCore()
    core.tools.register("probe", probe)

    def make_session():
        return GhostRunSession(core, RunJournal(store), CheckpointStore(store), ClaimRegistry(store))

    print("=== 1. checkpoint save / interrupt / resume ===")
    sess = make_session()
    steps = [{"tool": "probe", "description": f"step {i}", "params": {"n": i}} for i in range(3)]
    run_id = sess.start("demo run", steps)
    print(f"started run {run_id}")
    out = sess.run_all(run_id, max_steps=1)  # process "dies" after step 1
    print(f"after crash simulation: status={out['status']}, checkpoint step_index={sess.checkpoints.load(run_id).step_index}")
    print(f"tool calls so far: {calls}")

    sess2 = make_session()  # fresh session objects, same durable store = node restart
    resumed = sess2.resume(run_id)
    print(f"after resume: status={resumed['status']}")
    print(f"tool calls total: {calls}")
    assert calls == [0, 1, 2], "a finished step must never re-execute"
    print("OK: step 0 was not re-executed after resume")

    print()
    print("=== 2. ambient scheduler tick ===")
    sched = AmbientScheduler(
        store=store,
        journal=RunJournal(store),
        tasks={"demo_task": lambda ctx: {"summary": "checked the skies", "data": {"clouds": 0}}},
    )
    print(f"default config enabled={sched.get_config().enabled} (ambient is opt-in)")
    sched.configure(enabled=True, interval_seconds=60, tasks=["demo_task"])
    tick = sched.tick()
    print(f"tick ran={tick['ran']}, results={tick['results']}")
    entries = sched.journal.for_run(tick["run_id"])
    print(f"journal entries for tick {tick['run_id']}:")
    for e in entries:
        print(f"  #{e.seq} [{e.entry_type.value}] {e.message}")
    assert any(e.entry_type.value == "observation" for e in entries)
    print("OK: tick produced journal entries")

    print()
    print("=== 3. claims: confirm then refute ===")
    claims = ClaimRegistry(store)
    c1 = claims.register("the demo workspace exists")
    print(f"registered {c1.id}: status={c1.status.value}")
    c1 = claims.confirm(c1.id, "probe step wrote and read it back")
    print(f"after confirm: status={c1.status.value}, evidence={c1.evidence}")
    c2 = claims.register("the demo ran on Mars")
    c2 = claims.refute(c2.id, "workspace path is a local temp dir")
    print(f"second claim: status={c2.status.value}, evidence={c2.evidence}")
    try:
        claims.confirm(c1.id, "second thoughts")
        raise AssertionError("double decide should fail")
    except ValueError as e:
        print(f"double decide correctly rejected: {e}")
    print("OK: claim lifecycle works")

    print()
    print("demo complete: checkpoints, journals, scheduler, claims all live")


if __name__ == "__main__":
    main()
