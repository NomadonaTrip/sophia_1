"""SSE event bus for real-time approval state broadcasts.

ApprovalEventBus supports multiple concurrent subscribers via asyncio.Queue.
The router publishes events after each approval action; the SSE endpoint
yields events to all connected frontend clients.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator


class ApprovalEventBus:
    """Publish/subscribe event bus for approval state changes.

    Subscribers get an asyncio.Queue that receives events. The subscribe()
    async generator yields events and cleans up in its finally block.
    """

    def __init__(self, max_subscribers: int = 10) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._max_subscribers = max_subscribers

    async def publish(self, event_type: str, data: dict) -> None:
        """Broadcast an event to all subscriber queues."""
        event = {"type": event_type, "data": data}
        # Copy list to avoid mutation during iteration
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop events for slow consumers rather than blocking
                pass

    async def subscribe(self) -> AsyncGenerator[dict, None]:
        """Yield events as they arrive.

        Cleans up the queue from subscribers on exit (generator close or error).
        """
        if len(self._subscribers) >= self._max_subscribers:
            return
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)


# Module-level singleton used by router and service
event_bus = ApprovalEventBus()
