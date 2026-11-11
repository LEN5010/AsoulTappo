"""Rooms at the edges of their writers: a full outbox, members leaving mid-send, timers of an emptied room."""
import asyncio

import pytest

from app.rooms import RoomManager
from test_room_regressions import Socket, delivered


def test_a_full_outbox_refuses_more_and_the_slow_member_is_dropped():
    async def run():
        from app.rooms import MAX_OUTBOX
        manager = RoomManager(send_timeout=.05)
        good, slow = Socket(), Socket(slow=True)
        manager.join("o", "good", "c", good)
        stuck = manager.join("o", "slow", "c", slow)
        stuck.enqueue({"type": "tap", "n": -1})  # taken by the writer, which then waits on the socket
        await asyncio.sleep(0)
        for n in range(MAX_OUTBOX):
            stuck.enqueue({"type": "tap", "n": n})
        loop = asyncio.get_running_loop()
        refused = loop.create_future()
        stuck.enqueue({"type": "tap", "n": "one too many"}, refused)
        assert stuck.overloaded
        with pytest.raises(ConnectionError, match="outbox full"):
            await refused
        async def dropped():
            while stuck.active:
                await asyncio.sleep(.001)
        await asyncio.wait_for(dropped(), .5)
        await delivered(good, 1)
        assert good.messages[-1] == {"type": "member_left", "id": stuck.id}
        assert not stuck.outbox
    asyncio.run(run())


def test_a_send_to_a_member_who_already_left_fails_at_once():
    async def run():
        manager = RoomManager()
        peer = manager.join("l", "a", "c", Socket())
        manager.join("l", "b", "c", Socket())
        manager.leave("l", peer.id)
        with pytest.raises(ConnectionError, match="member left"):
            await peer.send({"type": "tap"}, 1)
    asyncio.run(run())


def test_a_send_waiting_on_a_slow_socket_fails_when_the_member_leaves():
    async def run():
        manager = RoomManager(send_timeout=5)
        peer = manager.join("w", "slow", "c", Socket(slow=True))
        manager.join("w", "other", "c", Socket())
        sending = asyncio.ensure_future(peer.send({"type": "tap"}, 5))
        await asyncio.sleep(0)
        queued = asyncio.ensure_future(peer.send({"type": "tap", "n": 2}, 5))
        await asyncio.sleep(0)
        manager.leave("w", peer.id)
        for future in (sending, queued):
            with pytest.raises(ConnectionError):
                await asyncio.wait_for(future, .5)
    asyncio.run(run())


def test_the_last_member_leaving_cancels_the_pending_motion_batch():
    async def run():
        manager = RoomManager(motion_interval=60)
        a = manager.join("m", "a", "c", Socket())
        manager.join("m", "b", "c", Socket())
        pose = {"dx": 0.0, "dy": 0.0, "keyDown": False, "left": False, "right": False}
        await manager.motion("m", a, pose)
        await manager.motion("m", a, {**pose, "dx": 3.0})
        timer = manager.rooms["m"].motion_timer
        assert timer is not None
        for peer in list(manager.rooms["m"].peers):
            manager.leave("m", peer)
        assert "m" not in manager.rooms
        assert timer.cancelled()
    asyncio.run(run())
