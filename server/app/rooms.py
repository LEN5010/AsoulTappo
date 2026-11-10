"""In-memory rooms with ordered per-connection writers and 50ms motion batches."""
from __future__ import annotations

import asyncio
import secrets
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

MAX_ROOM_SIZE = 20
MAX_OUTBOX = 256


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
        if data["type"] == "motion_batch" and self.outbox and self.outbox[-1][0]["type"] == "motion_batch":
            previous, _ = self.outbox[-1]
            latest = {m["id"]: m for m in previous["motions"]}
            latest.update({m["id"]: m for m in data["motions"]})
            self.outbox[-1] = ({"type": "motion_batch", "motions": list(latest.values())}, None)
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
    host: str | None = None
    public: bool = False
    # saves the host removed; gone with the room
    banned: set[str] = field(default_factory=set)
    # save -> (emote key, monotonic expiry): a duel loser's sticker, shown again when it rejoins
    stickers: dict[str, tuple[str, float]] = field(default_factory=dict)

    def info(self) -> dict:
        """Room-wide state sent in `joined` and `room_info`."""
        return {"host": self.host, "public": self.public}


class RoomManager:
    def __init__(self, max_size: int = MAX_ROOM_SIZE, send_timeout: float = 2.0,
                 motion_interval: float = 0.05) -> None:
        self.max_size = max_size
        self.send_timeout = send_timeout
        self.motion_interval = motion_interval
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
        if peer.writer and peer.writer is not asyncio.current_task():
            peer.writer.cancel()
        room.motions.pop(peer_id, None)
        if not room.peers:
            if room.motion_timer:
                room.motion_timer.cancel()
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
            await self.broadcast(room_id, {"type": "motion", "id": peer.id, **pose}, exclude=peer.id)
        else:
            room.motions[peer.id] = {"id": peer.id, **pose}
            if room.motion_timer is None:
                room.motion_timer = asyncio.get_running_loop().call_later(self.motion_interval, self._flush_motion, room)

    def _flush_motion(self, room: Room) -> None:
        room.motion_timer = None
        updates = list(room.motions.values())
        room.motions.clear()
        for peer in list(room.peers.values()):
            motions = [m for m in updates if m["id"] != peer.id]
            if motions:
                peer.enqueue({"type": "motion_batch", "motions": motions})
