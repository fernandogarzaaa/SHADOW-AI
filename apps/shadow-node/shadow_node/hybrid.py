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
import re
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


class GroundingVerifier:
    """Lexical grounding check, in the spirit of AXIOM-AETHER's hallucination.rs.

    Scores how much of an answer's content vocabulary is actually supported by the
    supplied context. Used to decide whether a low-grounding frontier answer
    should be retried against the full (uncompressed) context.
    """
    _WORD = re.compile(r"[a-z0-9]+")

    def _content_words(self, text: str) -> set[str]:
        return {w for w in self._WORD.findall((text or "").lower()) if len(w) > 3}

    def score(self, answer: str, context: str) -> float:
        a = self._content_words(answer)
        if not a:
            return 1.0  # nothing to ground (e.g. a refusal or empty answer)
        ctx = self._content_words(context)
        return len(a & ctx) / len(a)


class HybridRouter:
    def __init__(self, local, axiom: AxiomAdapter | None = None, router: ComplexityRouter | None = None,
                 verifier: GroundingVerifier | None = None):
        self.local = local
        self.axiom = axiom or AxiomAdapter()
        self.router = router or ComplexityRouter()
        self.verifier = verifier or GroundingVerifier()
        self.estimator = TokenBudgetEstimator()

    def run(self, prompt: str, raw_context: str, frontier=None, threshold: float = 0.5,
            verify: bool = False, grounding_threshold: float = 0.3) -> dict:
        raw_tokens = self.estimator.estimate(raw_context) if raw_context else 0
        packaged = self.axiom.package_context(raw_context or "")
        compressed_context = packaged["context"]
        # Estimate from the actual compressed text (package_context.tokens_estimated
        # counts the pre-compression redacted text, which would under-report savings).
        compressed_tokens = self.estimator.estimate(compressed_context)
        # Routing keys off RAW context size (how much information there is);
        # compression affects cost/savings, not complexity.
        decision = self.router.decide(prompt, raw_tokens, frontier is not None, threshold)
        regrounded = False

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
            # Draft-then-verify: if the compressed-context answer is poorly grounded,
            # retry once against the full uncompressed context (AXIOM-style expansion).
            if verify and raw_context and self.verifier.score(answer, raw_context) < grounding_threshold:
                answer = frontier.complete(prompt, raw_context)
                frontier_tokens = raw_tokens
                tokens_saved = 0
                regrounded = True

        grounding = round(self.verifier.score(answer, raw_context), 3) if raw_context else 1.0
        return {
            "answer": answer,
            "route": decision.route,
            "provider": provider,
            "reason": decision.reason,
            "complexity": round(decision.complexity, 3),
            "grounding": grounding,
            "regrounded": regrounded,
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
