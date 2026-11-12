"""Rooms across a restart: what the server notes when it is told to stop, and what it gives back afterwards."""
import signal

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import player_id_for
from app.main import app, manager
from app.rooms import RESTORE_SECONDS, Banned, RoomManager
from app.store import Store

from test_room_host import Dummy, join, token


@pytest.fixture(autouse=True)
def _clean():
    manager.rooms.clear()
    manager.restoring.clear()
    yield
    manager.rooms.clear()
    manager.restoring.clear()


def manager_at(clock):
    return RoomManager(clock=lambda: clock[0])


# ------------------------------------------------------------------ manager
def test_a_snapshot_keeps_the_listing_the_host_save_and_the_removed_saves():
    m = RoomManager()
    m.join("x", "a", "c", Dummy(), token="pa")
    m.join("x", "b", "c", Dummy(), token="pb")
    m.rooms["x"].public = True
    m.rooms["x"].banned.add("pz")
    # A room whose host has no save and that nobody listed or guarded has nothing to keep.
    m.join("y", "c", "c", Dummy())
    assert m.snapshot() == [{"room": "x", "public": True, "host": "pa", "banned": ["pz"]}]


def test_the_host_of_the_last_run_takes_its_room_back():
    clock = [0.0]
    m = manager_at(clock)
    m.restore([{"room": "x", "public": True, "host": "pa", "banned": ["pz"]}], lambda entry: 30.0)
    # A removed save stays out, also as the first one back.
    with pytest.raises(Banned):
        m.join("x", "z", "c", Dummy(), token="pz")
    assert "x" not in m.rooms
    pb = m.join("x", "b", "c", Dummy(), token="pb")
    # Until the host is back, the first one in holds the room and it is not listed.
    assert (m.rooms["x"].host, m.rooms["x"].public) == (pb.id, False)
    with pytest.raises(Banned):
        m.join("x", "z", "c", Dummy(), token="pz")
    pa = m.join("x", "a", "c", Dummy(), token="pa")
    assert (m.rooms["x"].host, m.rooms["x"].public) == (pa.id, True)
    assert "x" not in m.restoring


def test_a_returning_host_that_may_not_list_gets_the_role_only():
    m = RoomManager()
    m.restore([{"room": "x", "public": True, "host": "pa", "banned": []}], lambda entry: 0.0)
    pa = m.join("x", "a", "c", Dummy(), token="pa", may_list=False)
    assert (m.rooms["x"].host, m.rooms["x"].public) == (pa.id, False)


def test_a_listing_set_meanwhile_is_kept():
    m = RoomManager()
    m.restore([{"room": "x", "public": False, "host": "pa", "banned": []}], lambda entry: 0.0)
    m.join("x", "b", "c", Dummy(), token="pb")
    m.rooms["x"].public = True
    m.join("x", "a", "c", Dummy(), token="pa")
    assert m.rooms["x"].public


def test_what_the_last_run_left_runs_out():
    clock = [0.0]
    m = manager_at(clock)
    m.restore([{"room": "x", "public": True, "host": "pa", "banned": ["pz"]},
               {"room": "old", "public": True, "host": "pa", "banned": []}],
              lambda entry: RESTORE_SECONDS - 10 if entry["room"] == "x" else RESTORE_SECONDS)
    assert set(m.restoring) == {"x"}
    clock[0] = 10
    pb = m.join("x", "b", "c", Dummy(), token="pb")
    m.join("x", "z", "c", Dummy(), token="pz")
    m.join("x", "a", "c", Dummy(), token="pa")
    assert (m.rooms["x"].host, m.rooms["x"].public) == (pb.id, False)
    assert "x" not in m.restoring


# ------------------------------------------------------------------ store
def test_the_store_hands_the_rooms_back_once():
    s = Store(":memory:")
    s.save_rooms([{"room": "x", "public": True, "host": "pa", "banned": ["pz"]}], 100.0)
    s.save_rooms([{"room": "y", "public": False, "host": None, "banned": ["pz", "py"]}], 200.0)
    assert s.take_rooms() == [{"room": "y", "public": False, "host": None, "banned": ["pz", "py"], "saved": 200.0}]
    assert s.take_rooms() == []


# ------------------------------------------------------------------ server
def test_the_stop_signal_notes_the_rooms_before_the_server_closes_them(monkeypatch):
    monkeypatch.setattr(main, "_stopping_rooms", None)
    seen = []
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda signum, frame: seen.append(signum))
    try:
        manager.join("x", "a", "c", Dummy(), token="pa")
        main._note_rooms_on_stop()
        handler = signal.getsignal(signal.SIGTERM)
        handler(signal.SIGTERM, None)
        # A second signal keeps the first snapshot, taken before any connection closed.
        manager.rooms.clear()
        handler(signal.SIGTERM, None)
    finally:
        signal.signal(signal.SIGTERM, previous)
    assert seen == [signal.SIGTERM, signal.SIGTERM]
    assert main._stopping_rooms == [{"room": "x", "public": False, "host": "pa", "banned": []}]


def test_a_restarted_room_is_handed_back_to_its_host(monkeypatch):
    monkeypatch.setattr(main, "_stopping_rooms", None)
    host, removed = player_id_for(token("a")), player_id_for(token("z"))
    main.game.store.save_rooms([{"room": "r1", "public": True, "host": host, "banned": [removed]}], main.game.now())
    with TestClient(app) as c:
        assert set(manager.restoring) == {"r1"}
        with c.websocket_connect("/ws") as z:
            refused = join(z, tok=token("z"))
            assert refused["code"] == "room_full" and refused["reason"] == "banned"
        with c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as a:
            jb = join(b, nick="b", tok=token("b"))
            assert jb["info"] == {"host": jb["you"], "public": False}
            ja = join(a, nick="a", tok=token("a"))
            assert ja["info"] == {"host": ja["you"], "public": True}
            assert b.receive_json()["type"] == "member_joined"
            assert b.receive_json() == {"type": "room_info", "host": ja["you"], "public": True}
            assert c.get("/rooms").json()["rooms"][0]["room"] == "r1"
    # Without a stop signal (as in tests) nothing is saved for the next start.
    assert main.game.store.take_rooms() == []
