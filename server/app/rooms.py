"""In-memory room manager. Single-process only (see docs/ARCHITECTURE.md)."""
from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from typing import Any, Protocol

MAX_ROOM_SIZE = 20


class Sender(Protocol):
    async def send_json(self, data: Any) -> None: ...


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
    frame: str | None = None
    badge: str | None = None
    token: str | None = None  # secret player token (never broadcast)


@dataclass
class Room:
    id: str
    peers: dict[str, Peer] = field(default_factory=dict)


class RoomManager:
    def __init__(self, max_size: int = MAX_ROOM_SIZE) -> None:
        self.max_size = max_size
        self.rooms: dict[str, Room] = {}

    def create_room(self) -> str:
        rid = new_room_id()
        self.rooms[rid] = Room(rid)
        return rid

    def join(self, room_id: str, nick: str, character: str, ws: Sender,
             frame: str | None = None, badge: str | None = None, token: str | None = None) -> Peer:
        """Join (auto-creating) a room. Raises RoomFull when at capacity."""
        room = self.rooms.get(room_id)
        if room is None:
            room = self.rooms[room_id] = Room(room_id)
        if len(room.peers) >= self.max_size:
            raise RoomFull(room_id)
        peer = Peer(id=secrets.token_hex(4), nick=nick, character=character, ws=ws,
                    frame=frame, badge=badge, token=token)
        room.peers[peer.id] = peer
        return peer

    def leave(self, room_id: str, peer_id: str) -> None:
        room = self.rooms.get(room_id)
        if room is None:
            return
        room.peers.pop(peer_id, None)
        if not room.peers:
            del self.rooms[room_id]  # empty rooms are garbage-collected

    def members(self, room_id: str) -> list[Peer]:
        room = self.rooms.get(room_id)
        return list(room.peers.values()) if room else []

    async def broadcast(self, room_id: str, data: dict, exclude: str | None = None) -> None:
        room = self.rooms.get(room_id)
        if room is None:
            return
        targets = [p for p in room.peers.values() if p.id != exclude]
        results = await asyncio.gather(*(p.ws.send_json(data) for p in targets), return_exceptions=True)
        # failed sends are ignored; the disconnect handler cleans the peer up
        del results
