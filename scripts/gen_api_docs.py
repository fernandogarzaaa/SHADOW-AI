"""Regenerate the endpoint reference in docs/API.md from the live route table.

    python scripts/gen_api_docs.py          # rewrite the generated section
    python scripts/gen_api_docs.py --check  # exit 1 if docs/API.md is stale (CI)

Only the block between the BEGIN/END markers is generated; the narrative
above it is hand-written.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in ("apps/shadow-node", "packages/agent-core", "packages/memory-engine",
          "packages/axiom-adapter", "packages/ghost-adapter"):
    sys.path.insert(0, str(ROOT / p))
os.environ.setdefault("SHADOW_AUTH_REQUIRED", "false")

BEGIN = "<!-- BEGIN GENERATED ENDPOINTS (scripts/gen_api_docs.py) -->"
END = "<!-- END GENERATED ENDPOINTS -->"
DOC = ROOT / "docs" / "API.md"
PUBLIC = {"/", "/health", "/ready", "/pair/start", "/pair/confirm"}


def _summary(doc: str | None) -> str:
    """First sentence of a docstring, whitespace-collapsed, max 160 chars."""
    import re
    text = " ".join((doc or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    first = m.group(1) if m else text
    return first if len(first) <= 160 else first[:157].rstrip() + "..."


def render() -> str:
    from fastapi.routing import APIRoute, APIWebSocketRoute
    from shadow_node.main import app

    groups: dict[str, list[str]] = {}
    for route in app.routes:
        if isinstance(route, APIRoute):
            if not route.include_in_schema:
                continue
            methods = sorted(m for m in route.methods if m not in {"HEAD", "OPTIONS"})
            summary = _summary(route.endpoint.__doc__)
        elif isinstance(route, APIWebSocketRoute):
            methods, summary = ["WS"], "Signed WebSocket (HMAC headers on the handshake)."
        else:
            continue
        group = route.path.strip("/").split("/")[0] or "root"
        auth = "public" if route.path in PUBLIC else "signed"
        for m in methods:
            line = f"| `{m}` | `{route.path}` | {auth} | {summary.replace('|', '/')} |"
            groups.setdefault(group, []).append(line)

    out = [BEGIN, "", "## Endpoint reference", "",
           "Generated from the route table. \"signed\" routes need the `x-shadow-*` "
           "request-signature headers (see AUTHENTICATED_TRANSPORT.md).", ""]
    for group in sorted(groups):
        out += [f"### {group}", "", "| Method | Path | Auth | Summary |", "|---|---|---|---|"]
        out += sorted(set(groups[group]), key=lambda l: (l.split("|")[2], l.split("|")[1]))
        out.append("")
    out.append(END)
    return "\n".join(out) + "\n"


def main() -> int:
    text = DOC.read_text()
    generated = render()
    if BEGIN in text:
        head = text[: text.index(BEGIN)]
        tail = text[text.index(END) + len(END):].lstrip("\n") if END in text else ""
    else:
        head, tail = text.rstrip("\n") + "\n\n", ""
    new = head + generated + (("\n" + tail) if tail else "")
    if "--check" in sys.argv:
        if new != text:
            print("docs/API.md is out of date: run python scripts/gen_api_docs.py", file=sys.stderr)
            return 1
        print("docs/API.md is up to date")
        return 0
    DOC.write_text(new)
    print(f"wrote {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
