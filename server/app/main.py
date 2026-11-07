"""AsoulTappo room server: FastAPI + WebSocket rooms, SQLite-backed item progression."""
from __future__ import annotations

import asyncio
import os
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .accounts import MainAccounts
from .game import Game, GameError, PlayerId, player_id_for
from .manifest import Manifest, find_packs_dir
from .models import (
    EmoteBroadcast, EmoteMsg, ErrorMsg, JoinedMsg, JoinMsg, LeaveMsg, Member,
    MemberJoinedMsg, MemberLeftMsg, MotionMsg, PingMsg, PongMsg, StateBroadcast, StateMsg, TapBroadcast,
    TapMsg, client_message_adapter,
)
from .releases import ReleaseFeed
from .rooms import Peer, RoomFull, RoomManager
from .store import Store

app = FastAPI(title="AsoulTappo server", version="0.4.0")
manager = RoomManager()
EMOTE_INTERVAL = 0.25  # seconds between emotes of one member

PACKS_DIR = find_packs_dir()
manifest = Manifest.load(PACKS_DIR / "manifest.json")
# ASOULTAPPO_DB: sqlite file (default data/asoultappo.db, ":memory:" for throw-away runs)
game = Game(Store(os.environ.get("ASOULTAPPO_DB", "data/asoultappo.db")), manifest)

# MAIN_API_URL: the main site's API (official server: https://len5010.top/dynamics/api). Unset on
# self-hosted servers, which then offer guest saves only.
MAIN_API_URL = os.environ.get("MAIN_API_URL", "").strip().rstrip("/")
accounts = MainAccounts(MAIN_API_URL) if MAIN_API_URL else None
# The panel's update check reads the official release list even on self-hosted servers.
OFFICIAL_MAIN_API = "https://len5010.top/dynamics/api"
releases = ReleaseFeed(f"{MAIN_API_URL or OFFICIAL_MAIN_API}/tappo/release")

# ASOULTAPPO_ADMIN_KEY: shared secret the main site's admin backend sends as X-Admin-Key. Unset
# disables /admin. Keep /admin off the public proxy; the main site calls it on the same host.
ADMIN_KEY = os.environ.get("ASOULTAPPO_ADMIN_KEY", "")

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
    return Member(id=p.id, uid=p.uid, nick=p.nick, character=p.character, taps=p.taps, motion=p.motion,
                  plate=p.plate)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "rooms": len(manager.rooms)}


@app.post("/rooms")
async def create_room() -> dict:
    """Create a room and return its random long ID."""
    return {"room": manager.create_room()}


# ------------------------------------------------------------------ HTTP API
STATUS = {"bad_token": 401, "account_expired": 401, "save_linked": 401, "no_shards": 409, "owned": 409,
          "account_not_linked": 409, "account_unavailable": 503, "accounts_disabled": 404}


def _guard(fn, *args):
    try:
        return fn(*args)
    except GameError as e:
        raise HTTPException(status_code=STATUS.get(e.code, 400), detail={"code": e.code, "message": e.message})


def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


def _main_user(authorization: str) -> dict:
    if not accounts:
        raise GameError("accounts_disabled", "这个服务器没有接入主站账号")
    return accounts.user_for(_bearer(authorization))


def _who(token: str, authorization: str) -> PlayerId:
    """The save a request acts on: the account's linked save, or the guest token's own save."""
    if authorization:
        pid = game.store.linked_player(_main_user(authorization)["id"])
        if pid is None:
            raise GameError("account_not_linked", "账号还没有桌宠存档")
        return PlayerId(pid)
    pid = player_id_for(token)
    if game.store.account_for_player(pid):
        raise GameError("save_linked", "这份存档已绑定主站账号，请登录账号使用")
    return PlayerId(pid)


def player(x_player_token: str = Header(default=""), authorization: str = Header(default="")) -> PlayerId:
    return _guard(_who, x_player_token, authorization)


class ActivityBody(BaseModel):
    taps: int = Field(ge=0, le=100000)
    session: str = Field(min_length=16, max_length=128)
    sequence: int = Field(ge=1)


