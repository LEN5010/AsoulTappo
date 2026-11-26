"""Room names: the host names the room; members, the public list and a restart see it, blocked words masked."""
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import Game
from app.manifest import Manifest
from app.moderation import Blocklist
from app.rooms import ROOM_NAME_MAX, RoomManager, clean_room_name
from app.store import Store

from test_room_host import Dummy, join, token

KEY = {"X-Admin-Key": "admin-secret"}


@pytest.fixture()
def api(monkeypatch, tmp_path):
    store = Store(str(tmp_path / "tappo.db"))
    monkeypatch.setattr(main, "game", Game(store, Manifest.load()))
    monkeypatch.setattr(main, "blocklist", Blocklist())
    monkeypatch.setattr(main, "raw_nicks", {})
    monkeypatch.setattr(main, "ADMIN_KEY", "admin-secret")
    monkeypatch.setattr(main, "accounts", None)
    main.manager.rooms.clear()
    main.manager.by_save.clear()
    main.manager.restoring.clear()
    with TestClient(main.app) as c:
        yield c
    main.manager.rooms.clear()
    main.manager.by_save.clear()
    main.manager.restoring.clear()


def quiet(*sockets):
    """Nothing else is waiting: the next answer is the ping's."""
    for ws in sockets:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


@pytest.mark.parametrize("raw, clean", [
    ("  摸鱼  自习室 ", "摸鱼 自习室"),
    ("a\tb\nc", "a b c"),
    ("x​y\u0007", "xy"),
    ("", ""),
    (" 　 ", ""),
])
def test_names_lose_control_characters_and_extra_spaces(raw, clean):
    assert clean_room_name(raw) == clean


def test_the_host_names_the_room_and_everyone_hears_it(api):
    c = api
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = join(a, nick="a", tok=token("a"))
        assert ja["info"] == {"host": ja["you"], "public": False, "name": ""}
        join(b, nick="b", tok=token("b"))
        a.receive_json()  # b joined
        a.send_json({"type": "set_name", "name": "  摸鱼   自习室 "})
        info = {"type": "room_info", "host": ja["you"], "public": False, "name": "摸鱼 自习室"}
        assert a.receive_json() == info and b.receive_json() == info
        # The same name again answers the host only.
        a.send_json({"type": "set_name", "name": "摸鱼 自习室"})
        assert a.receive_json() == info
        quiet(b)
        b.send_json({"type": "set_name", "name": "抢"})
        assert b.receive_json()["code"] == "not_host"
        # A newcomer finds it in `joined`; a long name is cut, "" takes it off.
        with c.websocket_connect("/ws") as d:
            assert join(d, nick="d")["info"]["name"] == "摸鱼 自习室"
            a.receive_json(), b.receive_json()  # d joined
            a.send_json({"type": "set_name", "name": "长" * 40})
            assert a.receive_json()["name"] == "长" * ROOM_NAME_MAX
            a.send_json({"type": "set_name", "name": ""})
            assert a.receive_json()["name"] == ""
        assert a.receive_json()["type"] == "member_left"
        a.send_json({"type": "set_name", "name": "x" * 65})
        assert a.receive_json()["code"] == "bad_message"


def test_names_are_masked_listed_and_masked_again_with_a_new_list(api):
    c = api
    c.put("/admin/blocked-words", json={"words": ["坏词"]}, headers=KEY)
    with c.websocket_connect("/ws") as a:
        join(a, nick="a", tok=token("a"))
        a.send_json({"type": "set_name", "name": "坏词房"})
        assert a.receive_json()["name"] == "**房"
        a.send_json({"type": "set_public", "public": True})
        assert a.receive_json()["public"] is True
        assert c.get("/rooms").json()["rooms"][0]["name"] == "**房"
        c.put("/admin/blocked-words", json={"words": []}, headers=KEY)
        assert a.receive_json()["name"] == "坏词房"
        quiet(a)


def test_the_name_outlasts_a_restart_and_is_masked_when_it_comes_back():
    m = RoomManager()
    m.join("x", "a", "c", Dummy(), token="pa")
    m.rename(m.rooms["x"], "自习室")
    # A room with nothing else to keep keeps its name.
    m.join("y", "b", "c", Dummy())
    m.rename(m.rooms["y"], "夜猫")
    saved = m.snapshot()
    assert {e["room"]: e["name"] for e in saved} == {"x": "自习室", "y": "夜猫"}
    after = RoomManager()
    after.mask = lambda text: text.replace("猫", "*")
    after.restore(saved, lambda entry: 0.0)
    after.join("y", "c", "c", Dummy())
    assert after.rooms["y"].info()["name"] == "夜*"
    # Rooms saved by a server from before names come back without one.
    older = RoomManager()
    older.restore([{"room": "z", "public": False, "host": "pa", "banned": []}], lambda entry: 0.0)
    older.join("z", "a", "c", Dummy(), token="pa")
    assert older.rooms["z"].name == ""
