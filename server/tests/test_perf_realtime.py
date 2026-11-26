"""The room server's send path and indexes under load: a writer that falls behind, one text frame a broadcast, poses
packed once a tick, the saves' room index, frames read and checked in one pass, and expired restore entries."""
import asyncio
import json
import random
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from starlette.websockets import WebSocket, WebSocketState

import app.main as main
from app import rooms
from app.ddz import BID, Seat, Table
from app.models import client_message_adapter, parse_client_text
from app.rooms import RESTING, RESTORE_SECONDS, Banned, RoomManager
from test_ddz_match import MatchWorld
from test_duel import settle
from test_room_regressions import Socket


class Held:
    """A socket whose sends wait for [gate]."""

    def __init__(self):
        self.gate = asyncio.Event()
        self.messages = []

    async def send_json(self, data):
        await self.gate.wait()
        self.messages.append(json.loads(json.dumps(data)))

    async def close(self, code=1000):
        pass


# ------------------------------------------------------------------ a writer that falls behind
@pytest.mark.parametrize("kind", ["motion_edges", "room_tick"])
def test_a_writer_that_falls_behind_extends_one_batch_in_place(kind):
    batch = {"motion_edges": "edges", "room_tick": "motions"}[kind]
    tick = kind == "room_tick"

    def message(i, taps=None):
        out = {"type": kind, batch: [{"id": "m", "b": i % 2}]}
        if tick:
            out["taps"] = taps if taps is not None else [{"id": "t", "count": 1, "total": i + 1}]
        return out

    async def run():
        manager = RoomManager()
        socket = Held()
        peer = manager.join("r", "a", "嘉然", socket)
        peer.enqueue({"type": "pong"})
        await settle()  # the writer holds the pong at the gate
        shared = [{"id": "t", "count": 1, "total": 1}]
        first = message(0, shared)
        peer.enqueue(first)
        lists = set()
        for i in range(1, 600):
            peer.enqueue(message(i))
            lists.add(id(peer.outbox[-1][0][batch]))
        assert len(peer.outbox) == 1
        assert len(lists) == 1  # copied once, then extended
        assert first == message(0, [{"id": "t", "count": 1, "total": 1}])
        assert shared == [{"id": "t", "count": 1, "total": 1}]
        merged = peer.outbox[-1][0]
        expected = {"type": kind, batch: [{"id": "m", "b": i % 2} for i in range(600)]}
        if tick:
            expected["taps"] = [{"id": "t", "count": 600, "total": 600}]
        assert merged == expected
        assert not peer.overloaded
        socket.gate.set()
        await peer.send({"type": "pong"}, 1)
        assert socket.messages == [{"type": "pong"}, expected, {"type": "pong"}]

    asyncio.run(run())


# ------------------------------------------------------------------ one text frame a broadcast
def test_broadcast_shares_one_text_frame_and_supports_json_only_senders(monkeypatch):
    class TextSocket(Socket):
        async def send_text(self, message):
            self.messages.append(message)

    encodings = []

    def encode(data, **options):
        message = json.dumps(data, **options)
        encodings.append(message)
        return message

    monkeypatch.setattr(rooms, "json", SimpleNamespace(dumps=encode))

    async def run():
        manager = RoomManager()
        peers = [manager.join("r", str(i), "嘉然", socket)
                 for i, socket in enumerate((TextSocket(), TextSocket(), Socket(), Socket()))]
        message = {"type": "room_info", "name": "汽水铺"}
        await manager.broadcast("r", message, exclude=peers[-1].id)
        for peer in peers:
            await peer.send({"type": "pong"}, 1)
        assert encodings == ['{"type":"room_info","name":"汽水铺"}']
        assert peers[0].ws.messages[0] is peers[1].ws.messages[0] is encodings[0]
        assert peers[2].ws.messages[0] == message
        assert peers[-1].ws.messages == [{"type": "pong"}]
        first = {"type": "room_tick", "motions": [{"id": "m", "b": 1}], "taps": []}
        last = {"type": "room_tick", "motions": [{"id": "m", "b": 0}], "taps": []}
        await manager.broadcast("r", first)
        peers[0].enqueue(last)
        for peer in peers:
            await peer.send({"type": "pong"}, 1)
        assert peers[0].ws.messages[-2]["motions"] == first["motions"] + last["motions"]
        assert json.loads(peers[1].ws.messages[-2]) == first
        assert peers[2].ws.messages[-2] == first

    asyncio.run(run())


