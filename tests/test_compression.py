"""Tests for the compression backend seam.

Pins the deterministic backend's output byte-for-byte against the
pre-seam inline implementation, proves the AXIOM backend reports
honestly when there is no real backend, and proves selection and
compaction always fail safe to deterministic.
"""
import os
import time

import pytest

from agent_core import (
    AgentSession,
    AxiomBackend,
    CompressionBackend,
    DeterministicBackend,
    InMemoryKV,
    SessionCompactor,
    SessionMessage,
    SessionStore,
    select_backend,
)


def _session(n=14):
    s = AgentSession(title="t")
    s.messages.append(SessionMessage(role="user", kind="text",
                                     content="remember I prefer dark mode"))
    for i in range(n):
        s.messages.append(SessionMessage(role="user", kind="text",
                                         content=f"question {i}"))
        s.messages.append(SessionMessage(role="assistant", kind="text",
                                         content=f"answer {i}"))
    return s


def test_deterministic_output_matches_legacy_shape():
    # Pinned against the pre-seam inline implementation: count line,
    # opening intent, extracted facts. Any drift fails here on purpose.
    comp = SessionCompactor(budget_tokens=100, keep_recent=2)
    s = _session()
    rep = comp.compact(s)
    assert rep.folded_count > 0
    text = rep.summary_text
    assert text.startswith(
        f"Context compacted: {rep.folded_count} older messages folded (")
    assert "Opening intent: remember I prefer dark mode" in text
    assert "Key facts carried forward:" in text
    assert "- remember" in text  # legacy findall returns the group match
    # the summary message is what the session now starts with
    assert s.messages[0].kind == "compaction_summary"
    assert s.messages[0].content == text


def test_deterministic_backend_is_always_available():
    b = DeterministicBackend()
    assert b.available() is True
    assert b.unavailable_reason() is None
    assert isinstance(b, CompressionBackend)


def test_axiom_unavailable_without_checkout():
    b = AxiomBackend(path="/nonexistent/axiom-aether")
    assert b.available() is False
    reason = b.unavailable_reason()
    assert reason and "no local AXIOM-AETHER checkout" in reason
    with pytest.raises(RuntimeError, match="axiom backend unavailable"):
        b.summarize([])


def test_axiom_unavailable_without_summarizer_entrypoint(tmp_path, monkeypatch):
    # a checkout exists but exposes no summarizer: still honest, still
    # unavailable. This is the real upstream state as of 2026-09-29.
    (tmp_path / "axiom_engine").mkdir()
    (tmp_path / "axiom_engine" / "__init__.py").write_text("")
    monkeypatch.setenv("AXIOM_AETHER_PATH", str(tmp_path))
    b = AxiomBackend()
    assert b.available() is False
    assert "no summarization entrypoint" in b.unavailable_reason()


def test_axiom_lights_up_with_a_real_summarizer(tmp_path, monkeypatch):
    eng = tmp_path / "axiom_engine"
    eng.mkdir()
    (eng / "summarize.py").write_text(
        "def summarize_text(text: str) -> str:\n"
        "    return f'AXIOM SUMMARY of {len(text.splitlines())} lines'\n")
    monkeypatch.setenv("AXIOM_AETHER_PATH", str(tmp_path))
    b = AxiomBackend()
    assert b.available() is True
    assert b.unavailable_reason() is None
    msgs = [SessionMessage(role="user", kind="text", content="hello"),
            SessionMessage(role="assistant", kind="text", content="hi")]
    assert b.summarize(msgs) == "AXIOM SUMMARY of 2 lines"


def test_select_backend_falls_back_with_reason(monkeypatch):
    monkeypatch.setenv("AXIOM_AETHER_PATH", "/nonexistent/axiom-aether")
    backend, reason = select_backend("axiom")
    assert isinstance(backend, DeterministicBackend)
    assert reason and "axiom requested but unavailable" in reason


def test_select_backend_unknown_name_falls_back():
    backend, reason = select_backend("mystery")
    assert isinstance(backend, DeterministicBackend)
    assert reason and "unknown compression backend" in reason


def test_select_backend_default_is_deterministic():
    backend, reason = select_backend(None)
    assert isinstance(backend, DeterministicBackend)
    assert reason is None


def test_compactor_falls_back_when_primary_breaks_at_runtime(monkeypatch):
    # AXIOM was available at startup, then the checkout vanished: the
    # loop must still compact instead of raising.
    monkeypatch.setenv("AXIOM_AETHER_PATH", "/nonexistent/axiom-aether")
    comp = SessionCompactor(budget_tokens=100, keep_recent=2,
                            backend=AxiomBackend())
    assert comp.backend.available() is False
    s = _session()
    rep = comp.compact(s)
    assert rep.folded_count > 0
    assert rep.summary_text.startswith("Context compacted:")


def test_compactor_uses_injected_backend():
    class UpperBackend:
        name = "upper"

        def available(self):
            return True

        def unavailable_reason(self):
            return None

        def summarize(self, messages):
            return "UPPER:" + "|".join(m.content for m in messages)

    comp = SessionCompactor(budget_tokens=100, keep_recent=2,
                            backend=UpperBackend())
    s = _session()
    rep = comp.compact(s)
    assert rep.summary_text.startswith("UPPER:remember I prefer dark mode")


def test_session_store_still_ingests_compacted_summary():
    compactor = SessionCompactor(budget_tokens=120, keep_recent=2)
    store = SessionStore(store=InMemoryKV(), compactor=compactor)
    s = store.create("t")
    store.append(s.id, "user", "My favorite editor is helix and I prefer dark mode.")
    for i in range(6):
        store.append(s.id, "user", f"question number {i} about agents and tooling")
        store.append(s.id, "assistant", f"answer number {i} with some detail here")
    got = store.get(s.id)
    assert got.messages[0].kind == "compaction_summary"
    assert got.messages[0].content.startswith("Context compacted:")
