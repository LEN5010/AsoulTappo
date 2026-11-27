"""In-memory rooms with ordered writers, motion subscriptions and one 100ms tick per room for edges, positions and
taps."""
from __future__ import annotations

import asyncio
import json
import math
import secrets
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

MAX_ROOM_SIZE = 20
MAX_OUTBOX = 256
# Batches waiting in an outbox that a newer one of the same kind joins: positions keep each member's latest; edges and
# room ticks keep their order (Peer.enqueue).
_POSITION_BATCHES = ("motion_batch", "motion_delta")
_ORDERED_BATCHES = {"motion_edges": "edges", "room_tick": "motions"}
# Motion formats: 1 full poses; 2 packed deltas for subscribed members, one message per button edge;
# 3 as 2 with the edges and positions of a room tick gathered into one ordered message per receiver (`motion_edges`);
# 4 as 3 with the tick's taps in that message too (`room_tick`), instead of one `tap` message per member.
MOTION_VERSION = 4
# Edges kept per member within one tick; earlier ones are dropped, the latest pose always goes out.
MAX_EDGES_PER_BATCH = 6
# Room messages beyond the 1.1 set, listed in `joined` for clients that announce a motion version.
# "drink": members tell the room they drank water; "name": the host names the room.
FEATURES = ("poke", "profile", "cheer", "status", "drink", "name")
# Cheer rounds: members' paid taps fill a bar. A save's taps go on the bar once it has put CHEER_MIN_SHARE into the
# round, and from then it cheers; the bar holds CHEER_PER_SAVE taps for each cheering save (CHEER_MIN_SAVES at least),
# so a full bar means they put in that many each on average, and many small shares cannot fill it early. When it is
# full every cheering save gets CHEER_REWARD_PER_SAVE shards for each cheering save (game.cheer_reward keeps the daily
# cap). Taps count only while CHEER_MIN_SAVES saves are in the room. A save that leaves still cheers, and is paid, for
# CHEER_GRACE seconds, so a dropped connection that comes back loses nothing; after that its taps stay on the bar and
# it no longer counts. Progress goes out at most every CHEER_SEND_INTERVAL.
CHEER_PER_SAVE = 300
CHEER_MIN_SHARE = 50
CHEER_MIN_SAVES = 2
CHEER_REWARD_PER_SAVE = 10
CHEER_GRACE = 60.0
CHEER_SEND_INTERVAL = 2.0
# Pokes: one per connection this often, and the same member again only after the longer wait.
POKE_INTERVAL = 3.0
POKE_SAME_INTERVAL = 10.0
# A member who drank water after a reminder shows the room a cup; one per connection this often.
DRINK_INTERVAL = 30.0
# Room names, set by the host: at most this many characters once trimmed.
ROOM_NAME_MAX = 16
# Profile requests: one per connection this often; each reads the save.
PROFILE_INTERVAL = 0.3
# Rooms live in memory, so a restart empties them and clients join their rooms again. What the server saved of each
# room when it stopped (see RoomManager.snapshot) is brought back for this long after: the saves the host removed, and
# for the save that was host its host role and the room's public listing.
RESTORE_SECONDS = 600.0
# A room whose last member left is kept the same way for this long, so that members coming back to it later (a desk
# can go back into its room on start) find its name, its removed saves and, with the save that was host last, its host
# role and listing. Only a room with a name, a listing or removed saves is kept: any other comes back the same without.
EMPTY_SECONDS = 24 * 3600.0
# At most this many rooms are kept at once; past it the one kept longest goes first.
RESTORE_MAX = 20000


class PokeRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
RESTING = {"dx": 0.0, "dy": 0.0, "keyDown": False, "left": False, "right": False}


def pack_motion(pose: dict) -> dict[str, int]:
    return {"x": math.floor(pose["dx"] * 4 + .5), "y": math.floor(pose["dy"] * 4 + .5),
            "b": int(pose["keyDown"]) | int(pose["left"]) << 1 | int(pose["right"]) << 2}


class _Broadcast(dict):
    """A message for a whole room, written once as the text every member is sent (as WebSocket.send_json writes it);
    a sender without send_text gets the message itself."""

    __slots__ = ("text",)

    def __init__(self, data: dict) -> None:
        super().__init__(data)
        self.text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)


class _MergedBatch(dict):
    """An ordered batch in one member's outbox that later batches joined: its list is that outbox's own, so the next
    one extends it in place."""

    __slots__ = ()


class Sender(Protocol):
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


class RoomFull(Exception):
    pass


class Banned(Exception):
    """The save was removed from this room by its host."""


