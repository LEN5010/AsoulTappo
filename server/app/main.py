"""AsoulTappo room server: FastAPI + WebSocket rooms, SQLite-backed item progression."""
from __future__ import annotations

import asyncio
import functools
import os
import secrets
import signal
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from . import analytics
from .accounts import MainAccounts, http_me
from .duel import Duels
from .game import Game, GameError, PlayerId, player_id_for
from .manifest import Manifest, find_packs_dir
from . import notice as notices
from .notice import Notice, OUTDATED_MESSAGE, version_key
from .models import (
    DndMsg, DuelAnswerMsg, DuelInviteMsg, DuelThrowMsg, EmoteBroadcast, EmoteMsg, ErrorMsg, JoinedMsg, JoinMsg,
    KickMsg, LeaveMsg, Member, MemberJoinedMsg, MotionMsg, PoseMsg, MotionSubscribeMsg, PingMsg, PokeMsg, PongMsg, ProfileMsg,
    ProfileReply, RoomInfo, RoomInfoMsg, ScratchBroadcast, SetPublicMsg, StateBroadcast, StateMsg, TapBroadcast, TapMsg, client_message_adapter,
)
from .moderation import Blocklist
from .park import Park
from .redeem import Locked, Redeem
from .releases import ReleaseFeed
from .rooms import (FEATURES, MOTION_VERSION, PROFILE_INTERVAL, Banned, NeedSave, Peer, PokeRefused, RoomFull, RoomManager,
                    room_status)
from .store import Store

SAMPLE_SECONDS = 60
# Background loops of the park's games (the race's schedule, the lottery's draw), each an async function that runs
# until cancelled; a game appends its own where it is set up below.
PARK_LOOPS: list = []


async def _sample_rooms() -> None:
    """Once a minute, at the minute's start: the room sample and the counts so far go to the database."""
    while True:
        await asyncio.sleep(SAMPLE_SECONDS - time.time() % SAMPLE_SECONDS)
        try:
            numbers = game.tracker.room_numbers(list(manager.rooms.values()))
            await run_in_threadpool(game.tracker.sample, numbers)
        except Exception as e:  # a failed sample must not stop the next ones
            print(f"room sample failed: {e!r}", flush=True)


# The rooms as they were when the stop signal came. Stopping closes every connection first, which empties the rooms,
# so they are noted before that and saved once the server is down (see RoomManager.snapshot).
_stopping_rooms: list[dict] | None = None


def _note_rooms_on_stop() -> None:
    """Wrap the server's stop-signal handlers so the rooms are noted before it starts closing connections. Handlers
    can only be set from the main thread; elsewhere (tests) nothing is noted, and a stop saves no rooms."""
    if threading.current_thread() is not threading.main_thread():
        return
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous = signal.getsignal(sig)
        if not callable(previous):
            continue

        def handler(signum, frame, previous=previous):
            global _stopping_rooms
            if _stopping_rooms is None:
                _stopping_rooms = manager.snapshot()
            previous(signum, frame)

        signal.signal(sig, handler)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    global _stopping_rooms
    _stopping_rooms = None
    saved = await run_in_threadpool(game.store.take_rooms)
    started = game.now()
    manager.restore(saved, lambda entry: max(0.0, started - entry["saved"]))
    _note_rooms_on_stop()
    sampler = asyncio.create_task(_sample_rooms())
    loops = [asyncio.create_task(loop()) for loop in PARK_LOOPS]
    try:
        yield
    finally:
        sampler.cancel()
        for task in loops:
            task.cancel()
        game.tracker.flush()
        if _stopping_rooms is not None:
            game.store.save_rooms(_stopping_rooms, game.now())


app = FastAPI(title="AsoulTappo server", version="0.4.0", lifespan=_lifespan)
manager = RoomManager()
EMOTE_INTERVAL = 0.25  # seconds between emotes of one member
PUBLIC_LIST_LIMIT = 50
TAP_RATE = 15.0  # room taps per second one member may broadcast (matches activity crediting)
TAP_BURST = 75.0  # taps that may pile up while idle, a few seconds' worth

PACKS_DIR = find_packs_dir()
manifest = Manifest.load(PACKS_DIR / "manifest.json")
# ASOULTAPPO_DB: sqlite file (default data/asoultappo.db, ":memory:" for throw-away runs)
game = Game(Store(os.environ.get("ASOULTAPPO_DB", "data/asoultappo.db")), manifest)
# 1.1: repeats turn into shards when drawn; cards kept as repeats before that are paid out once.
_paid_players, _paid_shards = game.refund_duplicate_cards()
if _paid_players:
    print(f"refunded duplicate cards: {_paid_shards} shards to {_paid_players} players", flush=True)
