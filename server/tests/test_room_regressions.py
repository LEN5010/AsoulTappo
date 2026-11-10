import asyncio
import threading

import pytest
from fastapi import WebSocketDisconnect

import app.main as main
from app.rooms import RoomManager


async def delivered(socket, count):
    async def wait():
        while len(socket.messages) < count:
            await asyncio.sleep(.001)
    await asyncio.wait_for(wait(), .5)


class Socket:
    def __init__(self, slow=False):
        self.messages = []
        self.slow = slow
        self.closed = False

    async def send_json(self, data):
        if self.slow:
            await asyncio.Event().wait()
        self.messages.append(data)

    async def close(self, code=1000):
        self.closed = True


def test_creating_ids_does_not_retain_empty_rooms():
    manager = RoomManager()
    ids = {manager.create_room() for _ in range(1000)}
    assert len(ids) == 1000
    assert manager.rooms == {}
    room = ids.pop()
    peer = manager.join(room, "one", "c", Socket())
    assert len(manager.rooms) == 1
    assert manager.leave(room, peer.id)
    assert not manager.leave(room, peer.id)
    assert manager.rooms == {}


def test_slow_receiver_is_closed_and_other_members_continue():
    async def run():
        manager = RoomManager(send_timeout=.02)
        good, slow = Socket(), Socket(slow=True)
        manager.join("r", "good", "c", good)
        bad = manager.join("r", "slow", "c", slow)
        await asyncio.wait_for(manager.broadcast("r", {"type": "tap", "count": 1}), .5)
        await delivered(good, 2)
        async def closed():
            while not slow.closed:
                await asyncio.sleep(.001)
        await asyncio.wait_for(closed(), .5)
        assert not bad.active
        assert good.messages == [
            {"type": "tap", "count": 1}, {"type": "member_left", "id": bad.id}]
        await manager.broadcast("r", {"type": "tap", "count": 2})
        await delivered(good, 3)
        assert good.messages[-1]["count"] == 2
        assert len(manager.members("r")) == 1
    asyncio.run(run())


def test_overlapping_broadcasts_remove_failed_peer_only_once():
    async def run():
        manager = RoomManager(send_timeout=.02)
        good, slow = Socket(), Socket(slow=True)
        manager.join("r", "good", "c", good)
        manager.join("r", "slow", "c", slow)
        await asyncio.gather(*(manager.broadcast("r", {"type": "tap", "count": i}) for i in range(2)))
        await delivered(good, 3)
        assert len([m for m in good.messages if m["type"] == "member_left"]) == 1
    asyncio.run(run())


@pytest.mark.parametrize("method", ["profile_for", "owns_emote", "owns_character"])
def test_database_work_does_not_block_other_event_loop_tasks(monkeypatch, method):
    entered, release = threading.Event(), threading.Event()

    def blocked(*args):
        entered.set()
        release.wait(2)
        return {"uid": None} if method == "profile_for" else True

    monkeypatch.setattr(main.game, method, blocked)
    monkeypatch.setattr(main, "manager", RoomManager())

    class Client(Socket):
        def __init__(self):
            super().__init__()
            self.queue = [
                {"type": "join", "room": "r", "nick": "n", "token": "test-player-000000"},
                {"type": "emote", "emote": "thumbup"},
            ]

        async def accept(self):
            pass

        async def receive_json(self):
            if self.queue:
                return self.queue.pop(0)
            raise WebSocketDisconnect()

    async def run():
        task = asyncio.create_task(main.ws_endpoint(Client()))
        try:
            # A synchronous DB call would consume the 2s wait before this task runs.
            started = asyncio.get_running_loop().time()
            while not entered.is_set():
                await asyncio.sleep(.001)
            assert asyncio.get_running_loop().time() - started < 1
        finally:
            release.set()
            await task
    asyncio.run(run())


def test_room_batches_continuous_motion_and_keeps_button_edges_ordered():
    async def run():
        manager = RoomManager(motion_interval=.01)
        a, b = Socket(), Socket()
        sender = manager.join("r", "a", "c", a)
        receiver = manager.join("r", "b", "c", b)
        pose = {"dx": 0, "dy": 0, "keyDown": False, "left": False, "right": False}
        await manager.motion("r", sender, pose)
        await delivered(b, 1)
        for dx in range(1, 20):
            await manager.motion("r", sender, {**pose, "dx": dx})
        await delivered(b, 2)
        assert b.messages[1] == {"type": "motion_batch", "motions": [{**pose, "dx": 19, "id": sender.id}]}
        await manager.motion("r", sender, {**pose, "left": True})
        await manager.motion("r", sender, pose)
        await delivered(b, 4)
        assert [m["left"] for m in b.messages[2:]] == [True, False]
        assert a.messages == []
        manager.leave("r", sender.id)
        manager.leave("r", receiver.id)
        assert not manager.rooms
    asyncio.run(run())


def test_slow_receiver_does_not_hold_up_broadcast_and_motion_backlog_is_coalesced():
    async def run():
        manager = RoomManager(send_timeout=.1)
        good, slow = Socket(), Socket(slow=True)
        a = manager.join("r", "good", "c", good)
        b = manager.join("r", "slow", "c", slow)
        started = asyncio.get_running_loop().time()
        await manager.broadcast("r", {"type": "tap", "count": 1})
        await delivered(good, 1)
        assert asyncio.get_running_loop().time() - started < .05
        for i in range(100):
            await manager.broadcast("r", {"type": "motion_batch", "motions": [{"id": a.id, "dx": i}]})
        assert len(b.outbox) <= 2
        assert b.outbox[-1][0]["motions"] == [{"id": a.id, "dx": 99}]
        manager.leave("r", a.id)
        manager.leave("r", b.id)
    asyncio.run(run())


