import os, time, json, socket, ipaddress
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin
import httpx
from pydantic import BaseModel

from .skills import SkillRegistry, build_default_registry
from .untrusted import fence_content
from .web_search import web_search as _web_search


# --- SSRF-hardened fetching -------------------------------------------------
# Every redirect hop is validated independently: scheme, embedded
# credentials, port, and ALL DNS resolutions (rebinding-safe: resolved
# immediately before the request, and every returned address must be
# globally routable). No proxies are honored, so a proxy cannot be used
# to smuggle requests to internal hosts.

SSRF_ALLOWED_PORTS = {80, 443}
SSRF_MAX_REDIRECTS = 5
SSRF_MAX_BODY_BYTES = 1 << 20  # 1 MiB


def _resolve_public_ips(host: str) -> list[str]:
    """Resolve ALL addresses for a host (IPv4 and IPv6); every one must be
    globally routable. Fails closed on resolution errors or any non-public
    address, which also defeats simple DNS-rebinding setups that mix a
    public first answer with private alternates."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError(f"could not resolve host {host!r}") from e
    ips = sorted({info[4][0] for info in infos})
    if not ips:
        raise ValueError(f"host {host!r} resolved to no addresses")
    for ip_str in ips:
        ip = ipaddress.ip_address(ip_str)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"blocked non-public address for {host!r}: {ip_str}")
    return ips


def _validate_http_hop(url: str) -> str:
    """Validate one redirect hop and return the normalized URL. Raises
    ValueError on anything that must not be fetched."""
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise ValueError("only http/https URLs are allowed")
    if u.username or u.password:
        raise ValueError("credentials embedded in URLs are not allowed")
    host = u.hostname
    if not host:
        raise ValueError("missing host")
    try:
        port = u.port
    except ValueError as e:
        raise ValueError("invalid port in URL") from e
    if port is None:
        port = 443 if u.scheme == "https" else 80
    if port not in SSRF_ALLOWED_PORTS:
        raise ValueError(f"blocked port {port}: only 80/443 are allowed")
    _resolve_public_ips(host)
    return u.geturl()


def _ssrf_fetch(url: str, timeout: float = 15, client=None):
    """Fetch a URL with SSRF hardening.

    No automatic redirects: each hop is re-validated (scheme, host, port,
    all DNS resolutions public) right before connecting, so a redirect
    cannot hop to an internal address and a rebinding hostname cannot
    slip a private address past an earlier check. Proxies are disabled
    (trust_env=False). Bodies are capped at SSRF_MAX_BODY_BYTES.

    Returns (body_text, status_code, content_type, final_url).
    ``client`` is an injection point for tests (must support .stream()).
    """
    own_client = client is None
    c = client if client is not None else httpx.Client(trust_env=False, timeout=timeout)
    try:
        current = url
        for _ in range(SSRF_MAX_REDIRECTS + 1):
            target = _validate_http_hop(current)
            with c.stream("GET", target, follow_redirects=False) as r:
                if r.is_redirect:
                    location = r.headers.get("location")
                    if not location:
                        raise ValueError("redirect without a location header")
                    current = urljoin(target, location)
                    continue
                chunks, total = [], 0
                for chunk in r.iter_bytes(65536):
                    if total + len(chunk) > SSRF_MAX_BODY_BYTES:
                        chunks.append(chunk[: SSRF_MAX_BODY_BYTES - total])
                        total = SSRF_MAX_BODY_BYTES
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                body = b"".join(chunks).decode("utf-8", errors="replace")
                return body, r.status_code, r.headers.get("content-type", ""), target
        raise ValueError("too many redirects")
    finally:
        if own_client:
            c.close()


def workspace_dir() -> Path:
    p = Path(os.getenv("SHADOW_WORKSPACE_DIR", "data/workspace"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _note_path(name: str) -> Path:
    safe = "".join(c for c in str(name) if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "-").lower()
    return workspace_dir() / f"{safe or 'untitled'}.md"


class LocalActionExecutor:
    """Performs real, sandboxed local actions.

    No shell, no arbitrary filesystem access: file actions are confined to the
    workspace directory and network actions are restricted to public http(s)
    hosts (SSRF-guarded). This is the real execution backend behind the
    approval gate.
    """

    # Tools requiring per-tool consent beyond the global approval gate.
    CONSENT_REQUIRED = {"calendar.create", "email.draft"}

    def __init__(self):
        self.handlers = {
            "note.create": self.note_create,
            "note.append": self.note_append,
            "note.list": self.note_list,
            "reminder.create": self.reminder_create,
            "calendar.create": self.calendar_create,
            "email.draft": self.email_draft,
            "http.get": self.http_get,
            "web.search": self.web_search,
        }
        self.skills: SkillRegistry = build_default_registry(self)

    def tool_metadata(self) -> list[dict]:
        """Return metadata for each tool, including consent requirements."""
        return [
            {
                "name": name,
                "needs_explicit_consent": name in self.CONSENT_REQUIRED,
                "description": getattr(handler, "__doc__", ""),
            }
            for name, handler in sorted(self.handlers.items())
        ]

    def names(self) -> list[str]:
        return sorted(self.handlers)

    def run(self, tool: str, params: dict | None, explicit_consent: bool = False) -> dict:
        if tool not in self.handlers:
            raise KeyError(f"unknown tool: {tool}")
        if tool in self.CONSENT_REQUIRED and not explicit_consent:
            return {"ok": False, "reason": "explicit_consent_required", "action": tool}
        return self.handlers[tool](params or {})

    # --- notes ---
    def note_create(self, p: dict) -> dict:
        title = p.get("title", "Untitled")
        path = _note_path(title)
        path.write_text(f"# {title}\n\n{p.get('body', '')}\n", encoding="utf-8")
        return {"ok": True, "action": "note.create", "path": str(path), "bytes": path.stat().st_size}

    def note_append(self, p: dict) -> dict:
        path = _note_path(p.get("title", "Untitled"))
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n{p.get('body', '')}\n")
        return {"ok": True, "action": "note.append", "path": str(path), "bytes": path.stat().st_size}

    def note_list(self, p: dict) -> dict:
        return {"ok": True, "action": "note.list", "notes": sorted(f.name for f in workspace_dir().glob("*.md"))}

    # --- reminders ---
    def reminder_create(self, p: dict) -> dict:
        rec = {"text": p.get("text", ""), "when": p.get("when"), "created_at": datetime.now(timezone.utc).isoformat()}
        with (workspace_dir() / "reminders.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return {"ok": True, "action": "reminder.create", "reminder": rec}

    # --- calendar ---
    def calendar_create(self, p: dict) -> dict:
        """Create a calendar event. Saved as JSONL in the workspace."""
        rec = {
            "title": p.get("title", ""),
            "start": p.get("start"),
            "end": p.get("end"),
            "description": p.get("description", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with (workspace_dir() / "calendar_events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return {"ok": True, "action": "calendar.create", "event": rec}

    # --- email ---
    def email_draft(self, p: dict) -> dict:
        """Draft an email message. Saved as a Markdown file in the workspace."""
        title = p.get("subject", "Draft Email")
        safe = "".join(c for c in str(title) if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "-").lower()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        path = workspace_dir() / "drafts" / f"{safe or 'draft'}-{stamp}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        body = p.get("body", "")
        content = f"""# Draft: {title}