_pruned = game.prune_activity_sessions()
if _pruned:
    print(f"pruned {_pruned} old tap sessions", flush=True)
_pruned = game.prune_scratch_cards()
if _pruned:
    print(f"pruned {_pruned} old scratch cards", flush=True)
# Rooms live in memory: a duel the last run left open cannot go on, so both bets go back.
_refunded = game.refund_open_duels()
if _refunded:
    print(f"refunded {_refunded} unfinished duels", flush=True)
# Rock-paper-scissors in rooms; a member leaving in any way loses the duel it plays.
duels = Duels(lambda: game, lambda: manager)
# The park's coins; its games take and give them through it. Nicks in its news are masked like room nicks.
park = Park(lambda: game, lambda nick: blocklist.mask(nick))
_pruned = park.prune_news()
if _pruned:
    print(f"pruned {_pruned} old park news", flush=True)
# park: scratch setup
# park: race setup
# park: lottery setup
# park: redeem setup
# Redeem codes: made through /admin/codes, entered through POST /api/redeem.
redeem = Redeem(lambda: game, park)


def load_blocklist(store: Store) -> Blocklist:
    return Blocklist(store.blocked_words())


# Nickname blocklist kept by the main site's admin backend (PUT /admin/blocked-words); rooms show masked nicks.
blocklist = load_blocklist(game.store)
# Nicks as members sent them, by member id: a new list is applied to these, never to already masked text.
raw_nicks: dict[str, str] = {}


def load_notice(store: Store) -> Notice:
    return Notice.load(store.setting(notices.KEY))


# Minimum client version and announcements, set through PUT /admin/notice.
notice = load_notice(game.store)


async def _departed(room_id: str, peer: Peer) -> None:
    raw_nicks.pop(peer.id, None)
    await duels.departed(room_id, peer)


manager.on_depart = _departed

# MAIN_API_URL: the main site's API (official server: https://len5010.top/dynamics/api). Unset on
# self-hosted servers, which then offer guest saves only.
MAIN_API_URL = os.environ.get("MAIN_API_URL", "").strip().rstrip("/")
accounts = (MainAccounts(MAIN_API_URL, functools.partial(http_me, key=os.environ.get("ASOULTAPPO_ADMIN_KEY", "")))
            if MAIN_API_URL else None)
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
                  plate=p.plate, status=p.status)


def _state(p: Peer) -> dict:
    return StateBroadcast(id=p.id, character=p.character, nick=p.nick, plate=p.plate, status=p.status).model_dump()


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "rooms": len(manager.rooms)}


@app.post("/rooms")
async def create_room() -> dict:
    """Create a room and return its random long ID."""
    return {"room": manager.create_room()}


@app.get("/rooms")
async def public_rooms(authorization: str = Header(default="")) -> dict:
    """Rooms their host made public: host nick and character, member count and room size. A server with main-site
    accounts shows them to signed-in accounts only (a linked save is not needed), so guest saves made in bulk cannot
    crowd them; joining by room id needs no account."""
    if accounts:
        if not _bearer(authorization):
            raise HTTPException(401, {"code": "account_required", "message": "登录账号后才能查看公开房间"})
        await run_in_threadpool(_guard, _main_user, authorization)
    return {"rooms": manager.public_rooms(PUBLIC_LIST_LIMIT)}


# ------------------------------------------------------------------ HTTP API
STATUS = {"bad_token": 401, "account_expired": 401, "save_linked": 401, "no_shards": 409, "owned": 409,
          "checked_in": 409, "account_not_linked": 409, "account_unavailable": 503, "accounts_disabled": 404,
          "sold_out": 409, "no_card": 404, "no_scratch": 404, "no_member": 404,
          # Admin calls answer these with 409: the main site reads a 404 from this server as "unavailable".
          "no_save": 409, "no_reward": 409, "reward_open": 409,
          # The park (park.py and its games).
          "no_park": 404, "park_locked": 409, "no_coins": 409, "coin_limit": 409, "coin_hold": 409, "bad_count": 400,
          "race_closed": 409, "race_cap": 409, "no_race": 404, "lottery_closed": 409, "lottery_cap": 409,
          "bad_number": 400, "bad_code": 409, "code_expired": 409, "code_used_up": 409, "already_redeemed": 409,
          "login_required": 401, "too_many_tries": 429, "no_code": 409}


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


def player(x_player_token: str = Header(default=""), authorization: str = Header(default=""),
           x_client_version: str = Header(default="")) -> PlayerId:
    if notice.outdated(x_client_version):
        raise HTTPException(426, {"code": "client_outdated", "message": OUTDATED_MESSAGE})
    who = _guard(_who, x_player_token, authorization)
    game.tracker.client(who, x_client_version)
    return who


