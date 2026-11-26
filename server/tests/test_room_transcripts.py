"""What each connection hears, recorded on pre-1.3.0's realtime code in room_transcripts.json beside this file, so a
change to how rooms batch, encode and fan out messages keeps every message, its text and its order: room ticks for
each motion version, writers that fall behind, broadcasts, members leaving mid-tick and a writer that overflows, the
cheer bar of a save in several rooms, dou dizhu games seen across rooms (the queue's, a hall table and a room's open
table, with watchers and a save on two devices), the autopilot's plays, and frames clients send.

ASOULTAPPO_RECORD_TRANSCRIPTS=1 records the transcripts again from the code as it is."""
from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import os
import random
import secrets
from pathlib import Path

import pytest
from starlette.websockets import WebSocket

import app.main as main
from app import ddz_rules as rules
from app.ddz import QUEUE_INTERVAL
from app.rooms import RESTING, RoomManager
from test_ddz import BASE
from test_ddz_hall import hall
from test_ddz_watch import WatchWorld
from test_duel import settle

SNAPSHOT = Path(__file__).with_name("room_transcripts.json")
RECORD = os.environ.get("ASOULTAPPO_RECORD_TRANSCRIPTS") == "1"


@pytest.fixture(autouse=True)
def ids(monkeypatch):
    """Member and table ids in the order they are made: 00000001, 00000002, ..."""
    counter = itertools.count(1)
    monkeypatch.setattr(secrets, "token_hex", lambda nbytes=None: f"{next(counter):0{2 * (nbytes or 32)}x}")


def check(name: str, transcript) -> None:
    """[transcript] is the one recorded as [name]; recorded instead with ASOULTAPPO_RECORD_TRANSCRIPTS=1."""
    data = json.loads(SNAPSHOT.read_text("utf-8")) if SNAPSHOT.exists() else {}
    if RECORD:
        data[name] = transcript
        SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")
        return
    assert name in data, f"no transcript {name!r}: record it with ASOULTAPPO_RECORD_TRANSCRIPTS=1"
    assert transcript == data[name]


def text(data) -> str:
    """A message as Starlette writes it (WebSocket.send_json)."""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


class Recorder:
    """A connection that keeps every frame as the text the client gets. With [gate], every write waits until it is
    set: what comes after the first message waits in the member's outbox."""

    def __init__(self, gate: asyncio.Event | None = None):
        self.frames: list[str] = []
        self.gate = gate

    async def send_json(self, data):
        await self._held()
        self.frames.append(text(data))

    async def send_text(self, data):
        await self._held()
        self.frames.append(data)

    async def _held(self):
        if self.gate is not None:
            await self.gate.wait()

    async def close(self, code=1000):
        self.frames.append(f"close {code}")


async def drain(peers):
    """Waits until what is queued for [peers] is written; each hears a `mark` after it."""
    await asyncio.gather(*(p.send({"type": "mark"}, 30) for p in peers if p.active))


def pose(**kw):
    return {**RESTING, **kw}


