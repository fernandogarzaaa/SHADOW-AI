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

Ambient GHOST capabilities (checkpointed runs, journals, claims, scheduler):

    python -m shadow_node.cli ambient on [--interval 3600] [--stealth|--no-stealth] [--tasks morning_brief,memory_digest]
    python -m shadow_node.cli ambient off
    python -m shadow_node.cli ambient status
    python -m shadow_node.cli journal show run_<id> [--limit 50]
    python -m shadow_node.cli claims list [--status unconfirmed]
    python -m shadow_node.cli claims confirm clm_<id> --evidence "text"
    python -m shadow_node.cli claims refute clm_<id> --evidence "text"

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

    am = sub.add_parser("ambient", help="control the ambient background scheduler (default: off)")
    am_sub = am.add_subparsers(dest="ambient_command", required=True)
    p_aon = am_sub.add_parser("on", help="enable ambient background work (explicit opt-in)")
    p_aon.add_argument("--interval", type=int, default=3600, help="seconds between ticks (min 60)")
    p_aon.add_argument("--stealth", action="store_true", help="stealth mode: journal everything, emit no SSE/push")
    p_aon.add_argument("--no-stealth", action="store_true", help="normal mode: emit SSE events for ambient activity")
    p_aon.add_argument("--tasks", default="morning_brief", help="comma-separated task names")
    p_aon.set_defaults(func=cmd_ambient_on)
    p_aoff = am_sub.add_parser("off", help="disable ambient background work")
    p_aoff.set_defaults(func=cmd_ambient_off)
    p_astatus = am_sub.add_parser("status", help="show ambient scheduler config and state")
    p_astatus.set_defaults(func=cmd_ambient_status)

    jo = sub.add_parser("journal", help="inspect per-run ambient journals")
    jo_sub = jo.add_subparsers(dest="journal_command", required=True)
    p_jshow = jo_sub.add_parser("show", help="show the journal for one run")
    p_jshow.add_argument("run_id")
    p_jshow.add_argument("--limit", type=int, default=50)
    p_jshow.set_defaults(func=cmd_journal_show)

    cl = sub.add_parser("claims", help="inspect and decide world-state claims")
    cl_sub = cl.add_subparsers(dest="claims_command", required=True)
    p_clist = cl_sub.add_parser("list", help="list claims, newest first")
    p_clist.add_argument("--status", choices=["unconfirmed", "confirmed", "refuted"], default=None)
    p_clist.set_defaults(func=cmd_claims_list)
    p_cconfirm = cl_sub.add_parser("confirm", help="confirm a claim with evidence")
    p_cconfirm.add_argument("claim_id")
    p_cconfirm.add_argument("--evidence", required=True)
    p_cconfirm.set_defaults(func=cmd_claims_confirm)
    p_crefute = cl_sub.add_parser("refute", help="refute a claim with evidence")
    p_crefute.add_argument("claim_id")
    p_crefute.add_argument("--evidence", required=True)
    p_crefute.set_defaults(func=cmd_claims_refute)

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


def _load_ambient():
    """Return (scheduler, journal, checkpoints, claims) backed by the runtime DB."""
    from .runtime_store import EncryptedRuntimeStore
    from agent_core import RunJournal, CheckpointStore, ClaimRegistry, AmbientScheduler, InMemoryKV

    db = os.getenv("SHADOW_RUNTIME_DB")
    if not db:
        print(
            "SHADOW_RUNTIME_DB is not set: ambient state is in-memory only and "
            "cannot be managed after the node stops. Set SHADOW_RUNTIME_DB to "
            "the node's runtime database path.",
            file=sys.stderr,
        )
        kv = InMemoryKV()
    else:
        kv = EncryptedRuntimeStore(db)
    journal = RunJournal(kv)
    scheduler = AmbientScheduler(store=kv, journal=journal)
    return scheduler, journal, CheckpointStore(kv), ClaimRegistry(kv)


def cmd_ambient_on(args) -> int:
    scheduler, _, _, _ = _load_ambient()
    stealth = True if args.stealth else (False if args.no_stealth else None)
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    try:
        cfg = scheduler.configure(enabled=True, interval_seconds=args.interval,
                                  stealth_mode=stealth, tasks=tasks)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    mode = "stealth (no SSE/push surface)" if cfg.stealth_mode else "normal (SSE events emitted)"
    print(f"ambient enabled: every {cfg.interval_seconds}s, tasks={','.join(cfg.tasks)}, {mode}")
    return 0


def cmd_ambient_off(args) -> int:
    scheduler, _, _, _ = _load_ambient()
    scheduler.configure(enabled=False)
    print("ambient disabled: the scheduler will not run background work")
    return 0


def cmd_ambient_status(args) -> int:
    scheduler, journal, checkpoints, claims = _load_ambient()
    cfg = scheduler.get_config()
    print(f"enabled:         {cfg.enabled}")
    print(f"interval:        {cfg.interval_seconds}s")
    print(f"stealth_mode:    {cfg.stealth_mode}")
    print(f"tasks:           {','.join(cfg.tasks) or '(none)'}")
    print(f"last_tick:       {cfg.last_tick_at or 'never'}")
    print(f"checkpoints:     {len(checkpoints.all())}")
    print(f"journal runs:    {len(journal.run_ids())}")
    unconfirmed = claims.list(status="unconfirmed")
    print(f"unconfirmed claims: {len(unconfirmed)}")
    return 0


def cmd_journal_show(args) -> int:
    _, journal, _, _ = _load_ambient()
    entries = journal.for_run(args.run_id, limit=args.limit)
    if not entries:
        print(f"no journal entries for run: {args.run_id}", file=sys.stderr)
        return 1
    for e in entries:
        ts = e.created_at.isoformat() if hasattr(e.created_at, "isoformat") else str(e.created_at)
        print(f"#{e.seq:3} [{e.entry_type.value:12}] {ts}  {e.message}")
        if e.execution_id:
            print(f"         execution: {e.execution_id}")
    return 0


def cmd_claims_list(args) -> int:
    _, _, _, claims = _load_ambient()
    rows = claims.list(status=args.status)
    for c in rows:
        print(f"{c.id}  {c.status.value:11}  {c.statement[:70]}")
        for ev in c.evidence:
            print(f"         evidence: {ev[:100]}")
    if not rows:
        print("no claims found")
    return 0


def _cmd_claims_decide(args, decide: str) -> int:
    _, _, _, claims = _load_ambient()
    try:
        claim = claims.confirm(args.claim_id, args.evidence) if decide == "confirm" \
            else claims.refute(args.claim_id, args.evidence)
    except KeyError:
        print(f"unknown claim: {args.claim_id}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"claim {claim.id} {decide}ed: {claim.statement[:70]}")
    return 0


def cmd_claims_confirm(args) -> int:
    return _cmd_claims_decide(args, "confirm")


def cmd_claims_refute(args) -> int:
    return _cmd_claims_decide(args, "refute")


if __name__ == "__main__":
    sys.exit(main())
