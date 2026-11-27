"""A save whose input counts as automatic (app/guard.py) keeps its seat in a room, but the room sees none of its
taps and motion."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.game import player_id_for
from app.main import app, manager

TOKEN = "hidden-member-token-0001"
OTHER = "hidden-member-token-0002"
REST = {"dx": 0.0, "dy": 0.0, "keyDown": False, "left": False, "right": False}


@pytest.fixture
def auto(monkeypatch):
    """Saves the game takes for automatic: add a save id to hide it, remove it to show it again."""
    saves: set[str] = set()
    monkeypatch.setattr(main.game, "auto_input", lambda pid: pid in saves)
    # Taps wait for the room tick; without the wait they are out before the pong that synced() waits for.
    monkeypatch.setattr(manager, "motion_interval", 0)
    return saves


def join(ws, nick, token, **extra):
    ws.send_json({"type": "join", "room": "hidden", "nick": nick, "token": token, **extra})
    return ws.receive_json()


def synced(ws):
    """Everything sent before this has been handled once the pong is back."""
    ws.send_json({"type": "ping"})
    got = []
    while (msg := ws.receive_json()) != {"type": "pong"}:
        got.append(msg)
    return got


def test_the_room_sees_no_taps_or_motion_of_a_hidden_member(auto):
    manager.rooms.clear()
    manager.by_save.clear()
    with TestClient(app) as client, client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        me = join(a, "a", TOKEN)["you"]
        join(b, "b", OTHER)
        a.receive_json()  # b joined
        held = {"dx": 3.0, "dy": -2.0, "keyDown": True, "left": False, "right": False}
        a.send_json({"type": "motion", **held})
        a.send_json({"type": "tap", "count": 3})
        synced(a)
        assert synced(b) == [{"type": "motion", "id": me, **held}, {"type": "tap", "id": me, "count": 3, "total": 3}]

        auto.add(player_id_for(TOKEN))
        a.send_json({"type": "tap", "count": 5})
        a.send_json({"type": "motion", **held, "dx": 9.0})
        a.send_json({"type": "tap", "count": 5})
        a.send_json({"type": "emote", "emote": "e.01"})
        synced(a)
        # The key it held is let go in the room's view, once; its taps do not count; an emote is its own choice.
        seen = synced(b)
        assert [m for m in seen if m["type"] != "error"][0] == {"type": "motion", "id": me, **REST}
        assert not [m for m in seen if m["type"] in ("tap", "motion")][1:]
        assert manager.members("hidden")[0].taps == 3
        # The other member's input still reaches the hidden one.
        b.send_json({"type": "tap", "count": 2})
        synced(b)
        assert {"type": "tap", "id": manager.members("hidden")[1].id, "count": 2, "total": 2} in synced(a)

        auto.clear()
        a.send_json({"type": "tap", "count": 1})
        synced(a)
        # Shown again with the pose it holds now, then the tap.
        assert synced(b) == [{"type": "motion", "id": me, **held, "dx": 9.0},
                             {"type": "tap", "id": me, "count": 1, "total": 4}]


def test_packed_poses_of_a_hidden_member_build_on_what_it_sent(auto):
    manager.rooms.clear()
    manager.by_save.clear()
    with TestClient(app) as client, client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        me = join(a, "a", TOKEN, motionVersion=3)["you"]
        join(b, "b", OTHER)
        a.receive_json()
        a.send_json({"type": "pose", "x": 8, "y": 4, "b": 1})
        synced(a)
        assert synced(b) == [{"type": "motion", "id": me, "dx": 2.0, "dy": 1.0, "keyDown": True, "left": False,
                              "right": False}]
        auto.add(player_id_for(TOKEN))
        a.send_json({"type": "pose", "x": 12})
        a.send_json({"type": "pose", "b": 3})
        synced(a)
        assert synced(b) == [{"type": "motion", "id": me, **REST}]
        auto.clear()
        a.send_json({"type": "pose", "b": 2})
        synced(a)
        # First the pose it held while hidden, then the change this message made to it.
        assert synced(b) == [
            {"type": "motion", "id": me, "dx": 3.0, "dy": 1.0, "keyDown": True, "left": True, "right": False},
            {"type": "motion", "id": me, "dx": 3.0, "dy": 1.0, "keyDown": False, "left": True, "right": False}]