class ActivityBody(BaseModel):
    taps: int = Field(ge=0, le=100000)
    session: str = Field(min_length=16, max_length=128)
    sequence: int = Field(ge=1)
    # Seconds left of a cooldown the client's own input guard started.
    cooldown: int = Field(default=0, ge=0, le=3600)


class CraftBody(BaseModel):
    item: str = Field(min_length=1, max_length=64)


class PresenceBody(BaseModel):
    session: str = Field(min_length=16, max_length=128)


class ResonanceBody(BaseModel):
    count: int = Field(default=1, ge=1, le=100)


class ScratchRevealBody(BaseModel):
    card: int = Field(ge=1, le=2**63 - 1)


class LoadoutBody(BaseModel):
    """Selected character, favorite emotes, name plate (null or "" for none) and showcase card ids."""

    character: str | None = Field(default=None, max_length=32)
    favorites: list[str] | None = Field(default=None, max_length=16)
    plate: str | None = Field(default=None, max_length=64)
    showcase: list[str] | None = Field(default=None, max_length=16)
    # The nickname the boards show, and false to stay off them.
    nick: str | None = Field(default=None, max_length=64)
    board: bool | None = None


@app.get("/api/board")
def api_board(order: Literal["cards", "score"] = "cards", who: PlayerId = Depends(player)) -> dict:
    """The collection board by cards (clients before the collection score) or by score; on a server with main-site
    accounts only saves linked to one are ranked."""
    out = _guard(game.board, who, accounts is not None, order)
    return {**out, "cards": [{**row, "nick": blocklist.mask(row["nick"])} for row in out["cards"]]}


@app.get("/api/board/profile/{bid}")
def api_board_profile(bid: str, who: PlayerId = Depends(player)) -> dict:
    """The showcase and progress of a save on the collection board's top rows."""
    out = _guard(game.board_profile, bid, accounts is not None)
    game.tracker.count("board_profile")
    return out


@app.get("/api/manifest")
def api_manifest() -> dict:
    return manifest.data


@app.get("/api/me")
def api_me(who: PlayerId = Depends(player)) -> dict:
    return _guard(game.status, who)


@app.post("/api/activity")
async def api_activity(body: ActivityBody, who: PlayerId = Depends(player)) -> dict:
    """Report the number of taps since the last report (counts only, never content)."""
    out = await run_in_threadpool(_guard, game.report_activity, who, body.taps, body.session, body.sequence,
                                  body.cooldown)
    # The taps that paid shards also fill the cheer bar of the room this save sits in.
    finished = manager.cheer(who, out.pop("cheerTaps", 0))
    if finished:
        room, number, earned, each = finished
        game.tracker.count("cheer_round")
        paid = await run_in_threadpool(game.cheer_reward, earned, each)
        await manager.cheer_done(room, number, paid)
        if paid.get(who):
            out = {**out, **await run_in_threadpool(game.status, who)}
    return out


@app.post("/api/presence")
def api_presence(body: PresenceBody, who: PlayerId = Depends(player)) -> dict:
    return _guard(game.presence, who, body.session)


@app.post("/api/resonance/draw")
def api_resonate(body: ResonanceBody, who: PlayerId = Depends(player),
                 x_client_version: str = Header(default="")) -> dict:
    return _guard(game.resonate, who, body.count, x_client_version)


@app.post("/api/craft")
def api_craft(body: CraftBody, who: PlayerId = Depends(player)) -> dict:
    return _guard(game.craft, who, body.item)


@app.get("/api/checkin")
def api_checkin_month(who: PlayerId = Depends(player)) -> dict:
    return _guard(game.checkin_month, who)


@app.post("/api/checkin")
def api_checkin(who: PlayerId = Depends(player)) -> dict:
    return _guard(game.checkin, who)


@app.post("/api/update-reward")
def api_update_reward(who: PlayerId = Depends(player), x_client_version: str = Header(default="")) -> dict:
    """Claims every update reward the client's version reaches (status `updateRewards`)."""
    return _guard(game.claim_update_rewards, who, x_client_version)


class CoinBuyBody(BaseModel):
    count: int = Field(ge=1, le=100)


@app.get("/api/park")
def api_park(who: PlayerId = Depends(player)) -> dict:
    """The save's coins, today's buying, free coin, stamps and result, and the scratch jackpot."""
    return _guard(park.state, who)


@app.post("/api/park/coins")
def api_park_coins(body: CoinBuyBody, who: PlayerId = Depends(player)) -> dict:
    return _guard(park.buy, who, body.count)


@app.post("/api/park/gift")
def api_park_gift(who: PlayerId = Depends(player)) -> dict:
    """The free coin of the day: `gift` is how many came (0 after the first visit of the day)."""
    return _guard(park.gift, who)


# park: scratch routes
# park: race routes
# park: lottery routes
# park: redeem routes
STATUS["code_taken"] = 409


