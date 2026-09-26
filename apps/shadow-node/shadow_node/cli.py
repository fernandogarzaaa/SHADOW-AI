"""Shadow Node operator CLI.

Inspect evidence-based execution records without touching the HTTP API:

    python -m shadow_node.cli executions list [--status verified] [--limit 20]
    python -m shadow_node.cli executions show exec_<id>

Inspect the Sentinel-lite audit chain, policy, and credential vault:

    python -m shadow_node.cli audit list [--limit 20]
    python -m shadow_node.cli audit verify
    python -m shadow_node.cli policy show
    python -m shadow_node.cli vault list
    python -m shadow_node.cli vault store NAME [--scopes a,b]
    python -m shadow_node.cli vault rotate NAME
    python -m shadow_node.cli vault revoke NAME
    python -m shadow_node.cli vault surrogate NAME [--ttl 300] [--scopes a,b]

Reads the encrypted runtime DB configured via SHADOW_RUNTIME_DB (same key
resolution as the node itself). Run with the repo packages on sys.path, e.g.
PYTHONPATH=apps/shadow-node:packages/agent-core.
"""
from __future__ import annotations

import argparse
import getpass
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

    au = sub.add_parser("audit", help="inspect the tamper-evident audit chain")
    au_sub = au.add_subparsers(dest="audit_command", required=True)
    p_alist = au_sub.add_parser("list", help="list audit entries, newest first")
    p_alist.add_argument("--limit", type=int, default=20)
    p_alist.add_argument("--event-type", default=None, help="filter by event type")
    p_alist.set_defaults(func=cmd_audit_list)
    p_averify = au_sub.add_parser("verify", help="verify the hash chain integrity")
    p_averify.set_defaults(func=cmd_audit_verify)

    pol = sub.add_parser("policy", help="inspect the loaded policy")
    pol_sub = pol.add_subparsers(dest="policy_command", required=True)
    p_pshow = pol_sub.add_parser("show", help="show the effective policy summary")
    p_pshow.set_defaults(func=cmd_policy_show)

    va = sub.add_parser("vault", help="manage node credentials (names only; values never print)")
    va_sub = va.add_subparsers(dest="vault_command", required=True)
    p_vlist = va_sub.add_parser("list", help="list credential names and scopes")
    p_vlist.set_defaults(func=cmd_vault_list)
    p_vstore = va_sub.add_parser("store", help="store a credential (value read securely from prompt)")
    p_vstore.add_argument("name")
    p_vstore.add_argument("--scopes", default="", help="comma-separated scopes")
    p_vstore.set_defaults(func=cmd_vault_store)
    p_vrotate = va_sub.add_parser("rotate", help="replace a credential value, revoking its surrogates")
    p_vrotate.add_argument("name")
    p_vrotate.set_defaults(func=cmd_vault_store)
    p_vrevoke = va_sub.add_parser("revoke", help="revoke a credential and its surrogates")
    p_vrevoke.add_argument("name")
    p_vrevoke.set_defaults(func=cmd_vault_revoke)
    p_vsur = va_sub.add_parser("surrogate", help="mint a short-lived surrogate token for a credential")
    p_vsur.add_argument("name")
    p_vsur.add_argument("--ttl", type=int, default=300, help="time to live in seconds")
    p_vsur.add_argument("--scopes", default="", help="comma-separated scopes")
    p_vsur.set_defaults(func=cmd_vault_surrogate)

    args = parser.parse_args(argv)
    return args.func(args)


def _load_runtime():
    """Return (chain, vault) backed by the runtime DB, or in-memory with a warning."""
    from .runtime_store import EncryptedRuntimeStore
    from agent_core import AuditChain, CredentialVault

    db = os.getenv("SHADOW_RUNTIME_DB")
    if not db:
        print(
            "SHADOW_RUNTIME_DB is not set: operating on an empty in-memory vault/audit chain. "
            "Set SHADOW_RUNTIME_DB to the node's runtime database path to manage the live node.",
            file=sys.stderr,
        )
        return AuditChain(), CredentialVault()
    store = EncryptedRuntimeStore(db)
    chain = AuditChain(store)
    vault = CredentialVault(store, audit=chain)
    return chain, vault


def _scopes_arg(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def cmd_audit_list(args) -> int:
    chain, _ = _load_runtime()
    entries = chain.entries()
    if args.event_type:
        entries = [e for e in entries if e.event_type == args.event_type]
    for e in reversed(entries[-args.limit:]):
        ts = e.timestamp.isoformat() if hasattr(e.timestamp, "isoformat") else str(e.timestamp)
        print(f"#{e.seq} {ts} {e.actor} {e.event_type} {e.hash[:12]}")
    if not entries:
        print("no audit entries found")
    return 0


def cmd_audit_verify(args) -> int:
    chain, _ = _load_runtime()
    ok, problems = chain.verify()
    print(f"entries: {len(chain)}")
    if ok:
        print("chain OK: every entry links to its predecessor and no content was altered")
        return 0
    print("chain BROKEN:")
    for p in problems:
        print(f"  - {p}")
    return 1


def _policy_file() -> str | None:
    from pathlib import Path

    cand = os.getenv("SHADOW_POLICY_FILE") or str(
        Path(__file__).parent / "policy.yaml"
    )
    return cand if os.path.isfile(cand) else None


def cmd_policy_show(args) -> int:
    from agent_core import PolicyEngine

    path = _policy_file()
    engine = PolicyEngine(policy_file=path)
    desc = engine.describe()
    print(f"source:  {path or 'built-in defaults'}")
    print(f"version:  {desc['version']}")
    print(f"blocked tools ({len(desc['blocked_tools'])}): {', '.join(desc['blocked_tools'])}")
    print(f"destructive tools ({len(desc['destructive_tools'])}): {', '.join(desc['destructive_tools'])}")
    print(f"sensitive tools ({len(desc['sensitive_tools'])}): {', '.join(desc['sensitive_tools'])}")
    print(f"approval-required risks: {', '.join(desc['approval_required_risks'])}")
    return 0


def cmd_vault_list(args) -> int:
    _, vault = _load_runtime()
    names = vault.credential_names()
    for n in names:
        print(n)
    if not names:
        print("no credentials stored")
    return 0


def cmd_vault_store(args) -> int:
    _, vault = _load_runtime()
    value = getpass.getpass(f"value for credential '{args.name}': ")
    if not value:
        print("empty value: not stored", file=sys.stderr)
        return 1
    if args.vault_command == "rotate":
        try:
            vault.rotate_credential(args.name, value)
        except KeyError:
            print(f"unknown credential: {args.name}", file=sys.stderr)
            return 1
        print(f"credential '{args.name}' rotated (outstanding surrogates revoked)")
    else:
        vault.set_credential(args.name, value, scopes=_scopes_arg(args.scopes))
        print(f"credential '{args.name}' stored (value never leaves the vault)")
    return 0


def cmd_vault_revoke(args) -> int:
    _, vault = _load_runtime()
    try:
        vault.revoke_credential(args.name)
    except KeyError:
        print(f"unknown credential: {args.name}", file=sys.stderr)
        return 1
    print(f"credential '{args.name}' revoked")
    return 0


def cmd_vault_surrogate(args) -> int:
    _, vault = _load_runtime()
    try:
        token = vault.mint_surrogate(args.name, scopes=_scopes_arg(args.scopes), ttl_seconds=args.ttl)
    except KeyError:
        print(f"unknown credential: {args.name}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
