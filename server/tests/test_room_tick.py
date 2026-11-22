"""One tick per room: edges, positions and taps gathered within it go out together, in as few messages per member
as that member's motion version reads (app/rooms.py)."""
import asyncio

from app.rooms import RoomManager


class Socket:
    def __init__(self):
        self.messages = []

    async def send_json(self, data):
        self.messages.append(data)

    async def close(self, code=1000):
        pass


async def settled():
    for _ in range(5):
        await asyncio.sleep(0)


def pose(**changes):
    return {"dx": 0.0, "dy": 0.0, "keyDown": False, "left": False, "right": False, **changes}


def room(versions):
    manager = RoomManager(motion_interval=60)
    peers = []
    for i, version in enumerate(versions):
        peer = manager.join("t", str(i), "c", Socket())
        peer.motion_version = version
        peers.append(peer)
    for peer in peers:
        if peer.motion_version >= 2:
            manager.subscribe_motion("t", peer, [p.id for p in peers])
    return manager, peers


def taps(manager, peer, *counts):
    for count in counts:
        peer.taps += count
        manager.tap("t", peer, count)


def test_a_version_4_member_gets_the_whole_tick_in_one_message():
    async def run():
        manager, (sender, other, watcher) = room([3, 3, 4])
        await settled()
        watcher.ws.messages.clear()
        await manager.motion("t", sender, pose(keyDown=True))
        await manager.motion("t", sender, pose(keyDown=True, dx=2.0))
        taps(manager, sender, 2, 3)
        taps(manager, other, 1)
        assert watcher.ws.messages == []  # all of it waits for the tick
        manager._flush_tick(manager.rooms["t"])
        await settled()
        assert watcher.ws.messages == [{"type": "room_tick", "motions": [
            {"id": sender.id, "b": 1}, {"id": sender.id, "x": 8}], "taps": [
            {"id": sender.id, "count": 5, "total": 5}, {"id": other.id, "count": 1, "total": 1}]}]
    asyncio.run(run())


def test_a_version_3_member_gets_one_motion_message_then_a_tap_message_per_member():
    async def run():
        manager, (sender, other, watcher) = room([3, 3, 3])
        await settled()
        watcher.ws.messages.clear()
        await manager.motion("t", sender, pose(left=True))
        await manager.motion("t", sender, pose(left=True, dy=1.0))
        taps(manager, sender, 4)
        taps(manager, other, 2, 2)
        manager._flush_tick(manager.rooms["t"])
        await settled()
        assert watcher.ws.messages == [
            {"type": "motion_edges", "edges": [{"id": sender.id, "b": 2}, {"id": sender.id, "y": 4}]},
            {"type": "tap", "id": sender.id, "count": 4, "total": 4},
            {"type": "tap", "id": other.id, "count": 4, "total": 4}]
        # The member who tapped hears its own taps too: its total comes from them.
        assert {"type": "tap", "id": sender.id, "count": 4, "total": 4} in sender.ws.messages
    asyncio.run(run())


def test_older_versions_get_positions_in_one_message_and_taps_at_the_tick():
    async def run():
        manager, (sender, v1, v2) = room([3, 1, 2])
        await settled()
        for peer in (v1, v2):
            peer.ws.messages.clear()
        await manager.motion("t", sender, pose())
        await manager.motion("t", sender, pose(dx=1.0))
        taps(manager, sender, 3)
        await settled()
        # The first pose is an edge for them (nothing before it): sent at once, as before the tick.
        assert [m["type"] for m in v1.ws.messages] == ["motion"]
        assert v2.ws.messages == []  # packed: it already holds the resting pose
        manager._flush_tick(manager.rooms["t"])
        await settled()
        assert v1.ws.messages[1:] == [
            {"type": "motion_batch", "motions": [{"id": sender.id, **pose(dx=1.0)}]},
            {"type": "tap", "id": sender.id, "count": 3, "total": 3}]
        assert v2.ws.messages == [
            {"type": "motion_delta", "motions": [{"id": sender.id, "x": 4}]},
            {"type": "tap", "id": sender.id, "count": 3, "total": 3}]
    asyncio.run(run())


def test_a_tick_with_nothing_for_a_member_sends_it_nothing():
    async def run():
        manager, (sender, watcher) = room([4, 4])
        await settled()
        watcher.ws.messages.clear()
        sender.ws.messages.clear()
        await manager.motion("t", sender, pose(right=True))
        manager._flush_tick(manager.rooms["t"])
        await settled()
        assert sender.ws.messages == []  # its own motion is not sent back
        assert len(watcher.ws.messages) == 1
    asyncio.run(run())


def test_the_tick_runs_by_itself_after_the_interval():
    async def run():
        manager = RoomManager(motion_interval=.01)
        sender = manager.join("t", "a", "c", Socket())
        watcher = manager.join("t", "b", "c", Socket())
        watcher.motion_version = 4
        taps(manager, sender, 1)
        assert manager.rooms["t"].motion_timer is not None
        await asyncio.sleep(.05)
        assert watcher.ws.messages[-1] == {"type": "room_tick", "motions": [],
                                           "taps": [{"id": sender.id, "count": 1, "total": 1}]}
        assert manager.rooms["t"].motion_timer is None
    asyncio.run(run())


def test_a_member_who_leaves_takes_its_pending_taps_along():
    async def run():
        manager, (sender, watcher) = room([4, 4])
        await settled()
        watcher.ws.messages.clear()
        taps(manager, sender, 3)
        manager.leave("t", sender.id)
        assert manager.rooms["t"].taps == {}
        manager._flush_tick(manager.rooms["t"])
        await settled()
        assert watcher.ws.messages == []
    asyncio.run(run())


def test_a_tick_for_a_room_that_emptied_does_nothing():
    async def run():
        manager, (sender,) = room([4])
        old = manager.rooms["t"]
        taps(manager, sender, 1)
        manager.leave("t", sender.id)
        manager._flush_tick(old)  # a timer that fired anyway
        assert "t" not in manager.rooms
    asyncio.run(run())


def test_ticks_waiting_in_an_outbox_join_up():
    async def run():
        manager, (sender, watcher) = room([4, 4])
        await settled()
        watcher.outbox.append(({"type": "pong"}, None))  # a writer still busy: later messages wait behind it
        watcher.enqueue({"type": "room_tick", "motions": [{"id": "a", "b": 1}], "taps": [
            {"id": "a", "count": 2, "total": 2}]})
        watcher.enqueue({"type": "room_tick", "motions": [{"id": "a", "b": 0}], "taps": [
            {"id": "a", "count": 3, "total": 5}, {"id": "b", "count": 1, "total": 9}]})
        assert len(watcher.outbox) == 2
        assert watcher.outbox[-1][0] == {"type": "room_tick", "motions": [{"id": "a", "b": 1}, {"id": "a", "b": 0}],
                                         "taps": [{"id": "a", "count": 5, "total": 5},
                                                  {"id": "b", "count": 1, "total": 9}]}
        await settled()
    asyncio.run(run())