# ------------------------------------------------------------------ poses packed once a tick
def test_each_motion_in_a_tick_is_packed_once_for_all_protocols(monkeypatch):
    async def run():
        manager = RoomManager(motion_interval=60)
        peers = [manager.join("r", str(i), "嘉然", Socket()) for i in range(6)]
        sender, legacy, v2, v3, v4, unsubscribed = peers
        for peer, version in zip(peers, (4, 1, 2, 3, 4, 4)):
            peer.motion_version = version
        for peer in (v2, v3, v4):
            manager.subscribe_motion("r", peer, [sender.id])
        await manager.motion("r", sender, RESTING)
        current = manager.rooms["r"]
        manager._flush_tick(current)
        for peer in peers:
            await peer.send({"type": "pong"}, 1)
            peer.ws.messages.clear()

        pack = rooms.pack_motion
        packed = []

        def track(pose):
            packed.append(pose)
            return pack(pose)

        monkeypatch.setattr(rooms, "pack_motion", track)
        edge = {**RESTING, "keyDown": True}
        position = {**edge, "dx": 1.25}
        await manager.motion("r", sender, edge)
        await manager.motion("r", sender, position)
        manager._flush_tick(current)
        for peer in peers:
            await peer.send({"type": "pong"}, 1)
        assert packed == [edge, position]
        delta = {"id": sender.id, "x": 5}
        assert legacy.ws.messages[1] == {"type": "motion_batch", "motions": [{"id": sender.id, **position}]}
        assert v2.ws.messages[1] == {"type": "motion_delta", "motions": [delta]}
        motions = [{"id": sender.id, "b": 1}, delta]
        assert v3.ws.messages[0] == {"type": "motion_edges", "edges": motions}
        assert v4.ws.messages[0] == {"type": "room_tick", "motions": motions, "taps": []}
        assert unsubscribed.ws.messages == [{"type": "pong"}]

    asyncio.run(run())


# ------------------------------------------------------------------ the saves' room index
def test_the_save_index_follows_joins_leaves_and_failed_writers():
    async def run():
        manager = RoomManager(send_timeout=0.01)
        a1 = manager.join("r1", "a", "嘉然", Socket(), token="sa")
        a2 = manager.join("r2", "a", "嘉然", Socket(), token="sa")
        a3 = manager.join("r1", "a", "嘉然", Socket(), token="sa")
        b = manager.join("r1", "b", "嘉然", Socket(), token="sb")
        manager.join("r1", "n", "嘉然", Socket())
        assert manager.rooms_of_save("sa") == {"r1", "r2"}
        assert manager.rooms_of_save("") == manager.rooms_of_save(None) == manager.rooms_of_save("nobody") == set()
        assert manager.peers_of_save(None) == [] and manager.peers_of_save("nobody") == []
        assert sorted((rid, p.id) for rid, p in manager.peers_of_save("sa")) == sorted(
            [("r1", a1.id), ("r1", a3.id), ("r2", a2.id)])
        assert set(manager.by_save) == {"sa", "sb"}

        await manager.depart("r2", a2.id)
        assert manager.rooms_of_save("sa") == {"r1"}
        assert manager.leave("r1", a1.id)
        assert [p.id for _, p in manager.peers_of_save("sa")] == [a3.id]
        assert manager.leave("r1", b.id)
        assert "sb" not in manager.by_save

        # A writer that cannot get its message out leaves the room, and the index with it.
        stuck = manager.join("r3", "a", "嘉然", Socket(slow=True), token="sa")
        assert manager.rooms_of_save("sa") == {"r1", "r3"}
        with pytest.raises(asyncio.TimeoutError):
            await stuck.send({"type": "pong"}, 0.01)
        await settle()
        assert manager.rooms_of_save("sa") == {"r1"}
        assert "r3" not in manager.rooms

        await manager.depart("r1", a3.id)
        assert manager.by_save == {}

    asyncio.run(run())


