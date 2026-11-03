"""AsoulTappo room server: FastAPI + WebSocket rooms, SQLite-backed item progression."""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .game import Game, GameError
from .manifest import Manifest, find_packs_dir
from .models import (
    EmoteBroadcast, EmoteMsg, ErrorMsg, JoinedMsg, JoinMsg, LeaveMsg, Member,
    MemberJoinedMsg, MemberLeftMsg, PingMsg, PongMsg, StateBroadcast, StateMsg, TapBroadcast,
    TapMsg, client_message_adapter,
)
from .rooms import Peer, RoomFull, RoomManager
from .store import Store

app = FastAPI(title="AsoulTappo server", version="0.3.0")
manager = RoomManager()
EMOTE_INTERVAL = 0.25  # seconds between emotes of one member

PACKS_DIR = find_packs_dir()
manifest = Manifest.load(PACKS_DIR / "manifest.json")
# ASOULTAPPO_DB: sqlite file (default data/asoultappo.db, ":memory:" for throw-away runs)
game = Game(Store(os.environ.get("ASOULTAPPO_DB", "data/asoultappo.db")), manifest)

# CORS for the browser/Tauri webview calling the HTTP API.
# ASOULTAPPO_CORS_ORIGINS: comma-separated origins, default "*" (no cookies are used).
_origins = [o.strip() for o in os.environ.get("ASOULTAPPO_CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _member(p: Peer) -> Member:
    return Member(id=p.id, uid=p.uid, nick=p.nick, character=p.character, taps=p.taps,
                  frame=p.frame, badge=p.badge, head=p.head, desk=p.desk)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "rooms": len(manager.rooms)}


@app.post("/rooms")
async def create_room() -> dict:
    """Create a room and return its random long ID."""
    return {"room": manager.create_room()}


# ------------------------------------------------------------------ HTTP API
def _guard(fn, *args):
    try:
        return fn(*args)
    except GameError as e:
        status = 401 if e.code == "bad_token" else 409 if e.code in ("no_box", "no_shards", "owned") else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": e.message})


class ActivityBody(BaseModel):
    taps: int = Field(ge=0, le=100000)
    session: str = Field(min_length=16, max_length=128)
    sequence: int = Field(ge=1)


class DecorBody(BaseModel):
    frame: str | None = Field(default=None, max_length=32)
    badge: str | None = Field(default=None, max_length=32)


class OpenBody(BaseModel):
    count: int = Field(default=1, ge=1, le=100)


class CraftBody(BaseModel):
    item: str = Field(min_length=1, max_length=64)


class LoadoutBody(BaseModel):
    """Loadout patch: only the given keys change.  "" clears head / desk / frame / badge."""

    character: str | None = Field(default=None, max_length=32)
    head: str | None = Field(default=None, max_length=48)
    desk: str | None = Field(default=None, max_length=48)
    theme: str | None = Field(default=None, max_length=48)
    favorites: list[str] | None = Field(default=None, max_length=16)
    frame: str | None = Field(default=None, max_length=32)
    badge: str | None = Field(default=None, max_length=32)


class PresetBody(BaseModel):
    """``loadout: null`` clears the slot."""

    loadout: LoadoutBody | None = None
    name: str | None = Field(default=None, max_length=24)


@app.get("/api/manifest")
def api_manifest() -> dict:
    return manifest.data


@app.get("/api/me")
def api_me(x_player_token: str = Header(default="")) -> dict:
    return _guard(game.status, x_player_token)


@app.post("/api/activity")
def api_activity(body: ActivityBody, x_player_token: str = Header(default="")) -> dict:
    """Report the number of taps since the last report (counts only, never content)."""
    return _guard(game.report_activity, x_player_token, body.taps, body.session, body.sequence)


@app.post("/api/boxes/open")
def api_open_box(body: OpenBody | None = None, x_player_token: str = Header(default="")) -> dict:
    return _guard(game.open_boxes, x_player_token, body.count if body else 1)


@app.post("/api/craft")
def api_craft(body: CraftBody, x_player_token: str = Header(default="")) -> dict:
    return _guard(game.craft, x_player_token, body.item)


@app.get("/api/loadout")
def api_loadout(x_player_token: str = Header(default="")) -> dict:
    return _guard(game.get_loadout, x_player_token)


@app.post("/api/loadout")
def api_set_loadout(body: LoadoutBody, x_player_token: str = Header(default="")) -> dict:
    return _guard(game.set_loadout, x_player_token, body.model_dump(exclude_unset=True))


@app.get("/api/presets")
def api_presets(x_player_token: str = Header(default="")) -> dict:
    return _guard(game.presets, x_player_token)


@app.post("/api/presets/{slot}")
def api_save_preset(slot: int, body: PresetBody, x_player_token: str = Header(default="")) -> dict:
    loadout: dict[str, Any] | None = body.loadout.model_dump(exclude_unset=True) if body.loadout else None
    return _guard(game.save_preset, x_player_token, slot, loadout, body.name)


@app.get("/api/collection")
def api_collection(x_player_token: str = Header(default="")) -> dict:
    return _guard(game.collection, x_player_token)


@app.post("/api/decor")
def api_decor(body: DecorBody, x_player_token: str = Header(default="")) -> dict:
    return _guard(game.set_decor, x_player_token, body.frame, body.badge)


# Heavy assets (card art, videos, theme backgrounds) as downloadable packs: /packs/index.json
if Path(PACKS_DIR).is_dir():
    app.mount("/packs", StaticFiles(directory=str(PACKS_DIR)), name="packs")


# ----------------------------------------------------------------- WebSocket
async def _leave(room_id: str | None, peer: Peer | None) -> None:
    if room_id and peer:
        if manager.leave(room_id, peer.id):
            await manager.broadcast(room_id, MemberLeftMsg(id=peer.id).model_dump())


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    room_id: str | None = None
    peer: Peer | None = None

    async def send(data: dict) -> None:
        if peer:
            await peer.send(data, manager.send_timeout)
        else:
            await asyncio.wait_for(ws.send_json(data), manager.send_timeout)

    async def err(code: str, message: str = "") -> None:
        await send(ErrorMsg(code=code, message=message).model_dump())

    try:
        while True:
            raw = await ws.receive_json()
            if peer is not None and not peer.active:
                break
            try:
                msg = client_message_adapter.validate_python(raw)
            except ValidationError:
                await err("bad_message", "invalid message")
                continue

            if isinstance(msg, PingMsg):  # keepalive, allowed before join
                await send(PongMsg().model_dump())
                continue

            if isinstance(msg, JoinMsg):
                if peer is not None:
                    await err("already_joined")
                    continue
                profile = await run_in_threadpool(game.profile_for, msg.token, msg.room)
                try:
                    peer = manager.join(msg.room, msg.nick, msg.character, ws, token=msg.token, **profile)
                except RoomFull:
                    await err("room_full", "room is full (max 20)")
                    continue
                room_id = msg.room
                await send(JoinedMsg(
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
                now = time.monotonic()
                if now - peer.last_emote < EMOTE_INTERVAL:
                    await err("rate_limited", "too many emotes")
                    continue
                if msg.emote not in peer.emotes:
                    if not await run_in_threadpool(game.owns_emote, peer.token, msg.emote):
                        await err("locked", "emote not owned")
                        continue
                    peer.emotes.add(msg.emote)
                peer.last_emote = now
                await manager.broadcast(room_id, EmoteBroadcast(
                    id=peer.id, emote=msg.emote).model_dump())
            elif isinstance(msg, StateMsg):
                if msg.frame is not None or msg.badge is not None:
                    if not peer.token:
                        await err("locked", "frame/badge need a player token")
                        continue
                    try:
                        st = await run_in_threadpool(game.set_decor, peer.token, msg.frame, msg.badge)
                    except GameError as e:
                        await err(e.code, e.message)
                        continue
                    peer.frame, peer.badge = st["frame"], st["badge"]
                if msg.head is not None or msg.desk is not None:
                    try:
                        acc = await run_in_threadpool(game.check_accessories, peer.token, msg.head, msg.desk)
                    except GameError as e:
                        await err(e.code, e.message)
                        continue
                    peer.head = acc.get("head", peer.head)
                    peer.desk = acc.get("desk", peer.desk)
                if msg.character is not None:
                    peer.character = msg.character
                if msg.nick is not None:
                    peer.nick = msg.nick
                await manager.broadcast(room_id, StateBroadcast(
                    id=peer.id, character=peer.character, nick=peer.nick,
                    frame=peer.frame, badge=peer.badge, head=peer.head, desk=peer.desk).model_dump())
    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        try:
            await asyncio.wait_for(ws.close(code=1013), manager.send_timeout)
        except (asyncio.TimeoutError, RuntimeError, OSError):
            pass
    finally:
        # shielded: the member_left broadcast must survive cancellation of this handler
        await asyncio.shield(_leave(room_id, peer))