# ------------------------------------------------------------------ rooms
async def room_story(slow: bool) -> dict:
    """One room through ticks, hiding, broadcasts, leaving and an overflowing writer, and the cheer bar of a save in
    two rooms. [slow]: members B to E write only at the end, everything for them waiting in their outboxes."""
    m = RoomManager(send_timeout=30, motion_interval=60, cheer_interval=60)
    gate, overflow = asyncio.Event(), asyncio.Event()
    peers = {}

    def member(label, version, token=None, room="r", held=None):
        peer = m.join(room, label.lower(), "嘉然", Recorder(held), token=token)
        peer.motion_version = version
        peers[label] = peer
        return peer

    a = member("A", 4, "sa")
    b = member("B", 1, "sb", held=gate if slow else None)
    c = member("C", 2, "sc", held=gate if slow else None)
    d = member("D", 3, "sd", held=gate if slow else None)
    e = member("E", 4, "se", held=gate if slow else None)
    f = member("F", 4)
    g = member("G", 2, "sa")
    leaver = member("L", 3, "sl")
    room = m.rooms["r"]

    def fast():
        return [p for label, p in peers.items() if not (slow and label in "BCDE")]

    m.subscribe_motion("r", a, [b.id, c.id, d.id, e.id, f.id, g.id])
    m.subscribe_motion("r", c, [a.id, b.id, g.id, e.id])
    m.subscribe_motion("r", d, [a.id, b.id, e.id])
    m.subscribe_motion("r", e, [a.id, b.id, c.id, d.id])
    m.subscribe_motion("r", g, [a.id, "nobody", g.id])
    m.subscribe_motion("r", leaver, [a.id, b.id])
    await drain(fast())

    # A tick: A's first pose (an edge), positions in between, more edges than a tick keeps, taps; B on full poses.
    await m.motion("r", a, pose(dx=1.0))
    for dx in (1.25, 1.5, 1.75):
        await m.motion("r", a, pose(dx=dx))
    await m.motion("r", b, pose(dy=-2.0))
    await m.motion("r", b, pose(dy=-2.5))
    for i in range(8):
        await m.motion("r", a, pose(dx=2.0, keyDown=i % 2 == 0, left=i % 4 == 1))
    await m.motion("r", a, pose(dx=2.25))
    for peer, n in ((a, 3), (c, 1), (a, 2)):
        peer.taps += n
        m.tap("r", peer, n)
    m._flush_tick(room)
    await drain(fast())

    # A member hidden rests in everyone's view and comes back with the pose it holds; E sends packed poses.
    await m.motion("r", c, pose(dx=-1.0))
    await m.hide("r", c, True)
    await m.motion("r", c, pose(dx=-3.0, right=True))
    await m.pose("r", e, {"x": 4})
    await m.pose("r", e, {"y": -8})
    await m.pose("r", e, {"b": 5})
    e.taps += 7
    m.tap("r", e, 7)
    m.tap("r", e, 0)
    m._flush_tick(room)
    await m.hide("r", c, False)
    m._flush_tick(room)
    await drain(fast())

    # Ticks back to back, a broadcast between two of them, and one with taps only.
    for i in range(3):
        await m.motion("r", a, pose(dx=-i / 4, keyDown=True))
        await m.motion("r", a, pose(dx=-i / 4 - .25, keyDown=True))
        await m.motion("r", b, pose(dy=i / 2))
        a.taps += i + 1
        m.tap("r", a, i + 1)
        m._flush_tick(room)
        if i == 0:
            await m.broadcast("r", {"type": "note", "text": "汽水铺 ✓ \"q\" \\ </script> ",
                                    "n": [1, 2.5, None, True, -0.0, 1e21], "nested": {"k": "é"}}, exclude=f.id)
    for peer in (c, g):
        peer.taps += 4
        m.tap("r", peer, 4)
    m._flush_tick(room)
    await drain(fast())

    # A member leaves with edges and taps waiting for it; the tick goes out without it.
    await m.motion("r", a, pose(dx=3.0))
    await m.motion("r", b, pose(dy=1.0, left=True))
    a.taps += 1
    m.tap("r", a, 1)
    await m.depart("r", leaver.id)
    m._flush_tick(room)
    await drain(fast())

    # A writer whose outbox fills up stops; the room hears it left.
    o = member("O", 4, "so", held=overflow)
    o.enqueue({"type": "note", "i": 0})
    await asyncio.sleep(0)
    for i in range(1, 300):
        o.enqueue({"type": "note", "i": i})
    overflow.set()
    for _ in range(20):
        await asyncio.sleep(0)
    await drain(fast())

    # The cheer bar: a save cheers in the room it joined last, on any of its connections.
    cheers = []

    def cheer(save, taps):
        out = m.cheer(save, taps)
        cheers.append(None if out is None else [out[0].id, out[1], sorted(out[2]), out[3]])
        return out

    h = member("H", 4, "sa", room="r2")
    member("P", 4, "sp", room="r2")
    cheer("nobody", 5)
    cheer("sa", 0)
    cheer("sa", 60)
    m._send_cheer(m.rooms["r2"])
    done = cheer("sp", 600)
    await m.cheer_done(done[0], done[1], {"sa": 20, "sp": 0})
    await drain(fast())
    await m.depart("r2", h.id)
    cheer("sa", 70)
    cheer("sb", 40)
    cheer("sb", 20)
    m._send_cheer(room)
    # The host leaves: the room hears who left, the bar without it, and the new host.
    await m.depart("r", a.id)
    await m.broadcast("r2", {"type": "note", "text": "r2"})
    await drain(fast())

    gate.set()
    await drain([p for p in peers.values()])
    return {"frames": {label: p.ws.frames for label, p in peers.items()}, "cheers": cheers,
            "host": next(label for label, p in peers.items() if p.id == room.host),
            "rooms": {rid: sorted(label for label, p in peers.items() if p.id in r.peers) for rid, r in m.rooms.items()}}


@pytest.mark.parametrize("slow", [False, True], ids=["writing", "behind"])
def test_a_room_hears_what_it_heard(slow):
    check(f"room {'behind' if slow else 'writing'}", asyncio.run(room_story(slow)))


# ------------------------------------------------------------------ dou dizhu
class Heard:
    """What the dou dizhu tests' connections were told, by label, as text; a play (``ddz_play``, the bulk of a game
    and the same for every room) by a digest of its text."""

    def __init__(self):
        self.socks = {}

    def keep(self, label, pair):
        self.socks[label] = pair[1]
        return pair[0]

    def transcript(self):
        def frame(m):
            t = text(m)
            return f"ddz_play {hashlib.sha1(t.encode()).hexdigest()[:12]}" if m["type"] == "ddz_play" else t
        return {label: [frame(m) for m in sock.got] for label, sock in self.socks.items()}


