"""Regression tests for proxy-env sanitization (live-test finding 2026-09-27).

httpx<=0.28 raises ``InvalidURL: Invalid port`` at Client construction time
when no_proxy/NO_PROXY contains bracketed IPv6 literals like ``[::1]`` --
it parses each entry as a URL. That broke every cloud provider call in
proxied environments. ``sanitize_proxy_env()`` normalizes those entries at
import time; these tests pin that behavior.
"""
import os

import httpx
import pytest

from shadow_node.model_providers import sanitize_proxy_env


def test_sanitize_strips_brackets_from_ipv6_entries(monkeypatch):
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1,[::1],[fd8b:4f84:7d32:99::1]")
    monkeypatch.delenv("NO_PROXY", raising=False)
    sanitize_proxy_env()
    assert os.environ["no_proxy"] == "localhost,127.0.0.1,::1,fd8b:4f84:7d32:99::1"


def test_sanitize_preserves_plain_entries_and_ports(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "example.com, 10.0.0.1, *.internal:8080")
    monkeypatch.delenv("no_proxy", raising=False)
    sanitize_proxy_env()
    assert os.environ["NO_PROXY"] == "example.com,10.0.0.1,*.internal:8080"


def test_sanitize_is_idempotent(monkeypatch):
    monkeypatch.setenv("no_proxy", "[::1],localhost")
    monkeypatch.delenv("NO_PROXY", raising=False)
    sanitize_proxy_env()
    first = os.environ["no_proxy"]
    sanitize_proxy_env()
    assert os.environ["no_proxy"] == first == "::1,localhost"


def test_sanitize_handles_missing_vars(monkeypatch):
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    sanitize_proxy_env()  # must not raise


def test_httpx_client_constructs_with_bracketed_no_proxy(monkeypatch):
    """The actual regression: Client() raised InvalidURL before the fix."""
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1,[::1],[fd8b:4f84:7d32:99::1]")
    monkeypatch.setenv("https_proxy", "http://proxy.internal:3128")
    sanitize_proxy_env()
    client = httpx.Client(timeout=5.0)
    client.close()
