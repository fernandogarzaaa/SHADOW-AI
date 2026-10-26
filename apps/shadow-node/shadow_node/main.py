from fastapi import FastAPI, HTTPException, WebSocket, Request, UploadFile, File
from starlette.websockets import WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from agent_core import *
from agent_core import (
    RunJournal,
    CheckpointStore,
    ClaimRegistry,
    GhostRunSession,
    AmbientScheduler,
    InMemoryKV,
    AmbientLoop,
    ReminderWakeTrigger,
    GoogleCalendarWakeTrigger,
    MessageWakeTrigger,
    PushWakeTrigger,
    SessionStore,
    SessionCompactor,
)
from memory_engine import *
from axiom_adapter import AxiomAdapter
from ghost_adapter import GhostAdapter, LocalActionExecutor
from .connectors import read_local_document
from .runtime_scope import check_runtime_scope, RuntimeScopeError
from .request_hygiene import BodyLimitMiddleware, check_request_hygiene, HygieneError
from .bootstrap import from_env as bootstrap_code_from_env
from .ambient_tasks import build_task_map, BUILTIN_TASKS
from .model_providers import ModelProviderConfig, LocalMockModel
from .crypto_config import key_path, load_fernet_key
from .device_credentials import (
    load_master_secret,
    derive_device_token,
    token_scheme_for_version,
    DEVICE_TOKEN_VERSION,
)
from .providers import build_frontier, CATALOG
from .hybrid import HybridRouter
from .self_model import build_self_model, classify_self_intent, render_self_answer
from .persona import (
    default_persona,
    load_persona,
    save_persona,
    apply_update,
    PersonaUpdate,
    system_prompt_for,
    set_system_prompt_override,
)
from .goals import GoalStore, GoalCreate, GoalUpdate, ProgressCreate, GoalStatus
from .feed import (
    FeedStore,
    FeedGenerateRequest,
    FEED_KINDS,
    FeedUnit,
    generate_units,
    render_goals_briefing,
    render_memory_digest,
    render_morning_brief,
)
from .ideas import IdeaStore, IdeaCreate, IdeaUpdate, PlannedAction
from .reminders import ReminderStore, ReminderCreate, ReminderUpdate, fire_due
from .reminders import (
    RECURRENCES as REMINDER_RECURRENCES,
    STATUSES as REMINDER_STATUSES,
)
from .custom_panels import (
    CustomPanelDef,
    CustomPanelFilter,
    CustomPanelRegistry,
    CustomPanelSort,
    PanelClarification,
    PanelDeleteRequest,
    PanelInputs,
    PanelParseRequest,
    PanelProposal,
    PanelUpdateRequest,
    parse_panel_request,
    render_panel,
)
from .artifacts import (
    ArtifactStore,
    ArtifactCreate,
    ArtifactUpdate,
    ARTIFACT_KINDS,
    AGENT_READ_LIMIT,
    RevisionConflictError,
)
from .panels import build_panels
from .schedule_parse import parse_schedule
from .scheduled_tasks import (
    ScheduledTaskUpdate,
    ambient_task_to_task,
    is_valid_recurrence,
    list_scheduled_tasks,
    reminder_to_task,
    split_task_id,
)

from . import voice as voice_mod
from . import media as media_mod
from .continuity import (
    HandoffStore,
    build_session_snapshot,
    list_presence,
    note_presence,
)
from .ambient_tasks import (
    morning_brief as _amb_morning_brief,
    memory_digest as _amb_memory_digest,
)
from . import provider_auth
from . import claude_code
from .chatgpt_plan import (
    PROVIDER as CHATGPT_PLAN,
    MANAGE_USAGE_URL,
    ChatGPTPlanAuth,
    ChatGPTPlanError,
    ChatGPTPlanProvider,
)
CLAUDE_CODE = claude_code.PROVIDER
from . import accounts
from .events import EventBus
from pathlib import Path
import httpx
import contextlib, contextvars, re, tempfile, hashlib, uuid, os, time, secrets, json, asyncio, threading, urllib.request, base64
from contextlib import asynccontextmanager

APP_VERSION = "0.1.0"


@asynccontextmanager
async def _lifespan(app):
    # Fresh node (or all owners expired/revoked): print the single-use
    # bootstrap code so the operator can pair the first owner device.
    _ensure_bootstrap_code()
    yield
    # Clean shutdown: stop the always-on loop (join its thread, persist the
    # loop record) instead of letting the process die mid-tick.
    try:
        ambient_loop.stop(timeout=5)
    except Exception:
        pass


app = FastAPI(title="Shadow Node", version=APP_VERSION, lifespan=_lifespan)
# CORS: localhost by default; add deployed PWA/app origins via SHADOW_CORS_ORIGINS
# (comma-separated). Use "*" only for fully trusted/private deployments.
_DEFAULT_CORS = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:8787",
    "http://127.0.0.1:8787",
    "http://localhost:8081",
    "http://localhost:19006",
]
_EXTRA_CORS = [
    o.strip() for o in os.getenv("SHADOW_CORS_ORIGINS", "").split(",") if o.strip()
]
CORS_ORIGINS = _EXTRA_CORS if "*" in _EXTRA_CORS else (_DEFAULT_CORS + _EXTRA_CORS)
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)


def _build_memory_store():
    # Persistent, stable-key store when SHADOW_MEMORY_DB is set (production);
    # ephemeral temp store otherwise (tests/dev) so runs stay isolated.
    db = os.getenv("SHADOW_MEMORY_DB")
    if db:
        key = load_fernet_key(
            "SHADOW_MEMORY_KEY", "SHADOW_MEMORY_KEY_FILE", key_path("memory.key")
        )
        os.makedirs(os.path.dirname(os.path.abspath(db)), exist_ok=True)
        return EncryptedMemoryStore(path=db, key=key)
    return EncryptedMemoryStore(
        path=tempfile.gettempdir() + f"/shadow_memory_beta_{uuid.uuid4().hex}.db"
    )


# Persistent encrypted runtime state when SHADOW_RUNTIME_DB is set; in-memory otherwise.
_runtime_db = os.getenv("SHADOW_RUNTIME_DB")
if _runtime_db:
    from .runtime_store import build_runtime

    _runtime_store, audit, consents, sessions = build_runtime(_runtime_db)
    _approval_store = _runtime_store
else:
    audit: list[AuditEvent] = []
    sessions = DeviceSessionStore()
    consents: list[ConsentGrant] = []
    _approval_store = None
# Node master secret for HMAC-derived device credentials
# (device_credentials.py). Loaded once at boot: from SHADOW_MASTER_SECRET,
# then the key file, else generated and persisted with 0600 perms. The
# value is never logged and never returned by any API. When unavailable
# (unwritable key path), pairing falls back to legacy random stored
# secrets and derived-scheme devices fail closed at verify time.
try:
    _MASTER_SECRET = load_master_secret()
except Exception:
    # Unwritable key path or empty configured value: pairing falls back
    # to legacy random stored secrets, and derived-scheme devices fail
    # closed at verify time. (No logger available this early in boot.)
    _MASTER_SECRET = None
sessions.master_secret = _MASTER_SECRET
# Sentinel-lite: tamper-evident audit chain + credential vault, backed by the
# encrypted runtime DB when configured, in-memory otherwise. Every policy
# decision, approval event, credential resolution, and execution verdict lands
# in the chain; inspect with `python -m shadow_node.cli audit ...`.
sentinel_audit = AuditChain(_runtime_store if _runtime_db else None)
sentinel_vault = CredentialVault(
    _runtime_store if _runtime_db else None, audit=sentinel_audit
)
sessions.event_sink = lambda actor, event_type, payload: sentinel_audit.record(
    actor, event_type, payload
)
_POLICY_FILE = os.getenv("SHADOW_POLICY_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "policy.yaml"
)
if not os.path.isfile(_POLICY_FILE):
    _POLICY_FILE = None  # fall back to built-in defaults
profile = UserProfile()
if _runtime_db:
    # Durable emergency pause (audit P1): the kill switch survives
    # restarts. Conservative startup: a missing flag means never paused;
    # an unreadable flag fails closed (stays paused).
    from .runtime_store import load_pause_flag

    profile.emergency_paused = load_pause_flag(_runtime_store)
    if profile.emergency_paused:
        audit.append(
            AuditEvent(
                actor="safety",
                event_type="emergency_pause_restored",
                status="paused",
                result="pause flag restored from runtime DB at startup",
            )
        )
# Cookie-style persona (Phase 1): the assistant's editable identity, persisted
# encrypted in the runtime DB when configured. The vibe becomes the
# frontier-model system prompt via the process-wide override below.
persona = load_persona(_runtime_store) if _runtime_db else default_persona()
goal_store = GoalStore(_runtime_store if _runtime_db else None)
feed_store = FeedStore(_runtime_store if _runtime_db else None)
idea_store = IdeaStore(_runtime_store if _runtime_db else None)
reminder_store = ReminderStore(_runtime_store if _runtime_db else None)
panel_registry = CustomPanelRegistry(_runtime_store if _runtime_db else None)
artifact_store = ArtifactStore(_runtime_store if _runtime_db else None)
media_store = media_mod.MediaStore(_runtime_store if _runtime_db else None)
set_system_prompt_override(system_prompt_for(persona))
bus = EventBus()
EXPO_PUSH_ENABLED = os.getenv("SHADOW_EXPO_PUSH_ENABLED", "false").lower() == "true"


def _send_expo_push(
    token: str, title: str, body: str, data: dict, category_id: str | None = None
):
    """Best-effort Expo push; failures are logged, never raised."""
    try:
        message = {
            "to": token,
            "title": title,
            "body": body,
            "data": data,
            "sound": "default",
        }
        if category_id:
            # Lets the app render action buttons (e.g. Approve / Deny) and
            # route the response. See mobile src/lib/approvalNotifications.ts.
            message["categoryId"] = category_id
        payload = json.dumps(message).encode()
        req = urllib.request.Request(
            "https://exp.host/--/api/v2/push/send",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        log.warning("expo_push_failed", extra={"error": str(e)[:200]})


def _notify_approval_created(req):
    if not EXPO_PUSH_ENABLED:
        return

    def _run():
        for device_id, token in list(sessions.push_tokens.items()):
            dev = sessions.devices.get(device_id)
            if dev is None or dev.revoked:
                continue
            _send_expo_push(
                token,
                "Approval needed",
                req.action_preview or req.action.description,
                {"type": "approval.created", "approval_id": req.id},
                category_id="shadow.approval",
            )

    threading.Thread(target=_run, daemon=True).start()


def _approval_event_sink(event_type: str, req):
    bus.publish(event_type, req.model_dump(mode="json"))
    if event_type == "approval.created":
        _notify_approval_created(req)


def _notify_proactive(title: str, body: str, data: dict):
    """Proactive push (reminders, digests). Best-effort, never raised."""
    if not EXPO_PUSH_ENABLED:
        return

    def _run():
        for device_id, token in list(sessions.push_tokens.items()):
            dev = sessions.devices.get(device_id)
            if dev is None or dev.revoked:
                continue
            _send_expo_push(token, title, body, data)

    threading.Thread(target=_run, daemon=True).start()


core = AgentCore(
    profile,
    approval_store=_approval_store,
    event_sink=_approval_event_sink,
    execution_store=_approval_store,
    audit_chain=sentinel_audit,
    vault=sentinel_vault,
    policy_file=_POLICY_FILE,
)
store = _build_memory_store()
memory = MemoryEngine(store)
axiom = AxiomAdapter()
ghost = GhostAdapter()
model_config = ModelProviderConfig()
model = LocalMockModel()
pairing = {}
# Explicit per-tool consent (calendar.create, email.draft, ...) comes ONLY
# from a server-verified approval bound to this exact action. /agent/execute
# sets this for the duration of the call; every other path (autonomous
# execution, ambient runs, tier waivers) runs with consent withheld.
_execution_consent: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "execution_consent", default=False
)

@contextlib.contextmanager
def _consent_granted(approved: bool):
    """Grant explicit tool consent for one verified-approval execution."""
    token = _execution_consent.set(bool(approved))
    try:
        yield
    finally:
        _execution_consent.reset(token)


# Register real, sandboxed action handlers so approved /agent/execute calls run for real.
action_executor = LocalActionExecutor()
for _tool in action_executor.names():
    core.tools.register(
        _tool,
        (
            lambda t: (
                lambda params: action_executor.run(
                    t, params, explicit_consent=_execution_consent.get()
                )
            )
        )(_tool),
    )


def _ghost_handoff_tool(params):
    """ghost_handoff as a first-class ToolRegistry entry so it flows through
    central policy, execution evidence, verification, and Sentinel audit
    like every other tool (audit P0-3). approved=True is sound here:
    core.execute only invokes the tool after policy ALLOWED, and
    ghost_handoff is a sensitive tool that can never be tier-waived, so a
    valid server-side approval was established first."""
    desc = params.get("description") or "ghost handoff"
    act = AgentAction(tool_name="ghost_handoff", description=desc, params=params)
    return ghost.execute(
        ghost.to_ir(AgentPlan(user_intent=desc, actions=[act])),
        approved=True,
        explicit_consent=_execution_consent.get(),
    )


core.tools.register("ghost_handoff", _ghost_handoff_tool)


def _artifact_create_tool(params):
    """Create a durable artifact (document) the user can open later.

    The mobile app renders `artifact:<id>` references as tappable cards,
    so the agent should mention the id in its reply text.
    """
    req = ArtifactCreate(
        title=params.get("title") or "Untitled",
        kind=params.get("kind") or "markdown",
        content=params.get("content") or "",
        tags=params.get("tags") or [],
    )
    a = artifact_store.create(req)
    return {
        "id": a.id,
        "title": a.title,
        "kind": a.kind,
        "version": a.version,
        "reference": f"artifact:{a.id}",
    }


def _artifact_update_tool(params):
    artifact_id = params.get("id") or params.get("artifact_id")
    if not artifact_id:
        return {"error": "id is required"}
    try:
        a = artifact_store.update(
            artifact_id,
            ArtifactUpdate(
                title=params.get("title"),
                kind=params.get("kind"),
                content=params.get("content"),
                expected_version=params.get("expected_version"),
            ),
        )
    except RevisionConflictError as e:
        return {"error": str(e)}
    if a is None:
        return {"error": "artifact not found"}
    return {
        "id": a.id,
        "title": a.title,
        "version": a.version,
        "reference": f"artifact:{a.id}",
    }


def _artifact_read_tool(params):
    artifact_id = params.get("id") or params.get("artifact_id")
    if not artifact_id:
        return {"error": "id is required"}
    a = artifact_store.get(artifact_id)
    if a is None:
        return {"error": "artifact not found"}
    content = a.content
    truncated = False
    if len(content) > AGENT_READ_LIMIT:
        content = content[:AGENT_READ_LIMIT]
        truncated = True
    return {
        "id": a.id,
        "title": a.title,
        "kind": a.kind,
        "version": a.version,
        "content": content,
        "truncated": truncated,
    }


core.tools.register("artifact_create", _artifact_create_tool)
core.tools.register("artifact_update", _artifact_update_tool)
core.tools.register("artifact_read", _artifact_read_tool)


