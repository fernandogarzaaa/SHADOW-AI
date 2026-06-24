"""Route-prompting engine — the logic behind Shadow's frontier-router MCP server.

This module is dependency-free (no ``mcp`` import) so it is fully unit-testable
and reusable. It wraps the hybrid router, AXIOM compression, the frontier
providers, and the encrypted credential store into four tools:

- ``route_estimate``  — decide local vs frontier + estimated token savings (no inference)
- ``compress_context`` — AXIOM-compress text + skeleton digest + token counts
- ``route_complete``  — full hybrid completion (local short-circuit or compressed frontier)
- ``list_providers``  — connection status of each frontier provider
"""
from __future__ import annotations
from axiom_adapter import AxiomAdapter, TokenBudgetEstimator, SemanticSkeletonGenerator
from .model_providers import LocalMockModel, ModelProviderConfig
from .hybrid import HybridRouter, ComplexityRouter
from .providers import build_frontier
from .provider_auth import CredentialStore


class RouteEngine:
    def __init__(self, local=None, axiom=None, credentials=None, config=None):
        self.axiom = axiom or AxiomAdapter()
        self.local = local or LocalMockModel()
        self.hybrid = HybridRouter(self.local, self.axiom)
        self.credentials = credentials or CredentialStore()
        self.config = config or ModelProviderConfig()
        self.router = ComplexityRouter()
        self.estimator = TokenBudgetEstimator()
        self.skeleton = SemanticSkeletonGenerator()

    # --- tool implementations ---
    def compress_context(self, text: str = "") -> dict:
        pkg = self.axiom.package_context(text or "")
        return {
            "compressed_context": pkg["context"],
            "skeleton": self.skeleton.generate(pkg["context"]),
            "fingerprint": pkg["fingerprint"],
            "raw_tokens": self.estimator.estimate(text or ""),
            "compressed_tokens": self.estimator.estimate(pkg["context"]),
        }

    def route_estimate(self, prompt: str, context: str = "", threshold: float = 0.5) -> dict:
        pkg = self.axiom.package_context(context or "")
        compressed = self.estimator.estimate(pkg["context"])
        raw = self.estimator.estimate(context or "")
        d = self.router.decide(prompt, raw, frontier_available=True, threshold=threshold)
        would_save = raw if d.route == "local" else max(0, raw - compressed)
        return {
            "route": d.route, "complexity": round(d.complexity, 3), "reason": d.reason,
            "raw_context_tokens": raw, "compressed_context_tokens": compressed,
            "would_save_tokens_estimate": would_save,
        }

    def _frontier(self, provider: str | None):
        prov = provider or self.config.provider
        cred = self.credentials.resolve(prov)
        if not cred:
            return None
        cred = {**cred, "endpoint": self.config.endpoint}
        return build_frontier(prov, cred, self.config.model_name)

    def route_complete(self, prompt: str, context: str = "", allow_cloud: bool = False,
                       provider: str | None = None, threshold: float = 0.5) -> dict:
        frontier = self._frontier(provider) if allow_cloud else None
        try:
            out = self.hybrid.run(prompt, context or "", frontier=frontier, threshold=threshold)
        except Exception as e:
            out = self.hybrid.run(prompt, context or "", frontier=None, threshold=threshold)
            out["frontier_error"] = str(e)[:200]
        return out

    def list_providers(self) -> dict:
        return {"active": self.config.provider, "providers": self.credentials.status()}

    # --- MCP plumbing (dependency-free description + dispatch) ---
    def tool_specs(self) -> list[dict]:
        return [
            {
                "name": "route_estimate",
                "description": "Decide whether a prompt should be answered by the local on-device model or escalated to a frontier model, and estimate token savings. No inference is performed.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The user prompt to route."},
                        "context": {"type": "string", "description": "Optional retrieved context."},
                        "threshold": {"type": "number", "description": "Complexity threshold 0-1 (default 0.5)."},
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "compress_context",
                "description": "AXIOM-compress text (redact + compress) and return a skeleton digest plus raw/compressed token counts. Use before sending context to a frontier model to cut token cost.",
                "schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string", "description": "Text to compress."}},
                    "required": ["text"],
                },
            },
            {
                "name": "route_complete",
                "description": "Hybrid completion: simple prompts are answered fully on-device (zero frontier tokens); complex prompts are sent to a frontier model with only AXIOM-compressed context. Returns answer, route, and token savings.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "context": {"type": "string"},
                        "allow_cloud": {"type": "boolean", "description": "Permit frontier escalation (requires a connected provider)."},
                        "provider": {"type": "string", "description": "anthropic | openai | gemini (defaults to configured provider)."},
                        "threshold": {"type": "number"},
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "list_providers",
                "description": "List frontier providers and whether each is connected (API key or OAuth).",
                "schema": {"type": "object", "properties": {}},
            },
        ]

    def dispatch(self, name: str, arguments: dict | None = None) -> dict:
        args = arguments or {}
        if name == "route_estimate":
            return self.route_estimate(args["prompt"], args.get("context", ""), args.get("threshold", 0.5))
        if name == "compress_context":
            return self.compress_context(args.get("text", ""))
        if name == "route_complete":
            return self.route_complete(args["prompt"], args.get("context", ""), args.get("allow_cloud", False), args.get("provider"), args.get("threshold", 0.5))
        if name == "list_providers":
            return self.list_providers()
        raise KeyError(f"unknown tool: {name}")