async def counted(w):
    """Fires what waits on the count timers (watchers, the rooms' view of a game) a while after it was last told."""
    w.mono += 60
    await w.counts.fire()


async def queue_table_story() -> dict:
    """A table the queue made, seen from the rooms its saves are in: a on two devices, watchers in two rooms,
    members coming and going during the game, the end."""
    w = WatchWorld()
    heard = Heard()
    wa = heard.keep("wa@r-a", w.member("wa", room="r-a"))
    wc = heard.keep("wc@r-c", w.member("wc", room="r-c"))
    a_room = heard.keep("a@r-a", w.member("a", room="r-a"))
    heard.keep("c@r-c", w.member("c", room="r-c"))
    heard.keep("old@r-c", w.member("old", room="r-c", watch=False))
    seats = [heard.keep(n, w.queuer(n)) for n in "abc"]
    for peer in seats:
        await w.t.queue(peer, BASE)
    await w.t.idle()
    tid = heard.socks["a"].of("ddz_invite")[0]["table"]
    for peer in seats:
        await w.t.answer(peer, tid, True)
    await w.settled()
    table = w.t.by_id[tid]
    w.watch(wa, table, 0)
    w.watch(wc, table, 0)
    await counted(w)
    # a on a second device in r-c: every room hears its new member id, wc may see a's hand.
    a_dev = heard.keep("a@r-c", w.member("a", room="r-c"))
    await w.t.joined("r-c", a_dev)
    await counted(w)
    newcomer = heard.keep("n1@r-a", w.member("n1", room="r-a"))
    await w.t.joined("r-a", newcomer)
    await w.bid(table)
    await counted(w)
    # a's first device leaves r-a: r-a no longer sees the game's seats, wa no longer a's hand.
    await w.m.depart("r-a", a_room.id)
    await counted(w)
    late = heard.keep("n2@r-a", w.member("n2", room="r-a"))
    await w.t.joined("r-a", late)
    b_room = heard.keep("b@r-b", w.member("b", room="r-b"))
    await w.t.joined("r-b", b_room)
    await counted(w)
    await w.play_out(table)
    await counted(w)
    after = heard.keep("n3@r-c", w.member("n3", room="r-c"))
    await w.t.joined("r-c", after)
    return heard.transcript()


async def plays(w, table, n):
    """[n] turns: each seat leads its lowest card and passes otherwise."""
    for _ in range(n):
        s = table.seats[table.turn]
        await w.t.play(s.peer, table.id, [] if table.last is not None else [s.hand[0]])


async def same_room_story() -> dict:
    """A table the queue made, one of its saves on two devices in the same room with a watcher of its seat there: the
    room knows the seat by the newest device, then by the older one once the newest leaves, then not at all, and again
    when the save comes back; the seats leave and the game ends with nothing won."""
    w = WatchWorld()
    heard = Heard()
    older = heard.keep("a1@r-s", w.member("a", room="r-s"))
    newer = heard.keep("a2@r-s", w.member("a", room="r-s"))
    watcher = heard.keep("w@r-s", w.member("w", room="r-s"))
    heard.keep("old@r-s", w.member("old", room="r-s", watch=False))
    seats = [heard.keep(n, w.queuer(n)) for n in "abc"]
    for peer in seats:
        await w.t.queue(peer, BASE)
    await w.t.idle()
    tid = heard.socks["a"].of("ddz_invite")[0]["table"]
    for peer in seats:
        await w.t.answer(peer, tid, True)
    await w.settled()
    table = w.t.by_id[tid]
    w.watch(watcher, table, 0)
    await counted(w)
    await w.bid(table)
    await w.m.depart("r-s", newer.id)
    await counted(w)
    first = heard.keep("n1@r-s", w.member("n1", room="r-s"))
    await w.t.joined("r-s", first)
    await plays(w, table, 2)
    await counted(w)
    await w.m.depart("r-s", older.id)
    await counted(w)
    second = heard.keep("n2@r-s", w.member("n2", room="r-s"))
    await w.t.joined("r-s", second)
    back = heard.keep("a3@r-s", w.member("a", room="r-s"))
    await w.t.joined("r-s", back)
    await counted(w)
    await plays(w, table, 2)
    await counted(w)
    for peer in seats:
        await w.bye(peer)
    await w.settled()
    await counted(w)
    return heard.transcript()