def _resolve_server_approval(approval_id: str | None, action: AgentAction) -> bool:
    """Derive the approved flag from a server-side approval record.

    The client-supplied `approved` boolean is never trusted: a paired
    device must reference a granted approval. This only VERIFIES the
    reference (exists, granted, unexpired, envelope binding matches);
    the actual one-shot CONSUME happens atomically inside
    AgentCore.execute() after the policy gate allows the action, so a
    policy-blocked attempt never burns the approval. Raises 404/403
    BEFORE any execution takes place.

    The presented action must reproduce the stored authorization envelope
    hash (tool, params, destination, data/model scope, risk, destructive,
    requires_approval, envelope version): any security-relevant divergence
    fails the claim even when tool/params/description match.

    Also wired into GhostRunSession as its approval resolver, so ghost
    runs enforce the identical contract: no valid approval, no execution.
    """
    if approval_id is None:
        return False
    # Normalize server-derived fields before verifying, mirroring what
    # POST /approvals does at creation: destructiveness is derived
    # server-side (audit P0-4), so the presented action is compared
    # apples-to-apples against the stored envelope.
    action.destructive = core.policy.is_destructive(action)
    try:
        core.approvals.verify(approval_id, action)
    except KeyError:
        raise HTTPException(404, "unknown approval")
    except ValueError as e:
        raise HTTPException(403, str(e))
    return True


# Ambient GHOST capabilities: journaled, checkpointed multi-step runs, world-state
# claims, and the opt-in background scheduler. Backed by the encrypted runtime
# DB when configured, in-memory otherwise. Ambient is OFF by default; nothing
# runs in the background until the operator enables it explicitly.
_ambient_kv = _runtime_store if _runtime_db else InMemoryKV()
ambient_journal = RunJournal(_ambient_kv, event_sink=bus.publish)
ambient_checkpoints = CheckpointStore(_ambient_kv)
ambient_claims = ClaimRegistry(_ambient_kv)
# Ghost runs resolve every step's approval through the same server-side
# binding /agent/execute uses. The session cannot manufacture approval:
# without a valid referenced approval, an approval-gated step is blocked.
ghost_runs = GhostRunSession(
    core,
    journal=ambient_journal,
    checkpoints=ambient_checkpoints,
    claims=ambient_claims,
    event_sink=bus.publish,
    audit=sentinel_audit,
    approval_resolver=_resolve_server_approval,
    consent_scope=lambda approved: _consent_granted(approved),
)
ambient_scheduler = AmbientScheduler(
    store=_ambient_kv,
    journal=ambient_journal,
    tasks=build_task_map(),
    event_sink=bus.publish,
    audit=sentinel_audit,
    context={
        "core": core,
        "memory": memory,
        "claims": ambient_claims,
        "sessions": sessions,
        "goals": goal_store,
        "feed_store": feed_store,
        "reminders": reminder_store,
        "is_quiet": lambda: ambient_scheduler.get_config().is_quiet(),
        "quiet_until": lambda: quiet_ends_at(
            ambient_scheduler.get_config().quiet_start,
            ambient_scheduler.get_config().quiet_end,
        ),
        "notify": _notify_proactive,
        "feed_add": lambda kind, title, body: feed_store.add(
            FeedUnit(kind=kind, title=title, body=body)
        ),
        "publish": bus.publish,
    },
    checkpoints=ambient_checkpoints,
)
# Always-on loop ("o"-pattern, local-first): one background thread owns the
# scheduler tick and the SLEEPING/AWAKE lifecycle. Wake sources are local:
# device push taps (POST /ambient/wake), the node's own reminder store,
# the user's real Google Calendar (via the already-connected
# hatch_gws_cli; read-only polling, cached), and inbound messages from
# the ask pipeline. Push providers needing paid accounts (APNs/FCM) are
# deliberately not wired: the local push path stays, and the account
# step is documented, not stubbed.
# Durable conversation sessions with automatic compaction. The summary
# backend is selectable via SHADOW_COMPRESSION_BACKEND ("deterministic"
# default, "axiom" for a local AXIOM-AETHER checkout): selection fails
# safe to deterministic and the choice is audit-logged at startup.
_compactor_backend, _compactor_fallback = select_backend(
    os.getenv("SHADOW_COMPRESSION_BACKEND", "deterministic")
)
session_store = SessionStore(
    _ambient_kv,
    compactor=SessionCompactor(backend=_compactor_backend),
    memory=memory,
    event_sink=bus.publish,
    audit=sentinel_audit,
)
# Cross-device continuity (Hark backlog item 11): explicit conversation
# handoffs between registered clients, KV-backed like sessions.
handoff_store = HandoffStore(kv=_ambient_kv)
sentinel_audit.record(
    "ambient",
    "compression_backend_selected",
    {"backend": _compactor_backend.name, "fallback_reason": _compactor_fallback},
)
_rehydrated_sessions = session_store.rehydrate()
reminder_trigger = ReminderWakeTrigger(
    reminder_source=lambda: [
        {"id": r.id, "title": r.title, "due_at": r.due_at}
        for r in reminder_store.reminders.values()
        if r.status == "pending"
    ]
)
google_calendar_trigger = GoogleCalendarWakeTrigger(
    lead_seconds=float(os.getenv("SHADOW_CALENDAR_LEAD_SECONDS", "300")),
    days_ahead=int(os.getenv("SHADOW_CALENDAR_DAYS", "2")),
    refresh_seconds=float(os.getenv("SHADOW_CALENDAR_REFRESH_SECONDS", "300")),
)
message_trigger = MessageWakeTrigger()
push_trigger = PushWakeTrigger()
ambient_loop = AmbientLoop(
    scheduler=ambient_scheduler,
    store=_ambient_kv,
    journal=ambient_journal,
    triggers=(reminder_trigger, google_calendar_trigger, message_trigger, push_trigger),
    event_sink=bus.publish,
    audit=sentinel_audit,
)
ambient_loop.start()
# Shadow Acts (v0.3): the runner is built once and handed to the
# scheduler context after the loop exists. Acts run inside the ambient
# tick through the policy gate; without an explicit tool_tiers grant in
# the policy document they are held for approval, never silently
# auto-run. See agent_core.shadow_acts and docs/AMBIENT.md.
shadow_act_runner = ShadowActRunner(
    core, profile, audit=sentinel_audit, plan_store=PlanStore(kv=_ambient_kv)
)
ambient_scheduler.update_context(
    {
        "shadow_acts": shadow_act_runner,
        "calendar": google_calendar_trigger,
        "ambient_loop": ambient_loop,
        "agent_sessions": session_store,
        "compression_backend": _compactor_backend,
    }
)
# Hybrid local+frontier router and provider credential store.
hybrid = HybridRouter(model, axiom)
credentials = provider_auth.CredentialStore()
oauth_txns = provider_auth.OAuthTransactionStore()
chatgpt_auth = ChatGPTPlanAuth(credentials)
SUBSCRIPTION_PROVIDERS = {CHATGPT_PLAN, CLAUDE_CODE}


# User approval rules (Allow / Ask first / Block per tool), persisted
# encrypted on the node and layered over the operator policy.
_RULES_KEY = "_policy_rules"


def _load_user_rules() -> None:
    for tool, rule in ((credentials.get(_RULES_KEY) or {}).get("rules") or {}).items():
        try:
            core.policy.set_user_rule(tool, rule)
        except ValueError:
            # Operator policy changed since the rule was saved (e.g. the tool
            # became sensitive): drop the now-invalid allow.
            pass


def _save_user_rules() -> None:
    credentials.set(_RULES_KEY, {"rules": dict(core.policy.user_rules)})


_load_user_rules()


def active_provider() -> str:
    """The provider asks go to: chosen in the dashboard (stored), else the
    SHADOW_MODEL_PROVIDER environment default."""
    chosen = (credentials.get("_active") or {}).get("provider")
    return chosen or model_config.provider


def _claude_code_enabled() -> bool:
    return bool((credentials.get("_claude_code") or {}).get("enabled")) and not claude_code.killed()


def _build_active_frontier(provider: str):
    """Construct the frontier model for `provider`, or None when it isn't
    connected. Subscription providers are only ever built for a
    user-initiated ask (this function's only caller)."""
    if provider == CHATGPT_PLAN:
        cred = credentials.get(CHATGPT_PLAN) or {}
        if cred.get("type") != "chatgpt_plan":
            return None
        return ChatGPTPlanProvider(chatgpt_auth, cred.get("model") or "")
    if provider == CLAUDE_CODE:
        return claude_code.ClaudeCodeProvider() if _claude_code_enabled() else None
    cred = credentials.resolve(provider)
    if cred is None:
        return None
    cred = {**cred, "endpoint": model_config.endpoint if provider == model_config.provider else ""}
    # SHADOW_MODEL_NAME belongs to the env-configured provider; any other
    # provider uses its own catalog default (never a foreign model id).
    model = model_config.model_name if (provider == model_config.provider and os.getenv("SHADOW_MODEL_NAME")) else None
    return build_frontier(provider, cred, model)
AUTH_REQUIRED = os.getenv("SHADOW_AUTH_REQUIRED", "true").lower() == "true"
GROUNDING_VERIFY = os.getenv("SHADOW_GROUNDING_VERIFY", "true").lower() == "true"
RATE_LIMIT_RPM = int(os.getenv("SHADOW_RATE_LIMIT_RPM", "0"))  # 0 disables
from .obs import RateLimiter, configure_logging, client_key

log = configure_logging()
rate_limiter = RateLimiter(RATE_LIMIT_RPM) if RATE_LIMIT_RPM > 0 else None


class IngestRequest(BaseModel):
    text: str
    source_kind: str = "manual"
    source_title: str = "Manual Import"
    consent_grant_id: str | None = None
    sensitive: bool | None = None
    do_not_send_to_cloud: bool | None = None


class FileIngestRequest(BaseModel):
    path: str
    consent_grant_id: str
    source_title: str | None = None


class AskRequest(BaseModel):
    prompt: str
    allow_cloud: bool = False
    cloud_approval: bool = False
    session_id: str | None = None


class PairStart(BaseModel):
    device_name: str
    public_key: str
    # Client family ("web", "ios", "mobile"). Web clients always sign with
    # v2, so their devices start with min_sig_version=2.
    client_kind: str | None = None


class PairApprove(BaseModel):
    pairing_id: str


class PairConfirm(BaseModel):
    pairing_id: str
    # Required for first-owner enrollment when auth is on: the single-use
    # code printed to the node's terminal (see bootstrap.py).
    bootstrap_code: str | None = None


class DeviceRegisterRequest(BaseModel):
    """Owner-initiated companion-device enrollment. The caller's HMAC
    authentication IS the owner approval: no device is minted here. The
    server returns a pairing_id/code; the new device collects its
    credentials via POST /pair/confirm. Only the name and public key are
    client-supplied; the server mints the device id, fingerprint, trust
    state, session window, and HMAC secret at confirm time. Client device
    records are never written directly (see audit P0-7)."""

    name: str
    public_key: str


class DenyRequest(BaseModel):
    reason: str


class ExecuteRequest(BaseModel):
    action: AgentAction
    # Legacy client hint. IGNORED by the server: approval is derived
    # exclusively from a server-side approval record referenced by
    # approval_id (see _resolve_server_approval). Never trust this flag.
    approved: bool = False
    double_confirmed: bool = False
    approval_id: str | None = None
    # HITL run linkage (OpenDots backlog #1): the idempotency receipt key.
    # When the policy suspends for approval, the returned approval carries
    # this pair; retries reuse the pending approval instead of duplicating it.
    thread_id: str | None = None
    tool_call_id: str | None = None


class ApprovalCreateRequest(BaseModel):
    action: AgentAction
    reason: str = "User requested approval"


class EmergencyPauseRequest(BaseModel):
    paused: bool
    reason: str | None = None


class ConsentRequest(BaseModel):
    data_source: str
    scope: str
    purpose: str
    retention_days: int = 30
    model_access_level: ModelAccessLevel = ModelAccessLevel.LOCAL_ONLY


class ProviderConnectRequest(BaseModel):
    api_key: str


class OAuthExchangeRequest(BaseModel):
    state: str
    code: str


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": str(exc.detail),
                "message": str(exc.detail),
                "path": request.url.path,
            }
        },
    )


@app.middleware("http")
async def runtime_scope_middleware(request: Request, call_next):
    # Runtime scope guard (OpenDots backlog #7): explicit (path, method)
    # allowlist plus strict ID validation for the sensitive route families,
    # independent of the framework router. Failures are client errors (400)
    # in the standard error envelope. CORS preflight (OPTIONS) passes
    # through untouched: the preflighted method is scope-checked on the
    # real request, mirroring auth_middleware's OPTIONS exemption.
    if request.method == "OPTIONS":
        return await call_next(request)
    try:
        check_runtime_scope(request.method, request.url.path, request.query_params)
    except RuntimeScopeError as e:
        log.warning(
            "runtime_scope_denied",
            extra={
                "path": request.url.path,
                "method": request.method,
                "reason": str(e),
            },
        )
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "runtime_scope_denied", "message": str(e)}},
        )
    return await call_next(request)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    start = time.perf_counter()
    if rate_limiter is not None and request.url.path not in {"/health", "/ready"}:
        if not rate_limiter.allow(client_key(request)):
            log.warning(
                "rate_limited",
                extra={
                    "path": request.url.path,
                    "client": client_key(request),
                    "status": 429,
                },
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": {"code": "rate_limited", "message": "too many requests"}
                },
            )
    response = await call_next(request)
    log.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": round((time.perf_counter() - start) * 1000, 1),
            "client": client_key(request),
        },
    )
    return response


def _canonical_body(raw: bytes, content_type: str) -> str:
    """Body text used in the HMAC canonical string.

    Multipart bodies may carry arbitrary binary (audio recordings) that is
    not valid UTF-8, and decoding it would crash before signature
    verification. For multipart, sign "sha256:<hex>" of the raw bytes
    instead; every other body keeps the exact legacy rule (raw UTF-8 text)
    so existing clients are unaffected.
    """
    if "multipart/form-data" in content_type:
        return "sha256:" + hashlib.sha256(raw).hexdigest()
    return raw.decode()


def _signed_path(scope, version: int) -> str:
    """The path a signature covers. v2 signs the path exactly as sent on the
    wire (percent-encoding preserved), which is what browsers and fetch
    clients produce; decoding is lossy (%2F vs /). v1 keeps the decoded
    path for clients paired before v2."""
    if version == 2:
        raw = scope.get("raw_path")
        if raw:
            return raw.decode("latin-1").split("?", 1)[0]
    return scope["path"]


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    exempt = (
        request.method == "OPTIONS"
        or request.url.path
        in {"/", "/health", "/ready", "/pair/start", "/pair/confirm"}
        or request.url.path.startswith("/web/")
        or request.url.path == "/auth/callback"
        or request.url.path.startswith("/docs")
        or request.url.path.startswith("/openapi")
    )
    if AUTH_REQUIRED and not exempt:
        h = request.headers
        device_id = h.get("x-shadow-device-id")
        # Failed authentication is rate limited per client IP (when the
        # limiter is enabled) before any signature work, so guessing device
        # ids or signatures can't run unthrottled.
        ip_bucket = "authfail:" + (request.client.host if request.client else "anon")
        if rate_limiter is not None and not rate_limiter.peek(ip_bucket):
            return JSONResponse(status_code=429, content={"detail": "rate_limited"})
        try:
            version = int(h.get("x-shadow-signature-version") or "1")
        except ValueError:
            version = 0
        # Cheap header checks first: an unauthenticated client must not be
        # able to make the node buffer a request body it will reject anyway.
        if not device_id or device_id not in sessions.devices:
            ok, reason = False, "unknown_device"
            sessions.verify(device_id, None, None, None, request.method, request.url.path)
        elif not h.get("x-shadow-signature"):
            # verify() records the auth_failed audit event without needing
            # the body (it fails before any signature work).
            ok, reason = sessions.verify(
                device_id, None, h.get("x-shadow-nonce"), h.get("x-shadow-timestamp"),
                request.method, request.url.path,
            )
        else:
            raw = await request.body()
            if version == 2:
                body = hashlib.sha256(raw).hexdigest()
            else:
                body = _canonical_body(raw, h.get("content-type", ""))
            ok, reason = sessions.verify(
                device_id,
                h.get("x-shadow-signature"),
                h.get("x-shadow-nonce"),
                h.get("x-shadow-timestamp"),
                request.method,
                _signed_path(request.scope, version),
                body,
                query=request.url.query,
                version=version,
            )
        if not ok:
            if rate_limiter is not None:
                rate_limiter.allow(ip_bucket)  # charge the failure
            # This middleware runs outside CORSMiddleware, so auth rejections
            # would otherwise leave browser clients with an opaque
            # "Failed to fetch" instead of the 401. Reflect the origin for
            # allowlisted origins so browsers can read the rejection.
            resp = JSONResponse(status_code=401, content={"detail": reason})
            origin = request.headers.get("origin")
            if origin and origin in CORS_ORIGINS:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Vary"] = "Origin"
            return resp
        request.state.device_id = device_id
        response = await call_next(request)
        dev = sessions.devices.get(device_id)
        if dev is not None:
            response.headers["X-Shadow-Session-Expires"] = dev.session_expires_at.isoformat()
        if version == 1 and request.url.query:
            # v1 does not sign the query string; flag it so operators can
            # see which clients still need to move to v2.
            response.headers["Deprecation"] = "true"
            response.headers["X-Shadow-Signature-Hint"] = "use signature version 2"
        return response
    return await call_next(request)


