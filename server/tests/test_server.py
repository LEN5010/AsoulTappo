import pytest
from fastapi.testclient import TestClient

from app.main import app, manager
from app.rooms import MAX_ROOM_SIZE, RoomManager, new_room_id


@pytest.fixture(autouse=True)
def _clean():
    manager.rooms.clear()
    yield
    manager.rooms.clear()


def join(ws, room="r1", nick="a"):
    ws.send_json({"type": "join", "room": room, "nick": nick, "character": "嘉然"})
    return ws.receive_json()


def test_healthz():
    r = TestClient(app).get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_room_id_is_long_and_random():
    ids = {new_room_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(len(i) >= 20 for i in ids)


def test_room_manager_max_20():
    class Dummy:
        async def send_json(self, data): ...

    m = RoomManager()
    for i in range(MAX_ROOM_SIZE):
        m.join("x", f"n{i}", "c", Dummy())
    with pytest.raises(Exception):
        m.join("x", "extra", "c", Dummy())


def test_join_tap_emote_leave_broadcast():
    c = TestClient(app)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = join(a, nick="alice")
        assert ja["type"] == "joined" and len(ja["members"]) == 1
        jb = join(b, nick="bob")
        assert len(jb["members"]) == 2
        assert a.receive_json()["type"] == "member_joined"

        b.send_json({"type": "tap", "count": 7})
        ta = a.receive_json()
        assert ta["type"] == "tap" and ta["count"] == 7 and ta["total"] == 7 and ta["id"] == jb["you"]
        assert b.receive_json()["type"] == "tap"

        a.send_json({"type": "emote", "emote": "heart"})
        assert b.receive_json() == {"type": "emote", "id": ja["you"], "emote": "heart"}
        a.receive_json()

        b.send_json({"type": "leave"})
        assert a.receive_json() == {"type": "member_left", "id": jb["you"]}


def test_not_joined_and_bad_message():
    c = TestClient(app)
    with c.websocket_connect("/ws") as ws:
        ws.send_json({"type": "tap", "count": 1})
        assert ws.receive_json()["code"] == "not_joined"
        ws.send_json({"type": "nope"})
        assert ws.receive_json()["code"] == "bad_message"
        ws.send_json({"type": "tap", "count": 0})
        assert ws.receive_json()["code"] == "bad_message"


def test_room_full_over_websocket():
    c = TestClient(app)
    socks = []
    try:
        for i in range(MAX_ROOM_SIZE):
            ws = c.websocket_connect("/ws").__enter__()
            socks.append(ws)
            assert join(ws, room="full", nick=f"n{i}")["type"] == "joined"
        extra = c.websocket_connect("/ws").__enter__()
        socks.append(extra)
        extra.send_json({"type": "join", "room": "full", "nick": "x"})
        assert extra.receive_json()["code"] == "room_full"
    finally:
        for s in reversed(socks):
            s.__exit__(None, None, None)