class RoomClosed(Exception):
    """A join that goes only into a room with members found none there."""


class NeedSave(Exception):
    """Public rooms take members with a save only."""


# Statuses a member may show in a room, chosen from this list only: slacking off, working, studying, gaming,
# listening to music (clients from before 1.2.5 only), watching a live stream, away. A client shows `away` by
# itself too, after a while without input.
ROOM_STATUSES = ("fish", "work", "study", "game", "music", "live", "away")


def room_status(value: str | None) -> str | None:
    """[value] when it is one of ROOM_STATUSES, else None (no status shown)."""
    return value if value in ROOM_STATUSES else None


def clean_room_name(value: str) -> str:
    """[value] without control and format characters, runs of whitespace as one space, trimmed."""
    kept = "".join(c for c in value if c.isspace() or not unicodedata.category(c).startswith("C"))
    return " ".join(kept.split())


def new_room_id() -> str:
    return secrets.token_urlsafe(16)


@dataclass
class Peer:
    id: str
    nick: str
    character: str
    ws: Sender
    taps: int = 0
    uid: str | None = None
    token: str | None = None
    # name plate worn (a big hidden card id or a manifest `plates` id), checked against the save
    plate: str | None = None
    # one of ROOM_STATUSES, None for none
    status: str | None = None
    # turns rock-paper-scissors invites down; never shown to the room
    dnd: bool = False
    # the nick as the client sent it, before the blocklist masked it into `nick` (seats re-mask it, app/ddz.py)
    raw_nick: str = ""
    # joined with a valid main-site account token: may make the room public on a server with accounts
    account: bool = False
    # the client can play dou dizhu (it said so when joining)
    ddz: bool = False
    # the client also queues for dou dizhu tables across rooms (app/ddz.py, the queue)
    ddz_match: bool = False
    # the client watches dou dizhu games and shows who watches its own seat (app/ddz.py, watching)
    ddz_watch: bool = False
    # the table this connection watches, None for none; and the clock time of its last ddz_watch (Tables.watch)
    watching: str | None = None
    watch_at: float = float("-inf")
    # the room this connection joined; "" for a dou dizhu connection (`lobby`)
    room: str = ""
    # a dou dizhu connection, in no room: it queues and plays at the tables the queue makes (app/ddz.py)
    lobby: bool = False
    emotes: set[str] = field(default_factory=set)
    last_emote: float = 0.0
    tap_budget: float = 0.0
    tap_at: float = 0.0
    motion: dict[str, float | bool] | None = None
    motion_version: int = 1
    # The room is not shown this member's taps and motion (its save's input counts as automatic, see app/guard.py);
    # `unseen` is then the pose it last sent, for the day the room sees it again.
    hidden: bool = False
    unseen: dict[str, float | bool] | None = None
    # Monotonic time of the last poke sent, and of the last one sent to each member.
    poke_at: float = float("-inf")
    poked: dict[str, float] = field(default_factory=dict)
    # Monotonic time of the last drink shown to the room.
    drink_at: float = float("-inf")
    # Monotonic time of the last profile request.
    profile_at: float = float("-inf")
    # Order of joining across all rooms: a save in two rooms cheers in the one it joined last.
    join_seq: int = 0
    motion_ids: set[str] = field(default_factory=set)
    sent_motion: dict[str, dict[str, int]] = field(default_factory=dict)
    active: bool = True
    outbox: deque = field(default_factory=deque)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    writer: asyncio.Task | None = None
    overloaded: bool = False
    send_timeout: float = 2.0
    on_failure: Callable[[], Awaitable[None]] | None = None

    def enqueue(self, data: dict, done: asyncio.Future | None = None) -> None:
        if not self.active:
            if done is not None:
                done.set_exception(ConnectionError("member left"))
            return
        if self.overloaded:
            # The writer stops at its next message: nothing more goes out.
            if done is not None:
                done.set_exception(ConnectionError("outbox full"))
            return
        kind = data["type"]
        previous, previous_done = self.outbox[-1] if self.outbox else (None, None)
        # Only adjacent batches join, and none that someone waits for: ordered edges remain between position batches.
        joins = done is None and previous_done is None and previous is not None and previous["type"] == kind
        if joins and kind in _POSITION_BATCHES:
            latest = {m["id"]: m.copy() for m in previous["motions"]}
            for motion in data["motions"]:
                latest.setdefault(motion["id"], {}).update(motion)
            self.outbox[-1] = ({"type": kind, "motions": list(latest.values())}, None)
        elif joins and kind in _ORDERED_BATCHES:
            self._merge_ordered(previous, data, _ORDERED_BATCHES[kind])
        elif len(self.outbox) >= MAX_OUTBOX:
            self.overloaded = True
            if done is not None:
                done.set_exception(ConnectionError("outbox full"))
        else:
            self.outbox.append((data, done))
        self.ready.set()
        if self.writer is None:
            self.writer = asyncio.create_task(self._write())

    def _merge_ordered(self, previous: dict, data: dict, batch: str) -> None:
        """[data] joins the batch [previous] at the end of the outbox: edges, and a room tick's motions, in order; a
        room tick's taps add up to each member's latest total. The lists of a batch still as it was made may be
        shared (a tick's taps go to every member), so the first join copies, and later ones extend the copy."""
        taps = None
        if batch == "motions" and data["taps"]:
            by_id = {tap["id"]: tap for tap in previous["taps"]}
            for tap in data["taps"]:
                held = by_id.get(tap["id"])
                by_id[tap["id"]] = {**tap, "count": tap["count"] + held["count"]} if held else tap
            taps = list(by_id.values())
        if not isinstance(previous, _MergedBatch):
            previous = _MergedBatch(previous)
            previous[batch] = previous[batch].copy()
            self.outbox[-1] = (previous, None)
        previous[batch].extend(data[batch])
        if taps is not None:
            previous["taps"] = taps

    async def send(self, data: dict, timeout: float) -> None:
        self.send_timeout = timeout
        done = asyncio.get_running_loop().create_future()
        self.enqueue(data, done)
        await done

    async def _write(self) -> None:
        current = None
        try:
            while self.active:
                await self.ready.wait()
                while self.outbox or self.overloaded:
                    if self.overloaded:
                        raise ConnectionError("outbox full")
                    data, current = self.outbox.popleft()
                    send_text = getattr(self.ws, "send_text", None) if isinstance(data, _Broadcast) else None
                    send = send_text(data.text) if send_text is not None else self.ws.send_json(data)
                    await asyncio.wait_for(send, self.send_timeout)
                    if current is not None and not current.done():
                        current.set_result(None)
                    current = None
                self.ready.clear()
        except asyncio.CancelledError:
            if current is not None and not current.done():
                current.set_exception(ConnectionError("member left"))
            raise
        except Exception as error:
            if current is not None and not current.done():
                current.set_exception(error)
            if self.on_failure is not None:
                await self.on_failure()
        finally:
            for _, done in self.outbox:
                if done is not None and not done.done():
                    done.set_exception(ConnectionError("writer stopped"))
            self.outbox.clear()


