"""Rooms across a restart: what the server notes when it is told to stop, and what it gives back afterwards."""
import signal
import sqlite3

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
    manager.by_save.clear()
    manager.restoring.clear()
    yield
    manager.rooms.clear()
    manager.by_save.clear()
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
    assert m.snapshot() == [{"room": "x", "public": True, "host": "pa", "banned": ["pz"], "name": ""}]


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
    s.save_rooms([{"room": "x", "public": True, "host": "pa", "banned": ["pz"], "name": ""}], 100.0)
    s.save_rooms([{"room": "y", "public": False, "host": None, "banned": ["pz", "py"], "name": "自习室"}], 200.0)
    assert s.take_rooms() == [{"room": "y", "public": False, "host": None, "banned": ["pz", "py"], "saved": 200.0,
                               "name": "自习室"}]
    assert s.take_rooms() == []


def test_every_part_of_a_snapshot_comes_back_from_the_store():
    m = RoomManager()
    m.join("x", "a", "c", Dummy(), token="pa")
    m.rooms["x"].public = True
    m.rooms["x"].banned.add("pz")
    m.rename(m.rooms["x"], "自习室")
    s = Store(":memory:")
    s.save_rooms(m.snapshot(), 100.0)
    [back] = s.take_rooms()
    assert back.pop("saved") == 100.0
    assert [back] == m.snapshot()


def test_a_database_from_before_room_names_gets_the_column_and_its_rooms_come_back_without_one(tmp_path):
    path = str(tmp_path / "tappo.db")
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE room_restore (room TEXT PRIMARY KEY, public INTEGER NOT NULL, host TEXT, "
               "banned TEXT NOT NULL, saved REAL NOT NULL)")
    db.execute("INSERT INTO room_restore VALUES ('x', 1, 'pa', '[]', 100.0)")
    db.commit()
    db.close()
    s = Store(path)
    assert s.take_rooms() == [{"room": "x", "public": True, "host": "pa", "banned": [], "saved": 100.0, "name": ""}]
    s.save_rooms([{"room": "y", "public": False, "host": None, "banned": [], "name": "夜猫"}], 200.0)
    assert s.take_rooms()[0]["name"] == "夜猫"


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
        manager.by_save.clear()
        handler(signal.SIGTERM, None)
    finally:
        signal.signal(signal.SIGTERM, previous)
    assert seen == [signal.SIGTERM, signal.SIGTERM]
    assert main._stopping_rooms == [{"room": "x", "public": False, "host": "pa", "banned": [], "name": ""}]


def test_a_restarted_room_is_handed_back_to_its_host(monkeypatch):
    monkeypatch.setattr(main, "_stopping_rooms", None)
    host, removed = player_id_for(token("a")), player_id_for(token("z"))
    main.game.store.save_rooms([{"room": "r1", "public": True, "host": host, "banned": [removed], "name": "自习室"}],
                               main.game.now())
    with TestClient(app) as c:
        assert set(manager.restoring) == {"r1"}
        with c.websocket_connect("/ws") as z:
            refused = join(z, tok=token("z"))
            assert refused["code"] == "room_full" and refused["reason"] == "banned"
        with c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as a:
            jb = join(b, nick="b", tok=token("b"))
            assert jb["info"] == {"host": jb["you"], "public": False, "name": "自习室"}
            ja = join(a, nick="a", tok=token("a"))
            assert ja["info"] == {"host": ja["you"], "public": True, "name": "自习室"}
            assert b.receive_json()["type"] == "member_joined"
            assert b.receive_json() == {"type": "room_info", "host": ja["you"], "public": True, "name": "自习室"}
            assert c.get("/rooms").json()["rooms"][0]["room"] == "r1"
    # Without a stop signal (as in tests) nothing is saved for the next start.
    assert main.game.store.take_rooms() == []


# ------------------------------------------------------------------ two restarts in a row
def restart(store, wall, clock):
    """A start at wall time [wall]: the rooms of the last stop come back into a new manager on [clock]."""
    m = manager_at(clock)
    m.restore(store.take_rooms(), lambda entry: max(0.0, wall - entry["saved"]))
    return m


def named_public_room(m):
    m.join("x", "a", "c", Dummy(), token="pa")
    m.rename(m.rooms["x"], "夜间自习")
    m.rooms["x"].public = True
    m.rooms["x"].banned.add("pz")


def test_a_room_still_waiting_for_its_host_survives_a_second_restart():
    s = Store(":memory:")
    first = RoomManager()
    named_public_room(first)
    s.save_rooms(first.snapshot(), 100.0)
    second = restart(s, 101.0, [0.0])
    # Stopped again before anyone came back.
    s.save_rooms(second.snapshot(), 102.0)
    third = restart(s, 103.0, [0.0])
    with pytest.raises(Banned):
        third.join("x", "z", "c", Dummy(), token="pz")
    pa = third.join("x", "a", "c", Dummy(), token="pa")
    assert third.rooms["x"].info() == {"host": pa.id, "public": True, "name": "夜间自习"}


def test_a_room_carried_over_a_second_restart_keeps_its_first_deadline():
    def third_start(wall):
        s = Store(":memory:")
        first = RoomManager()
        named_public_room(first)
        s.save_rooms(first.snapshot(), 100.0)
        clock = [0.0]
        second = restart(s, 650.0, clock)
        clock[0] = 10.0
        s.save_rooms(second.snapshot(), 660.0)
        return restart(s, wall, [0.0])

    assert third_start(690.0).restoring["x"].name == "夜间自习"
    # 605 seconds after the first stop: gone, as it would be without the second restart.
    assert third_start(705.0).restoring == {}


def test_an_expired_room_is_not_carried_over():
    clock = [0.0]
    m = manager_at(clock)
    m.restore([{"room": "x", "public": True, "host": "pa", "banned": [], "name": "n"}], lambda entry: 590.0)
    clock[0] = 10.0
    assert m.snapshot() == []


def test_a_room_whose_members_came_back_first_keeps_the_hosts_claim():
    s = Store(":memory:")
    first = RoomManager()
    named_public_room(first)
    s.save_rooms(first.snapshot(), 100.0)
    clock = [0.0]
    second = restart(s, 400.0, clock)
    pb = second.join("x", "b", "c", Dummy(), token="pb")
    assert (second.rooms["x"].host, second.rooms["x"].public) == (pb.id, False)
    clock[0] = 5.0
    # One row per room: the table keys on the room.
    [entry] = second.snapshot()
    s.save_rooms([entry], 405.0)
    [row] = s.take_rooms()
    assert (row["host"], row["public"], row["banned"], row["name"]) == ("pa", True, ["pz"], "夜间自习")
    # The host's claim runs out when it would have without the restart.
    assert row["saved"] == pytest.approx(100.0)
    s.save_rooms([entry], 405.0)
    third = restart(s, 410.0, [0.0])
    third.join("x", "b", "c", Dummy(), token="pb")
    pa = third.join("x", "a", "c", Dummy(), token="pa")
    assert third.rooms["x"].info() == {"host": pa.id, "public": True, "name": "夜间自习"}


def test_a_live_room_without_a_pending_host_is_saved_as_it_is():
    clock = [0.0]
    m = manager_at(clock)
    m.restore([{"room": "x", "public": False, "host": None, "banned": ["pz"], "name": "n"}], lambda entry: 100.0)
    m.join("x", "b", "c", Dummy(), token="pb")
    m.rename(m.rooms["x"], "新名")
    assert m.snapshot() == [{"room": "x", "public": False, "host": "pb", "banned": ["pz"], "name": "新名"}]
