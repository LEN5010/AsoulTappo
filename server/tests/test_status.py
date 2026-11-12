"""A member's status in a room: chosen from a fixed list, shown to the room, cleared with an empty one."""
import pytest
from fastapi.testclient import TestClient

from app.main import app, manager
from app.rooms import ROOM_STATUSES, room_status


@pytest.fixture(autouse=True)
def _clean():
    manager.rooms.clear()
    yield
    manager.rooms.clear()


def join(ws, nick, **extra):
    ws.send_json({"type": "join", "room": "status", "nick": nick, "character": "嘉然", **extra})
    return ws.receive_json()


def test_only_listed_statuses_show():
    assert ROOM_STATUSES == ("fish", "work", "study", "game", "music", "live")
    assert [room_status(s) for s in ("game", "", None, "chat", "GAME")] == ["game", None, None, None, None]


def test_a_status_from_joining_shows_to_the_room():
    c = TestClient(app).__enter__()  # single portal/loop for every socket
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = join(a, "a", status="game")
        assert ja["members"][0]["status"] == "game"
        jb = join(b, "b", status="chat")
        assert {m["nick"]: m["status"] for m in jb["members"]} == {"a": "game", "b": None}
        assert a.receive_json()["member"]["status"] is None


def test_a_status_changes_and_clears_with_state():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = join(a, "a")
        join(b, "b")
        a.receive_json()  # member_joined(b)
        # A status alone is a state of its own.
        a.send_json({"type": "state", "status": "music"})
        assert b.receive_json() == {"type": "state", "id": ja["you"], "character": "嘉然", "nick": "a", "plate": None,
                                    "status": "music"}
        a.receive_json()
        # A nick change keeps the status.
        a.send_json({"type": "state", "nick": "a2"})
        assert b.receive_json()["status"] == "music"
        a.receive_json()
        for cleared in ("", "chat"):
            a.send_json({"type": "state", "nick": "a2", "status": "work"})
            assert b.receive_json()["status"] == "work"
            a.receive_json()
            a.send_json({"type": "state", "nick": "a2", "status": cleared})
            assert b.receive_json()["status"] is None
            a.receive_json()
