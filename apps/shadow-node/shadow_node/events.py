"""In-process publish/subscribe bus feeding the SSE stream.

Endpoints publish plain dicts of the form {"type": ..., "properties": {...}};
GET /agent/stream fans them out to every connected device as SSE
`data:` lines. Delivery is best-effort: a slow consumer's queue is bounded and
publish() never blocks or raises into the request path.

Threading: FastAPI runs sync endpoints in a worker thread pool, while each
SSE subscriber's queue is consumed by the server event loop. publish() therefore
schedules put_nowait onto the subscriber's loop with call_soon_threadsafe
instead of touching the queue from the worker thread.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("shadow_node.events")

# Bound per-subscriber queues so one stalled phone cannot grow memory unbounded.
MAX_QUEUE_SIZE = 256


class _Subscriber:
    __slots__ = ("queue", "loop")

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop | None):
        self.queue = queue
        self.loop = loop


class EventBus:
    def __init__(self) -> None:
        self._subs: set[_Subscriber] = set()

    def subscribe(self) -> asyncio.Queue:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None  # sync test context; publish() will put_nowait directly
        q: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._subs.add(_Subscriber(q, loop))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        for sub in list(self._subs):
            if sub.queue is q:
                self._subs.discard(sub)

    def subscriber_count(self) -> int:
        return len(self._subs)

    def _deliver(self, sub: _Subscriber, evt: dict) -> None:
        try:
            if sub.loop is not None and sub.loop.is_running():
                sub.loop.call_soon_threadsafe(sub.queue.put_nowait, evt)
            else:
                sub.queue.put_nowait(evt)
        except asyncio.QueueFull:
            log.warning("event subscriber queue full, dropping %s", evt.get("type"))
        except RuntimeError:
            # Loop closed under us; drop the event for this subscriber.
            pass

    def publish(self, event_type: str, properties: dict | None = None) -> int:
        """Fan out to all subscribers. Returns the number of queues reached."""
        evt = {"type": event_type, "properties": properties or {}}
        reached = 0
        for sub in list(self._subs):
            self._deliver(sub, evt)
            reached += 1
        return reached
