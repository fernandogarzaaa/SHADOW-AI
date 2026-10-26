"""Outgoing-data filter: catch secrets and personal identifiers in actions
that send data off the node (messages, web requests, searches).

Two severities:
- ``block``: credentials (API keys, tokens, private keys, passwords in
  URLs). These never leave the node, approval or not.
- ``confirm``: payment cards (Luhn-checked) and US Social Security numbers.
  The action needs an explicit approval that names what was found; no
  tier or user rule can waive it.

Pattern-based, so it complements (never replaces) the approval gate.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

#: Tools whose parameters leave the node (or are written for sending).
DEFAULT_OUTBOUND_TOOLS = (
    "send_email", "send_message", "email.draft", "calendar.create",
    "http.get", "web.search",
)

_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("Anthropic or OpenAI API key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Stripe secret key", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}")),
    ("JSON web token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("password in a URL", re.compile(r"://[^/\s:@]+:[^/\s@]+@")),
    ("password", re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*\S{6,}")),
]

_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_SSN = re.compile(r"(?<!\d)(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)")


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str  # "block" | "confirm"


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _flatten(value) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def scan(value) -> list[Finding]:
    """Findings in a string or JSON-like value (deduplicated by kind)."""
    text = _flatten(value)
    found: dict[str, Finding] = {}
    for kind, pat in _SECRET_PATTERNS:
        if pat.search(text):
            found[kind] = Finding(kind, "block")
    for m in _CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and len(set(digits)) > 1 and _luhn_ok(digits):
            found["payment card number"] = Finding("payment card number", "confirm")
            break
    if _SSN.search(text):
        found["Social Security number"] = Finding("Social Security number", "confirm")
    return list(found.values())