@app.middleware("http")
async def hygiene_middleware(request: Request, call_next):
    # Request hygiene (OpenDots backlog #10): body limit, JSON content-type
    # enforcement, and sec-fetch-site cross-site rejection. Registered last
    # so it runs outermost, before auth and rate limiting: oversized or
    # malformed requests are rejected before any expensive work.
    try:
        check_request_hygiene(
            request.method, request.url.path, request.headers, CORS_ORIGINS
        )
    except HygieneError as e:
        log.warning(
            "hygiene_rejected",
            extra={"path": request.url.path, "method": request.method, "code": e.code},
        )
        return JSONResponse(
            status_code=e.status_code,
            content={"error": {"code": e.code, "message": str(e)}},
        )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# Outermost layer: cap streamed (chunked) bodies before any middleware
# buffers them; Content-Length bodies are also rejected early by hygiene.
app.add_middleware(BodyLimitMiddleware)

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
WEB_INDEX = os.path.join(WEB_DIR, "index.html")
# The dashboard is static and same-origin only: no inline script, no
# third-party origins, no framing. Signing keys live in this origin's
# IndexedDB, so the CSP is the main defence against injected script.
DASHBOARD_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'self'; object-src 'none'"
)


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(
        WEB_INDEX,
        headers={
            "Content-Security-Policy": DASHBOARD_CSP,
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        },
    )


@app.get("/web/{asset}", include_in_schema=False)
def dashboard_asset(asset: str):
    """Static dashboard assets (flat directory; no traversal possible since
    the name is matched against an allowlist of files that exist)."""
    allowed = {"app.js", "signer.js", "orb.js", "styles.css", "favicon.svg"}
    if asset not in allowed:
        raise HTTPException(404, "not found")
    return FileResponse(
        os.path.join(WEB_DIR, asset),
        headers={"Content-Security-Policy": DASHBOARD_CSP},
    )


# Third-party dashboard code, vendored and served same-origin (see
# web/vendor/*/README.md). Explicit allowlist per library.
DASHBOARD_VENDOR = {
    "thinking-orbs": {"engine.es.js", "index-B8WsUNf5.js", "LICENSE"},
}


@app.get("/web/vendor/{lib}/{asset}", include_in_schema=False)
def dashboard_vendor_asset(lib: str, asset: str):
    if asset not in DASHBOARD_VENDOR.get(lib, set()):
        raise HTTPException(404, "not found")
    return FileResponse(
        os.path.join(WEB_DIR, "vendor", lib, asset),
        media_type="text/javascript" if asset.endswith(".js") else "text/plain",
        headers={"Content-Security-Policy": DASHBOARD_CSP},
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "local_first": True,
        "emergency_paused": profile.emergency_paused,
        "auth_required": AUTH_REQUIRED,
        # True while no active owner device exists: the next enrollment
        # needs the bootstrap code from the node's terminal.
        "bootstrap_open": AUTH_REQUIRED and not sessions.active_owners(),
    }


@app.get("/ready")
def ready():
    # Readiness probe: the node can serve memory + routing.
    try:
        memory.search("ready", 1)
        ok = True
    except Exception:
        ok = False
    status = "ready" if ok else "degraded"
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": status,
            "version": APP_VERSION,
            "auth_required": AUTH_REQUIRED,
            "rate_limit_rpm": RATE_LIMIT_RPM,
            "grounding_verify": GROUNDING_VERIFY,
            "providers_ready": model_config.cloud_model_ready(),
        },
    )


PAIRING_TTL_SECONDS = 300
MAX_PENDING_PAIRINGS = 20


def _pairing_sweep(now=None):
    now = time.time() if now is None else now
    for _pid, _entry in list(pairing.items()):
        if now - _entry["created_at"] > PAIRING_TTL_SECONDS:
            del pairing[_pid]


def _require_owner(request: Request):
    """The HMAC-authenticated caller must be an owner device: trusted,
    non-revoked, and flagged is_owner. Returns the approver device id.

    Grandfathering: nodes enrolled before the owner flag existed have no
    owner devices; there, any trusted non-revoked device still passes, so
    existing deployments are not locked out. The first bootstrap pairing
    mints an owner, so fresh nodes get the strict rule immediately.

    In dev mode (auth disabled) there is no caller to check, so enrollment
    proceeds as owner-initiated."""
    if not AUTH_REQUIRED:
        return "devmode-owner"
    device_id = request.headers.get("x-shadow-device-id")
    dev = sessions.devices.get(device_id or "")
    if dev is None or dev.revoked:
        raise HTTPException(403, "approver is not a trusted owner device")
    owners = [d for d in sessions.devices.values() if d.is_owner and not d.revoked]
    if owners:
        if not dev.is_owner:
            raise HTTPException(403, "owner device required")
    elif not dev.trusted:
        raise HTTPException(403, "approver is not a trusted owner device")
    return device_id


# Serializes enrollment: the bootstrap "no devices yet" check and the
# device minting below must be atomic, otherwise two simultaneous
# /pair/confirm calls could both pass the bootstrap condition and mint
# two owners (re-audit item 11).
_pairing_lock = threading.Lock()


bootstrap = bootstrap_code_from_env()


def _bootstrap_open() -> bool:
    """No active owner device (fresh node, or every owner revoked or
    expired). A bootstrap code is the only way to mint a new owner."""
    return not sessions.active_owners()


def _ensure_bootstrap_code() -> None:
    if AUTH_REQUIRED and _bootstrap_open():
        bootstrap.ensure()


def _new_pairing(device_name, public_key, approved_by=None, client_kind=None):
    _pairing_sweep()
    if len(pairing) >= MAX_PENDING_PAIRINGS:
        audit.append(
            AuditEvent(
                actor="pairing",
                event_type="pairing_rejected",
                status="blocked",
                metadata={"reason": "too_many_pending"},
            )
        )
        raise HTTPException(429, "too many pending pairings")
    pid = new_id("pair")
    pairing[pid] = {
        "status": "approved" if approved_by else "pending",
        "device_name": device_name,
        "public_key": public_key,
        "created_at": time.time(),
        "approved_by": approved_by,
        "approved_at": time.time() if approved_by else None,
        "client_kind": client_kind,
    }
    return pid


@app.post("/pair/start")
def pair_start(req: PairStart):
    """New device proposes enrollment. Returns a pairing_id/code; a trusted
    owner device must approve via /pair/approve before /pair/confirm mints
    credentials. The proposed identity is bound at start and cannot be
    swapped at confirm."""
    pid = _new_pairing(req.device_name, req.public_key, client_kind=req.client_kind)
    _ensure_bootstrap_code()
    audit.append(
        AuditEvent(
            actor="pairing",
            event_type="pairing_started",
            status="pending",
            metadata={"pairing_id": pid},
        )
    )
    return {
        "pairing_id": pid,
        "code": pid[-6:].upper(),
        "expires_in_seconds": PAIRING_TTL_SECONDS,
        "bootstrap_required": AUTH_REQUIRED and _bootstrap_open(),
    }


@app.get("/pair/pending")
def pair_pending(request: Request):
    """Pending (not yet approved) pairings, for an owner to review and
    approve. Owner-only: the list reveals who is trying to enroll."""
    _require_owner(request)
    with _pairing_lock:
        _pairing_sweep()
        items = [
            {
                "pairing_id": pid,
                "code": pid[-6:].upper(),
                "device_name": e["device_name"],
                "client_kind": e.get("client_kind"),
                "created_at": e["created_at"],
                "expires_in_seconds": max(
                    0, int(PAIRING_TTL_SECONDS - (time.time() - e["created_at"]))
                ),
            }
            for pid, e in pairing.items()
            if e["status"] == "pending"
        ]
    return _page(sorted(items, key=lambda i: i["created_at"], reverse=True))


@app.post("/pair/approve")
def pair_approve(req: PairApprove, request: Request):
    """Owner-approved challenge: only a trusted, non-revoked device (HMAC
    authenticated by the middleware) can approve a pending pairing."""
    approver = _require_owner(request)
    with _pairing_lock:
        entry = _live_pairing(req.pairing_id)
        if entry["status"] == "approved":
            return {"pairing_id": req.pairing_id, "status": "approved"}
        entry["status"] = "approved"
        entry["approved_by"] = approver
        entry["approved_at"] = time.time()
    audit.append(
        AuditEvent(
            actor="pairing",
            event_type="pairing_approved",
            status="approved",
            metadata={"pairing_id": req.pairing_id, "approved_by": approver},
        )
    )
    return {"pairing_id": req.pairing_id, "status": "approved"}


def _live_pairing(pairing_id: str) -> dict:
    """Fetch a pending pairing, expiring it if past its TTL. Caller holds
    _pairing_lock."""
    entry = pairing.get(pairing_id)
    if entry is None:
        raise HTTPException(404, "pairing not found")
    if time.time() - entry["created_at"] > PAIRING_TTL_SECONDS:
        del pairing[pairing_id]
        audit.append(
            AuditEvent(
                actor="pairing",
                event_type="pairing_expired",
                status="blocked",
                metadata={"pairing_id": pairing_id},
            )
        )
        raise HTTPException(410, "pairing expired")
    return entry


def _approve_bootstrap(entry: dict, pairing_id: str) -> None:
    entry["status"] = "approved"
    entry["approved_by"] = "bootstrap"
    entry["approved_at"] = time.time()
    audit.append(
        AuditEvent(
            actor="pairing",
            event_type="pairing_approved",
            status="approved",
            metadata={"pairing_id": pairing_id, "approved_by": "bootstrap"},
        )
    )


@app.post("/pair/confirm")
def pair_confirm(req: PairConfirm):
    """The new device collects its credentials. Succeeds only after owner
    approval, or for first-owner enrollment: with auth on, that requires
    the single-use bootstrap code from the node's terminal; in dev mode
    (auth off) the first device on an empty node self-completes."""
    # One critical section: the approval check, the pairing pop, and the
    # device mint are atomic, so concurrent confirms of the same pairing
    # mint exactly one device and two bootstrap confirms cannot both win.
    with _pairing_lock:
        entry = _live_pairing(req.pairing_id)
        if entry["status"] != "approved":
            if req.bootstrap_code and _bootstrap_open() and bootstrap.check(req.bootstrap_code):
                bootstrap.consume()
                _approve_bootstrap(entry, req.pairing_id)
            elif not AUTH_REQUIRED and not sessions.devices:
                # Dev mode only: no device has ever been enrolled.
                _approve_bootstrap(entry, req.pairing_id)
            else:
                if req.bootstrap_code:
                    audit.append(
                        AuditEvent(
                            actor="pairing",
                            event_type="bootstrap_code_rejected",
                            status="blocked",
                            metadata={"pairing_id": req.pairing_id},
                        )
                    )
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "invalid_bootstrap_code",
                                 "pairing_id": req.pairing_id, "status": "pending"},
                    )
                return JSONResponse(
                    status_code=202,
                    content={"pairing_id": req.pairing_id, "status": "pending",
                             "bootstrap_required": AUTH_REQUIRED and _bootstrap_open()},
                )
        pairing.pop(req.pairing_id)
        is_owner = entry.get("approved_by") == "bootstrap"
        if _MASTER_SECRET is not None:
            # HMAC-derived device credential (OpenDots backlog #6): the
            # device's request-signing secret is derived from the node
            # master secret and the minted device id. Nothing per device
            # is stored; verification recomputes the token.
            dev = sessions.register(
                entry["device_name"],
                entry["public_key"],
                None,
                is_owner=is_owner,
                credential_scheme=token_scheme_for_version(DEVICE_TOKEN_VERSION),
            )
            secret = derive_device_token(_MASTER_SECRET, dev.id)
        else:
            # Master secret unavailable (unwritable key path): legacy
            # random stored secret. Still 256 bits, still per device.
            secret = secrets.token_hex(32)
            # The owner flag is set at registration time so the persistent row
            # carries it: assigning it after register() lost the flag on restart.
            dev = sessions.register(
                entry["device_name"],
                entry["public_key"],
                secret,
                is_owner=is_owner,
            )
        kind = entry.get("client_kind")
        if kind:
            dev.client_kind = kind
            if kind == "web":
                dev.min_sig_version = 2
            sessions._persist_device(dev)
    audit.append(
        AuditEvent(
            actor="pairing",
            event_type="device_paired",
            status="trusted",
            metadata={
                "device_id": dev.id,
                "fingerprint": dev.fingerprint,
                "approved_by": entry.get("approved_by"),
            },
        )
    )
    # "shared_secret" is an alias kept for the mobile and iOS clients,
    # which historically read that key.
    return {
        "device": dev,
        "secret": secret,
        "shared_secret": secret,
        "session_expires_at": dev.session_expires_at.isoformat(),
    }


@app.post("/devices/register")
def register(req: DeviceRegisterRequest, request: Request):
    """Owner-initiated enrollment. The caller's HMAC authentication IS the
    owner approval, but no device is minted here: the server returns a
    pairing_id/code and the new device collects its credentials via
    POST /pair/confirm. An authenticated device can no longer mint another
    device in a single call."""
    approver = _require_owner(request)
    pid = _new_pairing(req.name, req.public_key, approved_by=approver)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="device_enrollment_initiated",
            status="pending",
            metadata={"pairing_id": pid, "approved_by": approver, "name": req.name},
        )
    )
    return {
        "pairing_id": pid,
        "code": pid[-6:].upper(),
        "expires_in_seconds": PAIRING_TTL_SECONDS,
    }


@app.post("/devices/{device_id}/revoke")
def revoke_device(device_id: str, request: Request):
    """Revoke a device. A device may always revoke itself; revoking any
    OTHER device requires owner authority (a trusted, non-revoked owner
    device). Capability model: the emergency pause is a kill-switch any
    trusted device may hit, but cross-device management is owner-only."""
    if device_id not in sessions.devices:
        raise HTTPException(404, "unknown device")
    if AUTH_REQUIRED:
        caller = request.headers.get("x-shadow-device-id")
        if caller != device_id:
            _require_owner(request)
    sessions.revoke(device_id)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="device_revoked",
            status="revoked",
            metadata={"device_id": device_id},
        )
    )
    return {"revoked": device_id}


@app.post("/devices/{device_id}/renew")
def renew_device(device_id: str, request: Request):
    """Start a fresh 30-day session window. A device may renew itself (it
    just authenticated, so it is still valid); renewing any other device,
    including reviving an expired one, requires owner authority. Revoked
    devices cannot be renewed."""
    dev = sessions.devices.get(device_id)
    if dev is None:
        raise HTTPException(404, "unknown device")
    if dev.revoked:
        raise HTTPException(409, "device is revoked")
    if AUTH_REQUIRED and request.headers.get("x-shadow-device-id") != device_id:
        _require_owner(request)
    sessions.renew(device_id)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="device_renewed",
            status="ok",
            metadata={"device_id": device_id},
        )
    )
    return {"device_id": device_id, "session_expires_at": dev.session_expires_at.isoformat()}