@dataclass(slots=True)
class _Motion:
    """A member's pose for a room tick, packed (pack_motion) once for every member that gets it packed."""
    sender: str
    pose: dict
    packed: dict[str, int] | None = None

    def for_peer(self, receiver: Peer) -> dict | None:
        """What [receiver] gets of it: the full pose (motion version 1), or the packed fields that changed since it
        last got this member's, for a member it subscribed to; None for nothing."""
        sender = self.sender
        if receiver.id == sender:
            return None
        if receiver.motion_version < 2:
            return {"id": sender, **self.pose}
        if sender not in receiver.motion_ids:
            return None
        if self.packed is None:
            self.packed = pack_motion(self.pose)
        previous = receiver.sent_motion.get(sender, {})
        delta = {key: value for key, value in self.packed.items() if previous.get(key) != value}
        receiver.sent_motion[sender] = self.packed
        return {"id": sender, **delta} if delta else None


@dataclass
class Room:
    id: str
    # in join order: the host passes to the earliest remaining member
    peers: dict[str, Peer] = field(default_factory=dict)
    # Latest positions not sent yet, by member id; they go out with the room's next tick.
    motions: dict[str, _Motion] = field(default_factory=dict)
    # The room tick: edges, positions and taps waiting go out together (RoomManager._flush_tick).
    motion_timer: asyncio.TimerHandle | None = None
    # Button edges for motion version 3 and up, in the order they happened.
    edges: list[_Motion] = field(default_factory=list)
    # Taps not sent yet, by member id in the order they first came: [taps since the last tick, member's total].
    taps: dict[str, list[int]] = field(default_factory=dict)
    host: str | None = None
    public: bool = False
    # The name the host gave the room as typed (kept for masking again when the blocked words change), and as shown.
    raw_name: str = ""
    name: str = ""
    # saves the host removed; kept with the room's other state once it empties (RoomManager._keep_emptied)
    banned: set[str] = field(default_factory=set)
    # This cheer round's paid taps by player id (a save that left keeps its taps on the bar), when each save with taps
    # on it left (monotonic clock; gone again when it comes back), and rounds finished.
    cheer: dict[str, int] = field(default_factory=dict)
    cheer_gone: dict[str, float] = field(default_factory=dict)
    cheer_rounds: int = 0
    cheer_timer: asyncio.TimerHandle | None = None

    def info(self) -> dict:
        """Room-wide state sent in `joined` and `room_info`."""
        return {"host": self.host, "public": self.public, "name": self.name}