async def hall_table_story() -> dict:
    """A hall table of no room, its seats on dou dizhu connections and two of its saves in a room on their room
    connections; one leaves the room during the game, then the three seats leave and the game ends with nothing
    won."""
    w = WatchWorld()
    heard = Heard()
    x_room = heard.keep("x@r-h", w.member("x", room="r-h"))
    heard.keep("y@r-h", w.member("y", room="r-h"))
    watcher = heard.keep("w@r-h", w.member("w", room="r-h"))
    out, tid = await hall(w, "x", "y", "z")
    for label, (peer, sock) in zip("xyz", out):
        heard.socks[label] = sock
    await w.settled()
    table = w.t.by_id[tid]
    w.watch(watcher, table, 1)
    await counted(w)
    await w.bid(table)
    await w.m.depart("r-h", x_room.id)
    await counted(w)
    await plays(w, table, 4)
    await counted(w)
    for peer, _ in out:
        await w.bye(peer)
    await w.settled()
    await counted(w)
    return heard.transcript()


async def open_table_story() -> dict:
    """A room's open table: a watcher in the room sees the seat it asked for; a seat's save in another room on a
    second device, and leaving it again; then the three seats leave the room and the game ends with nothing won."""
    w = WatchWorld()
    heard = Heard()
    watcher = heard.keep("w@r", w.member("w"))
    out = [heard.keep(f"{n}@r", w.member(n)) for n in ("o1", "o2", "o3")]
    await w.t.open("r", out[0], BASE)
    tid = heard.socks["o1@r"].of("ddz_open")[-1]["table"]
    for peer in out[1:]:
        w.mono += QUEUE_INTERVAL
        await w.t.sit("r", peer, tid)
    await w.settled()
    table = w.t.by_id[tid]
    w.watch(watcher, table, 1)
    await counted(w)
    elsewhere = heard.keep("o1@r-x", w.member("o1", room="r-x"))
    await w.t.joined("r-x", elsewhere)
    await counted(w)
    await w.m.depart("r-x", elsewhere.id)
    await counted(w)
    await w.bid(table)
    await plays(w, table, 4)
    await counted(w)
    for peer in out:
        await w.m.depart("r", peer.id)
    await w.settled()
    await counted(w)
    return heard.transcript()


@pytest.mark.parametrize("story", [queue_table_story, same_room_story, hall_table_story, open_table_story],
                         ids=["queue", "same-room", "hall", "open"])
def test_dou_dizhu_games_are_seen_across_rooms_as_before(story):
    check(f"ddz {story.__name__}", asyncio.run(story()))


def test_the_autopilot_plays_what_it_played():
    rng = random.Random(20261126)
    cases = []
    for _ in range(400):
        hand = sorted(rng.sample(range(54), rng.randint(1, 20)))
        last = None if rng.random() < .3 else rules.choose(sorted(rng.sample(range(54), rng.randint(1, 20))), None)
        partner, danger = rng.random() < .2, rng.random() < .3
        played = rules.choose(hand, last, partner_led=partner, danger=danger)
        cases.append(f"{hand} {last} {int(partner)}{int(danger)} -> {played}")
    check("ddz autopilot", cases)


# ------------------------------------------------------------------ frames
FRAMES = [
    {"text": "hello"},
    {"bytes": b'{"type":"ping"}'},
    {"text": None, "bytes": b"x"},
    {"text": '{"type":"join","room":"frames-check","nick":"b"}'},
    {"text": '{"type":"ping"}'},
    {"text": '  {"type":"ping","extra":[1,{"x":null}]}  '},
    {"text": '{"type":"motion","dx":NaN,"dy":0,"keyDown":false,"left":false,"right":false}'},
    {"text": '{"type":"motion","dx":9,"dy":0,"keyDown":true,"left":false,"right":false,"dx":1.5}'},
    {"text": '{"type":"pose","x":1.0}'},
    {"text": '{"type":"poke","id":""}'},
    {"text": "[]"},
    {"text": '{"type":"state","nick":"b2"}'},
    {"text": '{"type":"ping"}'},
]


def test_frames_clients_send_are_answered_as_before(monkeypatch):
    """A connection's frames as clients send them, good and bad: what it is answered, and what the room hears."""
    monkeypatch.setattr(main, "notice", main.Notice())

    async def go():
        mate = main.manager.join("frames-check", "a", "嘉然", Recorder())
        inbox = [{"type": "websocket.connect"}, *({"type": "websocket.receive", **f} for f in FRAMES),
                 {"type": "websocket.disconnect", "code": 1000}]
        sent = []

        async def receive():
            await settle()
            return inbox.pop(0)

        async def send(message):
            sent.append(message)

        scope = {"type": "websocket", "path": "/ws", "query_string": b"", "headers": [], "client": ("127.0.0.1", 1)}
        await main.ws_endpoint(WebSocket(scope, receive, send))
        await settle()
        await main.manager.depart("frames-check", mate.id)
        return {"b": [m.get("text") or m["type"] for m in sent], "a": mate.ws.frames}

    main.manager.rooms.pop("frames-check", None)
    check("frames", asyncio.run(go()))
