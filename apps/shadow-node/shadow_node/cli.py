"""Shadow Node operator CLI.

Inspect evidence-based execution records without touching the HTTP API:

    python -m shadow_node.cli executions list [--status verified] [--limit 20]
    python -m shadow_node.cli executions show exec_<id>

Reads the encrypted runtime DB configured via SHADOW_RUNTIME_DB (same key
resolution as the node itself). Run with apps/shadow-node on sys.path.
"""
from __future__ import annotations

import argparse
import os
import sys


def _load_executions():
    db = os.getenv("SHADOW_RUNTIME_DB")
    if not db:
        print(
            "SHADOW_RUNTIME_DB is not set: execution history is in-memory only "
            "and cannot be inspected after the node stops. Set SHADOW_RUNTIME_DB "
            "to the node's runtime database path.",
            file=sys.stderr,
        )
        return None
    from .runtime_store import EncryptedRuntimeStore
    from agent_core import ExecutionRecord

    store = EncryptedRuntimeStore(db)
    return sorted(
        store.all("executions", ExecutionRecord),
        key=lambda r: r.started_at,
        reverse=True,
    )


def _print_record(rec) -> None:
    print(f"id:           {rec.id}")
    print(f"intent:       {rec.intent}")
    print(f"tool:         {rec.action.tool_name if rec.action else '?'}")
    print(f"approval:     {rec.approval_id or '-'}")
    print(f"policy:       {'allowed' if rec.policy_allowed else 'blocked'} ({rec.policy_reason})")
    print(f"verification: {rec.verification.value}")
    print(f"reason:       {rec.verification_reason}")
    print(f"started:      {rec.started_at}")
    print(f"finished:     {rec.finished_at}")


def cmd_list(args) -> int:
    recs = _load_executions()
    if recs is None:
        return 1
    if args.status:
        recs = [r for r in recs if r.verification.value == args.status]
    for r in recs[: args.limit]:
        finished = r.finished_at.isoformat() if r.finished_at else "running"
        tool = r.action.tool_name if r.action else "?"
        print(f"{r.id}  {r.verification.value:11}  {tool:16}  {finished}  {r.intent[:60]}")
    if not recs:
        print("no execution records found")
    return 0


def cmd_show(args) -> int:
    recs = _load_executions()
    if recs is None:
        return 1
    rec = next((r for r in recs if r.id == args.execution_id), None)
    if rec is None:
        print(f"unknown execution: {args.execution_id}", file=sys.stderr)
        return 1
    _print_record(rec)
    print("\nevidence:")
    for e in rec.evidence:
        print(f"  - [{e.kind}] {e.summary}")
    if rec.tool_error:
        print(f"\ntool error: {rec.tool_error}")
    if rec.world_state:
        d = rec.world_state
        print("\nworld-state diff:")
        for rel in d.added:
            print(f"  + {rel}")
        for rel in d.modified:
            print(f"  ~ {rel}")
        for rel in d.removed:
            print(f"  - {rel}")
        if not d.changed:
            print("  (no changes)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="shadow-node", description="Shadow Node operator CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("executions", help="inspect execution records")
    ex_sub = ex.add_subparsers(dest="exec_command", required=True)
    p_list = ex_sub.add_parser("list", help="list execution records, newest first")
    p_list.add_argument("--status", choices=["verified", "failed", "uncertain", "conflicting"])
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list)
    p_show = ex_sub.add_parser("show", help="show one execution in full detail")
    p_show.add_argument("execution_id")
    p_show.set_defaults(func=cmd_show)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