**To:** {p.get("to", "")}
**Subject:** {title}

---

{body}
"""
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "action": "email.draft", "path": str(path), "bytes": path.stat().st_size}

    # --- network ---
    def http_get(self, p: dict) -> dict:
        """Fetch a public URL. The body is fenced as untrusted web data.

        SSRF-hardened: redirects are followed manually with each hop
        re-validated (scheme, credentials, port 80/443 only, all DNS
        resolutions globally routable), proxies are disabled, and the
        body is capped."""
        url = p.get("url", "")
        body, status, content_type, final_url = _ssrf_fetch(url)
        return {
            "ok": True, "action": "http.get", "url": final_url, "status": status,
            "content_type": content_type,
            "body": fence_content(body[:2000], source="web"),
        }

    def web_search(self, p: dict) -> dict:
        """Search the web via a SearXNG instance. Results are fenced as untrusted."""
        return _web_search(p.get("query", ""), max_results=int(p.get("max_results", 10) or 10))


class GhostTaskIR(BaseModel):
    objective: str
    steps: list[dict]
    safety_profile: str = "approval_gated"
    sandbox: str = "local_user_boundary"
    timeout_seconds: int = 30


class GhostAdapter:
    """Translates approved plans into the GHOST task IR and executes them.

    - ``mock`` mode simulates execution (used in tests / dry-runs).
    - ``local`` mode runs the real :class:`LocalActionExecutor` over each step.
    """

    def __init__(self, mode: str | None = None):
        self.mode = mode or os.getenv("GHOST_RUNTIME_MODE", "mock")
        self.executor = LocalActionExecutor()

    def to_ir(self, plan) -> GhostTaskIR:
        return GhostTaskIR(
            objective=plan.user_intent,
            steps=[{"tool": a.tool_name, "risk": str(getattr(a, "risk", "low")), "description": a.description, "params": getattr(a, "params", {})} for a in plan.actions],
        )

    def execute(self, ir: GhostTaskIR, approved: bool = False) -> dict:
        if not approved:
            return {"status": "approval_required", "ir": ir.model_dump(), "mode": self.mode}
        start = time.time()
        if self.mode == "mock":
            return {"status": "mock_executed", "backend": "safe-local-mock", "duration_ms": int((time.time() - start) * 1000), "telemetry": {"steps": len(ir.steps)}, "ir": ir.model_dump()}
        results = []
        for step in ir.steps:
            tool = step.get("tool", "")
            try:
                results.append({"tool": tool, "result": self.executor.run(tool, step.get("params", {}), explicit_consent=approved)})
            except KeyError:
                results.append({"tool": tool, "skipped": "no real handler for this tool", "description": step.get("description", "")})
            except Exception as e:
                results.append({"tool": tool, "error": str(e)})
        executed = sum(1 for r in results if "result" in r)
        return {
            "status": "executed" if executed else "no_op",
            "backend": "ghost-local-adapter",
            "duration_ms": int((time.time() - start) * 1000),
            "telemetry": {"steps": len(ir.steps), "executed": executed},
            "results": results,
            "ir": ir.model_dump(),
        }


# Retained seams for compatibility; the real behavior lives in LocalActionExecutor.
class DesktopActionAdapter:
    def __init__(self): self.executor = LocalActionExecutor()
    def run(self, tool: str, params: dict | None = None, explicit_consent: bool = False): return self.executor.run(tool, params, explicit_consent=explicit_consent)
class ExecutionPolicyAdapter: pass
class SafetyProfileAdapter: pass
class TelemetryAdapter: pass
