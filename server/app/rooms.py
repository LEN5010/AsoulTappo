"""In-memory rooms with ordered writers, subscriptions, 100ms motion batches and 50ms button-edge batches."""
from __future__ import annotations

import asyncio
import math
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

MAX_ROOM_SIZE = 20
MAX_OUTBOX = 256
# Motion formats: 1 full poses; 2 packed deltas for subscribed members, one message per button edge;
# 3 as 2 with the edges of a room gathered into one ordered message per receiver.
MOTION_VERSION = 3
# Edges kept per member within one edge batch; earlier ones are dropped, the latest pose always goes out.
MAX_EDGES_PER_BATCH = 6
# Room messages beyond the 1.1 set, listed in `joined` for clients that announce a motion version.
FEATURES = ("poke", "profile", "cheer")
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
# Profile requests: one per connection this often; each reads the save.
PROFILE_INTERVAL = 0.3


class PokeRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
RESTING = {"dx": 0.0, "dy": 0.0, "keyDown": False, "left": False, "right": False}


def pack_motion(pose: dict) -> dict[str, int]:
    return {"x": math.floor(pose["dx"] * 4 + .5), "y": math.floor(pose["dy"] * 4 + .5),
            "b": int(pose["keyDown"]) | int(pose["left"]) << 1 | int(pose["right"]) << 2}


class Sender(Protocol):
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


class RoomFull(Exception):
    pass


class Banned(Exception):
    """The save was removed from this room by its host."""


class NeedSave(Exception):
    """Public rooms take members with a save only."""


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
    # turns rock-paper-scissors invites down; never shown to the room
    dnd: bool = False
    # joined with a valid main-site account token: may make the room public on a server with accounts
    account: bool = False
    emotes: set[str] = field(default_factory=set)
    last_emote: float = 0.0
    tap_budget: float = 0.0
    tap_at: float = 0.0
    motion: dict[str, float | bool] | None = None
    motion_version: int = 1
    # Monotonic time of the last poke sent, and of the last one sent to each member.
    poke_at: float = float("-inf")
    poked: dict[str, float] = field(default_factory=dict)
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
        # Only coalesce adjacent position batches: ordered edges remain between them.
        if data["type"] in ("motion_batch", "motion_delta") and self.outbox and self.outbox[-1][0]["type"] == data["type"]:
            previous, _ = self.outbox[-1]
            latest = {m["id"]: m.copy() for m in previous["motions"]}
            for motion in data["motions"]:
                latest.setdefault(motion["id"], {}).update(motion)
            self.outbox[-1] = ({"type": data["type"], "motions": list(latest.values())}, None)
        elif data["type"] == "motion_edges" and self.outbox and self.outbox[-1][0]["type"] == "motion_edges":
            # Edge batches still waiting to go out join up; the order of their edges is kept.
            previous, _ = self.outbox[-1]
            self.outbox[-1] = ({"type": "motion_edges", "edges": previous["edges"] + data["edges"]}, None)
        elif len(self.outbox) >= MAX_OUTBOX:
            self.overloaded = True
            if done is not None:
                done.set_exception(ConnectionError("outbox full"))
        else:
            self.outbox.append((data, done))
        self.ready.set()
        if self.writer is None:
            self.writer = asyncio.create_task(self._write())

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
                while self.outbox:
                    if self.overloaded:
                        raise ConnectionError("outbox full")
                    data, current = self.outbox.popleft()
                    await asyncio.wait_for(self.ws.send_json(data), self.send_timeout)
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


@dataclass
class Room:
    id: str
    # in join order: the host passes to the earliest remaining member
    peers: dict[str, Peer] = field(default_factory=dict)
    motions: dict[str, dict] = field(default_factory=dict)
    motion_timer: asyncio.TimerHandle | None = None
    # Button edges for motion version 3 receivers, in the order they happened: (member id, full pose).
    edges: list[tuple[str, dict]] = field(default_factory=list)
    edge_timer: asyncio.TimerHandle | None = None
    host: str | None = None
    public: bool = False
    # saves the host removed; gone with the room
    banned: set[str] = field(default_factory=set)
    # This cheer round's paid taps by player id (a save that left keeps its taps on the bar), when each save with taps
    # on it left (monotonic clock; gone again when it comes back), and rounds finished.
    cheer: dict[str, int] = field(default_factory=dict)
    cheer_gone: dict[str, float] = field(default_factory=dict)
    cheer_rounds: int = 0
    cheer_timer: asyncio.TimerHandle | None = None

    def info(self) -> dict:
        """Room-wide state sent in `joined` and `room_info`."""
        return {"host": self.host, "public": self.public}


