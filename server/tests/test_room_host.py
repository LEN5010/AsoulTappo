"""Room host, public rooms, the public list and removing members."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app, manager
from app.rooms import Banned, NeedSave, RoomManager


@pytest.fixture(autouse=True)
def _clean():
    manager.rooms.clear()
    yield
    manager.rooms.clear()


def token(name):
    return f"{name}-token-0123456789"


def join(ws, room="r1", nick="a", tok=None, character="嘉然"):
    msg = {"type": "join", "room": room, "nick": nick, "character": character}
    if tok:
        msg["token"] = tok
    ws.send_json(msg)
    return ws.receive_json()


class Dummy:
    def __init__(self):
        self.got = []

    async def send_json(self, data):
        self.got.append(data)

    async def close(self, code=1000):
        pass


def test_first_member_hosts_and_the_earliest_remaining_member_takes_over():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as d:
        ja = join(a, nick="a")
        assert ja["info"] == {"host": ja["you"], "public": False}
        jb = join(b, nick="b")
        assert jb["info"] == {"host": ja["you"], "public": False}
        a.receive_json()  # member_joined b
        jd = join(d, nick="d")
        a.receive_json()
        b.receive_json()  # member_joined d
        a.send_json({"type": "leave"})
        assert b.receive_json() == {"type": "member_left", "id": ja["you"]}
        assert b.receive_json() == {"type": "room_info", "host": jb["you"], "public": False}
        assert d.receive_json()["type"] == "member_left"
        assert d.receive_json() == {"type": "room_info", "host": jb["you"], "public": False}
        # a member who is not the host leaving keeps the host
        d.send_json({"type": "leave"})
        assert b.receive_json() == {"type": "member_left", "id": jd["you"]}
        b.send_json({"type": "ping"})
        assert b.receive_json() == {"type": "pong"}


def test_host_passes_on_when_the_host_connection_fails():
    async def run():
        m = RoomManager()
        a, b, d = Dummy(), Dummy(), Dummy()
        pa = m.join("x", "a", "c", a)
        pb = m.join("x", "b", "c", b)
        m.join("x", "d", "c", d)
        assert m.rooms["x"].host == pa.id
        await m._failed("x", pa)
        await asyncio.sleep(0)
        assert m.rooms["x"].host == pb.id
        assert {"type": "room_info", "host": pb.id, "public": False} in d.got
        assert d.got.index({"type": "member_left", "id": pa.id}) < d.got.index(
            {"type": "room_info", "host": pb.id, "public": False})

    asyncio.run(run())


def test_only_the_host_with_a_save_can_make_the_room_public():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        join(a, nick="a")  # no save
        join(b, nick="b", tok=token("b"))
        a.receive_json()
        b.send_json({"type": "set_public", "public": True})
        assert b.receive_json()["code"] == "not_host"
        a.send_json({"type": "set_public", "public": True})
        assert a.receive_json()["code"] == "host_needs_save"
        assert c.get("/rooms").json() == {"rooms": []}
        b.send_json({"type": "kick", "id": "nobody"})
        assert b.receive_json()["code"] == "not_host"


def test_public_rooms_are_listed_until_the_host_closes_them():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = join(a, nick="房主", tok=token("a"), character="贝拉")
        join(b, nick="b", tok=token("b"))
        a.receive_json()
        assert c.get("/rooms").json() == {"rooms": []}  # private by default
        a.send_json({"type": "set_public", "public": True})
        assert a.receive_json() == {"type": "room_info", "host": ja["you"], "public": True}
        assert b.receive_json() == {"type": "room_info", "host": ja["you"], "public": True}
        assert c.get("/rooms").json() == {"rooms": [
            {"room": "r1", "host": {"nick": "房主", "character": "贝拉"}, "members": 2, "max": 20},
        ]}
        a.send_json({"type": "set_public", "public": False})
        assert b.receive_json()["public"] is False
        assert c.get("/rooms").json() == {"rooms": []}
    assert c.post("/rooms").status_code == 200  # creating rooms is unchanged


def test_public_list_is_capped_and_keeps_full_rooms_after_the_others():
    m = RoomManager(max_size=2)
    for i in range(55):
        m.join(f"r{i}", f"h{i}", "嘉然", Dummy(), token=f"p{i}")
        m.rooms[f"r{i}"].public = True
    m.join("r7", "guest", "乃琳", Dummy(), token="g")  # r7 is now full
    m.join("private", "h", "嘉然", Dummy(), token="q")
    listed = m.public_rooms(50)
    assert len(listed) == 50
    assert listed[0]["room"] == "r0" and "r7" not in [r["room"] for r in listed]
    full = m.public_rooms(100)
    assert len(full) == 55 and full[-1] == {"room": "r7", "host": {"nick": "h7", "character": "嘉然"},
                                            "members": 2, "max": 2}
    assert "private" not in [r["room"] for r in full]
    # a full room still shows, after the rooms with space
    m2 = RoomManager(max_size=2)
    m2.join("full", "h", "嘉然", Dummy(), token="a")
    m2.join("full", "x", "嘉然", Dummy(), token="b")
    m2.join("open", "h", "嘉然", Dummy(), token="c")
    for room in m2.rooms.values():
        room.public = True
    assert [r["room"] for r in m2.public_rooms(50)] == ["open", "full"]


def test_public_room_refuses_members_without_a_save_as_a_final_room_full():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as d:
        join(a, nick="a", tok=token("a"))
        a.send_json({"type": "set_public", "public": True})
        a.receive_json()
        refused = join(b, nick="b")
        assert refused["type"] == "error" and refused["code"] == "room_full" and refused["reason"] == "need_save"
        assert join(d, nick="d", tok=token("d"))["type"] == "joined"


def test_members_without_a_save_already_inside_stay_when_the_room_goes_public():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        join(a, nick="a", tok=token("a"))
        jb = join(b, nick="b")
        a.receive_json()
        a.send_json({"type": "set_public", "public": True})
        a.receive_json()
        b.receive_json()
        assert [p.id for p in manager.members("r1")][1] == jb["you"]


def test_host_removes_a_member_whose_save_stays_out_until_the_room_closes():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = join(a, nick="a", tok=token("a"))
        jb = join(b, nick="b", tok=token("b"))
        a.receive_json()
        a.send_json({"type": "kick", "id": ja["you"]})
        assert a.receive_json()["code"] == "no_member"  # not the host itself
        b.send_json({"type": "kick", "id": ja["you"]})
        assert b.receive_json()["code"] == "not_host"
        a.send_json({"type": "kick", "id": jb["you"]})
        kicked = b.receive_json()
        assert kicked["type"] == "error" and kicked["code"] == "room_full" and kicked["reason"] == "kicked"
        assert a.receive_json() == {"type": "member_left", "id": jb["you"]}
        assert [p.id for p in manager.members("r1")] == [ja["you"]]

        with c.websocket_connect("/ws") as again:
            refused = join(again, nick="b2", tok=token("b"))
            assert refused["code"] == "room_full" and refused["reason"] == "banned"
            # the same connection may still go elsewhere
            assert join(again, room="r2", nick="b2", tok=token("b"))["type"] == "joined"
        with c.websocket_connect("/ws") as other:
            assert join(other, nick="d", tok=token("d"))["type"] == "joined"
            a.receive_json()

    # everyone left: the room and its bans are gone
    assert "r1" not in manager.rooms
    with c.websocket_connect("/ws") as b:
        assert join(b, nick="b", tok=token("b"))["type"] == "joined"


def test_removing_a_save_removes_its_other_connections_too():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as b2:
        join(a, nick="a", tok=token("a"))
        jb = join(b, nick="b", tok=token("b"))
        a.receive_json()
        join(b2, nick="b", tok=token("b"))
        a.receive_json()
        b.receive_json()
        a.send_json({"type": "kick", "id": jb["you"]})
        assert b.receive_json()["reason"] == "kicked"
        assert b2.receive_json() == {"type": "member_left", "id": jb["you"]}
        assert b2.receive_json()["reason"] == "kicked"
        assert len(manager.members("r1")) == 1


def test_a_member_without_a_save_can_be_removed_but_not_barred():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        join(a, nick="a", tok=token("a"))
        jb = join(b, nick="b")
        a.receive_json()
        a.send_json({"type": "kick", "id": jb["you"]})
        assert b.receive_json()["reason"] == "kicked"
        assert manager.rooms["r1"].banned == set()
        with c.websocket_connect("/ws") as again:
            assert join(again, nick="b")["type"] == "joined"


def test_room_manager_join_checks():
    m = RoomManager()
    m.join("x", "a", "c", Dummy(), token="a")
    m.rooms["x"].banned.add("b")
    with pytest.raises(Banned):
        m.join("x", "b", "c", Dummy(), token="b")
    m.rooms["x"].public = True
    with pytest.raises(NeedSave):
        m.join("x", "n", "c", Dummy())
    assert m.join("x", "d", "c", Dummy(), token="d").token == "d"


def test_messages_of_older_clients_and_servers_keep_their_shape():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as ws:
        # the 1.1 join, without any new field
        joined = join(ws, nick="a", tok=token("a"))
        assert set(joined) == {"type", "room", "you", "members", "info"}
        ws.send_json({"type": "tap", "count": 2})
        assert ws.receive_json()["type"] == "tap"
        ws.send_json({"type": "join", "room": "r1", "nick": "a", "character": "嘉然"})
        # plain errors carry no reason field
        assert ws.receive_json() == {"type": "error", "code": "already_joined", "message": ""}
        ws.send_json({"type": "set_public"})
        assert ws.receive_json()["code"] == "bad_message"


def test_setting_the_same_public_flag_again_answers_only_the_host():
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = join(a, nick="a", tok=token("a"))
        join(b, nick="b", tok=token("b"))
        a.receive_json()
        for _ in range(3):
            a.send_json({"type": "set_public", "public": False})
            assert a.receive_json() == {"type": "room_info", "host": ja["you"], "public": False}
        a.send_json({"type": "set_public", "public": True})
        assert a.receive_json()["public"] is True
        a.send_json({"type": "set_public", "public": True})
        assert a.receive_json()["public"] is True
        # b heard the one change only
        assert b.receive_json() == {"type": "room_info", "host": ja["you"], "public": True}
        b.send_json({"type": "ping"})
        assert b.receive_json() == {"type": "pong"}


def test_a_connection_whose_member_was_removed_counts_as_not_joined(monkeypatch):
    import app.main as main
    from fastapi import WebSocketDisconnect

    m = RoomManager()
    monkeypatch.setattr(main, "manager", m)

    async def remove():
        # As a failed writer or a kick does, with the connection still open; the room closes with it.
        peer = next(iter(m.rooms["r"].peers))
        await m.depart("r", peer)

    class Client:
        def __init__(self):
            self.sent = []
            self.steps = [{"type": "join", "room": "r", "nick": "a"}, remove,
                          {"type": "set_public", "public": True}, {"type": "kick", "id": "x"},
                          {"type": "motion", "dx": 1, "dy": 0, "keyDown": False, "left": False, "right": False},
                          {"type": "ping"}, {"type": "join", "room": "r2", "nick": "a"}]

        async def accept(self):
            pass

        async def send_json(self, data):
            self.sent.append(data)

        async def close(self, code=1000):
            pass

        async def receive_json(self):
            while self.steps and callable(self.steps[0]):
                await self.steps.pop(0)()
            if not self.steps:
                raise WebSocketDisconnect()
            await asyncio.sleep(0.01)  # lets the joined message out first
            return self.steps.pop(0)

    client = Client()
    asyncio.run(main.ws_endpoint(client))
    assert [x["type"] for x in client.sent] == ["joined", "error", "error", "error", "pong", "joined"]
    assert [x["code"] for x in client.sent if x["type"] == "error"] == ["not_joined"] * 3
    assert client.sent[-1]["room"] == "r2"


def test_the_leave_a_removed_client_sends_on_its_way_out_is_dropped_quietly():
    # Clients answer a final room_full with a last `leave`; the server closed that connection already.
    c = TestClient(app).__enter__()
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        join(a, nick="a", tok=token("a"))
        jb = join(b, nick="b", tok=token("b"))
        a.receive_json()
        a.send_json({"type": "kick", "id": jb["you"]})
        assert b.receive_json()["reason"] == "kicked"
        b.send_json({"type": "leave"})
        assert b.receive()["type"] == "websocket.close"
        a.send_json({"type": "ping"})
        assert a.receive_json()["type"] == "member_left"
        assert a.receive_json() == {"type": "pong"}