class NoScan(dict):
    """The rooms, read one by one only: a scan of all of them fails the test."""

    def items(self):
        pytest.fail("scanned every room")

    def values(self):
        pytest.fail("scanned every room")


def test_joining_and_leaving_a_room_tells_live_games_without_scanning_every_room():
    """A newcomer learns a live game's seats by the member ids its room knows them by: the seat's own connection when
    it is there, else the newest connection of the seat's save there, else nothing; a room left by every save of the
    table hears that the game ended there."""
    async def run():
        w = MatchWorld()
        a, _ = w.member("a", room="r")
        b, _ = w.member("b")
        c, _ = w.member("c")
        table = Table("t", None, [Seat(p.token, p, p.id, p.nick, p.character, accepted=True) for p in (a, b, c)],
                      100, 100, phase=BID)
        w.t.by_id[table.id] = table
        for p in (b, c):
            w.t.by_save[p.token] = table
        w.t.by_save[a.token] = table
        w.m.rooms = NoScan(w.m.rooms)
        await w.t._live(table, True)

        def live(sock):
            return [{k: v for k, v in m.items() if k in ("on", "ids")} for m in sock.of("ddz_live")]

        a2, _ = w.join("a", a.token, room="r")
        newcomer, first = w.join("first", None, room="r")
        await w.t.joined("r", newcomer)
        assert live(first) == [{"on": True, "ids": [a.id, b.id, c.id]}]

        await w.m.depart("r", a.id)
        a3, _ = w.join("a", a.token, room="r")
        newcomer, second = w.join("second", None, room="r")
        await w.t.joined("r", newcomer)
        assert live(second) == [{"on": True, "ids": [a3.id, b.id, c.id]}]

        await w.m.depart("r", a3.id)
        newcomer, third = w.join("third", None, room="r")
        await w.t.joined("r", newcomer)
        assert live(third) == [{"on": True, "ids": [a2.id, b.id, c.id]}]

        await w.m.depart("r", a2.id)
        newcomer, fourth = w.join("fourth", None, room="r")
        await w.t.joined("r", newcomer)
        assert live(fourth) == []

        w.join("b", b.token, room="s")
        await w.t._live(table, False)
        assert live(fourth) == [{"on": False}]

    asyncio.run(run())


# ------------------------------------------------------------------ frames read and checked in one pass
CORPUS = [
    "", " ", "null", "true", "1", '"ping"', "[]", "{}", '{"type":1}', '{"type":"nope"}', '{"type":"ping"}',
    ' {"type":"ping"} ', '{"type":"ping","extra":{"deep":[1,2,{"x":null}]}}', '{"type":"ping"', '{"type":"ping"}x',
    '{"type":"join","room":"r","nick":"b"}', '{"type":"join","room":"r","nick":"b","character":"嘉然"}',
    '{"type":"join","room":"","nick":"b"}', '{"type":"join","room":"r","nick":7}', '{"type":"join","nick":"b"}',
    '{"type":"motion","dx":0.5,"dy":-1,"keyDown":true,"left":false,"right":true}',
    '{"type":"motion","dx":1e308,"dy":0,"keyDown":false,"left":false,"right":false}',
    '{"type":"motion","dx":1e999,"dy":0,"keyDown":false,"left":false,"right":false}',
    '{"type":"motion","dx":NaN,"dy":0,"keyDown":false,"left":false,"right":false}',
    '{"type":"motion","dx":Infinity,"dy":0,"keyDown":false,"left":false,"right":false}',
    '{"type":"motion","dx":"1","dy":0,"keyDown":false,"left":false,"right":false}',
    '{"type":"motion","dx":1,"dy":0,"keyDown":1,"left":false,"right":false}',
    '{"type":"motion","dx":9,"dy":0,"keyDown":true,"left":false,"right":false,"dx":1.5}',
    '{"type":"motion","dx":1}', '{"type":"pose","x":1.0}', '{"type":"poke","id":""}', '{"type":"poke","id":"ab"}',
    '{"type":"state","nick":"b2"}', '{"type":"state","nick":"\\u5609\\u7136"}', '{"type":"state","status":"work"}',
    '{"type":"emote","id":"x"}', '{"type":"ping","x":"\\ud83d\\ude00"}', '{"type":"ping","x":"\\ud800"}',
    '{"type":"ping","n":123456789012345678901234567890}', '{"type" : "ping" ,\n "x" : [ ] }',
]
# Accepted when the frame was parsed by json.loads first; json.loads keeps a lone surrogate that the one-pass parser
# rejects. No client sends one (JSON.stringify escapes it, and only in fields the server ignores).
NOW_REJECTED = {'{"type":"ping","x":"\\ud800"}'}