class RoomManager:
    def __init__(self, max_size: int = MAX_ROOM_SIZE, send_timeout: float = 2.0,
                 motion_interval: float = 0.1, edge_interval: float = 0.05,
                 cheer_interval: float = CHEER_SEND_INTERVAL, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_size = max_size
        self.send_timeout = send_timeout
        self.motion_interval = motion_interval
        self.edge_interval = edge_interval
        self.cheer_interval = cheer_interval
        self.clock = clock
        self._joins = 0
        self.rooms: dict[str, Room] = {}
        # Called once for every member removed by depart (leave, kick, failed writer), after member_left.
        self.on_depart: Callable[[str, Peer], Awaitable[None]] | None = None

    def create_room(self) -> str:
        return new_room_id()

    def join(self, room_id: str, nick: str, character: str, ws: Sender,
             token: str | None = None, **profile: str | None) -> Peer:
        """[token]: the joining save's player id, None without a save."""
        room = self.rooms.get(room_id)
        if room is not None:
            if token and token in room.banned:
                raise Banned(room_id)
            if room.public and not token:
                raise NeedSave(room_id)
            if len(room.peers) >= self.max_size:
                raise RoomFull(room_id)
        if room is None:
            room = self.rooms[room_id] = Room(room_id)
        peer = Peer(id=secrets.token_hex(4), nick=nick, character=character, ws=ws,
                    token=token, send_timeout=self.send_timeout, **profile)
        peer.on_failure = lambda: self._failed(room_id, peer)
        self._joins += 1
        peer.join_seq = self._joins
        if token:
            room.cheer_gone.pop(token, None)
        room.peers[peer.id] = peer
        if room.host is None:
            room.host = peer.id
        return peer

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
        if peer.token in room.cheer and not any(p.token == peer.token for p in room.peers.values()):
            room.cheer_gone[peer.token] = self.clock()
        if peer.writer and peer.writer is not asyncio.current_task():
            peer.writer.cancel()
        room.motions.pop(peer_id, None)
        room.edges = [edge for edge in room.edges if edge[0] != peer_id]
        for other in room.peers.values():
            other.motion_ids.discard(peer_id)
            other.sent_motion.pop(peer_id, None)
        if not room.peers:
            for timer in (room.motion_timer, room.edge_timer, room.cheer_timer):
                if timer:
                    timer.cancel()
            del self.rooms[room_id]
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
            out.append({"room": room.id, "host": {"nick": host.nick, "character": host.character},
                        "members": len(room.peers), "max": self.max_size})
        return out

    def members(self, room_id: str) -> list[Peer]:
        room = self.rooms.get(room_id)
        return list(room.peers.values()) if room else []

    async def broadcast(self, room_id: str, data: dict, exclude: str | None = None) -> None:
        room = self.rooms.get(room_id)
        if room:
            for peer in list(room.peers.values()):
                if peer.id != exclude:
                    peer.enqueue(data)

    async def motion(self, room_id: str, peer: Peer, pose: dict) -> None:
        room = self.rooms[room_id]
        previous = peer.motion
        peer.motion = pose
        edge = previous is None or any(previous[k] != pose[k] for k in ("keyDown", "left", "right"))
        if edge:
            room.motions.pop(peer.id, None)
            for receiver in room.peers.values():
                if receiver.motion_version >= 3:
                    continue
                update = self._motion_for(receiver, peer.id, pose)
                if update:
                    receiver.enqueue({"type": "motion_edge" if receiver.motion_version == 2 else "motion", **update})
            self._queue_edge(room, peer.id, pose)
        else:
            room.motions[peer.id] = {"id": peer.id, **pose}
            if room.motion_timer is None:
                room.motion_timer = asyncio.get_running_loop().call_later(self.motion_interval, self._flush_motion, room)

    def _queue_edge(self, room: Room, sender: str, pose: dict) -> None:
        """Holds an edge for the version 3 receivers until the room's edge batch goes out."""
        if not any(p.motion_version >= 3 and p.id != sender for p in room.peers.values()):
            return
        mine = [i for i, (pid, _) in enumerate(room.edges) if pid == sender]
        if len(mine) >= MAX_EDGES_PER_BATCH:
            # Faster than anyone can watch: the oldest of this member's edges gives way.
            del room.edges[mine[0]]
        room.edges.append((sender, pose))
        if room.edge_timer is None:
            room.edge_timer = asyncio.get_running_loop().call_later(self.edge_interval, self._flush_edges, room)

    def _flush_edges(self, room: Room) -> None:
        """Each version 3 receiver gets the room's edges in order, as changes against what it already has."""
        if room.edge_timer is not None:
            room.edge_timer.cancel()
            room.edge_timer = None
        edges, room.edges = room.edges, []
        if not edges:
            return
        for receiver in list(room.peers.values()):
            if receiver.motion_version < 3:
                continue
            out = [delta for sender, pose in edges if (delta := self._motion_for(receiver, sender, pose))]
            if out:
                receiver.enqueue({"type": "motion_edges", "edges": out})

    def _flush_motion(self, room: Room) -> None:
        room.motion_timer = None
        # Positions that came after an edge must not overtake it.
        self._flush_edges(room)
        updates = list(room.motions.values())
        room.motions.clear()
        for peer in list(room.peers.values()):
            motions = [delta for m in updates if (delta := self._motion_for(peer, m["id"], m))]
            if motions:
                peer.enqueue({"type": "motion_delta" if peer.motion_version >= 2 else "motion_batch", "motions": motions})

    def _motion_for(self, receiver: Peer, sender: str, pose: dict) -> dict | None:
        if receiver.id == sender:
            return None
        if receiver.motion_version < 2:
            return {"id": sender, **pose}
        if sender not in receiver.motion_ids:
            return None
        packed = pack_motion(pose)
        previous = receiver.sent_motion.get(sender, {})
        delta = {key: value for key, value in packed.items() if previous.get(key) != value}
        receiver.sent_motion[sender] = packed
        return {"id": sender, **delta} if delta else None

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
        seats = [(peer.join_seq, room) for room in self.rooms.values()
                 for peer in room.peers.values() if peer.token == pid]
        if taps <= 0 or not seats:
            return None
        room = max(seats, key=lambda seat: seat[0])[1]
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
        pose = dict(peer.motion or RESTING)
        if "x" in patch:
            pose["dx"] = patch["x"] / 4
        if "y" in patch:
            pose["dy"] = patch["y"] / 4
        if "b" in patch:
            pose.update(keyDown=bool(patch["b"] & 1), left=bool(patch["b"] & 2), right=bool(patch["b"] & 4))
        await self.motion(room_id, peer, pose)