def _page(items):
    """Uniform list envelope: {"items", "count", "next_cursor"}.

    Contract-first rule: every list endpoint returns this object, never a
    bare array, so generated clients and hand-written clients agree.
    next_cursor is reserved for cursor pagination; currently always None.
    """
    items = list(items)
    return {"items": items, "count": len(items), "next_cursor": None}


@app.get("/devices")
def list_devices():
    return _page(sessions.devices.values())


@app.post("/consent")
def grant_consent(req: ConsentRequest):
    c = ConsentGrant(**req.model_dump())
    consents.append(c)
    return c


@app.post("/memory/ingest")
def ingest(req: IngestRequest):
    if req.consent_grant_id and not any(
        c.id == req.consent_grant_id and c.is_active() for c in consents
    ):
        raise HTTPException(403, "active consent grant required")
    src = MemorySource(
        kind=req.source_kind,
        title=req.source_title,
        consent_grant_id=req.consent_grant_id,
    )
    items = memory.ingest(
        req.text,
        src,
        sensitive=req.sensitive,
        do_not_send_to_cloud=req.do_not_send_to_cloud,
    )
    audit.append(
        AuditEvent(
            actor="user",
            event_type="memory_ingest",
            data_used=[src.title],
            status="stored",
            metadata={"source_id": src.id, "count": len(items)},
        )
    )
    return {"source": src, "items": items}


@app.post("/memory/ingest_file")
def ingest_file(req: FileIngestRequest):
    if not any(c.id == req.consent_grant_id and c.is_active() for c in consents):
        raise HTTPException(403, "active consent grant required")
    # Ingestion is confined to allowed roots: the node workspace plus any
    # operator-configured extra roots (audit P0-6). Symlinks and ".." are
    # resolved before the check, so escapes are rejected, not followed.
    roots = [workspace_root()] + [
        Path(p)
        for p in os.environ.get("SHADOW_INGEST_ROOTS", "").split(os.pathsep)
        if p.strip()
    ]
    try:
        text, kind = read_local_document(req.path, allowed_roots=roots)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    src = MemorySource(
        kind=f"file/{kind}",
        title=req.source_title or req.path,
        uri=req.path,
        consent_grant_id=req.consent_grant_id,
    )
    items = memory.ingest(text, src)
    audit.append(
        AuditEvent(
            actor="connector:file",
            event_type="file_ingest",
            data_used=[req.path],
            status="stored",
            metadata={"source_id": src.id, "count": len(items)},
        )
    )
    return {"source": src, "items": items}


@app.get("/memory")
def list_memory(include_sensitive: bool = False):
    return memory.export(include_sensitive)


@app.get("/memory/search")
def search(q: str, limit: int = 5, include_sensitive: bool = False):
    return memory.search(q, limit, include_sensitive)


@app.delete("/memory/source/{source_id}")
def delete_source(source_id: str):
    memory.delete_by_source(source_id)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="memory_source_deleted",
            status="revoked",
            metadata={"source_id": source_id},
        )
    )
    return {"deleted_source": source_id}


@app.get("/memory/recent")
def recent_memory(limit: int = 20, offset: int = 0, include_sensitive: bool = False):
    """Newest-first memory cards for the mobile Memory screen. Paginated;
    sensitive items are excluded by default."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    items, total = memory.recent(limit, offset, include_sensitive)
    return {
        "items": items,
        "count": len(items),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.delete("/memory/{item_id}")
def delete_memory_item(item_id: str):
    """Revoke one memory item (soft delete; the ciphertext stays but is
    excluded from search, export, and recent)."""
    if memory.store.get(item_id) is None:
        raise HTTPException(404, "memory item not found")
    memory.store.revoke(item_id)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="memory_item_deleted",
            status="revoked",
            metadata={"item_id": item_id},
        )
    )
    return {"deleted_item": item_id}


@app.get("/memory/export")
def export_memory(include_sensitive: bool = False):
    return memory.export(include_sensitive)


@app.get("/agent/self")
def agent_self():
    """Runtime-derived self-description: what SHADOW is, where it runs, and
    what it can do. Every field is read from the live node process."""
    return build_self_model(
        core, sessions, memory, model_config, APP_VERSION, persona_name=persona.name
    )


@app.get("/persona")
def get_persona():
    """The assistant's Cookie-style identity: name, avatar emoji, vibe, status."""
    return persona.model_dump()


@app.put("/persona")
def put_persona(update: PersonaUpdate):
    """Update the assistant's identity. Validated; audited; the vibe takes
    effect as the frontier-model system prompt immediately."""
    global persona
    try:
        persona = apply_update(persona, update)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if _runtime_db:
        save_persona(_runtime_store, persona)
    set_system_prompt_override(system_prompt_for(persona))
    audit.append(
        AuditEvent(
            actor="user",
            event_type="persona_updated",
            status="ok",
            result=f"name={persona.name!r}",
        )
    )
    return persona.model_dump()


@app.post("/goals", status_code=201)
def create_goal(data: GoalCreate):
    """Create a user goal: a durable outcome with progress tracking."""
    goal = goal_store.create(data)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="goal_created",
            status="stored",
            metadata={"goal_id": goal.id},
        )
    )
    return goal.model_dump()


@app.get("/goals")
def list_goals(status: str | None = None):
    """List goals newest-updated first, each with a progress roll-up."""
    if status is not None and status not in GoalStatus.values():
        raise HTTPException(422, f"status must be one of {GoalStatus.values()}")
    return [goal_store.summarize(g).model_dump() for g in goal_store.list(status)]


@app.get("/goals/briefing")
def goals_briefing():
    """Goal briefing: stale goals, goals due soon/overdue, completed this
    week, and recent progress entries."""
    return goal_store.briefing().model_dump()


@app.get("/goals/{goal_id}")
def get_goal(goal_id: str):
    detail = goal_store.detail(goal_id)
    if detail is None:
        raise HTTPException(404, "goal not found")
    return detail.model_dump()


@app.patch("/goals/{goal_id}")
def update_goal(goal_id: str, patch: GoalUpdate):
    """Update title/description/status/target_date. target_date "" clears it."""
    try:
        goal = goal_store.update(goal_id, patch)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if goal is None:
        raise HTTPException(404, "goal not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="goal_updated",
            status="ok",
            metadata={"goal_id": goal_id},
        )
    )
    return goal.model_dump()


@app.delete("/goals/{goal_id}")
def delete_goal(goal_id: str):
    if not goal_store.delete(goal_id):
        raise HTTPException(404, "goal not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="goal_deleted",
            status="revoked",
            metadata={"goal_id": goal_id},
        )
    )
    return {"deleted_goal": goal_id}


@app.post("/goals/{goal_id}/progress", status_code=201)
def log_progress(goal_id: str, data: ProgressCreate):
    """Log a progress entry (note + optional 0-100 percent) on a goal."""
    try:
        entry = goal_store.add_progress(goal_id, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if entry is None:
        raise HTTPException(404, "goal not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="goal_progress",
            status="stored",
            metadata={"goal_id": goal_id, "entry_id": entry.id},
        )
    )
    return entry.model_dump()


def _feed_renderers():
    ctx = {
        "core": core,
        "memory": memory,
        "claims": ambient_claims,
        "sessions": sessions,
    }
    return {
        "morning_brief": lambda: render_morning_brief(_amb_morning_brief(ctx)["data"]),
        "goals_briefing": lambda: render_goals_briefing(goal_store.briefing()),
        "memory_digest": lambda: render_memory_digest(_amb_memory_digest(ctx)["data"]),
    }


@app.post("/feed/generate")
def feed_generate(req: FeedGenerateRequest):
    """Render editorial feed units from live node state (offline, no cloud
    model). Empty kinds = all; force = bypass the ~20h per-kind dedupe."""
    for k in req.kinds:
        if k not in FEED_KINDS:
            raise HTTPException(422, f"unknown feed kind {k!r}; kinds: {FEED_KINDS}")
    kinds = req.kinds or list(FEED_KINDS)
    units = generate_units(feed_store, kinds, _feed_renderers(), force=req.force)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="feed_generated",
            status="ok",
            metadata={"kinds": [u.kind for u in units], "forced": req.force},
        )
    )
    return {"units": [u.model_dump() for u in units], "count": len(units)}


@app.get("/feed")
def feed_list(limit: int = 20, offset: int = 0):
    """Feed units newest-first, paginated."""
    units, total = feed_store.list(limit=limit, offset=offset)
    return {
        "items": [u.model_dump() for u in units],
        "count": len(units),
        "total": total,
        "limit": max(1, min(limit, 200)),
        "offset": max(0, offset),
    }


@app.post("/ideas", status_code=201)
def create_idea(data: IdeaCreate):
    """Create an idea card."""
    idea = idea_store.create(data)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="idea_created",
            status="stored",
            metadata={"idea_id": idea.id},
        )
    )
    return idea.model_dump()


@app.get("/ideas")
def list_ideas(status: str | None = None):
    """List idea cards newest-updated first."""
    from .ideas import IDEA_STATUSES

    if status is not None and status not in IDEA_STATUSES:
        raise HTTPException(422, f"status must be one of {IDEA_STATUSES}")
    return [i.model_dump() for i in idea_store.list(status)]


@app.get("/ideas/{idea_id}")
def get_idea(idea_id: str):
    idea = idea_store.get(idea_id)
    if idea is None:
        raise HTTPException(404, "idea not found")
    return idea.model_dump()


@app.patch("/ideas/{idea_id}")
def update_idea(idea_id: str, patch: IdeaUpdate):
    try:
        idea = idea_store.update(idea_id, patch)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if idea is None:
        raise HTTPException(404, "idea not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="idea_updated",
            status="ok",
            metadata={"idea_id": idea_id},
        )
    )
    return idea.model_dump()


@app.delete("/ideas/{idea_id}")
def delete_idea(idea_id: str):
    if not idea_store.delete(idea_id):
        raise HTTPException(404, "idea not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="idea_deleted",
            status="revoked",
            metadata={"idea_id": idea_id},
        )
    )
    return {"deleted_idea": idea_id}


@app.post("/ideas/{idea_id}/run")
def run_idea(idea_id: str):
    """Turn an idea into a real agent plan via AgentCore.propose. Risky
    actions raise approval requests and execute only through the
    approval-gated /agent/execute path; nothing runs here."""
    idea = idea_store.get(idea_id)
    if idea is None:
        raise HTTPException(404, "idea not found")
    prompt = f"Idea: {idea.title}\n{idea.description}".strip()
    plan = core.propose(prompt)
    audit.extend(core.drain_audit())
    actions = [
        PlannedAction(
            description=a.description, requires_approval=bool(a.requires_approval)
        )
        for a in plan.actions
    ]
    idea = idea_store.mark_running(idea_id, actions)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="idea_run",
            status="planned",
            metadata={
                "idea_id": idea_id,
                "actions": len(actions),
                "approvals_needed": sum(1 for a in actions if a.requires_approval),
            },
        )
    )
    return {
        "idea": idea.model_dump(),
        "plan": {
            "actions": [
                {"description": a.description, "requires_approval": a.requires_approval}
                for a in actions
            ]
        },
    }


@app.post("/reminders", status_code=201)
def create_reminder(data: ReminderCreate):
    """Create a reminder. `due_at` is a unix timestamp; `recurrence` is one
    of none/daily/weekly."""
    if data.recurrence not in REMINDER_RECURRENCES:
        raise HTTPException(422, f"recurrence must be one of {REMINDER_RECURRENCES}")
    r = reminder_store.create(data)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="reminder_created",
            status="stored",
            metadata={"reminder_id": r.id},
        )
    )
    return r.model_dump()


@app.get("/reminders")
def list_reminders(status: str | None = None):
    """List reminders, soonest-due first."""
    if status is not None and status not in REMINDER_STATUSES:
        raise HTTPException(422, f"status must be one of {REMINDER_STATUSES}")
    return [r.model_dump() for r in reminder_store.list(status)]


@app.get("/reminders/due")
def due_reminders():
    """Pending reminders whose due time has passed (includes ones held by quiet hours)."""
    return [r.model_dump() for r in reminder_store.due()]


@app.get("/reminders/{reminder_id}")
def get_reminder(reminder_id: str):
    r = reminder_store.get(reminder_id)
    if r is None:
        raise HTTPException(404, "reminder not found")
    return r.model_dump()


@app.patch("/reminders/{reminder_id}")
def update_reminder(reminder_id: str, patch: ReminderUpdate):
    if patch.recurrence is not None and patch.recurrence not in REMINDER_RECURRENCES:
        raise HTTPException(422, f"recurrence must be one of {REMINDER_RECURRENCES}")
    if patch.status is not None and patch.status not in REMINDER_STATUSES:
        raise HTTPException(422, f"status must be one of {REMINDER_STATUSES}")
    try:
        r = reminder_store.update(reminder_id, patch)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if r is None:
        raise HTTPException(404, "reminder not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="reminder_updated",
            status="ok",
            metadata={"reminder_id": reminder_id},
        )
    )
    return r.model_dump()


@app.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: str):
    if not reminder_store.delete(reminder_id):
        raise HTTPException(404, "reminder not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="reminder_deleted",
            status="revoked",
            metadata={"reminder_id": reminder_id},
        )
    )
    return {"deleted_reminder": reminder_id}


@app.post("/reminders/check")
def check_reminders():
    """Fire due reminders now: push + SSE event + feed unit per reminder.
    During quiet hours nothing fires; the response reports what was held."""
    import time as _time

    now = _time.time()
    quiet = ambient_scheduler.get_config().is_quiet()
    if quiet:
        held = reminder_store.due(now)
        return {"fired": [], "held": [r.id for r in held], "quiet": True}
    fired = fire_due(
        reminder_store, now, lambda: False, _notify_proactive, bus.publish, feed_store
    )
    for r in fired:
        audit.append(
            AuditEvent(
                actor="agent",
                event_type="reminder_fired",
                status="ok",
                metadata={"reminder_id": r.id, "recurrence": r.recurrence},
            )
        )
    return {"fired": [r.model_dump() for r in fired], "held": [], "quiet": False}
# --- Panels (Hark item 2: glanceable data panels) ---
@app.get("/panels")
def list_panels():
    """Glanceable data panels for the client's PanelCard: pending approvals,
    goals progress, and memory inventory as panel JSON (title, headline,
    stat tiles, rows). Node-state only; cheap to compute."""
    pending = [
        r
        for r in core.approvals.requests.values()
        if r.status == ApprovalStatus.PENDING
    ]
    return [p.model_dump() for p in build_panels(pending, goal_store.briefing(), memory.export())]


# --- Custom panels (Hark item 3: natural-language panel creation) ---
@app.post("/custom-panels/parse")
def parse_custom_panel(req: PanelParseRequest):
    """Parse "make a panel showing my top 5 overdue goals" into a panel
    proposal, or return a clarifying question. Ambiguous input is never
    guessed."""
    result = parse_panel_request(req.text)
    if isinstance(result, PanelProposal):
        return {
            "status": "proposal",
            "proposal": {
                "name": result.name,
                "source": result.source.value,
                "filter": result.filter.value,
                "sort": result.sort.value,
                "limit": result.limit,
                "matched": result.matched,
            },
        }
    return {
        "status": "needs_clarification",
        "question": result.question,
        "options": result.options,
    }


@app.get("/custom-panels")
def list_custom_panels():
    """List custom panel definitions (inspectable: the definition is the panel)."""
    return [p.model_dump(mode="json") for p in panel_registry.list()]