def _before(text):
    try:
        return client_message_adapter.validate_python(json.loads(text))
    except (ValueError, ValidationError):
        return "bad"


def _now(text):
    try:
        return parse_client_text(text)
    except ValidationError:
        return "bad"


def test_frames_are_read_and_checked_in_one_pass_as_before():
    for text in CORPUS:
        before, now = _before(text), _now(text)
        if text in NOW_REJECTED:
            assert before != "bad" and now == "bad", text
        else:
            assert type(before) is type(now) and before == now, text
        assert _now(text.encode()) == now, text
    # A frame that is not text at all is a bad message.
    for raw in (None, 7):
        with pytest.raises(ValidationError):
            parse_client_text(raw)


def test_the_handler_stops_reading_once_the_server_closed_the_connection(monkeypatch):
    monkeypatch.setattr(main, "notice", main.Notice())

    async def go():
        inbox = [{"type": "websocket.connect"}, {"type": "websocket.receive", "text": '{"type":"ping"}'},
                 {"type": "websocket.receive", "text": '{"type":"ping"}'}, {"type": "websocket.disconnect", "code": 1000}]
        sent = []

        async def receive():
            await settle()
            return inbox.pop(0)

        async def send(message):
            sent.append(message.get("text") or message["type"])
            if message.get("text") == '{"type":"pong"}':
                # A kick or a failed writer closed the connection meanwhile.
                ws.application_state = WebSocketState.DISCONNECTED

        scope = {"type": "websocket", "path": "/ws", "query_string": b"", "headers": [], "client": ("127.0.0.1", 1)}
        ws = WebSocket(scope, receive, send)
        await main.ws_endpoint(ws)
        await settle()
        return sent, inbox

    sent, inbox = asyncio.run(go())
    assert sent[:2] == ["websocket.accept", '{"type":"pong"}']
    assert '{"type":"pong"}' not in sent[2:]
    assert [m.get("text") for m in inbox[:1]] == ['{"type":"ping"}']


# ------------------------------------------------------------------ expired restore entries
def test_joining_any_room_clears_expired_restore_entries():
    clock = [0.0]
    m = RoomManager(clock=lambda: clock[0])
    m.restore([{"room": rid, "public": False, "host": None, "banned": ["pz"]} for rid in ("a", "b", "c")],
              lambda entry: RESTORE_SECONDS - (20 if entry["room"] == "c" else 10))
    with pytest.raises(Banned):
        m.join("a", "z", "c", Socket(), token="pz")
    clock[0] = 10
    m.join("unrelated", "n", "c", Socket())
    assert set(m.restoring) == {"c"}
    m.join("a", "z", "c", Socket(), token="pz")  # its entry is gone, and the ban with it
    with pytest.raises(Banned):
        m.join("c", "z", "c", Socket(), token="pz")
    clock[0] = 20
    m.join("unrelated", "n", "c", Socket())
    assert not m.restoring


def test_restore_entries_expire_in_any_order():
    rng = random.Random(20261126)
    for _ in range(50):
        clock = [0.0]
        m = RoomManager(clock=lambda: clock[0])
        ages = {f"r{i}": rng.uniform(0, RESTORE_SECONDS + 5) for i in range(8)}
        m.restore([{"room": rid, "public": False, "host": None, "banned": []} for rid in ages],
                  lambda entry: ages[entry["room"]])
        for t in sorted(rng.uniform(0, RESTORE_SECONDS) for _ in range(5)):
            clock[0] = t
            m.join("unrelated", "n", "c", Socket())
            assert set(m.restoring) == {rid for rid, age in ages.items() if RESTORE_SECONDS - age > t}
