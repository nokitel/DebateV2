from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass
class Event:
    event: str
    data: dict[str, Any]

    def encode(self) -> str:
        return f"event: {self.event}\ndata: {json.dumps(self.data, default=str)}\n\n"


class EventBus:
    def __init__(self, queue_size: int = 200) -> None:
        self._queue_size = queue_size
        self._history: dict[str, deque[Event]] = defaultdict(lambda: deque(maxlen=queue_size))
        self._subscribers: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, debate_id: str, event: str, data: dict[str, Any]) -> None:
        payload = Event(event=event, data=data)
        async with self._lock:
            self._history[debate_id].append(payload)
            for queue in list(self._subscribers.get(debate_id, ())):
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        pass

    async def subscribe(self, debate_id: str, replay_history: bool = True) -> AsyncIterator[str]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            history = list(self._history.get(debate_id, ())) if replay_history else []
            self._subscribers[debate_id].add(queue)
        try:
            yield "event: connected\ndata: {}\n\n"
            for event in history:
                yield event.encode()
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield event.encode()
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            async with self._lock:
                self._subscribers[debate_id].discard(queue)


event_bus = EventBus()