def packed(manager, room, name, socket):
    peer = manager.join(room, name, "c", socket)
    peer.motion_version = 2
    return peer


REST = {"dx": 0, "dy": 0, "keyDown": False, "left": False, "right": False}


def test_packed_motion_reaches_subscribers_only_and_carries_changed_fields():
    async def run():
        manager = RoomManager(motion_interval=.01)
        a, b, c = Socket(), Socket(), Socket()
        sender = packed(manager, "r", "a", a)
        watching = packed(manager, "r", "b", b)
        away = packed(manager, "r", "c", c)
        await manager.motion("r", sender, {**REST, "dx": 1.3, "dy": -2})
        # Nobody asked for the sender yet: not even its first pose goes out.
        await asyncio.sleep(.03)
        assert b.messages == [] and c.messages == []
        manager.subscribe_motion("r", watching, [sender.id, watching.id, "gone"])
        await delivered(b, 1)
        # Quarter pixels; the snapshot brings a subscriber up to the pose already held.
        assert b.messages[0] == {"type": "motion_snapshot", "motions": [{"id": sender.id, "x": 5, "y": -8, "b": 0}]}
        assert watching.motion_ids == {sender.id}
        await manager.motion("r", sender, {**REST, "dx": 2, "dy": -2})
        await delivered(b, 2)
        assert b.messages[1] == {"type": "motion_delta", "motions": [{"id": sender.id, "x": 8}]}
        # A pose that rounds to what was sent costs nothing.
        await manager.motion("r", sender, {**REST, "dx": 2.1, "dy": -2})
        await asyncio.sleep(.03)
        assert len(b.messages) == 2
        # Button edges go at once, in order, with the position they happened at.
        await manager.motion("r", sender, {**REST, "dx": 3, "dy": -2, "keyDown": True, "right": True})
        await manager.motion("r", sender, {**REST, "dx": 3, "dy": -2})
        await delivered(b, 4)
        assert b.messages[2:] == [{"type": "motion_edge", "id": sender.id, "x": 12, "b": 5},
                                  {"type": "motion_edge", "id": sender.id, "b": 0}]
        assert c.messages == [] and a.messages == []
        # Unsubscribing stops the stream; subscribing again starts from a fresh snapshot.
        manager.subscribe_motion("r", watching, [])
        await manager.motion("r", sender, {**REST, "dx": -4})
        await asyncio.sleep(.03)
        assert len(b.messages) == 4
        manager.subscribe_motion("r", watching, [sender.id])
        await delivered(b, 5)
        assert b.messages[4] == {"type": "motion_snapshot", "motions": [{"id": sender.id, "x": -16, "y": 0, "b": 0}]}
        for peer in (sender, watching, away):
            manager.leave("r", peer.id)
    asyncio.run(run())


def test_packed_and_older_members_share_a_room():
    async def run():
        manager = RoomManager(motion_interval=.01)
        a, b, c = Socket(), Socket(), Socket()
        old = manager.join("r", "old", "c", a)
        new = packed(manager, "r", "new", b)
        other = packed(manager, "r", "other", c)
        manager.subscribe_motion("r", other, [old.id, new.id])
        await delivered(c, 1)
        # The newer client moves with `pose`, which names changed fields only.
        await manager.pose("r", new, {"x": 6, "b": 2})
        await manager.pose("r", new, {"y": -3})
        await delivered(a, 2)
        # An older member hears everyone, in the 1.1 shape.
        assert a.messages == [
            {"type": "motion", "id": new.id, **REST, "dx": 1.5, "left": True},
            {"type": "motion_batch", "motions": [{"id": new.id, **REST, "dx": 1.5, "dy": -.75, "left": True}]}]
        await manager.motion("r", old, {**REST, "dx": .26})
        await delivered(c, 4)
        assert c.messages[1:] == [{"type": "motion_edge", "id": new.id, "x": 6, "b": 2},
                                  {"type": "motion_delta", "motions": [{"id": new.id, "y": -3}]},
                                  {"type": "motion_edge", "id": old.id, "x": 1}]
        assert b.messages == []
        for peer in (old, new, other):
            manager.leave("r", peer.id)
    asyncio.run(run())


def test_a_member_who_leaves_is_dropped_from_every_subscription():
    async def run():
        manager = RoomManager(motion_interval=.01)
        a, b = Socket(), Socket()
        sender = packed(manager, "r", "a", a)
        watching = packed(manager, "r", "b", b)
        manager.subscribe_motion("r", watching, [sender.id])
        await delivered(b, 1)
        manager.leave("r", sender.id)
        assert watching.motion_ids == set() and watching.sent_motion == {}
        manager.leave("r", watching.id)
    asyncio.run(run())


def test_queued_packed_batches_merge_field_by_field():
    async def run():
        manager = RoomManager(send_timeout=.1)
        good, slow = Socket(), Socket(slow=True)
        a = manager.join("r", "good", "c", good)
        b = manager.join("r", "slow", "c", slow)
        await manager.broadcast("r", {"type": "tap", "count": 1})
        b.enqueue({"type": "motion_delta", "motions": [{"id": a.id, "x": 1, "b": 1}]})
        b.enqueue({"type": "motion_delta", "motions": [{"id": a.id, "x": 2}, {"id": "z", "y": 3}]})
        b.enqueue({"type": "motion_delta", "motions": [{"id": a.id, "y": 4}]})
        assert len(b.outbox) <= 2
        assert b.outbox[-1][0] == {"type": "motion_delta", "motions": [{"id": a.id, "x": 2, "b": 1, "y": 4},
                                                                    {"id": "z", "y": 3}]}
        manager.leave("r", a.id)
        manager.leave("r", b.id)
    asyncio.run(run())