class RedeemBody(BaseModel):
    code: str = Field(max_length=64)


def _redeem(who: PlayerId, code: str) -> dict:
    try:
        return redeem.redeem(who, code, accounts is not None)
    except Locked as e:
        raise HTTPException(429, {"code": e.code, "message": e.message, "seconds": e.seconds},
                            headers={"Retry-After": str(e.seconds)})


@app.post("/api/redeem")
def api_redeem(body: RedeemBody, who: PlayerId = Depends(player)) -> dict:
    """Pays a redeem code's reward: status, `park` (on a server with the park) and `redeemed: {shards, coins}`."""
    return _guard(_redeem, who, body.code)


# The admin dependencies are defined further down; these defer to them when called.
def _code_admin(x_admin_key: str = Header(default="")) -> None:
    admin(x_admin_key)


def _code_actor(x_admin_actor: str = Header(default="")) -> str:
    return actor(x_admin_actor)


class CodeCreateBody(BaseModel):
    shards: int = Field(default=0, ge=0, le=1_000_000)
    coins: int = Field(default=0, ge=0, le=1000)
    count: int = Field(default=1, ge=1, le=500)
    uses: int = Field(default=1, ge=1, le=1_000_000)
    # Unix seconds; 0 = never.
    expires: float = Field(default=0, ge=0)
    note: str = Field(default="", max_length=200)
    # A memorable code instead of generated ones (count must be 1).
    code: str = Field(default="", max_length=64)


class CodeDisableBody(BaseModel):
    reason: str = Field(default="", max_length=200)


@app.post("/admin/codes", dependencies=[Depends(_code_admin)])
def admin_create_codes(body: CodeCreateBody, who: str = Depends(_code_actor)) -> dict:
    return _guard(redeem.create, body.shards, body.coins, body.count, body.uses, body.expires, body.note.strip(),
                  body.code.strip(), who)


@app.get("/admin/codes", dependencies=[Depends(_code_admin)])
def admin_codes(q: str = Query(default="", max_length=200), limit: int = Query(default=50, ge=1, le=500),
                before: int | None = Query(default=None, ge=1)) -> dict:
    """[q]: part of a code (dashes, spaces and case ignored) or of the note; [before]: continue below that code id."""
    return redeem.find(q, limit, before)


@app.post("/admin/codes/{code_id}/disable", dependencies=[Depends(_code_admin)])
def admin_disable_code(code_id: int, body: CodeDisableBody | None = None, who: str = Depends(_code_actor)) -> dict:
    return _guard(redeem.disable, code_id, who, body.reason.strip() if body else "")


@app.get("/admin/codes/{code_id}/claims", dependencies=[Depends(_code_admin)])
def admin_code_claims(code_id: int, limit: int = Query(default=200, ge=1, le=1000)) -> dict:
    return _guard(redeem.claims, code_id, limit)


@app.get("/api/scratch")
def api_scratch_state(who: PlayerId = Depends(player)) -> dict:
    return _guard(game.scratch_state, who)


@app.post("/api/scratch")
def api_scratch_buy(who: PlayerId = Depends(player)) -> dict:
    return _guard(game.scratch_buy, who)


@app.post("/api/scratch/reveal")
async def api_scratch_reveal(body: ScratchRevealBody, who: PlayerId = Depends(player)) -> dict:
    out = await run_in_threadpool(_guard, game.scratch_reveal, who, body.card)
    if out.pop("announce"):
        # Every room this save sits in sees the win over that member's pet.
        for room_id, room in list(manager.rooms.items()):
            for peer in [p for p in room.peers.values() if p.token == who]:
                await manager.broadcast(room_id, ScratchBroadcast(id=peer.id, shards=out["prize"]["shards"]).model_dump())
    return out


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
    """The newest release, with the minimum version and the announcements riding along."""
    latest = releases.latest()
    if not latest and notice.min_version:
        # The main site does not answer: the minimum is still a version to update to.
        latest = {"version": notice.min_version, "notes": ""}
    if not latest:
        raise HTTPException(503, {"code": "release_unavailable", "message": "暂时查不到最新版本"})
    return {**latest, "minVersion": notice.min_version or None, "announcements": notice.current()}


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
            # The guest may already be the linked save (an earlier link whose answer never arrived).
            return {"user": _public_user(user), "save": game.save_summary(linked), "linkedGuest": guest == linked}
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


MAX_ACTOR = 64


def actor(x_admin_actor: str = Header(default="")) -> str:
    """The main site's admin making the change, percent-encoded by the main site; kept in the admin log."""
    return unquote(x_admin_actor).strip()[:MAX_ACTOR]


class ShardsBody(BaseModel):
    delta: int = Field(ge=-1_000_000, le=1_000_000)
    # Why; the main site requires one, scripts may leave it out.
    reason: str = Field(default="", max_length=200)


