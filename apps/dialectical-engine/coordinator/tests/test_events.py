from __future__ import annotations

import asyncio

import pytest

from app.services.events import EventBus


@pytest.mark.asyncio
async def test_subscribe_replays_bounded_history_before_live_events() -> None:
    bus = EventBus(queue_size=2)
    await bus.publish("debate-1", "node_started", {"node_id": "root"})
    await bus.publish("debate-1", "node_token", {"node_id": "root", "delta": "hello"})

    stream = bus.subscribe("debate-1")
    try:
        connected = await asyncio.wait_for(stream.__anext__(), timeout=0.1)
        started = await asyncio.wait_for(stream.__anext__(), timeout=0.1)
        token = await asyncio.wait_for(stream.__anext__(), timeout=0.1)

        assert connected == "event: connected\ndata: {}\n\n"
        assert started.startswith("event: node_started\n")
        assert '"node_id": "root"' in started
        assert token.startswith("event: node_token\n")

        await bus.publish("debate-1", "node_complete", {"node_id": "root"})
        complete = await asyncio.wait_for(stream.__anext__(), timeout=0.1)
        assert complete.startswith("event: node_complete\n")
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_publish_drops_oldest_event_when_subscriber_queue_is_full() -> None:
    bus = EventBus(queue_size=1)
    stream = bus.subscribe("debate-1")
    try:
        connected = await asyncio.wait_for(stream.__anext__(), timeout=0.1)
        assert connected == "event: connected\ndata: {}\n\n"

        await bus.publish("debate-1", "node_token", {"delta": "first"})
        await asyncio.wait_for(bus.publish("debate-1", "node_token", {"delta": "second"}), timeout=0.1)

        event = await asyncio.wait_for(stream.__anext__(), timeout=0.1)
        assert '"delta": "second"' in event
        assert '"delta": "first"' not in event
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_publish_keeps_other_subscribers_when_one_queue_is_full() -> None:
    bus = EventBus(queue_size=1)
    slow_stream = bus.subscribe("debate-1")
    active_stream = bus.subscribe("debate-1")
    try:
        await asyncio.wait_for(slow_stream.__anext__(), timeout=0.1)
        await asyncio.wait_for(active_stream.__anext__(), timeout=0.1)

        await bus.publish("debate-1", "node_token", {"delta": "first"})
        active_first = await asyncio.wait_for(active_stream.__anext__(), timeout=0.1)
        assert '"delta": "first"' in active_first

        await asyncio.wait_for(bus.publish("debate-1", "node_token", {"delta": "second"}), timeout=0.1)

        active_second = await asyncio.wait_for(active_stream.__anext__(), timeout=0.1)
        slow_second = await asyncio.wait_for(slow_stream.__anext__(), timeout=0.1)
        assert '"delta": "second"' in active_second
        assert '"delta": "second"' in slow_second
    finally:
        await slow_stream.aclose()
        await active_stream.aclose()
