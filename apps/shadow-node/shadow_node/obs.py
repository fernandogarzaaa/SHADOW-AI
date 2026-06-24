"""Production observability + protection: token-bucket rate limiting and
structured JSON request logging. Both are zero-dependency and opt-in via env.
"""
from __future__ import annotations
import json, logging, sys, time


class RateLimiter:
    """In-memory token-bucket limiter, keyed per client (device id or IP)."""

    def __init__(self, rpm: int, burst: int | None = None):
        self.rate = rpm / 60.0
        self.capacity = burst or max(1, rpm)
        self._tokens: dict[str, float] = {}
        self._last: dict[str, float] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        tokens = self._tokens.get(key, self.capacity)
        tokens = min(self.capacity, tokens + (now - self._last.get(key, now)) * self.rate)
        self._last[key] = now
        if tokens < 1:
            self._tokens[key] = tokens
            return False
        self._tokens[key] = tokens - 1
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        if isinstance(record.args, dict):
            payload.update(record.args)
        for k in ("method", "path", "status", "ms", "client"):
            v = getattr(record, k, None)
            if v is not None:
                payload[k] = v
        return json.dumps(payload, default=str)


def configure_logging(name: str = "shadow") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(_JsonFormatter())
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def client_key(request) -> str:
    return (request.headers.get("x-shadow-device-id")
            or (request.client.host if request.client else "anon"))
