"""In-memory room manager. Single-process only (see docs/ARCHITECTURE.md)."""
from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from typing import Any, Protocol

MAX_ROOM_SIZE = 20


class Sender(Protocol):
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


class RoomFull(Exception):
    pass


def new_room_id() -> str:
    """Long, unguessable room ID (~128 bits, URL-safe)."""
    return secrets.token_urlsafe(16)


@dataclass
class Peer:
    id: str
    nick: str
    character: str
    ws: Sender
    taps: int = 0
    uid: str | None = None
    token: str | None = None  # secret player token (never broadcast)
    emotes: set[str] = field(default_factory=set)  # emote keys known to be owned
    last_emote: float = 0.0
    motion: dict[str, float | bool] | None = None
    active: bool = True
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, data: dict, timeout: float) -> None:
        async def write() -> None:
            async with self.send_lock:
                await self.ws.send_json(data)
        await asyncio.wait_for(write(), timeout)


@dataclass
class Room:
    id: str
    peers: dict[str, Peer] = field(default_factory=dict)


class RoomManager:
    def __init__(self, max_size: int = MAX_ROOM_SIZE, send_timeout: float = 2.0) -> None:
        self.max_size = max_size
        self.send_timeout = send_timeout
        self.rooms: dict[str, Room] = {}

    def create_room(self) -> str:
        return new_room_id()

    def join(self, room_id: str, nick: str, character: str, ws: Sender,
             token: str | None = None,
             **profile: str | None) -> Peer:
        """Join (auto-creating) a room. Raises RoomFull when at capacity.

        ``profile`` carries the stable room ``uid``."""
        room = self.rooms.get(room_id)
        if room is None:
            room = self.rooms[room_id] = Room(room_id)
        if len(room.peers) >= self.max_size:
            raise RoomFull(room_id)
        peer = Peer(id=secrets.token_hex(4), nick=nick, character=character, ws=ws,
                    token=token, **profile)
        room.peers[peer.id] = peer
        return peer

    def leave(self, room_id: str, peer_id: str) -> bool:
        room = self.rooms.get(room_id)
        if room is None:
            return False
        peer = room.peers.pop(peer_id, None)
        if peer is None:
            return False
        peer.active = False
        if not room.peers:
            del self.rooms[room_id]  # empty rooms are garbage-collected
        return True

    def members(self, room_id: str) -> list[Peer]:
        room = self.rooms.get(room_id)
        return list(room.peers.values()) if room else []

    async def broadcast(self, room_id: str, data: dict, exclude: str | None = None) -> None:
        room = self.rooms.get(room_id)
        if room is None:
            return
        targets = [p for p in room.peers.values() if p.id != exclude]
        results = await asyncio.gather(
            *(p.send(data, self.send_timeout) for p in targets), return_exceptions=True)
        removed = [p for p, result in zip(targets, results)
                   if isinstance(result, Exception) and self.leave(room_id, p.id)]
        if removed:
            await asyncio.gather(
                *(asyncio.wait_for(p.ws.close(code=1013), self.send_timeout) for p in removed),
                return_exceptions=True)
            for p in removed:
                await self.broadcast(room_id, {"type": "member_left", "id": p.id})
