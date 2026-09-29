"""Compression backends for session compaction.

The ambient loop's SessionCompactor folds old session messages through a
CompressionBackend. The default is fully local and deterministic; the
AXIOM backend is a real seam to Inan's local AXIOM-AETHER checkout that
reports honestly when the backend is not there.

Why a seam instead of a direct AXIOM call: AXIOM-AETHER upstream is a
Rust/Python inference research engine. It exposes no summarization
entrypoint today, so there is nothing real to call yet. Rather than fake
one, AxiomBackend lights up only when a local checkout provides
`axiom_engine/summarize.py` with a `summarize_text(text: str) -> str`
callable. Until then it reports unavailable with a concrete reason, and
selection falls back to the deterministic backend (the loop's behavior
is unchanged from before this seam existed).
"""
from __future__ import annotations

import importlib.util
import os
import re
from typing import Any, Protocol, runtime_checkable


class SummarizableMessage(Protocol):
    role: str
    content: str
    created_at: Any


@runtime_checkable
class CompressionBackend(Protocol):
    """Something that can fold old session messages into a summary."""

    name: str

    def available(self) -> bool:
        """True when this backend can summarize right now."""
        ...

    def unavailable_reason(self) -> str | None:
        """Human-readable reason when available() is False, else None."""
        ...

    def summarize(self, messages: list[SummarizableMessage]) -> str:
        """Fold messages into one summary string. May raise RuntimeError
        when the backend is unavailable."""
        ...


# Lines that look like durable user facts worth carrying across compaction.
_FACT_PATTERNS = (
    re.compile(r"(?i)\b(my|i'm|i am|i've|i have)\b[^.!?\n]{0,90}"),
    re.compile(r"(?i)\b(remember|prefer|always|never|don't|do not)\b[^.!?\n]{0,90}"),
)


class DeterministicBackend:
    """The loop's original local summarizer, extracted unchanged.

    No model call: message count, time span, opening user intent, and
    regex-extracted key facts. Always available; this is the fallback
    every other backend degrades to.
    """

    name = "deterministic"

    def __init__(self, max_facts: int = 8) -> None:
        self.max_facts = max(1, max_facts)

    def available(self) -> bool:
        return True

    def unavailable_reason(self) -> str | None:
        return None

    def _key_facts(self, messages: list[SummarizableMessage]) -> list[str]:
        facts: list[str] = []
        for m in messages:
            if m.role != "user":
                continue
            for pat in _FACT_PATTERNS:
                for hit in pat.findall(m.content):
                    text = " ".join(hit.split()) if isinstance(hit, str) else ""
                    text = text.strip(" .")
                    if text and text not in facts:
                        facts.append(text)
                    if len(facts) >= self.max_facts:
                        return facts
        return facts

    def summarize(self, messages: list[SummarizableMessage]) -> str:
        if not messages:
            return "(empty session)"
        first_user = next((m.content for m in messages if m.role == "user"), "")
        facts = self._key_facts(messages)
        span = ""
        try:
            span = f"{messages[0].created_at} .. {messages[-1].created_at}"
        except Exception:
            pass
        lines = [
            f"Context compacted: {len(messages)} older messages folded ({span}).",
        ]
        if first_user:
            lines.append(f"Opening intent: {first_user[:200]}")
        if facts:
            lines.append("Key facts carried forward:")
            lines.extend(f"- {f}" for f in facts)
        return "\n".join(lines)


class AxiomBackend:
    """Compression via a local AXIOM-AETHER checkout.

    Real seam, honest status: available() is True only when
    `<path>/axiom_engine/summarize.py` exists and defines a callable
    `summarize_text(text: str) -> str`. The checkout path comes from
    `AXIOM_AETHER_PATH` or defaults to `~/workspace/axiom-aether`.
    Everything else (missing checkout, no entrypoint, broken module)
    reports unavailable with a concrete reason; summarize() raises
    RuntimeError in that state so a misconfiguration fails loud instead
    of silently producing fake summaries.
    """

    name = "axiom"

    def __init__(self, path: str | None = None) -> None:
        env = os.environ.get("AXIOM_AETHER_PATH", "").strip()
        self.path = path or env or os.path.expanduser("~/workspace/axiom-aether")
        self._module: Any | None = None
        self._reason: str | None = "not checked yet"

    def _summarizer_file(self) -> str:
        return os.path.join(self.path, "axiom_engine", "summarize.py")

    def _check(self) -> str | None:
        """Returns None when the backend is usable, else the reason."""
        if not os.path.isdir(self.path):
            return (f"no local AXIOM-AETHER checkout at {self.path} "
                    "(set AXIOM_AETHER_PATH to point at one)")
        summarizer = self._summarizer_file()
        if not os.path.isfile(summarizer):
            return (f"AXIOM-AETHER checkout at {self.path} exposes no "
                    "summarization entrypoint (expected "
                    "axiom_engine/summarize.py defining "
                    "summarize_text(text: str) -> str)")
        if self._module is None:
            try:
                spec = importlib.util.spec_from_file_location(
                    "axiom_summarizer", summarizer)
                if spec is None or spec.loader is None:
                    return f"could not load summarizer module from {summarizer}"
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception as e:  # noqa: BLE001 - reported, not raised
                return f"could not load {summarizer}: {e}"
            if not callable(getattr(mod, "summarize_text", None)):
                return f"{summarizer} defines no callable summarize_text(text)"
            self._module = mod
        return None

    def available(self) -> bool:
        self._reason = self._check()
        return self._reason is None

    def unavailable_reason(self) -> str | None:
        if self._reason == "not checked yet":
            self._reason = self._check()
        return self._reason

    def summarize(self, messages: list[SummarizableMessage]) -> str:
        if not self.available() or self._module is None:
            raise RuntimeError(
                f"axiom backend unavailable: {self.unavailable_reason()}")
        text = "\n".join(
            f"{m.role}: {m.content}" for m in messages
            if getattr(m, "content", ""))
        return str(self._module.summarize_text(text))


def select_backend(preferred: str | None = None) -> tuple[CompressionBackend, str | None]:
    """Resolve the configured backend, failing safe to deterministic.

    Returns (backend, fallback_reason). fallback_reason is None when the
    preferred backend was used as-is; otherwise it explains why the
    deterministic backend is active instead. Never raises: compaction
    must keep working even with a misconfigured backend name.
    """
    name = (preferred or "deterministic").strip().lower()
    if name == "axiom":
        backend = AxiomBackend()
        if backend.available():
            return backend, None
        reason = backend.unavailable_reason() or "unknown reason"
        return (DeterministicBackend(),
                f"axiom requested but unavailable ({reason}); using deterministic")
    if name != "deterministic":
        return (DeterministicBackend(),
                f"unknown compression backend {preferred!r}; using deterministic")
    return DeterministicBackend(), None
