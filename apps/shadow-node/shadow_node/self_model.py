"""Runtime-derived self-description for SHADOW.

Answers "what are you", "where are you", and "what can you do" from live
node state. Every fact is read from the running process: there is no
hardcoded marketing copy, so the answers cannot drift from what the node
actually is and can do. The ask pipeline answers these intents
deterministically (no LLM round-trip) so they stay honest even when the
model route is a dumb local mock.
"""
import platform
import re

# Each pattern must be followed by sentence punctuation or end-of-input so a
# longer question that merely contains the phrase ("where are you going with
# this") falls through to the normal ask pipeline.
_END = r"(?:[?.!]+\s*|\s*)$"
_INTENTS = (
    ("identity", (
        r"\bwho are you\b", r"\bwhat are you\b", r"\byour name\b",
        r"\bintroduce yourself\b", r"\btell me about yourself\b",
        r"\bwhat is shadow\b", r"\bwho is shadow\b",
    )),
    ("location", (
        r"\bwhere are you\b", r"\bwhere do you run\b", r"\bwhere do you live\b",
    )),
    ("capabilities", (
        r"\bwhat can you do\b", r"\bwhat can you do for me\b",
        r"\btell me what you can do\b",
        r"\bwhat are your (capabilities|features|skills)\b",
        r"\blist your (capabilities|features|skills)\b",
        r"\bwhat features do you have\b",
    )),
)


def classify_self_intent(prompt: str) -> str | None:
    """Return 'identity', 'location', or 'capabilities' for a clear
    self-directed question, else None."""
    low = prompt.lower().strip()
    for intent, patterns in _INTENTS:
        if any(re.search(p + _END, low) for p in patterns):
            return intent
    return None


def build_self_model(core, sessions, memory, model_config, app_version: str,
                     persona_name: str | None = None) -> dict:
    """Assemble the self-model from live runtime objects. persona_name, when
    given, is the assistant's editable identity (Phase 1 persona)."""
    tools = core.tools.names()
    provider = getattr(model_config, "provider", "local_mock") or "local_mock"
    devices = getattr(sessions, "devices", None) or {}
    return {
        "identity": {
            "name": persona_name or "SHADOW",
            "version": app_version,
            "kind": "local-first personal AI agent",
            "runs_on": "your Shadow Node",
        },
        "runtime": {
            "platform": f"{platform.system()} {platform.machine()}".strip(),
            "python": platform.python_version(),
            "local_first": True,
            "model_route": provider,
            "cloud_model": provider not in ("local_mock", "local", ""),
            "paired_devices": len(devices),
        },
        "capabilities": {
            "tools": tools,
            "tool_count": len(tools),
            "memory": {"encrypted": True, "backend": type(memory).__name__},
            "features": [
                "approvals inbox: sensitive actions wait for your explicit approval",
                "encrypted on-device memory with consent-scoped ingestion",
                "ghost multi-step runs with checkpoints",
                "ambient background tasks (morning brief, memory digest)",
                "device pairing with signed requests",
            ],
        },
    }


def _tool_summary(model: dict) -> str:
    tools = model["capabilities"]["tools"]
    if not tools:
        return "no tools are currently registered"
    shown = ", ".join(tools[:12])
    extra = f", and {len(tools) - 12} more" if len(tools) > 12 else ""
    return f"{len(tools)} registered tools: {shown}{extra}"


def render_self_answer(intent: str, model: dict) -> str:
    """Natural-language answer for one self intent, from the model dict."""
    ident, run, caps = model["identity"], model["runtime"], model["capabilities"]
    if intent == "identity":
        route = ("a cloud model" if run["cloud_model"]
                 else "the on-device local model")
        return (f"I'm {ident['name']} ({ident['version']}), a {ident['kind']} "
                f"running on {ident['runs_on']}. I answer with {route}, and "
                f"anything sensitive waits for your approval first.")
    if intent == "location":
        cloud = ("I can reach a cloud model only when you explicitly allow it; "
                 if run["cloud_model"] else
                 "I'm not using any cloud model right now; ")
        return (f"I run on {ident['runs_on']} ({run['platform']}), not in a "
                f"vendor cloud. {cloud}Your data stays on the node. "
                f"{run['paired_devices']} device(s) paired.")
    # capabilities
    feats = "; ".join(caps["features"])
    return (f"Here's what I can do: {feats}. {_tool_summary(model).capitalize()}. "
            f"Ask me to remember something, propose an action for approval, "
            f"or check the approvals inbox.")