@app.post("/custom-panels", status_code=201)
def create_custom_panel(defn: CustomPanelDef):
    """Create a custom panel from a definition (or a confirmed parse proposal)."""
    try:
        panel = panel_registry.create(defn)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return panel.model_dump(mode="json")


@app.get("/custom-panels/{panel_id}")
def get_custom_panel(panel_id: str):
    try:
        return panel_registry.get(panel_id).model_dump(mode="json")
    except KeyError:
        raise HTTPException(404, "unknown panel")


@app.patch("/custom-panels/{panel_id}")
def update_custom_panel(panel_id: str, req: PanelUpdateRequest):
    try:
        panel = panel_registry.update(
            panel_id,
            name=req.name,
            filter=req.filter,
            sort=req.sort,
            limit=req.limit,
            fields=req.fields,
        )
    except KeyError:
        raise HTTPException(404, "unknown panel")
    except ValueError as e:
        raise HTTPException(422, str(e))
    return panel.model_dump(mode="json")


@app.delete("/custom-panels/{panel_id}")
def delete_custom_panel(panel_id: str, req: PanelDeleteRequest):
    """Delete a custom panel. Irreversible: requires explicit confirm=true."""
    if not req.confirm:
        raise HTTPException(
            409, "deleting a panel is irreversible: set confirm=true to proceed"
        )
    try:
        panel_registry.delete(panel_id)
    except KeyError:
        raise HTTPException(404, "unknown panel")
    return {"deleted": panel_id}


def _custom_panel_inputs() -> PanelInputs:
    pending = [
        r for r in core.approvals.requests.values() if r.status == ApprovalStatus.PENDING
    ]
    briefing = goal_store.briefing()
    active = [
        goal_store.summarize(g)
        for g in goal_store.goals.values()
        if g.status == GoalStatus.ACTIVE
    ]
    return PanelInputs(
        approvals=pending,
        goal_active=active,
        goal_overdue=briefing.overdue,
        goal_due_soon=briefing.due_soon,
        goal_stale=briefing.stale,
        goal_completed=briefing.completed_this_week,
        reminders=list(reminder_store.reminders.values()),
        memory_items=memory.export(),
        feed_units=list(feed_store.units),
    )


@app.get("/custom-panels/{panel_id}/render")
def render_custom_panel(panel_id: str):
    """Render a custom panel as panel JSON (same shape as built-in panels)."""
    try:
        defn = panel_registry.get(panel_id)
    except KeyError:
        raise HTTPException(404, "unknown panel")
    return render_panel(defn, _custom_panel_inputs()).model_dump(mode="json")


class ScheduleParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@app.post("/reminders/parse")
def parse_reminder_request(req: ScheduleParseRequest):
    """Parse a natural-language scheduling request ("remind me every weekday
    at 7am") into a structured reminder proposal, or a clarifying question.
    Deterministic; ambiguous input is never guessed."""
    return parse_schedule(req.text).as_dict()


# --- Scheduled tasks (Hark item 4: unified reminders + ambient tasks) ---
@app.get("/scheduled-tasks")
def list_scheduled_tasks_route():
    """Every scheduled thing in one shape: reminders plus builtin ambient
    tasks, soonest next run first. No hidden schedules."""
    return [
        t.model_dump()
        for t in list_scheduled_tasks(
            reminder_store, ambient_scheduler, ambient_checkpoints
        )
    ]


@app.get("/scheduled-tasks/{task_id}")
def get_scheduled_task(task_id: str):
    split = split_task_id(task_id)
    if split is None:
        raise HTTPException(404, "scheduled task not found")
    kind, ident = split
    if kind == "reminder":
        r = reminder_store.get(ident)
        if r is None:
            raise HTTPException(404, "scheduled task not found")
        return reminder_to_task(r).model_dump()
    if ident not in BUILTIN_TASKS and ident not in (
        ambient_scheduler.get_config().tasks or []
    ):
        raise HTTPException(404, "scheduled task not found")
    return ambient_task_to_task(
        ident, ambient_scheduler, ambient_checkpoints
    ).model_dump()


@app.post("/scheduled-tasks", status_code=201)
def create_scheduled_task(data: ReminderCreate):
    """Create a reminder through the unified surface. Ambient tasks are
    builtin: they can only be enabled/disabled, not created."""
    if not is_valid_recurrence(data.recurrence):
        raise HTTPException(422, f"recurrence must be one of {REMINDER_RECURRENCES}")
    r = reminder_store.create(data)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="reminder_created",
            status="stored",
            metadata={"reminder_id": r.id, "via": "scheduled-tasks"},
        )
    )
    return reminder_to_task(r).model_dump()


@app.patch("/scheduled-tasks/{task_id}")
def update_scheduled_task(task_id: str, patch: ScheduledTaskUpdate):
    split = split_task_id(task_id)
    if split is None:
        raise HTTPException(404, "scheduled task not found")
    kind, ident = split
    if kind == "ambient":
        others = {
            k: v
            for k, v in patch.model_dump().items()
            if k != "enabled" and v is not None
        }
        if others:
            raise HTTPException(
                422, f"ambient tasks only support 'enabled'; got {sorted(others)}"
            )
        if patch.enabled is None:
            raise HTTPException(422, "nothing to update: 'enabled' required")
        from .ambient_tasks import BUILTIN_TASKS

        if ident not in BUILTIN_TASKS:
            raise HTTPException(404, "scheduled task not found")
        cfg = ambient_scheduler.get_config()
        tasks = list(cfg.tasks or [])
        if patch.enabled and ident not in tasks:
            tasks.append(ident)
        elif not patch.enabled and ident in tasks:
            tasks.remove(ident)
        ambient_scheduler.configure(tasks=tasks)
        audit.append(
            AuditEvent(
                actor="user",
                event_type="scheduled_task_toggled",
                status="ok",
                metadata={"task_id": task_id, "enabled": patch.enabled},
            )
        )
        return ambient_task_to_task(
            ident, ambient_scheduler, ambient_checkpoints
        ).model_dump()
    if patch.recurrence is not None and not is_valid_recurrence(patch.recurrence):
        raise HTTPException(422, f"recurrence must be one of {REMINDER_RECURRENCES}")
    if patch.status is not None and patch.status not in REMINDER_STATUSES:
        raise HTTPException(422, f"status must be one of {REMINDER_STATUSES}")
    upd = ReminderUpdate(
        title=patch.title,
        note=patch.note,
        due_at=patch.due_at,
        recurrence=patch.recurrence,
        status=patch.status,
        enabled=patch.enabled,
    )
    try:
        r = reminder_store.update(ident, upd)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if r is None:
        raise HTTPException(404, "scheduled task not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="reminder_updated",
            status="ok",
            metadata={"reminder_id": ident, "via": "scheduled-tasks"},
        )
    )
    return reminder_to_task(r).model_dump()


@app.delete("/scheduled-tasks/{task_id}")
def delete_scheduled_task(task_id: str):
    split = split_task_id(task_id)
    if split is None:
        raise HTTPException(404, "scheduled task not found")
    kind, ident = split
    if kind == "ambient":
        raise HTTPException(
            422, "builtin ambient tasks cannot be deleted; disable them instead"
        )
    if not reminder_store.delete(ident):
        raise HTTPException(404, "scheduled task not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="reminder_deleted",
            status="revoked",
            metadata={"reminder_id": ident, "via": "scheduled-tasks"},
        )
    )
    return {"deleted_task": task_id}


# --- Artifacts (assistant parity: durable documents) ---
@app.post("/artifacts", status_code=201)
def create_artifact(req: ArtifactCreate):
    a = artifact_store.create(req)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="artifact_created",
            status="ok",
            metadata={"artifact_id": a.id, "kind": a.kind},
        )
    )
    return a.model_dump()


@app.get("/artifacts")
def list_artifacts(limit: int = 20, offset: int = 0, kind: str | None = None):
    if kind is not None and kind not in ARTIFACT_KINDS:
        raise HTTPException(422, f"kind must be one of {ARTIFACT_KINDS}")
    items, total = artifact_store.list(limit=limit, offset=offset, kind=kind)
    return {
        "artifacts": [a.meta() for a in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str):
    a = artifact_store.get(artifact_id)
    if a is None:
        raise HTTPException(404, "artifact not found")
    return a.model_dump()


@app.patch("/artifacts/{artifact_id}")
def update_artifact(artifact_id: str, patch: ArtifactUpdate):
    try:
        a = artifact_store.update(artifact_id, patch)
    except RevisionConflictError as e:
        raise HTTPException(409, str(e))
    if a is None:
        raise HTTPException(404, "artifact not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="artifact_updated",
            status="ok",
            metadata={"artifact_id": a.id, "version": a.version},
        )
    )
    return a.model_dump()


@app.get("/artifacts/{artifact_id}/versions")
def artifact_versions(artifact_id: str):
    v = artifact_store.versions(artifact_id)
    if v is None:
        raise HTTPException(404, "artifact not found")
    return {"artifact_id": artifact_id, "versions": v}


@app.get("/artifacts/{artifact_id}/versions/{version}")
def artifact_version(artifact_id: str, version: int):
    a = artifact_store.get_version(artifact_id, version)
    if a is None:
        raise HTTPException(404, "artifact version not found")
    return a.model_dump()


@app.delete("/artifacts/{artifact_id}")
def delete_artifact(artifact_id: str):
    if not artifact_store.delete(artifact_id):
        raise HTTPException(404, "artifact not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="artifact_deleted",
            status="revoked",
            metadata={"artifact_id": artifact_id},
        )
    )
    return {"deleted_artifact": artifact_id}


# --- Voice (assistant parity: speak and listen) ---
@app.get("/voice/capabilities")
def voice_capabilities():
    return voice_mod.capabilities()


@app.post("/voice/speak")
def voice_speak(req: dict):
    text = req.get("text") or ""
    voice = req.get("voice")
    fmt = req.get("format") or "mp3"
    try:
        data, mime = voice_mod.synthesize(text, voice=voice, format=fmt)
    except voice_mod.VoiceNotConfigured as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except voice_mod.VoiceProviderError as e:
        raise HTTPException(502, str(e))
    audit.append(
        AuditEvent(
            actor="user",
            event_type="voice_speak",
            status="ok",
            metadata={"chars": len(text)},
        )
    )
    return Response(content=data, media_type=mime)


@app.post("/voice/transcribe")
async def voice_transcribe(request: Request, audio: UploadFile | None = File(None)):
    # Two accepted shapes. Multipart (audio file field) is the classic file
    # upload; JSON {audio_base64, filename?, mime_type?} is the binary-safe
    # path mobile clients should use, since multipart bodies are signed by
    # digest (see _canonical_body).
    ctype = request.headers.get("content-type", "")
    filename = "audio.m4a"
    data = None
    if "application/json" in ctype:
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(422, "invalid JSON body")
        if not isinstance(payload, dict) or not payload.get("audio_base64"):
            raise HTTPException(422, "audio_base64 is required")
        try:
            data = base64.b64decode(payload["audio_base64"], validate=True)
        except Exception:
            raise HTTPException(422, "audio_base64 is not valid base64")
        filename = payload.get("filename") or filename
    elif audio is not None:
        data = await audio.read()
        filename = audio.filename or filename
    else:
        raise HTTPException(422, "audio file or audio_base64 is required")
    try:
        out = voice_mod.transcribe(data, filename=filename)
    except voice_mod.VoiceNotConfigured as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except voice_mod.VoiceProviderError as e:
        raise HTTPException(502, str(e))
    audit.append(
        AuditEvent(
            actor="user",
            event_type="voice_transcribe",
            status="ok",
            metadata={"bytes": len(data)},
        )
    )
    return out


# --- Media (assistant parity: image generation) ---
@app.get("/media/capabilities")
def media_capabilities():
    return media_mod.capabilities()


@app.post("/media/generate", status_code=201)
def media_generate(req: media_mod.MediaGenerateRequest):
    try:
        data, mime = media_mod.generate_image(req.prompt, req.size)
    except media_mod.MediaNotConfigured as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except media_mod.MediaProviderError as e:
        raise HTTPException(502, str(e))
    item = media_store.add(req.prompt, req.size, data, mime)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="media_generated",
            status="ok",
            metadata={"media_id": item.id, "bytes": len(data)},
        )
    )
    return item.meta()


