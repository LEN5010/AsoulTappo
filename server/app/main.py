"""AsoulTappo room server: FastAPI + WebSocket, in-memory state."""
from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .models import (
    EmoteBroadcast, EmoteMsg, ErrorMsg, JoinedMsg, JoinMsg, LeaveMsg, Member,
    MemberJoinedMsg, MemberLeftMsg, StateBroadcast, StateMsg, TapBroadcast,
    TapMsg, client_message_adapter,
)
from .rooms import Peer, RoomFull, RoomManager

app = FastAPI(title="AsoulTappo server", version="0.1.0")
manager = RoomManager()


def _member(p: Peer) -> Member:
    return Member(id=p.id, nick=p.nick, character=p.character, taps=p.taps)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "rooms": len(manager.rooms)}


@app.post("/rooms")
async def create_room() -> dict:
    """Create a room and return its random long ID."""
    return {"room": manager.create_room()}


async def _leave(room_id: str | None, peer: Peer | None) -> None:
    if room_id and peer:
        manager.leave(room_id, peer.id)
        await manager.broadcast(room_id, MemberLeftMsg(id=peer.id).model_dump())


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    room_id: str | None = None
    peer: Peer | None = None

    async def err(code: str, message: str = "") -> None:
        await ws.send_json(ErrorMsg(code=code, message=message).model_dump())

    try:
        while True:
            raw = await ws.receive_json()
            try:
                msg = client_message_adapter.validate_python(raw)
            except ValidationError:
                await err("bad_message", "invalid message")
                continue

            if isinstance(msg, JoinMsg):
                if peer is not None:
                    await err("already_joined")
                    continue
                try:
                    peer = manager.join(msg.room, msg.nick, msg.character, ws)
                except RoomFull:
                    await err("room_full", "room is full (max 20)")
                    continue
                room_id = msg.room
                await ws.send_json(JoinedMsg(
                    room=room_id, you=peer.id,
                    members=[_member(p) for p in manager.members(room_id)],
                ).model_dump())
                await manager.broadcast(
                    room_id, MemberJoinedMsg(member=_member(peer)).model_dump(), exclude=peer.id)
                continue

            if peer is None or room_id is None:
                await err("not_joined", "send join first")
                continue

            if isinstance(msg, LeaveMsg):
                await _leave(room_id, peer)
                room_id, peer = None, None
            elif isinstance(msg, TapMsg):
                peer.taps += msg.count
                await manager.broadcast(room_id, TapBroadcast(
                    id=peer.id, count=msg.count, total=peer.taps).model_dump())
            elif isinstance(msg, EmoteMsg):
                await manager.broadcast(room_id, EmoteBroadcast(
                    id=peer.id, emote=msg.emote).model_dump())
            elif isinstance(msg, StateMsg):
                peer.character = msg.character
                await manager.broadcast(room_id, StateBroadcast(
                    id=peer.id, character=msg.character).model_dump())
    except WebSocketDisconnect:
        pass
    finally:
        await _leave(room_id, peer)
