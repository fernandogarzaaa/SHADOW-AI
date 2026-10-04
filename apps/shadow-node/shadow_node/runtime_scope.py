"""Runtime scope guard for the Shadow Node HTTP surface.

Adapted from OpenDots' runtime scope validation (``src/server/runtime-scope.ts``,
MIT (c) Atai Barkai). OpenDots guards its CopilotKit runtime routes with an
explicit (path, method) allowlist plus strict ID validation, because the SDK
router underneath is permissive (suffix matching). The Shadow Node uses
FastAPI, whose router is strict by construction, so this guard is
defense-in-depth aimed at the residual risks:

1. A future route registration that is more permissive than intended (e.g. a
   stray GET on an execution endpoint) is rejected even though the framework
   would allow it: the allowlist below is the explicit contract.
2. Path-parameter IDs are confined to a safe charset (no ``/``, ``\\``,
   whitespace, ``..``, or control characters), so a smuggled ID can never
   become a key-confusion or traversal vector in the runtime DB.
3. When the same logical ID appears in both the path and the query string,
   the values must agree (OpenDots cross-checks path/body/query the same way).

The allowlist is data, not code. ``tests/test_runtime_scope.py`` asserts it
stays in sync with the real route table in both directions: every scoped
route+method must be listed, and nothing listed may be phantom.
"""
from __future__ import annotations

import re
from typing import Mapping

#: IDs may start with an alphanumeric and then contain alphanumerics plus
#: ``.``, ``_``, ``:``, ``-``. In particular: no ``/``, ``\\``, whitespace,
#: ``..`` segments, or control characters. Covers ``{prefix}_{uuid4hex}``
#: server IDs, UUIDs, and provider names.
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class RuntimeScopeError(ValueError):
    """A request fell outside the runtime scope contract."""