@app.get("/media")
def list_media(limit: int = 20, offset: int = 0):
    items, total = media_store.list(limit=limit, offset=offset)
    return {
        "items": [i.meta() for i in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/media/{item_id}/content")
def media_content(item_id: str):
    got = media_store.content(item_id)
    if got is None:
        raise HTTPException(404, "media not found")
    data, mime = got
    return Response(content=data, media_type=mime)


@app.delete("/media/{item_id}")
def delete_media(item_id: str):
    if not media_store.delete(item_id):
        raise HTTPException(404, "media not found")
    audit.append(
        AuditEvent(
            actor="user",
            event_type="media_deleted",
            status="revoked",
            metadata={"media_id": item_id},
        )
    )
    return {"deleted_media": item_id}


@app.post("/agent/ask")
def ask(req: AskRequest, request: Request):
    result = _run_ask_pipeline(req)
    result["session_id"] = _record_ask_session(
        req, result, device_id=request.headers.get("x-shadow-device-id")
    )
    _note_message_wake(req, result)
    return result


def _record_ask_session(req: AskRequest, result: dict, device_id: str | None = None):
    """Append this ask turn to a durable session when the caller named one.

    Returns the session id (or None). Sessions persist across restarts;
    appends auto-compact past the context budget, with folded summaries
    ingested into user-owned memory. When the calling device is known, it is
    recorded on the session so any client can see where a conversation was
    last active (cross-device continuity).
    """
    sid = req.session_id
    if sid is None:
        return None
    try:
        session_store.append(sid, "user", req.prompt)
        session_store.append(sid, "assistant", result.get("answer") or "")
        if device_id:
            session_store.note_device(sid, device_id)
    except KeyError:
        raise HTTPException(404, "unknown session")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return sid


def _note_message_wake(req: AskRequest, result: dict):
    """Message-arrival wake for the always-on loop. Best-effort: the ask
    answer is primary, the wake is secondary, so a stopped loop only logs."""
    try:
        message_trigger.deliver(
            session_id=req.session_id,
            preview=req.prompt[:160],
            metadata={"route": result.get("route")},
        )
    except RuntimeError as e:
        log.warning("message_wake_skipped", extra={"error": str(e)[:120]})


def _run_ask_pipeline(req: AskRequest):
    if is_suspicious_user_request(req.prompt):
        audit.append(
            AuditEvent(
                actor="user",
                event_type="suspicious_request_blocked",
                proposed_action=req.prompt,
                status="blocked",
            )
        )
        raise HTTPException(
            403, "request blocked by prompt-injection/data-exfiltration policy"
        )
    # Self questions ("what are you", "where are you", "what can you do") are
    # answered deterministically from the live self-model instead of going to
    # the LLM, so the answers stay honest about this node.
    self_intent = classify_self_intent(req.prompt)
    if self_intent:
        model = build_self_model(
            core, sessions, memory, model_config, APP_VERSION, persona_name=persona.name
        )
        answer = render_self_answer(self_intent, model)
        audit.append(
            AuditEvent(
                actor="agent",
                event_type="agent_ask",
                model_used="self_model",
                status="answered",
                metadata={"intent": "self_" + self_intent, "route": "local"},
            )
        )
        return {
            "answer": answer,
            "sources": [],
            "why": [],
            "model_used": "self_model",
            "cloud_allowed": False,
            "untrusted_context": False,
            "context_package": {},
            "plan": None,
            "route": "local",
            "routing_reason": "self-model intent",
            "grounding": {},
            "regrounded": False,
            "savings": {"tokens_saved_estimate": 0},
        }
    results = memory.search(req.prompt, 5, include_sensitive=False)
    raw_context = "\n".join(mark_untrusted(r.item.text) for r in results)
    plan = core.propose(
        req.prompt, data_used=[r.attribution for r in results], model_used="local_mock"
    )
    # Data-bound cloud egress (audit P0: cloud privacy). The coarse gate
    # below decides whether this request may escalate to cloud at all; the
    # per-item manifest decides which memory items may actually leave the
    # node. Items flagged do_not_send_to_cloud are NEVER in the cloud
    # payload, independent of the `sensitive` flag, grants, or approvals.
    cloud_manifest = core.policy.authorize_cloud_context(
        results,
        provider=active_provider(),
        purpose="answer_user_question",
        grants=consents,
    )
    cloud_results = [r for r in results if r.item.id in cloud_manifest["allowed_ids"]]
    cloud_context = "\n".join(mark_untrusted(r.item.text) for r in cloud_results)
    if req.allow_cloud and not core.policy.cloud_allowed(consents, req.cloud_approval):
        audit.append(
            AuditEvent(
                actor="agent", event_type="cloud_escalation_denied", status="blocked"
            )
        )
        sentinel_audit.record(
            "sentinel_policy",
            "policy.decision",
            {
                "outcome": "deny",
                "rule_id": "cloud_escalation",
                "reason": "cloud escalation requires active grant and explicit approval",
            },
        )
        raise HTTPException(
            403, "cloud escalation requires active grant and explicit approval"
        )
    # Hybrid routing: build a frontier provider only when cloud is approved AND a credential resolves; else fully local.
    provider_name = active_provider()
    frontier = _build_active_frontier(provider_name) if req.allow_cloud else None
    try:
        out = hybrid.run(
            req.prompt,
            raw_context,
            cloud_context=cloud_context,
            frontier=frontier,
            verify=GROUNDING_VERIFY,
        )
    except Exception as e:
        if frontier is None:
            raise  # a local failure is not a cloud error
        safe_error = _redact_provider_error(e)
        audit.append(
            AuditEvent(
                actor="agent",
                event_type="cloud_model_error",
                model_used=provider_name,
                status="fallback_local",
                result=safe_error,
            )
        )
        out = hybrid.run(req.prompt, raw_context, frontier=None)
        # Never pass a placeholder off as an answer, and never fall back to
        # another billing path (e.g. the user's API key) silently: say
        # plainly that the cloud model failed and flag the response.
        if isinstance(e, (ChatGPTPlanError, claude_code.ClaudeCodeError)):
            out["answer"] = f"{e} Nothing was generated."
        else:
            out["answer"] = (
                f"The cloud model ({provider_name}) could not answer ({safe_error}). "
                "Nothing was generated; try again shortly."
            )
        out["degraded"] = True
        out["error"] = getattr(e, "code", None) or "cloud_model_error"
        if provider_name == CHATGPT_PLAN:
            out["manage_usage_url"] = MANAGE_USAGE_URL
    cloud_used = out["route"] == "frontier"
    if cloud_used:
        # Every cloud egress carries its authorization manifest in the audit
        # trail: which memory items left the node, for which provider and
        # purpose, and which were held back.
        sentinel_audit.record(
            "sentinel_policy",
            "cloud.egress_authorized",
            {
                "provider": cloud_manifest["provider"],
                "purpose": cloud_manifest["purpose"],
                "allowed": cloud_manifest["allowed_count"],
                "excluded": cloud_manifest["excluded_count"],
                "decision": cloud_manifest["policy_decision"],
                "items": cloud_manifest["items"],
            },
        )
    audit.append(
        AuditEvent(
            actor="agent",
            event_type="agent_ask",
            data_used=[r.attribution for r in results],
            model_used=out["provider"],
            status="answered",
            metadata={
                "route": out["route"],
                "tokens_saved": out["savings"]["tokens_saved_estimate"],
                "grounding": out["grounding"],
                "cloud_excluded": cloud_manifest["excluded_count"],
                "cloud_allowed_items": cloud_manifest["allowed_count"],
            },
        )
    )
    return {
        "answer": out["answer"],
        "sources": [r.model_dump() for r in results],
        "why": [r.explanation for r in results],
        "model_used": out["provider"],
        "cloud_allowed": cloud_used,
        "untrusted_context": True,
        "context_package": out["context_package"],
        "plan": plan,
        "route": out["route"],
        "routing_reason": out["reason"],
        "grounding": out["grounding"],
        "regrounded": out["regrounded"],
        "savings": out["savings"],
        "cloud_manifest": cloud_manifest if req.allow_cloud else None,
        "degraded": out.get("degraded", False),
        "error": out.get("error"),
        "provider": active_provider() if out.get("route") == "frontier" or out.get("degraded") else None,
        "billing": (
            "chatgpt_plan" if active_provider() == CHATGPT_PLAN
            else "claude_code" if active_provider() == CLAUDE_CODE else "api_key"
        ) if out.get("route") == "frontier" else None,
        "manage_usage_url": out.get("manage_usage_url"),
    }


def _redact_provider_error(e: Exception) -> str:
    """Short, secret-free description of a provider failure. Provider
    exceptions can embed request URLs that carry credentials (Gemini's
    ?key=...), so only the exception type and HTTP status are surfaced."""
    status = getattr(getattr(e, "response", None), "status_code", None)
    msg = str(e)
    if status is None:
        m = re.search(r"\bHTTP (\d{3})\b|\b(\d{3}) [A-Z][a-z]", msg)
        status = (m.group(1) or m.group(2)) if m else None
    if type(e).__name__ == "ModelResponseError" and "declined" in msg:
        return "request declined by the provider's safety system"
    return f"{type(e).__name__}" + (f", HTTP {status}" if status else "")


def _sse_data(event_type: str, properties: dict) -> str:
    return (
        "data: " + json.dumps({"type": event_type, "properties": properties}) + "\n\n"
    )


@app.get("/agent/stream")
async def agent_stream(request: Request):
    """Long-lived SSE bus: node.hello on connect, then approval.created /
    approval.updated as they happen. Authenticated like any other endpoint
    (HMAC headers; XHR/fetch can set them, no query-param auth needed)."""
    q = bus.subscribe()

    async def gen():
        yield _sse_data(
            "node.hello",
            {
                "node": "shadow-node",
                "version": APP_VERSION,
                "device_id": request.headers.get("x-shadow-device-id"),
            },
        )
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=25)
                except asyncio.TimeoutError:
                    yield ":heartbeat\n\n"
                    continue
                yield "data: " + json.dumps(evt) + "\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/agent/ask_stream")
def ask_stream(req: AskRequest):
    """Run the ask pipeline, then stream the answer as agent.message.delta
    chunks followed by agent.message.done. Chunking is delivery-level
    (progressive rendering), not token-level generation."""
    result = _run_ask_pipeline(req)
    _note_message_wake(req, result)
    session_id = new_id("ses")
    message_id = new_id("msg")
    answer = result["answer"] or ""
    chunks = [answer[i : i + 160] for i in range(0, len(answer), 160)] or [""]

    def gen():
        for ch in chunks:
            yield _sse_data(
                "agent.message.delta",
                {"sessionID": session_id, "messageID": message_id, "delta": ch},
            )
        yield _sse_data(
            "agent.message.done",
            {
                "sessionID": session_id,
                "messageID": message_id,
                "answer": answer,
                "sources": result["sources"],
                "model_used": result["model_used"],
                "route": result["route"],
            },
        )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class PushTokenRequest(BaseModel):
    push_token: str


@app.post("/devices/{device_id}/push-token")
def set_push_token(device_id: str, req: PushTokenRequest, request: Request):
    # Ownership boundary (audit P1): a device may only register its own
    # push token. Without this, any authenticated device could overwrite
    # another device's token and hijack its approval notifications.
    if AUTH_REQUIRED and request.headers.get("x-shadow-device-id") != device_id:
        audit.append(
            AuditEvent(
                actor="user",
                event_type="push_token_rejected",
                status="blocked",
                metadata={"device_id": device_id},
            )
        )
        raise HTTPException(403, "a device may only register its own push token")
    if device_id not in sessions.devices:
        raise HTTPException(404, "unknown device")
    if not req.push_token.startswith("ExponentPushToken["):
        raise HTTPException(400, "not an Expo push token")
    sessions.push_tokens[device_id] = req.push_token
    audit.append(
        AuditEvent(
            actor="user",
            event_type="push_token_registered",
            status="stored",
            metadata={"device_id": device_id},
        )
    )
    return {"device_id": device_id, "push_registered": True}


@app.post("/agent/plan")
def plan(req: AskRequest):
    return core.propose(req.prompt)


@app.post("/agent/execute")
def execute(req: ExecuteRequest):
    server_approved = _resolve_server_approval(req.approval_id, req.action)
    with _consent_granted(server_approved):
        res = core.execute(
            req.action,
            server_approved,
            req.double_confirmed,
            approval_id=req.approval_id,
            thread_id=req.thread_id,
            tool_call_id=req.tool_call_id,
        )
    audit.extend(core.drain_audit())
    if req.approval_id:
        try:
            core.approvals.attach_execution(
                req.approval_id, res["execution_id"], res["verification"]
            )
        except KeyError:
            raise HTTPException(404, "unknown approval")
        audit.append(
            AuditEvent(
                actor="agent",
                event_type="execution_verified",
                proposed_action=req.action.description,
                status=res["verification"],
                result=res["verification_reason"],
                metadata={
                    "approval_id": req.approval_id,
                    "execution_id": res["execution_id"],
                },
            )
        )
    return res


@app.get("/executions")
def list_executions(status: str | None = None, limit: int = 50):
    """Execution records, newest first. Filter with ?status=verified|failed|uncertain|conflicting."""
    recs = sorted(core.executions.values(), key=lambda r: r.started_at, reverse=True)
    if status:
        recs = [r for r in recs if r.verification.value == status]
    return [r.summary() for r in recs[: max(1, min(limit, 200))]]


@app.get("/executions/{execution_id}")
def get_execution(execution_id: str):
    """Full execution detail: intent, policy decision, tool observation, evidence, world-state diff, verdict."""
    rec = core.executions.get(execution_id)
    if rec is None:
        raise HTTPException(404, "unknown execution")
    return rec