class CraftBody(BaseModel):
    item: str = Field(min_length=1, max_length=64)


class PresenceBody(BaseModel):
    session: str = Field(min_length=16, max_length=128)


class ResonanceBody(BaseModel):
    count: int = Field(default=1, ge=1, le=100)


class LoadoutBody(BaseModel):
    """Selected character, favorite emotes and name plate (null or "" for none)."""

    character: str | None = Field(default=None, max_length=32)
    favorites: list[str] | None = Field(default=None, max_length=16)
    plate: str | None = Field(default=None, max_length=64)


@app.get("/api/manifest")
def api_manifest() -> dict:
    return manifest.data


@app.get("/api/me")
def api_me(who: PlayerId = Depends(player)) -> dict:
    return _guard(game.status, who)


@app.post("/api/activity")
def api_activity(body: ActivityBody, who: PlayerId = Depends(player)) -> dict:
    """Report the number of taps since the last report (counts only, never content)."""
    return _guard(game.report_activity, who, body.taps, body.session, body.sequence)


@app.post("/api/presence")
def api_presence(body: PresenceBody, who: PlayerId = Depends(player)) -> dict:
    return _guard(game.presence, who, body.session)


@app.post("/api/resonance/draw")
def api_resonate(body: ResonanceBody, who: PlayerId = Depends(player)) -> dict:
    return _guard(game.resonate, who, body.count)


@app.post("/api/craft")
def api_craft(body: CraftBody, who: PlayerId = Depends(player)) -> dict:
    return _guard(game.craft, who, body.item)


@app.get("/api/loadout")
def api_loadout(who: PlayerId = Depends(player)) -> dict:
    return _guard(game.get_loadout, who)


@app.post("/api/loadout")
def api_set_loadout(body: LoadoutBody, who: PlayerId = Depends(player)) -> dict:
    return _guard(game.set_loadout, who, body.model_dump(exclude_unset=True))


@app.get("/api/info")
def api_info() -> dict:
    return {"accountLogin": accounts is not None, "mainApi": MAIN_API_URL or None}


@app.get("/api/client/release")
def api_client_release() -> dict:
    latest = releases.latest()
    if not latest:
        raise HTTPException(503, {"code": "release_unavailable", "message": "暂时查不到最新版本"})
    return latest


def _public_user(user: dict) -> dict:
    return {"id": user["id"], "username": user["username"], "email": user.get("email")}


@app.get("/api/account")
def api_account(authorization: str = Header(default="")) -> dict:
    user = _guard(_main_user, authorization)
    pid = game.store.linked_player(user["id"])
    return {"user": _public_user(user), "save": game.save_summary(pid) if pid else None}


def _link(token: str, authorization: str) -> dict:
    """Binds the account to this device's guest save, a new save, or reports two saves to choose from."""
    user = _main_user(authorization)
    guest = player_id_for(token) if token else None
    with game.store.transaction() as st:
        linked = st.linked_player(user["id"])
        if linked:
            if guest and guest != linked and st.has_player(guest) and not st.account_for_player(guest):
                summary = game.save_summary(guest)
                if summary["taps"] or summary["owned"]:
                    raise HTTPException(409, {"code": "account_has_save", "message": "账号已有桌宠存档",
                                              "account": game.save_summary(linked), "guest": summary})
            return {"user": _public_user(user), "save": game.save_summary(linked), "linkedGuest": False}
        if guest and st.account_for_player(guest):
            raise GameError("save_linked", "这份存档已绑定其他账号")
        pid = guest or secrets.token_hex(8)
        st.link_account(user["id"], pid, game.now())
    return {"user": _public_user(user), "save": game.save_summary(pid), "linkedGuest": guest is not None}


@app.post("/api/account/link")
def api_account_link(x_player_token: str = Header(default=""), authorization: str = Header(default="")) -> dict:
    return _guard(_link, x_player_token, authorization)