class ReasonBody(BaseModel):
    reason: str = Field(default="", max_length=200)


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
def admin_shards(user_id: str, body: ShardsBody, who: str = Depends(actor)) -> dict:
    return _guard(game.admin_adjust_shards, user_id, body.delta, who, body.reason.strip())


@app.post("/admin/accounts/{user_id}/unlink", dependencies=[Depends(admin)])
def admin_unlink(user_id: str, body: ReasonBody | None = None, who: str = Depends(actor)) -> dict:
    _guard(game.admin_unlink, user_id, who, body.reason.strip() if body else "")
    return {"ok": True}


@app.get("/admin/economy", dependencies=[Depends(admin)])
def admin_economy(days: int = Query(default=14, ge=1, le=90), scope: Literal["all", "new"] = "all",
                  new_days: int = Query(default=7, ge=1, le=30, alias="newDays")) -> dict:
    return game.admin_economy(days, scope, new_days)


@app.get("/admin/saves", dependencies=[Depends(admin)])
def admin_saves(q: str = Query(min_length=1, max_length=128), limit: int = Query(default=20, ge=1, le=50)) -> dict:
    """[q]: a main-site user id, or a player id prefix of 4-16 hex characters; both are tried."""
    return game.admin_saves(q, limit)


@app.get("/admin/saves/{player}", dependencies=[Depends(admin)])
def admin_save(player: str) -> dict:
    return _guard(game.admin_save, player)


@app.post("/admin/saves/{player}/shards", dependencies=[Depends(admin)])
def admin_save_shards(player: str, body: ShardsBody, who: str = Depends(actor)) -> dict:
    return _guard(game.admin_adjust_save_shards, player, body.delta, who, body.reason.strip())


@app.get("/admin/insights", dependencies=[Depends(admin)])
def admin_insights(days: int = Query(default=30, ge=1, le=90)) -> dict:
    """New saves and returns, clients and collections of active saves, draws by rarity."""
    return analytics.insights(game, days)


@app.get("/admin/online", dependencies=[Depends(admin)])
def admin_online(days: int = Query(default=14, ge=1, le=90)) -> dict:
    """Room occupancy, interaction counts, duels and cheer rounds."""
    return analytics.online(game, days, game.tracker.room_numbers(list(manager.rooms.values())))


