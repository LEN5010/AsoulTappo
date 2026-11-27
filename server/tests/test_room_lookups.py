"""One address may ask GET /rooms/{id} only so many times within a window (main.ROOM_LOOKUPS)."""
from urllib.parse import quote

import pytest

import app.main as main

from test_accounts import env  # noqa: F401  (env is a fixture)


@pytest.fixture()
def limited(env, monkeypatch):
    where = ["203.0.113.7"]
    monkeypatch.setattr(main, "ROOM_LOOKUPS", 2)
    monkeypatch.setattr(main, "_room_lookups", {})
    monkeypatch.setattr(main, "_address", lambda request: where[0])
    return env[0], env[1], where


def test_an_address_looks_up_rooms_only_so_many_times_within_the_window(limited):
    c, g, where = limited
    assert c.get("/rooms/a").json() == {"room": "a", "open": False}
    assert c.get("/rooms/b").status_code == 200
    third = c.get("/rooms/c")
    assert third.status_code == 429 and third.json()["detail"]["code"] == "too_many_lookups"
    # another address is counted on its own
    where[0] = "203.0.113.8"
    assert c.get("/rooms/c").status_code == 200
    where[0] = "203.0.113.7"
    g.now.t += main.ROOM_LOOKUP_SECONDS - 1
    assert c.get("/rooms/c").status_code == 429
    g.now.t += 1
    assert c.get("/rooms/c").status_code == 200
    assert c.get("/rooms/d").status_code == 200
    assert c.get("/rooms/e").status_code == 429


def test_lookups_from_this_machine_are_not_counted(env, monkeypatch):
    c, *_ = env
    monkeypatch.setattr(main, "ROOM_LOOKUPS", 1)
    monkeypatch.setattr(main, "_room_lookups", {})
    for n in range(3):  # the test client has no address to count
        assert c.get(f"/rooms/r{n}").status_code == 200
    assert main._room_lookups == {}


def test_a_room_id_with_a_slash_is_looked_up_whole(env):
    c, *_ = env
    main.manager.join("音乐/夜场", "a", "c", None)
    try:
        assert c.get("/rooms/" + quote("音乐/夜场", safe="")).json() == {"room": "音乐/夜场", "open": True}
        # A proxy that decodes the slash on its way still asks for the same room.
        assert c.get("/rooms/音乐/夜场").json() == {"room": "音乐/夜场", "open": True}
        assert c.get("/rooms/" + quote("音乐/", safe="")).json() == {"room": "音乐/", "open": False}
    finally:
        main.manager.rooms.clear()
        main.manager.by_save.clear()
    # The routes next to it are unchanged.
    assert c.post("/rooms").json()["room"]
    # the list, which this server shows to accounts only
    assert c.get("/rooms").json()["detail"]["code"] == "account_required"
    # As before the room id could hold a slash: the address with one at the end goes to the list.
    moved = c.get("/rooms/", follow_redirects=False)
    assert moved.status_code == 307 and moved.headers["location"].endswith("/rooms")
    assert main._room_lookups == {}


def test_a_full_table_drops_ended_windows_before_any_running_one(limited, monkeypatch):
    c, g, where = limited
    monkeypatch.setattr(main, "ROOM_LOOKUP_ADDRESSES", 3)
    for n in range(3):
        where[0] = f"198.51.100.{n}"
        c.get("/rooms/a")
    g.now.t += main.ROOM_LOOKUP_SECONDS
    # This address uses up its lookups in a fresh window; the three above have ended theirs.
    where[0] = "203.0.113.7"
    c.get("/rooms/a")
    c.get("/rooms/a")
    assert "198.51.100.0" not in main._room_lookups
    for n in range(3, 5):
        where[0] = f"198.51.100.{n}"
        assert c.get("/rooms/a").status_code == 200
    where[0] = "203.0.113.7"
    assert c.get("/rooms/a").status_code == 429


def test_a_table_full_of_running_windows_still_has_room_for_new_addresses(limited, monkeypatch):
    c, g, where = limited
    monkeypatch.setattr(main, "ROOM_LOOKUP_ADDRESSES", 3)
    for n in range(10):
        where[0] = f"198.51.100.{n}"
        assert c.get("/rooms/a").status_code == 200
    assert len(main._room_lookups) <= main.ROOM_LOOKUP_ADDRESSES + 1


def test_a_window_that_starts_again_moves_behind_the_running_ones(limited, monkeypatch):
    c, g, where = limited
    monkeypatch.setattr(main, "ROOM_LOOKUP_ADDRESSES", 2)
    where[0] = "198.51.100.1"
    c.get("/rooms/a")
    g.now.t += 300
    where[0] = "198.51.100.2"
    c.get("/rooms/a")
    c.get("/rooms/a")
    g.now.t += 300
    # .1 has ended its window and starts a new one, now the newest; .2 is still in its own, with no lookups left.
    where[0] = "198.51.100.1"
    c.get("/rooms/a")
    g.now.t += 300
    where[0] = "198.51.100.3"
    c.get("/rooms/a")
    where[0] = "198.51.100.1"
    # .2's window has ended by now, so it goes first; .1's new one is kept with its one lookup.
    assert c.get("/rooms/a").status_code == 200
    assert c.get("/rooms/a").status_code == 429