# ------------------------------------------------------------------ admin
def admin(x_admin_key: str = Header(default="")) -> None:
    if not ADMIN_KEY or not secrets.compare_digest(x_admin_key.encode(), ADMIN_KEY.encode()):
        raise HTTPException(status_code=404)


class ShardsBody(BaseModel):
    delta: int = Field(ge=-1_000_000, le=1_000_000)


@app.get("/admin/stats", dependencies=[Depends(admin)])
def admin_stats(days: int = Query(default=30, ge=1, le=180)) -> dict:
    out = game.admin_stats(days)
    out["totals"]["rooms"] = len(manager.rooms)
    out["totals"]["online"] = sum(len(r.peers) for r in manager.rooms.values())
    return out


@app.get("/admin/accounts", dependencies=[Depends(admin)])
def admin_accounts(ids: str | None = None, offset: int = Query(default=0, ge=0),
                   limit: int = Query(default=20, ge=1, le=100)) -> dict:
    """[ids]: comma-separated main-site user ids to narrow to (the main site resolves its search)."""
    user_ids = None if ids is None else [i for i in ids.split(",") if i][:100]
    return game.admin_accounts(user_ids, offset, limit)


@app.post("/admin/accounts/{user_id}/shards", dependencies=[Depends(admin)])
def admin_shards(user_id: str, body: ShardsBody) -> dict:
    return _guard(game.admin_adjust_shards, user_id, body.delta)


@app.post("/admin/accounts/{user_id}/unlink", dependencies=[Depends(admin)])
def admin_unlink(user_id: str) -> dict:
    _guard(game.admin_unlink, user_id)
    return {"ok": True}


@app.get("/api/collection")
def api_collection(who: PlayerId = Depends(player)) -> dict:
    return _guard(game.collection, who)


# Heavy assets (card art, videos, theme backgrounds) as downloadable packs: /packs/index.json
if Path(PACKS_DIR).is_dir():
    app.mount("/packs", StaticFiles(directory=str(PACKS_DIR)), name="packs")


# ----------------------------------------------------------------- WebSocket
async def _leave(room_id: str | None, peer: Peer | None) -> None:
    if room_id and peer:
        if manager.leave(room_id, peer.id):
            await manager.broadcast(room_id, MemberLeftMsg(id=peer.id).model_dump())


def _room_identity(token: str | None, account_token: str | None) -> PlayerId | None:
    """Rooms resolve the same save as HTTP; an unknown identity joins without unlocks."""
    try:
        return _who(token or "", f"Bearer {account_token}" if account_token else "")
    except GameError:
        return None


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
                who = await run_in_threadpool(_room_identity, msg.token, msg.accountToken)
                profile = await run_in_threadpool(game.profile_for, who, msg.room)
                plate = await run_in_threadpool(game.room_plate, who, msg.plate)
                try:
                    peer = manager.join(msg.room, msg.nick, msg.character, ws, token=who, plate=plate, **profile)
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
            elif isinstance(msg, MotionMsg):
                await manager.motion(room_id, peer, msg.model_dump(exclude={"type"}))
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
                if msg.plate:
                    plate = await run_in_threadpool(game.room_plate, peer.token, msg.plate)
                    if plate is None:
                        await err("locked", "plate not owned")
                        continue
                    peer.plate = plate
                elif msg.plate == "":
                    peer.plate = None
                if msg.character is not None:
                    peer.character = msg.character
                if msg.nick is not None:
                    peer.nick = msg.nick
                await manager.broadcast(room_id, StateBroadcast(
                    id=peer.id, character=peer.character, nick=peer.nick, plate=peer.plate).model_dump())
    except (WebSocketDisconnect, ConnectionError):
        pass
    except asyncio.TimeoutError:
        try:
            await asyncio.wait_for(ws.close(code=1013), manager.send_timeout)
        except (asyncio.TimeoutError, RuntimeError, OSError):
            pass
    finally:
        # shielded: the member_left broadcast must survive cancellation of this handler
        await asyncio.shield(_leave(room_id, peer))