@dataclass
class Restore:
    """A room as the last run left it, or as its last member left it; until is on the manager's clock."""
    public: bool
    host: str | None
    banned: set[str]
    until: float
    name: str = ""
    # How long the entry lasts from when it was made: RESTORE_SECONDS for a room of the last run, EMPTY_SECONDS for
    # a room that emptied.
    keep: float = RESTORE_SECONDS


class RoomManager:
    def __init__(self, max_size: int = MAX_ROOM_SIZE, send_timeout: float = 2.0, motion_interval: float = 0.1,
                 cheer_interval: float = CHEER_SEND_INTERVAL, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_size = max_size
        self.send_timeout = send_timeout
        # The room tick: how long edges, positions and taps wait to go out together.
        self.motion_interval = motion_interval
        self.cheer_interval = cheer_interval
        self.clock = clock
        self._joins = 0
        self.rooms: dict[str, Room] = {}
        # The members of each room by their save: save -> room id -> member id -> Peer (members without a save are
        # not in it). Kept by join and leave.
        self.by_save: dict[str, dict[str, dict[str, Peer]]] = {}
        # Called once for every member removed by depart (leave, kick, failed writer), after member_left.
        self.on_depart: Callable[[str, Peer], Awaitable[None]] | None = None
        # Rooms of the last run and rooms whose last member left, by room id, until their host is back or they run
        # out (RESTORE_SECONDS, EMPTY_SECONDS). In the order they were made: the first is the one kept longest.
        self.restoring: dict[str, Restore] = {}
        # The soonest `until` among them: joins drop the entries that ran out once the clock passes it.
        self._restore_at = float("inf")
        # Masks blocked words in room names; main sets the blocklist's.
        self.mask: Callable[[str], str] = lambda text: text

    def snapshot(self) -> list[dict]:
        """What a restart would lose of each room: whether it is listed, the host's save, the removed saves and the
        room's name. What this run still holds of the last one or of rooms that emptied goes in again with its "age"
        (seconds since it was made) and "keep" (how long it lasts), so the next run lets it run out when this one
        would have: a room nobody came back to, and for a room whose members came back before its host, that host's
        claim to the role and the listing, which then stands in for the save holding the role meanwhile. One entry per
        room."""
        now = self.clock()
        out = []
        for room_id, room in list(self.rooms.items()):
            host = room.peers.get(room.host) if room.host else None
            entry = {"room": room_id, "public": room.public, "host": host.token if host else None,
                     "banned": sorted(room.banned), "name": room.raw_name}
            pending = self.restoring.get(room_id)
            if pending is not None and pending.host and pending.until > now:
                entry["host"] = pending.host
                entry["public"] = room.public or pending.public
                entry["age"] = max(0.0, pending.keep - (pending.until - now))
                entry["keep"] = pending.keep
            if entry["public"] or entry["host"] or entry["banned"] or entry["name"]:
                out.append(entry)
        for room_id, pending in list(self.restoring.items()):
            if room_id in self.rooms or pending.until <= now:
                continue
            out.append({"room": room_id, "public": pending.public, "host": pending.host,
                        "banned": sorted(pending.banned), "name": pending.name,
                        "age": max(0.0, pending.keep - (pending.until - now)), "keep": pending.keep})
        return out

    def restore(self, rooms: list[dict], age: Callable[[dict], float]) -> None:
        """Take back what the last run saved; [age] gives each entry's seconds since it was made, and its "keep" how
        long it lasts (RESTORE_SECONDS when it has none, as from a server from before rooms that emptied were kept)."""
        now = self.clock()
        for entry in rooms:
            keep = float(entry.get("keep") or RESTORE_SECONDS)
            left = keep - age(entry)
            if left > 0:
                self.restoring[entry["room"]] = Restore(bool(entry["public"]), entry["host"] or None,
                                                        set(entry["banned"]), now + left, str(entry.get("name") or ""),
                                                        keep)
        self._expire_restoring(now)

    def _keep_emptied(self, room_id: str, room: Room, last: Peer) -> None:
        """[room] has just lost its last member, [last]: what members coming back would miss of it is kept for
        EMPTY_SECONDS, as for a room of the last run. Its host there is [last] when it held the role, and a listing
        still waiting for the last run's host goes with it. A room with no name, listing or removed saves is not kept,
        and nor is anything the last run left of it."""
        now = self.clock()
        pending = self.restoring.pop(room_id, None)
        public = room.public or (pending is not None and pending.host is not None and pending.until > now
                                 and pending.public)
        if not (public or room.raw_name or room.banned):
            return
        host = last.token if room.host == last.id else None
        self.restoring[room_id] = Restore(public, host, set(room.banned), now + EMPTY_SECONDS, room.raw_name,
                                          EMPTY_SECONDS)
        while len(self.restoring) > RESTORE_MAX:
            del self.restoring[next(iter(self.restoring))]
        self._restore_at = min(self._restore_at, now + EMPTY_SECONDS)

    def _expire_restoring(self, now: float) -> None:
        self.restoring = {rid: pending for rid, pending in self.restoring.items() if pending.until > now}
        self._restore_at = min((pending.until for pending in self.restoring.values()), default=float("inf"))

    def create_room(self) -> str:
        return new_room_id()

    def join(self, room_id: str, nick: str, character: str, ws: Sender,
             token: str | None = None, may_list: bool = True, seq: int | None = None, only_open: bool = False,
             **profile: str | None) -> Peer:
        """[token]: the joining save's player id, None without a save. [may_list]: whether this joiner may host a
        listed room, for a room of the last run whose host comes back. [seq]: the joiner's Peer.join_seq, taken when
        its join came (next_seq); a new one when None. [only_open]: join only a room that has members now, and
        raise RoomClosed rather than make one."""
        room = self.rooms.get(room_id)
        if room is None and only_open:
            raise RoomClosed(room_id)
        if self.restoring and (now := self.clock()) >= self._restore_at:
            self._expire_restoring(now)
        pending = self.restoring.get(room_id)
        if room is not None:
            if token and token in room.banned:
                raise Banned(room_id)
            if room.public and not token:
                raise NeedSave(room_id)
            if len(room.peers) >= self.max_size:
                raise RoomFull(room_id)
        if room is None:
            if pending is not None and token and token in pending.banned:
                raise Banned(room_id)
            room = self.rooms[room_id] = Room(room_id)
            if pending is not None:
                room.banned |= pending.banned
                self.rename(room, pending.name)
        peer = Peer(id=secrets.token_hex(4), nick=nick, character=character, ws=ws,
                    token=token, send_timeout=self.send_timeout, room=room_id, **profile)
        peer.on_failure = lambda: self._failed(room_id, peer)
        peer.join_seq = self.next_seq() if seq is None else seq
        if token:
            room.cheer_gone.pop(token, None)
            self.by_save.setdefault(token, {}).setdefault(room_id, {})[peer.id] = peer
        room.peers[peer.id] = peer
        if room.host is None:
            room.host = peer.id
        if pending is not None and token and token == pending.host:
            # The host of the last run is back: the role returns to it, and the listing with it.
            room.host = peer.id
            if pending.public and may_list:
                room.public = True
            del self.restoring[room_id]
        return peer

    def next_seq(self) -> int:
        """The next Peer.join_seq, shared by room joins and dou dizhu connections."""
        self._joins += 1
        return self._joins

    def rooms_of_save(self, token: str | None) -> set[str]:
        """The rooms [token] has a member in."""
        by_room = self.by_save.get(token) if token else None
        return set(by_room) if by_room else set()

    def peers_of_save(self, token: str | None) -> list[tuple[str, Peer]]:
        """(room id, member) for every member of [token], room by room."""
        by_room = self.by_save.get(token) if token else None
        if not by_room:
            return []
        return [(rid, peer) for rid, peers in list(by_room.items()) for peer in list(peers.values()) if peer.active]

    async def _failed(self, room_id: str, peer: Peer) -> None:
        if not await self.depart(room_id, peer.id):
            return
        try:
            await asyncio.wait_for(peer.ws.close(code=1013), self.send_timeout)
        except (asyncio.TimeoutError, RuntimeError, OSError):
            pass

    def leave(self, room_id: str, peer_id: str) -> bool:
        room = self.rooms.get(room_id)
        if room is None:
            return False
        peer = room.peers.pop(peer_id, None)
        if peer is None:
            return False
        peer.active = False
        if peer.token:
            by_room = self.by_save.get(peer.token)
            if by_room is not None:
                in_room = by_room.get(room_id)
                if in_room is not None:
                    in_room.pop(peer_id, None)
                    if not in_room:
                        del by_room[room_id]
                if not by_room:
                    del self.by_save[peer.token]
        if peer.token in room.cheer and not any(p.token == peer.token for p in room.peers.values()):
            room.cheer_gone[peer.token] = self.clock()
        if peer.writer and peer.writer is not asyncio.current_task():
            peer.writer.cancel()
        room.motions.pop(peer_id, None)
        room.edges = [edge for edge in room.edges if edge.sender != peer_id]
        room.taps.pop(peer_id, None)
        for other in room.peers.values():
            other.motion_ids.discard(peer_id)
            other.sent_motion.pop(peer_id, None)
        if not room.peers:
            for timer in (room.motion_timer, room.cheer_timer):
                if timer:
                    timer.cancel()
            del self.rooms[room_id]
            self._keep_emptied(room_id, room, peer)
        elif room.host == peer_id:
            room.host = next(iter(room.peers))
        return True

    async def depart(self, room_id: str, peer_id: str) -> bool:
        """Remove a member and tell the room, including a new host."""
        room = self.rooms.get(room_id)
        host = room.host if room else None
        peer = room.peers.get(peer_id) if room else None
        if not self.leave(room_id, peer_id):
            return False
        await self.broadcast(room_id, {"type": "member_left", "id": peer_id})
        if room is not None and room_id in self.rooms and room.cheer:
            # The leaver's share moves to the others on everyone's bar.
            await self.broadcast(room_id, self.cheer_state(room))
        if room is not None and room_id in self.rooms and room.host != host:
            await self.broadcast(room_id, {"type": "room_info", **room.info()})
        if peer is not None and self.on_depart is not None:
            await self.on_depart(room_id, peer)
        return True

    def public_rooms(self, limit: int) -> list[dict]:
        """Public rooms with space first, then by member count."""
        listed = [r for r in self.rooms.values() if r.public and r.host in r.peers]
        listed.sort(key=lambda r: (len(r.peers) >= self.max_size, -len(r.peers)))
        out = []
        for room in listed[:limit]:
            host = room.peers[room.host]
            out.append({"room": room.id, "name": room.name, "host": {"nick": host.nick, "character": host.character},
                        "members": len(room.peers), "max": self.max_size})
        return out

    def members(self, room_id: str) -> list[Peer]:
        room = self.rooms.get(room_id)
        return list(room.peers.values()) if room else []

    async def broadcast(self, room_id: str, data: dict, exclude: str | None = None) -> None:
        room = self.rooms.get(room_id)
        if room:
            message = _Broadcast(data)
            for peer in list(room.peers.values()):
                if peer.id != exclude:
                    peer.enqueue(message)

    async def hide(self, room_id: str, peer: Peer, hidden: bool) -> None:
        """Stops showing the room this member's taps and motion, or shows them again. A hidden member rests in
        everyone's view; shown again, it takes the pose it holds now."""
        if hidden == peer.hidden:
            return
        if hidden:
            held = peer.motion
            if held is not None and held != RESTING:
                await self.motion(room_id, peer, dict(RESTING))
            peer.hidden, peer.unseen = True, held
        else:
            held, peer.hidden, peer.unseen = peer.unseen, False, None
            if held is not None and held != peer.motion:
                await self.motion(room_id, peer, held)

    async def motion(self, room_id: str, peer: Peer, pose: dict) -> None:
        if peer.hidden:
            peer.unseen = pose
            return
        room = self.rooms[room_id]
        previous = peer.motion
        peer.motion = pose
        motion = _Motion(peer.id, pose)
        edge = previous is None or any(previous[k] != pose[k] for k in ("keyDown", "left", "right"))
        if edge:
            room.motions.pop(peer.id, None)
            for receiver in room.peers.values():
                if receiver.motion_version >= 3:
                    continue
                update = motion.for_peer(receiver)
                if update:
                    receiver.enqueue({"type": "motion_edge" if receiver.motion_version == 2 else "motion", **update})
            self._queue_edge(room, motion)
        else:
            room.motions[peer.id] = motion
            self._tick_soon(room)

    def tap(self, room_id: str, peer: Peer, count: int) -> None:
        """Holds [count] taps of [peer] (its Peer.taps already counts them) for the room's next tick."""
        room = self.rooms.get(room_id)
        if room is None or count <= 0:
            return
        held = room.taps.get(peer.id)
        room.taps[peer.id] = [count + (held[0] if held else 0), peer.taps]
        self._tick_soon(room)

    def _tick_soon(self, room: Room) -> None:
        if room.motion_timer is None:
            room.motion_timer = asyncio.get_running_loop().call_later(self.motion_interval, self._flush_tick, room)

    def _queue_edge(self, room: Room, motion: _Motion) -> None:
        """Holds an edge for the version 3 and later receivers until the room's next tick."""
        if not any(p.motion_version >= 3 and p.id != motion.sender for p in room.peers.values()):
            return
        mine = [i for i, edge in enumerate(room.edges) if edge.sender == motion.sender]
        if len(mine) >= MAX_EDGES_PER_BATCH:
            # Faster than anyone can watch: the oldest of this member's edges gives way.
            del room.edges[mine[0]]
        room.edges.append(motion)
        self._tick_soon(room)

    def _flush_tick(self, room: Room) -> None:
        """Sends each member what the room's tick gathered, as changes against what it already has. Version 3 gets
        the edges in order, then the positions (which must not overtake an edge), in one `motion_edges`; version 4
        gets those and the taps in one `room_tick`. Older versions get the positions in one message (they had the
        edges as they came). Up to version 3 every member's taps follow as one `tap` message each; the writes of one
        tick leave together (app/ws_writes.py)."""
        if room.motion_timer is not None:
            room.motion_timer.cancel()
            room.motion_timer = None
        if self.rooms.get(room.id) is not room:
            return
        edges, room.edges = room.edges, []
        updates = list(room.motions.values())
        room.motions.clear()
        taps = [{"id": pid, "count": count, "total": total} for pid, (count, total) in room.taps.items()]
        room.taps = {}
        for receiver in list(room.peers.values()):
            if receiver.motion_version >= 3:
                motions = [delta for edge in edges if (delta := edge.for_peer(receiver))]
                motions.extend(delta for update in updates if (delta := update.for_peer(receiver)))
                if receiver.motion_version >= 4:
                    if motions or taps:
                        receiver.enqueue({"type": "room_tick", "motions": motions, "taps": taps})
                    continue
                if motions:
                    receiver.enqueue({"type": "motion_edges", "edges": motions})
            else:
                motions = [delta for update in updates if (delta := update.for_peer(receiver))]
                if motions:
                    receiver.enqueue({"type": "motion_delta" if receiver.motion_version >= 2 else "motion_batch",
                                      "motions": motions})
            for tap in taps:
                receiver.enqueue({"type": "tap", **tap})

    def subscribe_motion(self, room_id: str, peer: Peer, ids: list[str]) -> None:
        room = self.rooms[room_id]
        wanted = (set(ids) & room.peers.keys()) - {peer.id}
        peer.sent_motion = {pid: pose for pid, pose in peer.sent_motion.items() if pid in wanted}
        peer.motion_ids = wanted
        snapshot = []
        for pid in sorted(wanted):
            if pid not in peer.sent_motion:
                pose = pack_motion(room.peers[pid].motion or RESTING)
                peer.sent_motion[pid] = pose
                snapshot.append({"id": pid, **pose})
        if snapshot:
            peer.enqueue({"type": "motion_snapshot", "motions": snapshot})

    # ------------------------------------------------------------------ cheer
    def _cheer_saves(self, room: Room) -> set[str]:
        """Saves that count for the round: those in the room, and those that left less than CHEER_GRACE ago."""
        now = self.clock()
        room.cheer_gone = {save: at for save, at in room.cheer_gone.items() if now - at < CHEER_GRACE}
        return {p.token for p in room.peers.values() if p.token} | set(room.cheer_gone)

    def _bar(self, room: Room, saves: set[str]) -> tuple[int, list[str]]:
        """The taps on the bar (every save's that reached CHEER_MIN_SHARE, also one gone for good) and the saves among
        [saves] that cheer."""
        on_bar = {save: n for save, n in room.cheer.items() if n >= CHEER_MIN_SHARE}
        return sum(on_bar.values()), [save for save in on_bar if save in saves]

    def cheer_state(self, room: Room) -> dict:
        """The cheer bar as members see it: the target for the saves cheering now, the taps on the bar up to it, each
        present member's share (also one not on the bar yet), how many saves cheer and what each would get, and the
        rounds finished."""
        total, cheering = self._bar(room, self._cheer_saves(room))
        count = len(cheering)
        target = CHEER_PER_SAVE * max(CHEER_MIN_SAVES, count)
        shares = {p.id: room.cheer[p.token] for p in room.peers.values() if p.token and room.cheer.get(p.token)}
        return {"type": "cheer", "target": target, "minShare": CHEER_MIN_SHARE,
                "total": min(total, target), "shares": shares, "count": count,
                "reward": CHEER_REWARD_PER_SAVE * max(CHEER_MIN_SAVES, count), "rounds": room.cheer_rounds}

    def cheer(self, pid: str, taps: int) -> tuple[Room, int, list[str], int] | None:
        """Adds [taps] paid taps of save [pid] to the round of the room it joined last. When the round is then full,
        returns the room, the round's number, the saves to pay and the shards for each; progress otherwise goes out
        by itself. A round left full by a save whose grace ran out finishes with the next taps anyone puts in."""
        seats = self.peers_of_save(pid) if taps > 0 else []
        if not seats:
            return None
        room = self.rooms[max(seats, key=lambda seat: seat[1].join_seq)[0]]
        saves = self._cheer_saves(room)
        if len(saves) < CHEER_MIN_SAVES:
            return None
        room.cheer[pid] = room.cheer.get(pid, 0) + taps
        total, cheering = self._bar(room, saves)
        if len(cheering) < CHEER_MIN_SAVES or total < CHEER_PER_SAVE * len(cheering):
            if room.cheer_timer is None:
                room.cheer_timer = asyncio.get_running_loop().call_later(self.cheer_interval, self._send_cheer, room)
            return None
        room.cheer = {}
        room.cheer_gone = {}
        room.cheer_rounds += 1
        if room.cheer_timer is not None:
            room.cheer_timer.cancel()
            room.cheer_timer = None
        return room, room.cheer_rounds, cheering, CHEER_REWARD_PER_SAVE * len(cheering)

    def _send_cheer(self, room: Room) -> None:
        room.cheer_timer = None
        if self.rooms.get(room.id) is not room:
            return
        state = self.cheer_state(room)
        for peer in list(room.peers.values()):
            peer.enqueue(state)

    async def cheer_done(self, room: Room, number: int, paid: dict[str, int]) -> None:
        """Tells the room round [number] finished, with the shards each paid member got (0 once its day's cheer is
        used up), then the bar as it stands."""
        if self.rooms.get(room.id) is not room:
            return
        rewards = {p.id: paid[p.token] for p in room.peers.values() if p.token in paid}
        await self.broadcast(room.id, {"type": "cheer_done", "round": number, "rewards": rewards})
        await self.broadcast(room.id, self.cheer_state(room))

    def rename(self, room: Room, raw: str) -> bool:
        """Names [room] (cleaned, blocked words masked; "" for none); whether what the room shows changed."""
        raw = clean_room_name(raw)[:ROOM_NAME_MAX]
        shown = self.mask(raw) if raw else ""
        changed = shown != room.name
        room.raw_name, room.name = raw, shown
        return changed

    def remask_names(self) -> list[Room]:
        """Masks every room's name again (after the blocked words changed); the rooms whose name changed."""
        changed = []
        for room in list(self.rooms.values()):
            shown = self.mask(room.raw_name) if room.raw_name else ""
            if shown != room.name:
                room.name = shown
                changed.append(room)
        return changed

    def drink(self, room_id: str, peer: Peer, now: float) -> bool:
        """Tells the rest of the room that [peer] drank water; False, and nothing sent, inside DRINK_INTERVAL."""
        room = self.rooms.get(room_id)
        if room is None or now - peer.drink_at < DRINK_INTERVAL:
            return False
        peer.drink_at = now
        message = {"type": "drink", "id": peer.id}
        for receiver in list(room.peers.values()):
            if receiver is not peer:
                receiver.enqueue(message)
        return True

    def poke(self, room_id: str, peer: Peer, target_id: str, now: float) -> None:
        """Tells the room that [peer] poked [target_id]; raises PokeRefused (no_member, poke_cooldown)."""
        room = self.rooms.get(room_id)
        target = room.peers.get(target_id) if room else None
        if target is None or target is peer:
            raise PokeRefused("no_member")
        if now - peer.poke_at < POKE_INTERVAL or now - peer.poked.get(target_id, float("-inf")) < POKE_SAME_INTERVAL:
            raise PokeRefused("poke_cooldown")
        peer.poke_at = now
        peer.poked = {pid: at for pid, at in peer.poked.items() if now - at < POKE_SAME_INTERVAL and pid in room.peers}
        peer.poked[target_id] = now
        message = {"type": "poke", "from": peer.id, "to": target_id}
        for receiver in list(room.peers.values()):
            receiver.enqueue({**message, "quiet": True} if receiver is target and target.dnd else message)

    async def pose(self, room_id: str, peer: Peer, patch: dict) -> None:
        pose = dict((peer.unseen if peer.hidden else peer.motion) or RESTING)
        if "x" in patch:
            pose["dx"] = patch["x"] / 4
        if "y" in patch:
            pose["dy"] = patch["y"] / 4
        if "b" in patch:
            pose.update(keyDown=bool(patch["b"] & 1), left=bool(patch["b"] & 2), right=bool(patch["b"] & 4))
        await self.motion(room_id, peer, pose)
