"""A room whose last member left: what is kept of it for its members coming back (rooms.EMPTY_SECONDS)."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

import app.rooms as rooms
from app.game import player_id_for
from app.main import app, manager
from app.rooms import EMPTY_SECONDS, RESTORE_SECONDS, Banned, RoomManager
from app.store import Store

from test_room_host import Dummy, join, token


@pytest.fixture(autouse=True)
def _clean():
    manager.rooms.clear()
    manager.by_save.clear()
    yield
    manager.rooms.clear()
    manager.by_save.clear()


def manager_at(clock):
    return RoomManager(clock=lambda: clock[0])


def named_room(m, room="x"):
    """A listed room "自习室" hosted by pa, with pb in it and pz removed; returns the two members."""
    pa = m.join(room, "a", "c", Dummy(), token="pa")
    pb = m.join(room, "b", "c", Dummy(), token="pb")
    m.rename(m.rooms[room], "自习室")
    m.rooms[room].public = True
    m.rooms[room].banned.add("pz")
    return pa, pb


# ------------------------------------------------------------------ manager
def test_a_room_that_empties_keeps_its_name_bans_and_listing_for_its_host():
    clock = [0.0]
    m = manager_at(clock)
    pa, pb = named_room(m)
    m.leave("x", pb.id)
    m.leave("x", pa.id)
    assert "x" not in m.rooms
    kept = m.restoring["x"]
    assert (kept.public, kept.host, kept.banned, kept.name) == (True, "pa", {"pz"}, "自习室")
    assert (kept.until, kept.keep) == (EMPTY_SECONDS, EMPTY_SECONDS)
    clock[0] = EMPTY_SECONDS - 1
    with pytest.raises(Banned):
        m.join("x", "z", "c", Dummy(), token="pz")
    # The first one back makes the room again with its name; the listing waits for the host.
    back = m.join("x", "b", "c", Dummy(), token="pb")
    assert m.rooms["x"].info() == {"host": back.id, "public": False, "name": "自习室"}
    with pytest.raises(Banned):
        m.join("x", "z", "c", Dummy(), token="pz")
    host = m.join("x", "a", "c", Dummy(), token="pa")
    assert m.rooms["x"].info() == {"host": host.id, "public": True, "name": "自习室"}
    assert "x" not in m.restoring


def test_the_host_kept_is_the_save_holding_the_role_when_the_room_emptied():
    m = RoomManager()
    pa, pb = named_room(m)
    # The host left first: the role went to pb, who left last.
    m.leave("x", pa.id)
    m.leave("x", pb.id)
    assert m.restoring["x"].host == "pb"
    back = m.join("x", "a", "c", Dummy(), token="pa")
    assert m.rooms["x"].info() == {"host": back.id, "public": False, "name": "自习室"}
    host = m.join("x", "b", "c", Dummy(), token="pb")
    assert m.rooms["x"].info() == {"host": host.id, "public": True, "name": "自习室"}


def test_a_room_with_nothing_to_miss_is_not_kept():
    m = RoomManager()
    pa = m.join("x", "a", "c", Dummy(), token="pa")
    m.leave("x", pa.id)
    assert m.restoring == {}
    # Each part alone is enough to keep it.
    for part in ("name", "public", "banned"):
        p = m.join(part, "a", "c", Dummy(), token="pa")
        if part == "name":
            m.rename(m.rooms[part], "夜猫")
        elif part == "public":
            m.rooms[part].public = True
        else:
            m.rooms[part].banned.add("pz")
        m.leave(part, p.id)
    assert list(m.restoring) == ["name", "public", "banned"]


def test_a_member_without_a_save_leaves_no_host_to_come_back():
    m = RoomManager()
    p = m.join("x", "a", "c", Dummy())
    m.rename(m.rooms["x"], "自习室")
    m.leave("x", p.id)
    assert m.restoring["x"].host is None
    back = m.join("x", "b", "c", Dummy(), token="pb")
    assert m.rooms["x"].info() == {"host": back.id, "public": False, "name": "自习室"}


def test_a_kept_room_runs_out():
    clock = [0.0]
    m = manager_at(clock)
    pa, pb = named_room(m)
    m.leave("x", pb.id)
    m.leave("x", pa.id)
    clock[0] = EMPTY_SECONDS
    # A room made again after that starts with nothing: no name, no bans, and its host is just the first one in.
    z = m.join("x", "z", "c", Dummy(), token="pz")
    assert m.rooms["x"].info() == {"host": z.id, "public": False, "name": ""}
    assert m.restoring == {}
    m.join("x", "a", "c", Dummy(), token="pa")
    assert m.rooms["x"].info() == {"host": z.id, "public": False, "name": ""}


def test_a_room_that_empties_again_is_kept_from_then():
    clock = [0.0]
    m = manager_at(clock)
    pa, pb = named_room(m)
    m.leave("x", pb.id)
    m.leave("x", pa.id)
    clock[0] = 100.0
    again = m.join("x", "a", "c", Dummy(), token="pa")
    m.rooms["x"].banned.add("py")
    clock[0] = 200.0
    m.leave("x", again.id)
    kept = m.restoring["x"]
    assert (kept.until, kept.banned, kept.public, kept.host) == (200.0 + EMPTY_SECONDS, {"pz", "py"}, True, "pa")


def test_a_listing_still_waiting_for_the_last_runs_host_goes_to_the_host_when_the_room_empties():
    m = RoomManager()
    m.restore([{"room": "x", "public": True, "host": "pa", "banned": [], "name": "自习室"}], lambda entry: 0.0)
    pb = m.join("x", "b", "c", Dummy(), token="pb")
    assert m.rooms["x"].info() == {"host": pb.id, "public": False, "name": "自习室"}
    m.leave("x", pb.id)
    kept = m.restoring["x"]
    assert (kept.host, kept.public, kept.keep) == ("pb", True, EMPTY_SECONDS)
    host = m.join("x", "b", "c", Dummy(), token="pb")
    assert m.rooms["x"].info() == {"host": host.id, "public": True, "name": "自习室"}


def test_a_plain_room_that_empties_drops_what_the_last_run_left_of_it():
    m = RoomManager()
    m.restore([{"room": "x", "public": False, "host": "pa", "banned": [], "name": ""}], lambda entry: 0.0)
    pb = m.join("x", "b", "c", Dummy(), token="pb")
    m.leave("x", pb.id)
    assert m.restoring == {}


def test_at_most_so_many_rooms_are_kept_and_the_one_kept_longest_goes_first(monkeypatch):
    monkeypatch.setattr(rooms, "RESTORE_MAX", 3)
    m = RoomManager()
    for n in range(5):
        p = m.join(f"r{n}", "a", "c", Dummy(), token="pa")
        m.rename(m.rooms[f"r{n}"], f"房间{n}")
        m.leave(f"r{n}", p.id)
    assert list(m.restoring) == ["r2", "r3", "r4"]
    # Emptying again counts as new.
    p = m.join("r2", "a", "c", Dummy(), token="pa")
    m.leave("r2", p.id)
    p = m.join("r5", "a", "c", Dummy(), token="pa")
    m.rename(m.rooms["r5"], "房间5")
    m.leave("r5", p.id)
    assert list(m.restoring) == ["r4", "r2", "r5"]


# ------------------------------------------------------------------ across a restart
def test_a_kept_room_lasts_its_own_time_across_a_restart():
    clock = [0.0]
    m = manager_at(clock)
    pa, pb = named_room(m)
    m.leave("x", pb.id)
    m.leave("x", pa.id)
    clock[0] = 1000.0
    [entry] = m.snapshot()
    assert (entry["age"], entry["keep"]) == (1000.0, EMPTY_SECONDS)
    s = Store(":memory:")
    s.save_rooms([entry], 5000.0)
    [row] = s.take_rooms()
    assert (row["saved"], row["keep"], row["name"], row["host"]) == (4000.0, EMPTY_SECONDS, "自习室", "pa")
    s.save_rooms([entry], 5000.0)

    def start(wall):
        after = manager_at([0.0])
        after.restore(s.take_rooms(), lambda e: max(0.0, wall - e["saved"]))
        return after

    # Down for an hour: still kept, until a day after the room emptied.
    after = start(5000.0 + 3600.0)
    assert after.restoring["x"].until == pytest.approx(EMPTY_SECONDS - 1000.0 - 3600.0)
    with pytest.raises(Banned):
        after.join("x", "z", "c", Dummy(), token="pz")
    host = after.join("x", "a", "c", Dummy(), token="pa")
    assert after.rooms["x"].info() == {"host": host.id, "public": True, "name": "自习室"}
    # Down past the day: gone.
    s.save_rooms([entry], 5000.0)
    assert start(4000.0 + EMPTY_SECONDS).restoring == {}


def test_rooms_of_the_last_run_keep_their_ten_minutes():
    m = RoomManager()
    m.join("x", "a", "c", Dummy(), token="pa")
    m.rename(m.rooms["x"], "自习室")
    s = Store(":memory:")
    s.save_rooms(m.snapshot(), 100.0)
    [row] = s.take_rooms()
    assert "keep" not in row
    after = manager_at([0.0])
    after.restore([row], lambda e: 30.0)
    assert (after.restoring["x"].until, after.restoring["x"].keep) == (RESTORE_SECONDS - 30.0, RESTORE_SECONDS)


def test_a_database_from_before_kept_rooms_gets_the_column(tmp_path):
    path = str(tmp_path / "tappo.db")
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE room_restore (room TEXT PRIMARY KEY, public INTEGER NOT NULL, host TEXT, "
               "banned TEXT NOT NULL, saved REAL NOT NULL, name TEXT NOT NULL DEFAULT '')")
    db.execute("INSERT INTO room_restore VALUES ('x', 1, 'pa', '[]', 100.0, '自习室')")
    db.commit()
    db.close()
    s = Store(path)
    assert s.take_rooms() == [{"room": "x", "public": True, "host": "pa", "banned": [], "saved": 100.0,
                               "name": "自习室"}]
    s.save_rooms([{"room": "y", "public": False, "host": None, "banned": [], "name": "夜猫", "age": 10.0,
                   "keep": EMPTY_SECONDS}], 200.0)
    [row] = s.take_rooms()
    assert (row["saved"], row["keep"]) == (190.0, EMPTY_SECONDS)


# ------------------------------------------------------------------ server
def test_members_coming_back_to_an_empty_room_find_its_name_and_host():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a:
        join(a, room="r1", nick="a", tok=token("a"))
        a.send_json({"type": "set_name", "name": "自习室"})
        assert a.receive_json()["type"] == "room_info"
    assert "r1" not in manager.rooms
    assert manager.restoring["r1"].host == player_id_for(token("a"))
    with c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as a:
        jb = join(b, room="r1", nick="b", tok=token("b"))
        assert jb["info"] == {"host": jb["you"], "public": False, "name": "自习室"}
        ja = join(a, room="r1", nick="a", tok=token("a"))
        assert ja["info"] == {"host": ja["you"], "public": False, "name": "自习室"}
        assert b.receive_json()["type"] == "member_joined"
        assert b.receive_json() == {"type": "room_info", "host": ja["you"], "public": False, "name": "自习室"}
