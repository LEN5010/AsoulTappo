import asyncio
import threading

import pytest
from fastapi import WebSocketDisconnect

import app.main as main
from app.rooms import RoomManager


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
        assert slow.closed and not bad.active
        assert good.messages == [
            {"type": "tap", "count": 1}, {"type": "member_left", "id": bad.id}]
        await manager.broadcast("r", {"type": "tap", "count": 2})
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
        assert len([m for m in good.messages if m["type"] == "member_left"]) == 1
    asyncio.run(run())


@pytest.mark.parametrize("method", ["profile_for", "owns_emote"])
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