#: Explicit (route template -> allowed methods) contract for the sensitive
#: route families: agent execution, approvals, artifacts, devices, memory,
#: providers, pairing, claims, goals, ideas, reminders, media, ambient, and
#: the persona endpoint. Anything not listed here but under these families is
#: denied; routes outside these families are left to the framework router.
SCOPED_ROUTES: dict[str, frozenset[str]] = {
    # agent
    "/agent/ask": frozenset({"POST"}),
    "/agent/ask_stream": frozenset({"POST"}),
    "/agent/execute": frozenset({"POST"}),
    "/agent/plan": frozenset({"POST"}),
    "/agent/self": frozenset({"GET"}),
    "/agent/sessions": frozenset({"GET", "POST"}),
    "/agent/sessions/{session_id}": frozenset({"GET"}),
    "/agent/sessions/{session_id}/close": frozenset({"POST"}),
    "/agent/stream": frozenset({"GET"}),
    # ambient
    "/ambient/acts": frozenset({"GET"}),
    "/ambient/acts/run": frozenset({"POST"}),
    "/ambient/config": frozenset({"POST"}),
    "/ambient/runs": frozenset({"GET"}),
    "/ambient/runs/{run_id}": frozenset({"GET"}),
    "/ambient/status": frozenset({"GET"}),
    "/ambient/tick": frozenset({"POST"}),
    "/ambient/wake": frozenset({"POST"}),
    # approvals
    "/approvals": frozenset({"GET", "POST"}),
    "/approvals/receipt": frozenset({"GET"}),
    "/approvals/sweep": frozenset({"POST"}),
    "/approvals/{id}/approve": frozenset({"POST"}),
    "/approvals/{id}/deny": frozenset({"POST"}),
    # artifacts
    "/artifacts": frozenset({"GET", "POST"}),
    "/artifacts/{artifact_id}": frozenset({"GET", "PATCH", "DELETE"}),
    "/artifacts/{artifact_id}/versions": frozenset({"GET"}),
    "/artifacts/{artifact_id}/versions/{version}": frozenset({"GET"}),
    # claims
    "/claims": frozenset({"GET", "POST"}),
    "/claims/{claim_id}/confirm": frozenset({"POST"}),
    "/claims/{claim_id}/refute": frozenset({"POST"}),
    # consent
    "/consent": frozenset({"POST"}),
    # devices + pairing
    "/devices": frozenset({"GET"}),
    "/devices/register": frozenset({"POST"}),
    "/devices/{device_id}/push-token": frozenset({"POST"}),
    "/devices/{device_id}/revoke": frozenset({"POST"}),
    "/pair/start": frozenset({"POST"}),
    "/pair/confirm": frozenset({"POST"}),
    "/pair/approve": frozenset({"POST"}),
    # goals
    "/goals": frozenset({"GET", "POST"}),
    "/goals/briefing": frozenset({"GET"}),
    "/goals/{goal_id}": frozenset({"GET", "PATCH", "DELETE"}),
    "/goals/{goal_id}/progress": frozenset({"POST"}),
    # ideas
    "/ideas": frozenset({"GET", "POST"}),
    "/ideas/{idea_id}": frozenset({"GET", "PATCH", "DELETE"}),
    "/ideas/{idea_id}/run": frozenset({"POST"}),
    # media
    "/media": frozenset({"GET"}),
    "/media/capabilities": frozenset({"GET"}),
    "/media/generate": frozenset({"POST"}),
    "/media/{item_id}": frozenset({"DELETE"}),
    "/media/{item_id}/content": frozenset({"GET"}),
    # memory
    "/memory": frozenset({"GET"}),
    "/memory/export": frozenset({"GET"}),
    "/memory/ingest": frozenset({"POST"}),
    "/memory/ingest_file": frozenset({"POST"}),
    "/memory/recent": frozenset({"GET"}),
    "/memory/search": frozenset({"GET"}),
    "/memory/source/{source_id}": frozenset({"DELETE"}),
    "/memory/{item_id}": frozenset({"DELETE"}),
    # providers
    "/providers": frozenset({"GET"}),
    "/providers/{name}": frozenset({"DELETE"}),
    "/providers/{name}/connect": frozenset({"POST"}),
    "/providers/{name}/oauth/exchange": frozenset({"POST"}),
    "/providers/{name}/oauth/start": frozenset({"GET"}),
    # reminders
    "/reminders": frozenset({"GET", "POST"}),
    "/reminders/check": frozenset({"POST"}),
    "/reminders/due": frozenset({"GET"}),
    "/reminders/{reminder_id}": frozenset({"GET", "PATCH", "DELETE"}),
    # persona
    "/persona": frozenset({"GET", "PUT"}),
}


def _template_to_regex(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}]+\})", template)
    out = []
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            out.append(f"(?P<{part[1:-1]}>[^/]+)")
        else:
            out.append(re.escape(part))
    return re.compile("^" + "".join(out) + "$")


_SCOPED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (t, _template_to_regex(t)) for t in SCOPED_ROUTES
]


def check_runtime_scope(
    method: str,
    path: str,
    query_params: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    """Validate one request against the runtime scope contract.

    Returns the extracted path params when ``path`` matches a scoped route
    template, or ``None`` when the path is outside the scoped families (the
    framework router owns those). Raises :class:`RuntimeScopeError` when a
    scoped path uses a disallowed method, carries a malformed ID, or has a
    path/query ID disagreement.
    """
    for template, pattern in _SCOPED_PATTERNS:
        m = pattern.match(path)
        if not m:
            continue
        if method.upper() not in SCOPED_ROUTES[template]:
            raise RuntimeScopeError(
                f"method {method.upper()} not allowed for {template}"
            )
        params = {k: v for k, v in m.groupdict().items()}
        for name, value in params.items():
            if not SAFE_ID_RE.match(value):
                raise RuntimeScopeError(
                    f"malformed id in path parameter {name!r}"
                )
        for name, value in params.items():
            qv = (query_params or {}).get(name)
            if qv is not None and qv != value:
                raise RuntimeScopeError(
                    f"path/query disagreement for {name!r}"
                )
        return params
    return None
