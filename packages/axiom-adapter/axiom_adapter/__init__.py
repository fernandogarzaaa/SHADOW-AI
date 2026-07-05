import os, re, hashlib
from typing import Optional


# ---------------------------------------------------------------------------
# Redaction layer
# ---------------------------------------------------------------------------
class RedactionLayer:
    """Redact PII and sensitive tokens before any context leaves the device."""

    patterns = [
        (re.compile(r"[\w.-]+@[\w.-]+"), "[EMAIL]"),
        (re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"), "[SSN]"),
        (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[CARD]"),
        (re.compile(r"(?i)(api[_ -]?key|token|password)\s*[:=]\s*\S+"), "[SECRET]"),
        (re.compile(r"(?i)(bearer\s+[a-z0-9_\-]{20,})"), "[TOKEN]"),
        (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[IP]"),
    ]

    def redact(self, text: str) -> str:
        for pat, replacement in self.patterns:
            text = pat.sub(replacement, text)
        return text


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------
class ContextCompressor:
    """Budget-aware compression with smart truncation that preserves edges."""

    def compress(self, text: str, budget: int = 1200) -> str:
        if len(text) <= budget:
            return text
        # Keep the beginning and end which usually carry the most signal.
        half = budget // 2
        return text[:half] + "\n…[AXIOM compressed — middle omitted]…\n" + text[-half:]


# ---------------------------------------------------------------------------
# Semantic skeleton generation
# ---------------------------------------------------------------------------
class SemanticSkeletonGenerator:
    """Extract a lightweight semantic skeleton from context for routing decisions."""

    _ENTITY_PATTERNS = {
        "email": re.compile(r"[\w.-]+@[\w.-]+"),
        "url": re.compile(r"https?://[^\s]+"),
        "date": re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s+\d{4})?\b", re.I),
        "project_ref": re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b"),
    }

    _INTENT_PATTERNS = {
        "summarize": re.compile(r"\b(summarize|summary|tldr|overview|brief)\b", re.I),
        "compare": re.compile(r"\b(compare|versus|vs|difference|better|worse)\b", re.I),
        "explain": re.compile(r"\b(explain|why|how does|what is|what are)\b", re.I),
        "action": re.compile(r"\b(create|send|draft|schedule|remind|write|delete|update)\b", re.I),
        "question": re.compile(r"\?\s*$"),
    }

    def generate(self, text: str) -> dict:
        entities = {}
        for label, pattern in self._ENTITY_PATTERNS.items():
            matches = list(set(pattern.findall(text)))
            if matches:
                entities[label] = matches[:10]  # cap to avoid bloat

        intents = []
        for label, pattern in self._INTENT_PATTERNS.items():
            if pattern.search(text):
                intents.append(label)

        return {
            "summary": text[:240] if len(text) <= 500 else text[:240] + " …",
            "entities": entities,
            "intents": intents,
            "word_count": len(text.split()),
        }


# ---------------------------------------------------------------------------
# Fingerprinting & drift detection
# ---------------------------------------------------------------------------
class Fingerprinter:
    def fingerprint(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()


class DriftDetector:
    def drift_score(self, old: str, new: str) -> float:
        """Simple normalized edit-distance approximation."""
        if old == new:
            return 0.0
        # Jaccard distance on word sets as a cheap proxy.
        old_words = set(old.lower().split())
        new_words = set(new.lower().split())
        union = old_words | new_words
        if not union:
            return 1.0
        return 1.0 - len(old_words & new_words) / len(union)


# ---------------------------------------------------------------------------
# Token budget estimation
# ---------------------------------------------------------------------------
class TokenBudgetEstimator:
    """Rough token estimation (~4 chars per token for English)."""

    def estimate(self, text: str) -> int:
        return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Semantic router — determines context priority and routing category
# ---------------------------------------------------------------------------
class SemanticRouter:
    """Deterministic content analysis for intelligent context routing.

    Mirrors the AXIOM-AETHER routing concept: classify context into priority
    tiers so the downstream planner knows which memory sources to trust most.
    """

    # Topic keywords for lightweight categorization.
    _TOPIC_KEYWORDS = {
        "project": ["project", "milestone", "deadline", "sprint", "ship", "launch"],
        "personal": ["preference", "like", "dislike", "style", "habit", "routine"],
        "contact": ["email", "phone", "contact", "meeting", "call", "spoke"],
        "finance": ["budget", "cost", "price", "invoice", "payment", "contract"],
        "technical": ["api", "code", "bug", "deploy", "server", "database", "error"],
    }

    def classify_topic(self, text: str) -> dict[str, float]:
        """Return topic → relevance scores (0-1)."""
        words = set(text.lower().split())
        scores = {}
        for topic, keywords in self._TOPIC_KEYWORDS.items():
            kw_set = set(keywords)
            scores[topic] = len(words & kw_set) / len(kw_set) if kw_set else 0.0
        return scores

    def relevance_score(self, query: str, context: str) -> float:
        """Compute a crude overlap score between query terms and context."""
        q_words = set(re.findall(r"[a-z0-9]+", query.lower()))
        c_words = set(re.findall(r"[a-z0-9]+", context.lower()))
        if not q_words:
            return 0.0
        return len(q_words & c_words) / len(q_words)

    def route_category(self, text: str) -> str:
        """Pick the dominant topic category for routing."""
        scores = self.classify_topic(text)
        if not scores:
            return "general"
        best = max(scores, key=scores.get)
        return best if scores[best] > 0.1 else "general"

    def build_routing_decision(self, query: str, context: str) -> dict:
        """Full routing analysis used by the hybrid router."""
        topic_scores = self.classify_topic(context)
        category = self.route_category(context)
        relevance = self.relevance_score(query, context)
        skeleton = SemanticSkeletonGenerator().generate(context)

        return {
            "category": category,
            "topic_scores": topic_scores,
            "relevance": round(relevance, 3),
            "intents": skeleton["intents"],
            "priority": "high" if relevance > 0.5 else "medium" if relevance > 0.2 else "low",
        }


# ---------------------------------------------------------------------------
# AXIOM runtime client
# ---------------------------------------------------------------------------
class AxiomRuntimeClient:
    def __init__(self, mode: str | None = None):
        self.mode = mode or os.getenv("AXIOM_RUNTIME_MODE", "deterministic")

    def available(self):
        return self.mode == "deterministic"

    def compress(self, text: str, budget: int):
        return ContextCompressor().compress(text, budget)


# ---------------------------------------------------------------------------
# Main adapter
# ---------------------------------------------------------------------------
class AxiomAdapter:
    def __init__(self, mode: str | None = None):
        self.redactor = RedactionLayer()
        self.compressor = ContextCompressor()
        self.fingerprinter = Fingerprinter()
        self.runtime = AxiomRuntimeClient(mode)
        self.router = SemanticRouter()
        self.skeleton_generator = SemanticSkeletonGenerator()

    def package_context(self, text: str, budget: int = 1200) -> dict:
        red = self.redactor.redact(text)
        compressed = (
            self.runtime.compress(red, budget)
            if self.runtime.available()
            else self.compressor.compress(red, budget)
        )
        skeleton = self.skeleton_generator.generate(red)
        routing = self.router.build_routing_decision("", red)

        return {
            "context": compressed,
            "fingerprint": self.fingerprinter.fingerprint(red),
            "tokens_estimated": TokenBudgetEstimator().estimate(red),
            "runtime_mode": self.runtime.mode,
            "fallback_used": not self.runtime.available(),
            "skeleton": skeleton,
            "routing": routing,
        }

    def analyze_for_routing(self, query: str, context: str) -> dict:
        """Standalone analysis entry-point used by the MCP tool layer."""
        red = self.redactor.redact(context)
        return self.router.build_routing_decision(query, red)