class AmbientConfigRequest(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None
    stealth_mode: bool | None = None
    tasks: list[str] | None = None
    quiet_start: str | None = None
    quiet_end: str | None = None


class GhostRunRequest(BaseModel):
    objective: str
    steps: list[dict]
    approval_id: str | None = None
    double_confirmed: bool = False


class ClaimRequest(BaseModel):
    statement: str
    run_id: str | None = None


class ClaimDecisionRequest(BaseModel):
    evidence: str


@app.get("/ambient/status")
def ambient_status():
    """Ambient scheduler state. Disabled by default; enabling is explicit opt-in."""
    cfg = ambient_scheduler.get_config()
    return {
        "config": cfg.model_dump(mode="json"),
        "tasks_available": sorted(build_task_map()),
        "background_running": ambient_loop.is_running,
        "loop": {
            "state": ambient_loop.state.value,
            "wake_count": ambient_loop.wake_count,
            "last_wake_at": str(ambient_loop.last_wake_at)
            if ambient_loop.last_wake_at
            else None,
            "sessions_open": len(session_store.list()),
            "sessions_rehydrated": _rehydrated_sessions,
        },
        "triggers": ambient_loop.trigger_statuses(),
    }


class WakeRequest(BaseModel):
    source: str
    reason: str = ""
    payload: dict = {}


@app.post("/ambient/wake")
def ambient_wake(req: WakeRequest):
    """Wake the always-on loop from a local source.

    Sources: "push" (device push tap, via the companion app), "message"
    (inbound message), "calendar" (real Google Calendar event),
    "reminder" (node-local reminder), "operator" (manual). The loop
    journals the wake and, when ambient is enabled, transitions
    SLEEPING -> AWAKE and runs its cycle.
    """
    src = req.source.lower()
    try:
        if src == "push":
            evt = push_trigger.deliver(
                device_id=str(req.payload.get("device_id", "")),
                action=str(req.payload.get("action", "tap")),
                payload=req.payload,
            )
        elif src == "message":
            evt = message_trigger.deliver(
                session_id=req.payload.get("session_id"),
                preview=str(req.payload.get("preview", "")),
                metadata=req.payload,
            )
        elif src in ("calendar", "reminder", "timer", "operator"):
            evt = ambient_loop.wake(src, req.reason, req.payload)
        else:
            raise HTTPException(400, f"unknown wake source: {req.source!r}")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {
        "wake_id": evt.id,
        "source": evt.source,
        "loop_state": ambient_loop.state.value,
    }


@app.get("/ambient/acts")
def ambient_acts():
    """List the registered Shadow Acts with their current policy
    evaluation. The evaluation is a dry run: it never creates approvals
    or runs anything. An act executes autonomously only when its
    evaluation is ALLOW, which additionally requires an explicit
    tool_tiers grant in the policy document."""
    acts = []
    for name, act in shadow_act_runner.acts.items():
        try:
            d = shadow_act_runner.evaluate(name)
            decision = {
                "outcome": d.outcome.value,
                "rule_id": d.rule_id,
                "risk": d.risk.value,
                "reason": d.reason,
            }
        except Exception as e:
            decision = {"outcome": "error", "reason": str(e)}
        acts.append(
            {
                "name": name,
                "description": act.description,
                "effect": act.effect,
                "tool_name": f"shadow_act:{name}",
                "decision": decision,
            }
        )
    return {"acts": acts}


class ActRunRequest(BaseModel):
    act: str


@app.post("/ambient/acts/run")
def ambient_acts_run(req: ActRunRequest):
    """Manually run one Shadow Act through the same policy gate the
    ambient tick uses. ALLOW runs it; REQUIRE_APPROVAL files (or reuses)
    an approval request and holds it; DENY refuses. Unknown act names
    are a 404."""
    try:
        result = shadow_act_runner.run_one(req.act, ambient_scheduler.task_context())
    except KeyError:
        raise HTTPException(404, f"unknown shadow act: {req.act!r}")
    return result


@app.get("/ambient/plans")
def ambient_plans(active_only: bool = False):
    """List stored paced plans: multi-step proactive deliveries created
    by shadow acts. Each plan shows its steps, their scheduled
    deliver_at times, and delivery status
    (pending/delivered/deferred/cancelled)."""
    return {
        "plans": [
            p.to_dict() for p in shadow_act_runner.list_plans(active_only=active_only)
        ]
    }


@app.get("/ambient/plans/{plan_id}")
def ambient_plan(plan_id: str):
    """Inspect one paced plan: steps, scheduled times, delivery status."""
    try:
        return shadow_act_runner.get_plan(plan_id).to_dict()
    except KeyError:
        raise HTTPException(404, f"unknown plan: {plan_id!r}")


@app.post("/ambient/plans/{plan_id}/cancel")
def ambient_plan_cancel(plan_id: str):
    """Cancel a paced plan. Pending and deferred steps become
    cancelled; already delivered steps stay delivered."""
    try:
        plan = shadow_act_runner.cancel_plan(plan_id)
    except KeyError:
        raise HTTPException(404, f"unknown plan: {plan_id!r}")
    return {
        "plan_id": plan.id,
        "status": plan.status.value,
        "steps": [s.to_dict() for s in plan.steps],
    }


class SessionCreateRequest(BaseModel):
    title: str = ""
    metadata: dict = {}


@app.post("/agent/sessions")
def create_session(req: SessionCreateRequest):
    """Create a durable conversation session. Sessions persist across
    restarts and auto-compact past their context budget."""
    return session_store.create(title=req.title, metadata=req.metadata).model_dump(
        mode="json"
    )


@app.get("/agent/sessions")
def list_sessions(open_only: bool = True):
    """List sessions, most recently active first."""
    return [s.model_dump(mode="json") for s in session_store.list(open_only=open_only)]


@app.get("/agent/sessions/{session_id}")
def get_session(session_id: str):
    """Session detail with full message history."""
    try:
        return session_store.get(session_id).model_dump(mode="json")
    except KeyError:
        raise HTTPException(404, "unknown session")


@app.post("/agent/sessions/{session_id}/close")
def close_session(session_id: str):
    """Close a session. Closed sessions are kept for history but reject appends."""
    try:
        return session_store.close(session_id).model_dump(mode="json")
    except KeyError:
        raise HTTPException(404, "unknown session")


# ---------------------------------------------------------------------------
# Cross-device continuity (Hark backlog item 11): one assistant identity
# across iOS, desktop, and web. Conversations and memory already live on the
# node; these routes add device presence and explicit conversation handoff.
# ---------------------------------------------------------------------------


class HandoffCreateRequest(BaseModel):
    target_device_id: str | None = None
    note: str = ""


class PresenceHeartbeat(BaseModel):
    display_name: str | None = None
    platform: str | None = None


def _caller_device(request: Request):
    device_id = request.headers.get("x-shadow-device-id")
    dev = sessions.devices.get(device_id) if device_id else None
    return device_id, dev


def _device_display_name(device_id: str | None) -> str | None:
    if not device_id:
        return None
    dev = sessions.devices.get(device_id)
    return dev.name if dev else None


def _iso(dt):
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


@app.post("/agent/sessions/{session_id}/handoff")
def create_handoff(session_id: str, req: HandoffCreateRequest, request: Request):
    """Start an explicit handoff of a conversation to another device.

    Freezes the message snapshot now; pending approvals and active plans are
    node-global and resolve live when the handoff is claimed. Never automatic:
    only this explicit call creates a handoff.
    """
    device_id, _dev = _caller_device(request)
    try:
        session = session_store.get(session_id)
    except KeyError:
        raise HTTPException(404, "unknown session")
    if session.closed:
        raise HTTPException(400, "session is closed")
    target_name = None
    if req.target_device_id:
        target = sessions.devices.get(req.target_device_id)
        if target is None or target.revoked:
            raise HTTPException(404, "unknown target device")
        target_name = target.name
    pending = [
        r
        for r in core.approvals.requests.values()
        if r.status == ApprovalStatus.PENDING
    ]
    active_plans = shadow_act_runner.list_plans(active_only=True)
    record = handoff_store.create(
        session_id=session_id,
        from_device_id=device_id,
        from_device_name=_device_display_name(device_id),
        target_device_id=req.target_device_id,
        target_device_name=target_name,
        note=req.note,
        snapshot=build_session_snapshot(session),
        pending_approval_count=len(pending),
        active_plan_count=len(active_plans),
    )
    if device_id:
        note_presence(
            _ambient_kv, device_id, display_name=_device_display_name(device_id)
        )
    sentinel_audit.record(
        "user",
        "continuity.handoff_created",
        {
            "handoff_id": record.id,
            "session_id": session_id,
            "from_device_id": device_id,
            "target_device_id": req.target_device_id,
        },
    )
    return record.model_dump(mode="json")


@app.get("/continuity/handoffs")
def list_handoffs(request: Request):
    """Pending handoffs visible to the caller: open ones, ones targeted at
    this device, and ones this device created."""
    device_id, _dev = _caller_device(request)
    visible = [
        h.model_dump(mode="json")
        for h in handoff_store.list_pending()
        if h.target_device_id is None
        or h.target_device_id == device_id
        or h.from_device_id == device_id
    ]
    return _page(visible)


@app.post("/continuity/handoffs/{handoff_id}/claim")
def claim_handoff(handoff_id: str, request: Request):
    """Claim a pending handoff and receive the full resume package: the
    frozen conversation snapshot plus live pending approvals and active
    plans. A handoff targeted at another device is indistinguishable from a
    missing one."""
    device_id, _dev = _caller_device(request)
    try:
        record = handoff_store.claim(handoff_id, device_id)
    except KeyError:
        raise HTTPException(404, "unknown handoff")
    except ValueError as e:
        if "expired" in str(e):
            raise HTTPException(410, str(e))
        raise HTTPException(409, str(e))
    try:
        session = session_store.get(record.session_id)
    except KeyError:
        raise HTTPException(404, "handoff session no longer exists")
    if device_id:
        session_store.note_device(record.session_id, device_id)
        note_presence(
            _ambient_kv, device_id, display_name=_device_display_name(device_id)
        )
    sentinel_audit.record(
        "user",
        "continuity.handoff_claimed",
        {"handoff_id": record.id, "claimed_by_device_id": device_id},
    )
    return {
        "handoff": record.model_dump(mode="json"),
        "session": session.model_dump(mode="json"),
        "pending_approvals": [
            r.card
            for r in core.approvals.requests.values()
            if r.status == ApprovalStatus.PENDING
        ],
        "active_plans": [
            p.to_dict() for p in shadow_act_runner.list_plans(active_only=True)
        ],
    }


@app.post("/continuity/handoffs/{handoff_id}/cancel")
def cancel_handoff(handoff_id: str, request: Request):
    """Cancel a pending handoff. Only the device that created it may cancel."""
    device_id, _dev = _caller_device(request)
    try:
        record = handoff_store.cancel(handoff_id, device_id)
    except KeyError:
        raise HTTPException(404, "unknown handoff")
    except ValueError as e:
        raise HTTPException(409, str(e))
    sentinel_audit.record(
        "user",
        "continuity.handoff_cancelled",
        {"handoff_id": record.id, "cancelled_by_device_id": device_id},
    )
    return record.model_dump(mode="json")


@app.post("/continuity/presence")
def heartbeat_presence(req: PresenceHeartbeat, request: Request):
    """Heartbeat: tell the node this client is active. Powers the active
    device list in the continuity overview."""
    device_id, dev = _caller_device(request)
    if not device_id:
        raise HTTPException(400, "x-shadow-device-id header required")
    record = note_presence(
        _ambient_kv,
        device_id,
        display_name=req.display_name or (dev.name if dev else None),
        platform=req.platform,
    )
    return record.model_dump(mode="json")


@app.get("/continuity/overview")
def continuity_overview():
    """One screen's worth of continuity state: registered devices with
    presence, open sessions with last-active device, pending handoff count."""
    presence = {p.device_id: p for p in list_presence(_ambient_kv)}
    devices = []
    for d in sessions.devices.values():
        if d.revoked:
            continue
        p = presence.get(d.id)
        devices.append(
            {
                "device_id": d.id,
                "display_name": d.name,
                "platform": p.platform if p else None,
                "trusted": d.trusted,
                "is_owner": d.is_owner,
                "last_seen_at": _iso(p.last_seen_at) if p else None,
            }
        )
    open_sessions = []
    for s in session_store.list(open_only=True):
        last_dev = s.metadata.get("last_device_id")
        open_sessions.append(
            {
                "session_id": s.id,
                "title": s.title,
                "message_count": len(s.messages),
                "updated_at": _iso(s.updated_at),
                "last_device_id": last_dev,
                "last_device_name": _device_display_name(last_dev),
            }
        )
    return {
        "devices": devices,
        "open_sessions": open_sessions,
        "pending_handoffs": len(handoff_store.list_pending()),
    }


@app.post("/ambient/config")
def ambient_config(req: AmbientConfigRequest):
    """Enable/disable ambient work, set interval and stealth mode, choose tasks, set quiet hours (HH:MM)."""
    try:
        cfg = ambient_scheduler.configure(
            enabled=req.enabled,
            interval_seconds=req.interval_seconds,
            stealth_mode=req.stealth_mode,
            tasks=req.tasks,
            quiet_start=req.quiet_start,
            quiet_end=req.quiet_end,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return cfg


@app.post("/ambient/tick")
def ambient_tick():
    """Run one ambient iteration now (operator-initiated, not scheduled)."""
    return ambient_scheduler.tick()


@app.get("/ambient/runs")
def ambient_runs(limit: int = 50):
    """Checkpointed runs (ghost agent runs and ambient ticks), newest first."""
    return [
        cp.model_dump(mode="json")
        for cp in ambient_checkpoints.all()[: max(1, min(limit, 200))]
    ]


@app.get("/ambient/runs/{run_id}")
def ambient_run_detail(run_id: str):
    """Run detail: checkpoint, full journal, linked claims, linked executions."""
    cp = ambient_checkpoints.load(run_id)
    if cp is None:
        raise HTTPException(404, "unknown run")
    exec_ids = [r.get("execution_id") for r in cp.results if r.get("execution_id")]
    return {
        "checkpoint": cp.model_dump(mode="json"),
        "journal": [e.model_dump(mode="json") for e in ambient_journal.for_run(run_id)],
        "claims": [c.model_dump(mode="json") for c in ambient_claims.for_run(run_id)],
        "executions": [
            core.executions[eid].summary() for eid in exec_ids if eid in core.executions
        ],
    }


@app.post("/ghost/runs")
def ghost_run_start(req: GhostRunRequest):
    """Start a checkpointed multi-step run. Every step executes through the
    policy gate with evidence and a verification verdict; progress is
    checkpointed after each step so an interrupted run can be resumed.

    Approval is never implicit: each step may carry its own "approval_id"
    (falling back to the run-level approval_id), resolved against the
    server-side approval store with the same binding /agent/execute uses.
    An unknown, denied, expired, or mismatched approval fails the run
    before that step executes. Steps without an approval run unapproved,
    so approval-gated tools are blocked by the policy gate.
    """
    if not req.objective.strip():
        raise HTTPException(400, "objective required")
    if not req.steps:
        raise HTTPException(400, "at least one step required")
    for s in req.steps:
        if not isinstance(s, dict) or "tool" not in s:
            raise HTTPException(400, "every step needs a tool")
    run_id = ghost_runs.start(
        req.objective,
        req.steps,
        approval_id=req.approval_id,
        double_confirmed=req.double_confirmed,
    )
    return ghost_runs.run_all(run_id)


@app.post("/ghost/runs/{run_id}/resume")
def ghost_run_resume(run_id: str):
    """Resume an interrupted run from its checkpoint. Finished steps are not re-executed."""
    try:
        return ghost_runs.resume(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/ghost/runs/{run_id}/interrupt")
def ghost_run_interrupt(run_id: str):
    """Stop a run mid-flight. The checkpoint remains and the run can be resumed later."""
    try:
        return ghost_runs.interrupt(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/claims")
def claims_list(status: str | None = None):
    """World-state claims. Filter with ?status=unconfirmed|confirmed|refuted."""
    try:
        return [c.model_dump(mode="json") for c in ambient_claims.list(status=status)]
    except ValueError:
        raise HTTPException(400, "unknown status")


@app.post("/claims")
def claim_register(req: ClaimRequest):
    if not req.statement.strip():
        raise HTTPException(400, "statement required")
    return ambient_claims.register(req.statement, run_id=req.run_id)


@app.post("/claims/{claim_id}/confirm")
def claim_confirm(claim_id: str, req: ClaimDecisionRequest):
    try:
        return ambient_claims.confirm(claim_id, req.evidence)
    except KeyError:
        raise HTTPException(404, "unknown claim")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/claims/{claim_id}/refute")
def claim_refute(claim_id: str, req: ClaimDecisionRequest):
    try:
        return ambient_claims.refute(claim_id, req.evidence)
    except KeyError:
        raise HTTPException(404, "unknown claim")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/approvals")
def create_approval(req: ApprovalCreateRequest):
    # Normalize destructiveness server-side so the card's double-confirmation
    # requirement matches what policy will enforce at execution (audit P0-4).
    req.action.destructive = core.policy.is_destructive(req.action)
    approval = core.approvals.create(req.action, req.reason)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="approval_created",
            proposed_action=req.action.description,
            status="pending",
            metadata={"approval_id": approval.id},
        )
    )
    return approval


@app.get("/approvals/receipt")
def approval_receipt(thread_id: str, tool_call_id: str):
    """Idempotency receipt lookup (OpenDots' restorePageReview analog):
    returns the approval card for a (thread_id, tool_call_id) pair so a
    client that lost the suspend response can recover it without minting
    a duplicate. 404 when no receipt exists."""
    req = core.approvals.receipt(thread_id, tool_call_id)
    if req is None:
        raise HTTPException(404, "no approval receipt for (thread_id, tool_call_id)")
    return {"approval": req.model_dump(mode="json"), "card": req.card}


@app.get("/approvals")
def approvals(status: str | None = None):
    """Uniform page envelope. ?status= filters by approval status
    (pending/approved/denied/expired/consumed)."""
    reqs = list(core.approvals.requests.values())
    if status:
        reqs = [r for r in reqs if r.status.value == status]
    return _page(reqs)


def _decider_id(request: Request) -> str | None:
    return getattr(request.state, "device_id", None) or request.headers.get(
        "x-shadow-device-id"
    )


class ApproveRequest(BaseModel):
    # "Always allow": also save a standing allow rule for this tool (only
    # for tools eligible for one; owner devices only).
    remember: bool = False


@app.post("/approvals/{id}/approve")
def approve(id: str, request: Request, req: ApproveRequest | None = None):
    # Any trusted paired device may approve: every device was enrolled with
    # the owner's approval, and phones (enrolled via /devices/register, not
    # owners) are the primary approval surface. The approving device is
    # recorded so every decision is attributable.
    approver = _decider_id(request)
    remember = bool(req and req.remember)
    if remember:
        # Check everything before deciding: a refused "Always allow" must
        # leave the approval untouched.
        _require_owner(request)
        pending = core.approvals.requests.get(id)
        if pending is not None:
            ok, why = core.policy.allow_eligible(pending.action.tool_name)
            if not ok:
                raise HTTPException(409, f"'{pending.action.tool_name}' can't be always allowed: {why}")
    try:
        req = core.approvals.decide(id, True)
    except ValueError as e:
        raise HTTPException(409, str(e))
    audit.append(
        AuditEvent(
            actor="user",
            event_type="approval_approved",
            proposed_action=req.action.description,
            status="approved",
            metadata={"approval_id": id, "approved_by": approver},
        )
    )
    if remember:
        _require_owner(request)
        try:
            core.policy.set_user_rule(req.action.tool_name, "allow")
        except ValueError as e:
            raise HTTPException(409, str(e))
        _save_user_rules()
        audit.append(AuditEvent(actor="user", event_type="policy_rule_set", status="ok",
                                metadata={"tool": req.action.tool_name, "rule": "allow", "via": id}))
    return req


@app.post("/approvals/{id}/deny")
def deny(id: str, req: DenyRequest, request: Request):
    try:
        out = core.approvals.decide(id, False, req.reason)
    except ValueError as e:
        raise HTTPException(409, str(e))
    audit.append(
        AuditEvent(
            actor="user",
            event_type="approval_denied",
            proposed_action=out.action.description,
            status="denied",
            result=req.reason,
            metadata={"approval_id": id, "denied_by": _decider_id(request)},
        )
    )
    return out


class RuleRequest(BaseModel):
    rule: str  # allow | ask | block


@app.get("/policy/rules")
def list_policy_rules():
    """Your per-tool rules plus, for every known tool, whether "Allow" is
    possible and why not. Hard gates (pause, blocked tools, irreversible
    actions, outgoing secrets) aren't rules: nothing here can change them."""
    tools = sorted(set(core.tools.names()) | set(core.policy.user_rules))
    rows = []
    for t in tools:
        ok, why = core.policy.allow_eligible(t)
        rows.append({
            "tool": t,
            "rule": core.policy.user_rules.get(t.lower()),
            "allow_eligible": ok,
            "allow_blocked_reason": why or None,
            "operator_tier": core.policy.tool_tiers.get(t.lower()),
            "outbound": t.lower() in core.policy.outbound_tools,
        })
    return _page(rows)


@app.put("/policy/rules/{tool}")
def set_policy_rule(tool: str, req: RuleRequest, request: Request):
    _require_owner(request)
    try:
        core.policy.set_user_rule(tool, req.rule)
    except ValueError as e:
        raise HTTPException(422, str(e))
    _save_user_rules()
    audit.append(AuditEvent(actor="user", event_type="policy_rule_set", status="ok",
                            metadata={"tool": tool, "rule": req.rule}))
    return {"tool": tool, "rule": req.rule}


@app.delete("/policy/rules/{tool}")
def delete_policy_rule(tool: str, request: Request):
    _require_owner(request)
    core.policy.set_user_rule(tool, None)
    _save_user_rules()
    audit.append(AuditEvent(actor="user", event_type="policy_rule_cleared", status="ok",
                            metadata={"tool": tool}))
    return {"tool": tool, "rule": None}


@app.get("/emergency_pause")
def get_emergency_pause():
    return {"paused": profile.emergency_paused}


@app.post("/emergency_pause")
def set_emergency_pause(req: EmergencyPauseRequest):
    """Kill-switch capability: any HMAC-authenticated trusted device may
    pause/resume the node. This is deliberate, not an oversight: the kill
    switch must work from every trusted device. (Cross-device management
    such as revoking another device is owner-only; see
    POST /devices/{id}/revoke.)"""
    profile.emergency_paused = req.paused
    if _runtime_db:
        from .runtime_store import save_pause_flag

        save_pause_flag(_runtime_store, req.paused)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="emergency_pause",
            status="paused" if req.paused else "resumed",
            result=req.reason,
        )
    )
    return {"paused": profile.emergency_paused}


