"""Free private web search through a SearXNG instance.

Adapted from GHOST-Chimera's ``ghostchimera.tool_layer.web_search``.

SearXNG aggregates public search engines without accounts or API keys, so it
is the no-cost research backend: point it at a locally provisioned instance
and queries never leave the operator's control. Result content is fenced as
untrusted web data (see :mod:`ghost_adapter.untrusted`) before any model or
UI consumes it.

Security posture
----------------
* The only host ever contacted is the operator-configured SearXNG base URL
  (``SHADOW_SEARXNG_URL``, default ``http://127.0.0.1:8080``). Result URLs
  are listed, never fetched, so there is no new SSRF surface beyond the
  configured endpoint.
* Read-only: the tool never changes world state and belongs in the
  read-only tool class alongside ``http.get``.
* When no instance is reachable the tool reports ``ok: False`` with
  ``reason: "unavailable"`` instead of raising, so the agent can say plainly
  that search is not configured.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .untrusted import fence_content

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
RESULT_SNIPPET_CHARS = 800
MAX_RESULTS = 10


class SearXNGClient:
    """Minimal client for the SearXNG JSON API."""

    def __init__(self, base_url: str | None = None, *, timeout: float = 10.0) -> None:
        configured = (base_url or os.environ.get("SHADOW_SEARXNG_URL", "")).strip()
        self.base_url = configured or DEFAULT_BASE_URL
        self.timeout = max(1.0, timeout)
        # SearXNG is operator-local infrastructure: never route it through
        # any egress proxy from the environment.
        self._client = httpx.Client(trust_env=False, follow_redirects=True)

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}{path}"

    def available(self) -> bool:
        """Return True when the instance answers at all."""

        try:
            r = self._client.get(self._url("/"), timeout=self.timeout)
            return r.status_code < 500
        except (httpx.HTTPError, httpx.InvalidURL, OSError, ValueError):
            return False

    def search(
        self,
        query: str,
        *,
        max_results: int = MAX_RESULTS,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Run a search and return fenced result dicts."""

        query = query.strip()
        if not query:
            raise ValueError("query is required")
        limit = max(1, min(int(max_results or MAX_RESULTS), MAX_RESULTS))
        try:
            r = self._client.get(
                self._url("/search"),
                params={"q": query, "format": "json", "language": language},
                headers={"Accept": "application/json", "User-Agent": "shadow-node/1.0"},
                timeout=self.timeout,
            )
            r.raise_for_status()
            payload = r.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"SearXNG request failed: {exc}") from exc
        except (httpx.InvalidURL, OSError, ValueError) as exc:
            raise RuntimeError(f"SearXNG unreachable at {self.base_url}: {exc}") from exc

        raw_results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(raw_results, list):
            raise RuntimeError(f"Endpoint at {self.base_url} did not return SearXNG JSON")

        out: list[dict[str, Any]] = []
        for item in raw_results[:limit]:
            if not isinstance(item, dict):
                continue
            snippet = str(item.get("content") or "")[:RESULT_SNIPPET_CHARS]
            out.append(
                {
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("url") or ""),
                    "engine": str(item.get("engine") or ""),
                    "snippet": fence_content(snippet, source="web-search"),
                }
            )
        return out


def web_search(query: str, *, max_results: int = MAX_RESULTS) -> dict[str, Any]:
    """Search the web via SearXNG. Returns fenced results or unavailable."""

    client = SearXNGClient()
    if not client.available():
        return {
            "ok": False,
            "action": "web.search",
            "reason": "unavailable",
            "detail": (
                "No SearXNG instance is reachable at "
                f"{client.base_url}. Set SHADOW_SEARXNG_URL to a running instance."
            ),
        }
    try:
        results = client.search(query, max_results=max_results)
    except (RuntimeError, ValueError) as exc:
        return {"ok": False, "action": "web.search", "reason": "error", "detail": str(exc)}
    return {"ok": True, "action": "web.search", "query": query, "results": results}


__all__ = ["DEFAULT_BASE_URL", "SearXNGClient", "web_search"]
