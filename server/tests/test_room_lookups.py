"""One address may ask GET /rooms/{id} only so many times within a window (main.ROOM_LOOKUPS)."""
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
