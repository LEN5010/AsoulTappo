"""A join with onlyOpen goes into a room that has members now and never makes one (a client going back to its room
on start)."""
import signal

import pytest
from fastapi.testclient import TestClient

from app.main import app, manager
from app.rooms import RoomClosed, RoomManager

from test_room_host import Dummy, join, token


@pytest.fixture(autouse=True)
def _clean():
    manager.rooms.clear()
    manager.by_save.clear()
    manager.restoring.clear()
    yield
    manager.rooms.clear()
    manager.by_save.clear()
    manager.restoring.clear()


@pytest.fixture()
def deadline():
    """WebSocket tests wait for a reply forever when it never comes: fail them after a while instead."""
    def expired(signum, frame):
        raise TimeoutError("no reply from the server")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(20)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, previous)


def test_the_manager_refuses_to_make_a_room_for_an_only_open_join():
    m = RoomManager()
    with pytest.raises(RoomClosed):
        m.join("x", "a", "c", Dummy(), token="pa", only_open=True)
    assert "x" not in m.rooms
    # A room of the last run nobody came back to is not open either.
    m.restore([{"room": "y", "public": True, "host": "pa", "banned": [], "name": "n"}], lambda entry: 0.0)
    with pytest.raises(RoomClosed):
        m.join("y", "a", "c", Dummy(), token="pa", only_open=True)
    assert "y" not in m.rooms and "y" in m.restoring
    first = m.join("x", "b", "c", Dummy(), token="pb")
    back = m.join("x", "a", "c", Dummy(), token="pa", only_open=True)
    assert [p.id for p in m.members("x")] == [first.id, back.id] and m.rooms["x"].host == first.id


def test_a_room_closed_between_the_lookup_and_the_join_is_not_made_again(deadline):
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as last:
        join(last, room="r1", nick="last", tok=token("last"))
    assert "r1" not in manager.rooms
    with c.websocket_connect("/ws") as back:
        back.send_json({"type": "join", "room": "r1", "nick": "a", "character": "嘉然", "token": token("a"),
                        "onlyOpen": True})
        refused = back.receive_json()
        assert refused["type"] == "error"
        # Final, like a full room: a client stops reconnecting.
        assert (refused["code"], refused["reason"]) == ("room_full", "room_closed")
        assert "r1" not in manager.rooms
        # The connection may still join a room the ordinary way.
        assert join(back, room="r2", nick="a", tok=token("a"))["type"] == "joined"


def test_an_only_open_join_of_a_room_with_members_goes_in(deadline):
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as here, c.websocket_connect("/ws") as back:
        first = join(here, room="r1", nick="here", tok=token("here"))
        back.send_json({"type": "join", "room": "r1", "nick": "a", "character": "嘉然", "token": token("a"),
                        "onlyOpen": True})
        joined = back.receive_json()
        assert joined["type"] == "joined" and joined["info"]["host"] == first["you"]
        assert len(joined["members"]) == 2
