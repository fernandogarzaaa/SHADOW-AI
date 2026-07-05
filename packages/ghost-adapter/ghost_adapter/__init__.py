import os, time, json, socket, ipaddress
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import httpx
from pydantic import BaseModel


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
        }

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

    def run(self, tool: str, params: dict | None) -> dict:
        if tool not in self.handlers:
            raise KeyError(f"unknown tool: {tool}")
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
        path = workspace_dir() / "drafts" / f"{safe or 'draft'}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        body = p.get("body", "")
        content = f"""# Draft: {title}

**To:** {p.get("to", "")}
**Subject:** {p.get("subject", "")}

---

{body}
"""
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "action": "email.draft", "path": str(path), "bytes": path.stat().st_size}

    # --- network ---
    def http_get(self, p: dict) -> dict:
        url = p.get("url", "")
        self._guard_url(url)
        r = httpx.get(url, timeout=15, follow_redirects=True)
        return {
            "ok": True, "action": "http.get", "url": url, "status": r.status_code,
            "content_type": r.headers.get("content-type", ""), "body": r.text[:2000],
        }

    @staticmethod
    def _guard_url(url: str) -> None:
        u = urlparse(url)
        if u.scheme not in ("http", "https"):
            raise ValueError("only http/https URLs are allowed")
        host = u.hostname
        if not host:
            raise ValueError("missing host")
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(host))
        except socket.gaierror as e:
            raise ValueError("could not resolve host") from e
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("blocked non-public address")


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
                results.append({"tool": tool, "result": self.executor.run(tool, step.get("params", {}))})
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
    def run(self, tool: str, params: dict | None = None): return self.executor.run(tool, params)
class ExecutionPolicyAdapter: pass
class SafetyProfileAdapter: pass
class TelemetryAdapter: pass
