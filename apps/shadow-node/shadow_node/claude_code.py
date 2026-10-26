"""Experimental: run requests through the user's own Claude Code.

Anthropic does not permit third-party apps to offer a Claude sign-in or to
collect, store or intermediate Claude.ai credentials. What its terms do not
prevent is an end user signing in to the unmodified Claude Code binary and
using it with their own subscription (`claude -p`). This module only ever
launches that binary as a local subprocess for the same user:

- Shadow never reads the Keychain, ~/.claude/.credentials.json, or a
  setup-token, and never ships Claude Code itself.
- Credentials that would override the subscription (ANTHROPIC_API_KEY,
  ANTHROPIC_AUTH_TOKEN, CLAUDE_CODE_OAUTH_TOKEN) are removed from the
  child environment.
- It runs in an empty, Shadow-owned working directory with no MCP servers
  and no Shadow tools, for user-initiated requests only (never ambient).
- It is off by default, needs an explicit acknowledgement of the risk, and
  has a kill switch (SHADOW_DISABLE_CLAUDE_CODE=true) so a policy change
  means flipping a flag, not shipping an update.

Policy can change without notice: see docs/research/subscription-auth-2026-10.md.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .crypto_config import data_dir

PROVIDER = "claude_code"
STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL")
TIMEOUT_SECONDS = 240

DISCLOSURE = (
    "Experimental: run requests through your own Claude Code. Shadow will start the Claude Code "
    "program you installed and signed in to on this computer, and pass your request to it. Shadow "
    "never sees or stores your Claude login. Anthropic's terms say subscription plans are designed "
    "for ordinary, individual use of Anthropic's own apps, and Anthropic may bill third-party use to "
    "paid usage credits, limit it, or act on accounts without notice. Use this only for your own "
    "personal requests on your own machine. For guaranteed, policy-clear access, use an Anthropic "
    "API key instead."
)


class ClaudeCodeError(RuntimeError):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


def killed() -> bool:
    return os.getenv("SHADOW_DISABLE_CLAUDE_CODE", "false").lower() == "true"


def binary() -> str | None:
    return os.getenv("SHADOW_CLAUDE_BIN") or shutil.which("claude")


def workdir() -> Path:
    p = data_dir() / "claude-code-sandbox"
    p.mkdir(parents=True, exist_ok=True)
    return p


def child_env() -> dict:
    """The node's environment minus anything that would override the user's
    own sign-in or change how Claude Code runs: Anthropic credentials and
    endpoints, and inherited Claude Code session variables (a node started
    from a Claude Code terminal carries CLAUDE_CODE_* / CLAUDECODE)."""
    return {
        k: v for k, v in os.environ.items()
        if k not in STRIP_ENV and not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_", "CLAUDECODE"))
    }


def detect() -> dict:
    """Is a Claude Code binary installed? (Does not run a model request.)"""
    path = binary()
    if killed():
        return {"available": False, "reason": "disabled by the node operator"}
    if not path:
        return {"available": False, "reason": "Claude Code isn't installed on this computer"}
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15,
                             env=child_env(), cwd=workdir())
        version = (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else ""
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "Claude Code didn't respond"}
    m = re.search(r"\d+\.\d+\.\d+", version)
    return {"available": True, "path": path, "version": m.group(0) if m else version}


class ClaudeCodeProvider:
    """complete() via `claude -p` in headless JSON mode."""

    name = PROVIDER
    cloud = True

    def __init__(self, system_prompt: str = "", timeout: int = TIMEOUT_SECONDS):
        self.system_prompt = system_prompt
        self.timeout = timeout

    def complete(self, prompt: str, context: str = "") -> str:
        if killed():
            raise ClaudeCodeError("Claude Code is disabled on this node.", "disabled")
        path = binary()
        if not path:
            raise ClaudeCodeError("Claude Code isn't installed on this computer.", "not_installed")
        from .persona import get_system_prompt

        request = f"<untrusted_context>\n{context}\n</untrusted_context>\n\nUser request: {prompt}"
        args = [
            path, "-p", request,
            "--output-format", "json",
            "--append-system-prompt", self.system_prompt or get_system_prompt(),
            # Answer only: no file edits, shell, or web from this delegate.
            "--disallowedTools", "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch",
        ]
        try:
            out = subprocess.run(args, capture_output=True, text=True, timeout=self.timeout,
                                 env=child_env(), cwd=workdir(), stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as e:
            raise ClaudeCodeError("Claude Code took too long to answer.", "timeout") from e
        except OSError as e:
            raise ClaudeCodeError("Claude Code couldn't be started.", "spawn_failed") from e
        try:
            payload = json.loads(out.stdout or "{}")
        except ValueError:
            payload = {}
        if out.returncode != 0 or payload.get("is_error"):
            text = (payload.get("result") or out.stderr or "").strip()
            low = text.lower()
            if "log in" in low or "login" in low or "authenticate" in low:
                raise ClaudeCodeError("Claude Code isn't signed in. Run `claude` in a terminal and sign in, then try again.",
                                      "not_signed_in")
            if "limit" in low:
                raise ClaudeCodeError("Your Claude plan's usage limit was reached.", "usage_limit")
            raise ClaudeCodeError("Claude Code couldn't answer.", "failed")
        result = (payload.get("result") or "").strip()
        if not result:
            raise ClaudeCodeError("Claude Code returned an empty answer.", "empty")
        return result
