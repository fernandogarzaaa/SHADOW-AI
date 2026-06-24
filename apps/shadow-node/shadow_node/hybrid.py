"""Hybrid local + frontier model router.

Token savings come from two real mechanisms, mirroring AXIOM-AETHER:

1. **Local short-circuit** — simple / short queries are answered fully on-device
   by the local model, sending ZERO tokens to a frontier provider.
2. **Context compression** — when a query is routed to a frontier model, only
   the AXIOM-compressed + redacted context (plus a skeleton digest) is sent, not
   the raw retrieved memory, so far fewer input tokens are billed.

The router reports an estimated token saving for every request so the UI can
show the user what the hybrid approach saved.
"""
from __future__ import annotations
from dataclasses import dataclass
from axiom_adapter import AxiomAdapter, TokenBudgetEstimator

HARD_SIGNALS = (
    "analyze", "compare", "explain why", "why ", "strategy", "design", "debug",
    "prove", "plan ", "summarize", "reason", "evaluate", "trade-off", "tradeoff",
    "recommend", "draft", "write a", "implications", "across",
)


@dataclass
class RouteDecision:
    route: str          # "local" | "frontier"
    reason: str
    complexity: float


class ComplexityRouter:
    """Cheap, deterministic complexity estimate to decide local vs frontier."""

    def score(self, prompt: str, context_tokens: int) -> float:
        p = prompt.lower()
        s = min(len(prompt) / 600.0, 0.45)
        if any(sig in p for sig in HARD_SIGNALS):
            s += 0.35
        if context_tokens > 400:
            s += 0.20
        if prompt.strip().endswith("?") and len(prompt) < 60:
            s -= 0.15  # short factual lookup
        return max(0.0, min(s, 1.0))

    def decide(self, prompt: str, context_tokens: int, frontier_available: bool, threshold: float = 0.5) -> RouteDecision:
        c = self.score(prompt, context_tokens)
        if not frontier_available:
            return RouteDecision("local", "no frontier model connected/approved — answered on-device", c)
        if c < threshold:
            return RouteDecision("local", f"low complexity ({c:.2f}) handled on-device", c)
        return RouteDecision("frontier", f"complexity ({c:.2f}) routed to frontier", c)


class HybridRouter:
    def __init__(self, local, axiom: AxiomAdapter | None = None, router: ComplexityRouter | None = None):
        self.local = local
        self.axiom = axiom or AxiomAdapter()
        self.router = router or ComplexityRouter()
        self.estimator = TokenBudgetEstimator()

    def run(self, prompt: str, raw_context: str, frontier=None, threshold: float = 0.5) -> dict:
        raw_tokens = self.estimator.estimate(raw_context) if raw_context else 0
        packaged = self.axiom.package_context(raw_context or "")
        compressed_context = packaged["context"]
        compressed_tokens = packaged["tokens_estimated"]
        decision = self.router.decide(prompt, compressed_tokens, frontier is not None, threshold)

        if decision.route == "local" or frontier is None:
            answer = self.local.complete(prompt, compressed_context)
            provider = getattr(self.local, "name", "local")
            frontier_tokens = 0
            # Local handled it: every context token that would have gone to a
            # frontier model was saved.
            tokens_saved = raw_tokens
        else:
            answer = frontier.complete(prompt, compressed_context)
            provider = getattr(frontier, "name", "frontier")
            frontier_tokens = compressed_tokens
            # Frontier handled it, but on compressed context: saving is the
            # difference vs sending the raw context.
            tokens_saved = max(0, raw_tokens - compressed_tokens)

        return {
            "answer": answer,
            "route": decision.route,
            "provider": provider,
            "reason": decision.reason,
            "complexity": round(decision.complexity, 3),
            "untrusted_context": True,
            "context_package": packaged,
            "savings": {
                "raw_context_tokens": raw_tokens,
                "compressed_context_tokens": compressed_tokens,
                "frontier_tokens_sent": frontier_tokens,
                "tokens_saved_estimate": tokens_saved,
                "saved_pct": round(100 * tokens_saved / raw_tokens, 1) if raw_tokens else 0.0,
            },
        }