@app.get("/admin/anomalies", dependencies=[Depends(admin)])
def admin_anomalies(day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")) -> dict:
    """Saves whose taps look automated and the saves that gained the most shards on [day] (default today)."""
    return analytics.anomalies(game, day)


@app.get("/admin/log", dependencies=[Depends(admin)])
def admin_log(player: str | None = Query(default=None, max_length=32), limit: int = Query(default=50, ge=1, le=200),
              before: int | None = Query(default=None, ge=1)) -> dict:
    """Changes made through /admin, newest first."""
    return game.admin_log(player, limit, before)


class UpdateRewardBody(BaseModel):
    version: str = Field(min_length=1, max_length=32)
    shards: int = Field(ge=1, le=1_000_000)


@app.get("/admin/update-rewards", dependencies=[Depends(admin)])
def admin_update_rewards() -> dict:
    return game.admin_update_rewards()


@app.post("/admin/update-rewards", dependencies=[Depends(admin)])
def admin_add_update_reward(body: UpdateRewardBody, who: str = Depends(actor)) -> dict:
    """Every save on [version] or newer can claim [shards] once, until the reward is ended."""
    return _guard(game.admin_add_update_reward, body.version, body.shards, who)


@app.post("/admin/update-rewards/{reward_id}/end", dependencies=[Depends(admin)])
def admin_end_update_reward(reward_id: int, who: str = Depends(actor)) -> dict:
    return _guard(game.admin_end_update_reward, reward_id, who)


MAX_BLOCKED_WORDS = 20000
MAX_BLOCKED_WORD_LEN = 64


class BlockedWordsBody(BaseModel):
    words: list[str] = Field(max_length=MAX_BLOCKED_WORDS)

    @field_validator("words")
    @classmethod
    def _trim(cls, words: list[str]) -> list[str]:
        trimmed = [w.strip() for w in words]
        if any(not 1 <= len(w) <= MAX_BLOCKED_WORD_LEN for w in trimmed):
            raise ValueError(f"each word needs 1-{MAX_BLOCKED_WORD_LEN} characters after trimming")
        return list(dict.fromkeys(trimmed))


async def _remask() -> None:
    """Apply the current blocklist to everyone online; rooms hear of each nick that changed."""
    changed: list[tuple[str, Peer]] = []
    online: set[str] = set()
    for room_id, room in list(manager.rooms.items()):
        for peer in room.peers.values():
            online.add(peer.id)
            nick = blocklist.mask(raw_nicks.get(peer.id, peer.nick))
            if nick != peer.nick:
                peer.nick = nick
                changed.append((room_id, peer))
    for gone in raw_nicks.keys() - online:
        del raw_nicks[gone]
    for room_id, peer in changed:
        await manager.broadcast(room_id, _state(peer))


@app.get("/admin/blocked-words", dependencies=[Depends(admin)])
def admin_blocked_words() -> dict:
    words = game.store.blocked_words()
    return {"words": words, "count": len(words)}


_blocklist_saving = threading.Lock()


def _save_blocklist(words: list[str]) -> None:
    """Store and swap in one step, so the list in use is always the last one stored."""
    global blocklist
    with _blocklist_saving:
        game.store.replace_blocked_words(words)
        blocklist = Blocklist(words)


@app.put("/admin/blocked-words", dependencies=[Depends(admin)])
async def admin_set_blocked_words(body: BlockedWordsBody, who: str = Depends(actor)) -> dict:
    """Replace the whole list; it applies to members online at once."""
    await run_in_threadpool(_save_blocklist, body.words)
    await run_in_threadpool(game.admin_note, who, "blocked_words", {"count": len(body.words)})
    await _remask()
    return {"count": len(body.words)}


class Announcement(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=40)
    body: str = Field(default="", max_length=2000)
    # Unix seconds after which it is no longer shown; 0 = no end.
    until: float = Field(default=0, ge=0)
    # Shown again on each China day's first panel opening until the player turns it off (clients from 1.2.2; older
    # ones show it once).
    daily: bool = False


class NoticeBody(BaseModel):
    """minVersion "" lifts the minimum."""

    minVersion: str = Field(default="", max_length=32)
    announcements: list[Announcement] = Field(default_factory=list, max_length=notices.MAX_ANNOUNCEMENTS)

    @field_validator("minVersion")
    @classmethod
    def _version(cls, v: str) -> str:
        v = v.strip()
        if v and version_key(v) is None:
            raise ValueError("minVersion is not a version like 1.2.3")
        return v


@app.get("/admin/notice", dependencies=[Depends(admin)])
def admin_notice() -> dict:
    return {"minVersion": notice.min_version, "announcements": notice.announcements}


@app.put("/admin/notice", dependencies=[Depends(admin)])
def admin_set_notice(body: NoticeBody, who: str = Depends(actor)) -> dict:
    """Replace the minimum version and the announcements; requests after this one see them."""
    global notice
    new = Notice(body.minVersion, [a.model_dump() for a in body.announcements])
    game.store.set_setting(notices.KEY, new.dump())
    notice = new
    game.admin_note(who, "notice", {"minVersion": body.minVersion,
                                    "announcements": [a.title for a in body.announcements]})
    return admin_notice()


@app.get("/api/collection")
def api_collection(who: PlayerId = Depends(player)) -> dict:
    return _guard(game.collection, who)


# Heavy assets (card art, videos, theme backgrounds) as downloadable packs: /packs/index.json
if Path(PACKS_DIR).is_dir():
    app.mount("/packs", StaticFiles(directory=str(PACKS_DIR)), name="packs")


# ----------------------------------------------------------------- WebSocket
async def _leave(room_id: str | None, peer: Peer | None) -> None:
    if room_id and peer:
        await manager.depart(room_id, peer.id)


def _final(reason: str, message: str) -> dict:
    """A refusal that ends the session. Clients before 1.2 stop reconnecting on room_full only."""
    return ErrorMsg(code="room_full", message=message, reason=reason).model_dump()


async def _kick(room_id: str, target: Peer, ban: bool) -> None:
    """Tell the member why, then remove it; with [ban] its save stays out until the room closes."""
    room = manager.rooms.get(room_id)
    if room is None:
        return
    if ban and target.token:
        room.banned.add(target.token)
    try:
        await target.send(_final("kicked", "你已被移出这个房间"), manager.send_timeout)
    except Exception:  # a dead connection is removed all the same
        pass
    if await manager.depart(room_id, target.id):
        try:
            await asyncio.wait_for(target.ws.close(code=1000), manager.send_timeout)
        except (asyncio.TimeoutError, RuntimeError, OSError):
            pass


def _room_info(room_id: str) -> dict:
    room = manager.rooms[room_id]
    return RoomInfoMsg(**room.info()).model_dump()


def _room_identity(token: str | None, account_token: str | None) -> tuple[PlayerId | None, bool]:
    """Rooms resolve the same save as HTTP; an unknown identity joins without unlocks. The flag tells whether the
    join carried a valid main-site account token (with or without a linked save)."""
    signed_in = False
    if account_token and accounts:
        try:
            _main_user(f"Bearer {account_token}")
            signed_in = True
        except GameError:
            pass
    try:
        return _who(token or "", f"Bearer {account_token}" if account_token else ""), signed_in
    except GameError:
        return None, signed_in


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    room_id: str | None = None
    peer: Peer | None = None
    # Clients from 1.1.3 on name their version in the address (`/ws?v=1.1.3`).
    params = getattr(ws, "query_params", None)
    client_version = params.get("v") if params is not None else None

    async def send(data: dict) -> None:
        # A member removed during an await answers on the bare connection, like one that never joined.
        if peer and peer.active:
            await peer.send(data, manager.send_timeout)
        else:
            await asyncio.wait_for(ws.send_json(data), manager.send_timeout)

    async def err(code: str, message: str = "") -> None:
        await send(ErrorMsg(code=code, message=message).model_dump(exclude_none=True))

    try:
        while True:
            try:
                raw = await ws.receive_json()
            except (ValueError, KeyError, TypeError):
                # Not JSON text: a bad JSON text frame, or a binary frame (no "text", or "text": None on
                # some ASGI servers). Validation below answers it as bad_message.
                raw = None
            if peer is not None and not peer.active:
                # Removed from the room (kicked, or its writer failed). The server closed that connection: stop
                # reading (clients send a last `leave` on the way out). Still open: it counts as not joined.
                if getattr(ws, "application_state", None) == WebSocketState.DISCONNECTED:
                    break
                room_id, peer = None, None
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
                who, signed_in = await run_in_threadpool(_room_identity, msg.token, msg.accountToken)
                profile = await run_in_threadpool(game.profile_for, who, msg.room)
                if notice.outdated(client_version):
                    await send(_final("client_outdated", OUTDATED_MESSAGE))
                    continue
                plate = await run_in_threadpool(game.room_plate, who, msg.plate)
                character = msg.character
                # A skin the save does not own shows its member instead; the join itself goes through.
                if (character not in game.manifest.character_names
                        and not await run_in_threadpool(game.owns_character, who, character)):
                    character = game.base_character(character)
                prior = manager.rooms.get(msg.room)
                prior_info = prior.info() if prior is not None else None
                try:
                    peer = manager.join(msg.room, blocklist.mask(msg.nick), character, ws, token=who, plate=plate,
                                        may_list=not accounts or signed_in, **profile)
                    raw_nicks[peer.id] = msg.nick
                except RoomFull:
                    await err("room_full", "room is full (max 20)")
                    continue
                except Banned:
                    await send(_final("banned", "你已被移出这个房间"))
                    continue
                except NeedSave:
                    await send(_final("need_save", "公开房间需要存档才能加入"))
                    continue
                room_id = msg.room
                game.tracker.count("room_join")
                peer.dnd = msg.dnd
                peer.status = room_status(msg.status)
                await run_in_threadpool(game.note_room_nick, who, msg.nick)
                peer.account = signed_in
                peer.motion_version = min(msg.motionVersion, MOTION_VERSION)
                joined = JoinedMsg(
                    room=room_id, you=peer.id,
                    members=[_member(p) for p in manager.members(room_id)],
                    info=RoomInfo(**manager.rooms[room_id].info()),
                ).model_dump()
                # Only a client that asked for packed motion hears which version it gets; older ones keep the 1.1 shape.
                if peer.motion_version >= 2:
                    joined["motionVersion"] = peer.motion_version
                    joined["features"] = list(FEATURES)
                    # The newcomer's cheer bar starts as the room's stands.
                    joined["cheer"] = {k: v for k, v in manager.cheer_state(manager.rooms[room_id]).items() if k != "type"}
                await send(joined)
                await manager.broadcast(
                    room_id, MemberJoinedMsg(member=_member(peer)).model_dump(), exclude=peer.id)
                if prior_info is not None and manager.rooms[room_id].info() != prior_info:
                    # The host of the last run came back to its room (see RoomManager.restore).
                    await manager.broadcast(room_id, _room_info(room_id), exclude=peer.id)
                continue

            if peer is None or room_id is None:
                await err("not_joined", "send join first")
                continue

            if isinstance(msg, LeaveMsg):
                await _leave(room_id, peer)
                room_id, peer = None, None
            elif isinstance(msg, TapMsg):
                # Token bucket: an auto-clicker or forged client can't inflate room totals
                # or flood the room faster than a human tapping rate.
                now = time.monotonic()
                elapsed = now - peer.tap_at if peer.tap_at else TAP_BURST / TAP_RATE
                peer.tap_budget = min(peer.tap_budget + elapsed * TAP_RATE, TAP_BURST)
                peer.tap_at = now
                count = min(msg.count, int(peer.tap_budget))
                if count <= 0:
                    continue
                peer.tap_budget -= count
                peer.taps += count
                await manager.broadcast(room_id, TapBroadcast(
                    id=peer.id, count=count, total=peer.taps).model_dump())
            elif isinstance(msg, MotionMsg):
                await manager.motion(room_id, peer, msg.model_dump(exclude={"type"}))
            elif isinstance(msg, PoseMsg):
                await manager.pose(room_id, peer, msg.model_dump(exclude={"type"}, exclude_none=True))
            elif isinstance(msg, MotionSubscribeMsg):
                if peer.motion_version >= 2:
                    manager.subscribe_motion(room_id, peer, msg.ids)
            elif isinstance(msg, PokeMsg):
                try:
                    manager.poke(room_id, peer, msg.id, time.monotonic())
                    game.tracker.count("poke")
                except PokeRefused as refused:
                    await err(refused.code, "")
            elif isinstance(msg, ProfileMsg):
                now = time.monotonic()
                if now - peer.profile_at < PROFILE_INTERVAL:
                    await err("rate_limited", "too many profile requests")
                    continue
                room = manager.rooms.get(room_id)
                target = room.peers.get(msg.id) if room else None
                if target is None:
                    await err("no_member", "no such member")
                    continue
                peer.profile_at = now
                shown = await run_in_threadpool(game.member_profile, target.token)
                game.tracker.count("profile")
                await send(ProfileReply(id=target.id, **shown).model_dump())
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
                game.tracker.count("emote")
                await manager.broadcast(room_id, EmoteBroadcast(
                    id=peer.id, emote=msg.emote).model_dump())
            elif isinstance(msg, (SetPublicMsg, KickMsg)):
                room = manager.rooms.get(room_id)
                if room is None or room.host != peer.id:
                    await err("not_host", "only the host can do this")
                elif isinstance(msg, SetPublicMsg):
                    if msg.public and accounts and not peer.account:
                        # With main-site accounts, only a host signed in to one lists a room.
                        await err("host_needs_account", "a public room needs a host signed in to an account")
                        continue
                    if msg.public and not peer.token:
                        # A host without a save could not come back to its own public room.
                        await err("host_needs_save", "a public room needs a host with a save")
                        continue
                    if room.public == msg.public:
                        # Nothing changed: only the sender hears the current state, so repeats cannot flood the room.
                        await send(_room_info(room_id))
                        continue
                    room.public = msg.public
                    await manager.broadcast(room_id, _room_info(room_id))
                else:
                    target = room.peers.get(msg.id)
                    if target is None or target.id == peer.id:
                        await err("no_member", "no such member")
                        continue
                    # The save is barred, so its other connections go too. The host's own save on
                    # another connection is only removed: barring it would lock the host out.
                    ban = bool(target.token) and target.token != peer.token
                    targets = [target] + [p for p in room.peers.values()
                                          if ban and p.token == target.token and p.id != target.id]
                    # Removing a member mid-duel would lose it the duel, which a host could play for.
                    if any(duels.in_duel(t) for t in targets):
                        await err("in_duel", "member is in a duel")
                        continue
                    for t in targets:
                        await _kick(room_id, t, ban)
            elif isinstance(msg, DuelInviteMsg):
                try:
                    await duels.invite(room_id, peer, msg.id, msg.bet)
                    game.tracker.count("duel_invite")
                except GameError as e:
                    await err(e.code, e.message if e.message != e.code else "")
            elif isinstance(msg, (DuelAnswerMsg, DuelThrowMsg)):
                try:
                    if isinstance(msg, DuelAnswerMsg):
                        await duels.answer(peer, msg.duel, msg.accept)
                    else:
                        await duels.throw(peer, msg.duel, msg.hand)
                except GameError as e:
                    await err(e.code, e.message if e.message != e.code else "")
            elif isinstance(msg, DndMsg):
                duels.set_dnd(peer, msg.dnd)
            elif isinstance(msg, StateMsg):
                # Checked before anything is applied: a locked part drops the whole message.
                if (msg.character is not None and msg.character not in game.manifest.character_names
                        and not await run_in_threadpool(game.owns_character, peer.token, msg.character)):
                    await err("locked", "skin not owned")
                    continue
                if msg.plate:
                    plate = await run_in_threadpool(game.room_plate, peer.token, msg.plate)
                    if plate is None:
                        await err("locked", "set not collected")
                        continue
                    peer.plate = plate
                elif msg.plate == "":
                    peer.plate = None
                if msg.character is not None:
                    peer.character = msg.character
                if msg.status is not None:
                    peer.status = room_status(msg.status)
                if msg.nick is not None:
                    raw_nicks[peer.id] = msg.nick
                    peer.nick = blocklist.mask(msg.nick)
                    await run_in_threadpool(game.note_room_nick, peer.token, msg.nick)
                await manager.broadcast(room_id, _state(peer))
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
