#!/usr/bin/env python3
"""Live test: shadow node /agent/ask answered by a real model via OpenRouter.

Path under test (all real, no mocks):
  TestClient -> FastAPI app -> consent grant -> cloud escalation gate
  -> CredentialStore -> build_frontier("openai") -> OpenAIProvider
  -> localhost relay (this machine only) -> authd surrogate swap at egress
  -> https://openrouter.ai/api/v1/chat/completions

The raw API key never appears here: the node only ever holds the
placeholder "relay-placeholder", which travels no further than
127.0.0.1. The relay attaches the real credential via the Secure Vault
surrogate exchange.

Usage: python3 scripts/live_openrouter_test.py
Env:    OPENROUTER_TEST_MODEL (default openai/gpt-4o-mini)
        RELAY_PORT (required: printed by skills/openrouter/bin/relay.py)
"""
import json
import os
import sys

RELAY_PORT = os.environ.get("RELAY_PORT", "").strip()
if not RELAY_PORT:
    sys.exit("RELAY_PORT is required: start bin/relay.py and export its port")
MODEL = os.getenv("OPENROUTER_TEST_MODEL", "openai/gpt-4o-mini")

# Env must be set before the node modules are imported.
os.environ["SHADOW_AUTH_REQUIRED"] = "false"
os.environ["SHADOW_CLOUD_ENABLED"] = "true"
os.environ["SHADOW_MODEL_PROVIDER"] = "openai"
os.environ["SHADOW_MODEL_NAME"] = MODEL
os.environ["SHADOW_MODEL_ENDPOINT"] = f"http://127.0.0.1:{RELAY_PORT}/v1/chat/completions"
# Keep the placeholder credential out of the repo's real key store.
os.environ["SHADOW_PROVIDERS_FILE"] = "/tmp/live-test-providers.enc"

from fastapi.testclient import TestClient  # noqa: E402

import shadow_node.main as main  # noqa: E402

# The node resolves a credential for the "openai" provider; the value is a
# placeholder that is only ever sent to the localhost relay, which swaps in
# the real credential at egress.
main.credentials.set("openai", {"type": "api_key", "api_key": "relay-placeholder",
                                "source": "live-test"})

client = TestClient(main.app)

health = client.get("/health").json()
print("health:", health.get("status"), "| keys:", sorted(health.keys()))

consent = client.post("/consent", json={
    "data_source": "live-test",
    "scope": "none",
    "purpose": "live OpenRouter model test",
    "model_access_level": "cloud_allowed",
}).json()
print("consent grant:", consent["id"])

PROMPT = ("Analyze the trade-offs between local-first and cloud-based personal "
           "AI assistants, covering privacy, latency, and cost. "
           "Keep the answer under 120 words.")
resp = client.post("/agent/ask", json={
    "prompt": PROMPT,
    "allow_cloud": True,
    "cloud_approval": True,
})
assert resp.status_code == 200, f"ask failed: {resp.status_code} {resp.text[:300]}"
result = resp.json()

print("route:", result["route"])
print("model_used:", result["model_used"])
print("cloud_allowed:", result["cloud_allowed"])
print("answer:", result["answer"][:400])

assert result["route"] == "frontier", "expected the frontier (cloud) route"
assert result["model_used"] == "openai", "expected the openai provider"
assert result["answer"] and "Local mock" not in result["answer"], "answer looks mocked"

asks = [e for e in client.get("/audit").json()
        if e.get("event_type") == "agent_ask"]
latest = asks[-1]
print("audit agent_ask: status=", latest["status"],
      "route=", latest["metadata"]["route"],
      "model=", latest["model_used"])

print("LIVE-TEST-PASS")