@app.get("/audit")
def get_audit(event_type: str | None = None, limit: int = 200):
    """Audit trail, oldest first, as the uniform page envelope.

    Core events are drained INTO the persistent audit list first (draining
    and only returning them used to lose them after one read). Transport
    auth events are merged in by timestamp. ``limit`` keeps the newest N
    matching events; ``count`` is the total number that matched."""
    audit.extend(core.drain_audit())
    events = sorted([*audit, *sessions.audit], key=lambda e: e.timestamp)
    if event_type:
        events = [e for e in events if e.event_type == event_type]
    limit = max(1, min(limit, 1000))
    page = _page(events[-limit:])
    page["count"] = len(events)
    return page


@app.get("/model/providers")
def model_providers():
    return model_config.safe_summary()


@app.get("/providers")
def providers_status():
    gpt = credentials.get(CHATGPT_PLAN) or {}
    cc_settings = credentials.get("_claude_code") or {}
    return {
        "active_provider": active_provider(),
        "providers": credentials.status(),
        "subscriptions": {
            CHATGPT_PLAN: {
                "label": "ChatGPT plan (Plus or Pro)",
                "connected": gpt.get("type") == "chatgpt_plan",
                "email": gpt.get("email"),
                "plan_usage": bool(gpt.get("plan_usage")),
                "model": gpt.get("model"),
                "manage_usage_url": MANAGE_USAGE_URL,
                "note": (
                    "Eligible requests use the usage included in your ChatGPT Plus or Pro plan. "
                    "Sign-in happens on OpenAI's site; Shadow stores the resulting token only on this "
                    "node and never sees your ChatGPT password or conversations. Requests count toward "
                    "your plan's limits (for Plus, the same 5-hour limit you use in ChatGPT). You can cap "
                    "or revoke Shadow's access anytime in ChatGPT Settings, Usage."
                ),
            },
            CLAUDE_CODE: {
                "label": "Your Claude Code (experimental)",
                "enabled": _claude_code_enabled(),
                "acknowledged_at": cc_settings.get("acknowledged_at"),
                "detected": claude_code.detect() if cc_settings.get("enabled") else None,
                "disabled_by_operator": claude_code.killed(),
                "disclosure": claude_code.DISCLOSURE,
            },
            "gemini": {
                "note": (
                    "Shadow uses Gemini with an API key from Google AI Studio. Google's terms prohibit "
                    "third-party apps from using Gemini CLI or Google AI subscription sign-ins, so "
                    "Shadow does not offer that option."
                ),
            },
        },
    }


class ActiveProviderRequest(BaseModel):
    provider: str


@app.post("/providers/active")
def set_active_provider(req: ActiveProviderRequest):
    """Choose where cloud-approved asks go. Only connected providers (or the
    on-device placeholder) can be selected."""
    p = req.provider
    usable = (
        p == "local_mock"
        or (p == CHATGPT_PLAN and (credentials.get(CHATGPT_PLAN) or {}).get("type") == "chatgpt_plan")
        or (p == CLAUDE_CODE and _claude_code_enabled())
        or (p in CATALOG and credentials.resolve(p) is not None)
    )
    if not usable:
        raise HTTPException(409, f"{p} isn't connected")
    credentials.set("_active", {"provider": p})
    audit.append(AuditEvent(actor="user", event_type="provider_activated", data_used=[p], status="ok"))
    return {"active_provider": p}


class ChatGPTSignInRequest(BaseModel):
    # Port the node is reachable on from the browser doing the sign-in. The
    # redirect is always http://127.0.0.1:<port>/auth/callback (SIWC rule).
    port: int | None = None
    # Dashboard origin to return to after sign-in (loopback origins only).
    return_to: str | None = None


@app.post("/providers/chatgpt_plan/signin")
def chatgpt_signin_start(req: ChatGPTSignInRequest, request: Request):
    """Start "Continue with ChatGPT". The browser doing the sign-in must be
    on this computer: OpenAI only redirects to a 127.0.0.1 loopback."""
    port = req.port or request.url.port or 8787
    start = chatgpt_auth.start(port, getattr(request.state, "device_id", None), req.return_to)
    audit.append(AuditEvent(actor="user", event_type="chatgpt_signin_started", status="pending"))
    return {"authorization_url": start["authorization_url"], "redirect_uri": start["redirect_uri"]}


@app.get("/auth/callback", include_in_schema=False)
def chatgpt_signin_callback(request: Request):
    """Loopback redirect target. Unauthenticated by necessity (the browser
    arrives from OpenAI), so it is bound to the single-use state value."""
    q = request.query_params
    ok, message, back = False, "", "/"
    if q.get("error"):
        message = "Sign-in was cancelled." if q.get("error") == "access_denied" else "Sign-in failed."
    elif not q.get("state") or not q.get("code"):
        message = "This page needs a sign-in response from OpenAI."
    else:
        try:
            info = chatgpt_auth.complete(q["state"], q["code"], q.get("client_id"), q.get("scope"))
            ok = True
            back = info.get("return_to") or "/"
            message = (
                "You're using your ChatGPT plan. Shadow will use the usage included in your ChatGPT plan."
                if info["plan_usage"]
                else "Signed in, but plan usage wasn't granted. Sign in again and allow it, or use an API key."
            )
            audit.append(AuditEvent(actor="user", event_type="chatgpt_signin_completed", status="connected",
                                    metadata={"plan_usage": info["plan_usage"]}))
        except ChatGPTPlanError as e:
            message = str(e)
        except httpx.HTTPError:
            message = "Couldn't reach OpenAI to finish signing in. Try again."
    import html as _html
    status = "Connected" if ok else "Not connected"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{status} · Shadow</title><link rel="stylesheet" href="/web/styles.css"></head>
<body><main class="connect"><div class="card"><h1>{status}</h1><p class="sub">{_html.escape(message)}</p>
<p><a class="btn" href="{_html.escape(back.rstrip('/'))}/#/models">Back to Shadow</a></p></div></main></body></html>"""
    return Response(page, media_type="text/html",
                    headers={"Content-Security-Policy": DASHBOARD_CSP, "Cache-Control": "no-store"})


@app.get("/providers/chatgpt_plan/models")
def chatgpt_models():
    try:
        return _page(chatgpt_auth.models())
    except ChatGPTPlanError as e:
        raise HTTPException(409, str(e))


class ModelChoiceRequest(BaseModel):
    model: str


@app.put("/providers/chatgpt_plan/model")
def chatgpt_set_model(req: ModelChoiceRequest):
    cred = credentials.get(CHATGPT_PLAN) or {}
    if cred.get("type") != "chatgpt_plan":
        raise HTTPException(409, "ChatGPT isn't connected")
    cred["model"] = req.model
    credentials.set(CHATGPT_PLAN, cred)
    return {"model": req.model}


def chatgpt_sign_out():
    res = chatgpt_auth.sign_out()
    if active_provider() == CHATGPT_PLAN:
        credentials.delete("_active")
    audit.append(AuditEvent(actor="user", event_type="chatgpt_signed_out", status="disconnected",
                            metadata={"remote_revocation_confirmed": res["revoked"]}))
    return {"connected": False, "remote_revocation_confirmed": res["revoked"]}


class ClaudeCodeEnableRequest(BaseModel):
    acknowledge: bool = False


@app.post("/providers/claude_code/enable")
def claude_code_enable(req: ClaudeCodeEnableRequest):
    """Opt in to the experimental Claude Code delegate. Requires explicit
    acknowledgement of the disclosure; refused when the operator disabled it."""
    if claude_code.killed():
        raise HTTPException(403, "Claude Code is disabled on this node")
    if not req.acknowledge:
        raise HTTPException(400, "acknowledge the disclosure to enable this")
    found = claude_code.detect()
    if not found.get("available"):
        raise HTTPException(409, found.get("reason", "Claude Code isn't available"))
    credentials.set("_claude_code", {"enabled": True, "acknowledged_at": time.time()})
    audit.append(AuditEvent(actor="user", event_type="claude_code_enabled", status="ok",
                            metadata={"version": found.get("version")}))
    return {"enabled": True, **found}


def claude_code_disable():
    credentials.delete("_claude_code")
    if active_provider() == CLAUDE_CODE:
        credentials.delete("_active")
    audit.append(AuditEvent(actor="user", event_type="claude_code_disabled", status="ok"))
    return {"enabled": False}


@app.post("/providers/{name}/connect")
def provider_connect(name: str, req: ProviderConnectRequest):
    if name not in CATALOG:
        raise HTTPException(404, "unknown provider")
    if not req.api_key:
        raise HTTPException(400, "api_key required")
    credentials.set(
        name, {"type": "api_key", "api_key": req.api_key, "source": "stored"}
    )
    audit.append(
        AuditEvent(
            actor="user",
            event_type="provider_connected",
            data_used=[name],
            status="connected",
        )
    )
    return {"connected": True, "provider": name}


@app.delete("/providers/{name}")
def provider_disconnect(name: str):
    # Subscription providers have their own teardown (remote revocation,
    # opt-out); never just drop their tokens.
    if name == CHATGPT_PLAN:
        return chatgpt_sign_out()
    if name == CLAUDE_CODE:
        return claude_code_disable()
    if name not in CATALOG:
        raise HTTPException(404, "unknown provider")
    if active_provider() == name:
        credentials.delete("_active")
    credentials.delete(name)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="provider_disconnected",
            data_used=[name],
            status="disconnected",
        )
    )
    return {"connected": False, "provider": name}


@app.get("/providers/{name}/oauth/start")
def provider_oauth_start(name: str, redirect_uri: str, request: Request):
    device_id = request.headers.get("x-shadow-device-id")
    try:
        return provider_auth.start_oauth(name, redirect_uri, device_id, oauth_txns)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/providers/{name}/oauth/exchange")
def provider_oauth_exchange(name: str, req: OAuthExchangeRequest, request: Request):
    device_id = request.headers.get("x-shadow-device-id")
    try:
        cred = provider_auth.exchange_code(
            name, req.state, req.code, device_id, oauth_txns
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"token exchange failed: {e}")
    credentials.set(name, cred)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="provider_oauth_connected",
            data_used=[name],
            status="connected",
        )
    )
    return {"connected": True, "provider": name, "type": "oauth"}


# --- Accounts hub (Hark item 5): uniform directory of services the node can
# act through. Delegates to the same encrypted CredentialStore as /providers;
# rows never carry secret values. Disconnect is irreversible and requires
# explicit confirm=true.


@app.get("/accounts")
def accounts_list():
    return {
        "accounts": [row.model_dump() for row in accounts.list_accounts(credentials)]
    }


@app.get("/accounts/{service_id}")
def account_detail(service_id: str):
    row = accounts.get_account(credentials, service_id)
    if row is None:
        raise HTTPException(404, "unknown service")
    return row.model_dump()


@app.post("/accounts/{service_id}/connect")
def account_connect(service_id: str, req: ProviderConnectRequest):
    if service_id not in accounts.service_ids():
        raise HTTPException(404, "unknown service")
    if not req.api_key:
        raise HTTPException(400, "api_key required")
    accounts.connect_account(credentials, service_id, req.api_key)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="account_connected",
            data_used=[service_id],
            status="connected",
        )
    )
    return {"connected": True, "service": service_id}


@app.post("/accounts/{service_id}/disconnect")
def account_disconnect(service_id: str, confirm: bool = False):
    if service_id not in accounts.service_ids():
        raise HTTPException(404, "unknown service")
    if not confirm:
        raise HTTPException(409, "disconnect requires confirm=true")
    accounts.disconnect_account(credentials, service_id)
    audit.append(
        AuditEvent(
            actor="user",
            event_type="account_disconnected",
            data_used=[service_id],
            status="disconnected",
        )
    )
    return {"connected": False, "service": service_id}


@app.get("/tools")
def tools():
    return {
        "tools": action_executor.names(),
        "tool_metadata": action_executor.tool_metadata(),
        "ghost_mode": ghost.mode,
        "workspace": os.getenv("SHADOW_WORKSPACE_DIR", "data/workspace"),
        "consent_required_tools": list(action_executor.CONSENT_REQUIRED),
    }


@app.post("/approvals/sweep")
def sweep_approvals():
    """Expire pending approvals past their expiry threshold."""
    expired_ids = core.approvals.sweep_expired()
    for rid in expired_ids:
        audit.append(
            AuditEvent(
                actor="system",
                event_type="approval_expired",
                status="expired",
                metadata={"approval_id": rid},
            )
        )
    return {
        "expired": expired_ids,
        "remaining_pending": len(
            [
                r
                for r in core.approvals.requests.values()
                if r.status == ApprovalStatus.PENDING
            ]
        ),
    }


@app.websocket("/ws/tasks")
async def ws_tasks(ws: WebSocket):
    # The HTTP auth middleware does not run for websocket routes, so the
    # handshake is verified here with the same HMAC scheme (signed
    # GET /ws/tasks, headers only: browsers cannot set them, native
    # clients can). Rejected before accept with a 4401 close.
    if AUTH_REQUIRED:
        h = ws.headers
        try:
            version = int(h.get("x-shadow-signature-version") or "1")
        except ValueError:
            version = 0
        ok, reason = sessions.verify(
            h.get("x-shadow-device-id"),
            h.get("x-shadow-signature"),
            h.get("x-shadow-nonce"),
            h.get("x-shadow-timestamp"),
            "GET",
            _signed_path(ws.scope, version),
            hashlib.sha256(b"").hexdigest() if version == 2 else "",
            query=ws.url.query,
            version=version,
        )
        if not ok:
            audit.append(
                AuditEvent(
                    actor="transport",
                    event_type="ws_auth_failed",
                    status="blocked",
                    result=reason,
                    metadata={"device_id": h.get("x-shadow-device-id")},
                )
            )
            await ws.close(code=4401, reason=reason)
            return
    await ws.accept()
    await ws.send_json({"type": "hello", "node": "shadow-node", "version": APP_VERSION})
    try:
        while True:
            data = await ws.receive_json()
            await ws.send_json({"type": "ack", "received": data})
    except WebSocketDisconnect:
        pass
