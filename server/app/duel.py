"""Rock-paper-scissors between two members of a room.

Invites, hands and timers live in memory and belong to the two connections; the bets and the outcome live in the
database (Game.duel_*), which pays every duel at most once. The server decides everything: clients send an invite,
an answer and a hand, and hear the hands only once both are in or the round is over.
"""
from __future__ import annotations

import asyncio
import math
import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from starlette.concurrency import run_in_threadpool

from .game import Game, GameError
from .models import DuelInvited, DuelOver, DuelResult, DuelRound, DuelStarted, StickerBroadcast
from .rooms import Peer, RoomManager

BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
# Draws in a row after which both bets go back, so a duel cannot go on forever.
MAX_DRAWS = 10
# After a refusal or an unanswered invite, the inviter waits this long before inviting the same save again.
RETRY_SEC = 30.0


class Timers:
    """Runs a coroutine function after a delay on the running loop. Tests swap in one they fire by hand."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def later(self, delay: float, fn: Callable[[], Awaitable[None]]) -> Any:
        loop = asyncio.get_running_loop()

        def start() -> None:
            task = loop.create_task(fn())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        return loop.call_later(delay, start)


@dataclass(eq=False)
class Duel:
    id: str
    room: str
    a: Peer  # the inviter
    b: Peer
    bet: int
    prize: int
    # invite -> starting (the bets are being taken) -> throw -> done
    phase: str = "invite"
    row: int | None = None  # database id once the bets are taken
    round: int = 0
    hands: dict[str, str] = field(default_factory=dict)  # member id -> hand, this round
    draws: int = 0
    timer: Any = None
    # members that left while the bets were being taken
    gone: set[str] = field(default_factory=set)

    def has(self, peer: Peer) -> bool:
        return peer is self.a or peer is self.b

    def other(self, peer: Peer) -> Peer:
        return self.b if peer is self.a else self.a

    def tell(self, data: dict) -> None:
        """Queued for both sides; a side that left hears nothing."""
        for p in (self.a, self.b):
            p.enqueue(data)


class Duels:
    """Every duel on the server, one at a time per save (invites included), across all rooms."""

    def __init__(self, game: Callable[[], Game], manager: Callable[[], RoomManager], timers: Any = None,
                 clock: Callable[[], float] = time.monotonic, rng: random.Random | None = None) -> None:
        # Read on every use: tests replace the module's game and room manager.
        self._game = game
        self._manager = manager
        self.timers = timers or Timers()
        self.clock = clock
        self.rng = rng or random.Random()
        self.by_save: dict[str, Duel] = {}
        self.by_id: dict[str, Duel] = {}
        # (inviter save, invited save) -> monotonic time from which a new invite is allowed
        self.refused: dict[tuple[str, str], float] = {}

    @property
    def game(self) -> Game:
        return self._game()

    @property
    def manager(self) -> RoomManager:
        return self._manager()

    def clear(self) -> None:
        for duel in list(self.by_id.values()):
            self._drop(duel)
        self.refused.clear()

    def in_duel(self, peer: Peer) -> bool:
        """Whether the connection plays a duel whose bets are taken (or being taken)."""
        duel = self.by_save.get(peer.token) if peer.token else None
        return duel is not None and duel.has(peer) and duel.phase in ("starting", "throw")

    # ------------------------------------------------------------------ invites
    def _check_free(self, peer: Peer, target: Peer) -> None:
        if not peer.token:
            raise GameError("duel_locked", "")
        if not target.token:
            raise GameError("duel_target_locked", "")
        if peer.token in self.by_save:
            raise GameError("duel_busy", "")
        if target.token in self.by_save:
            raise GameError("duel_target_busy", "")
        if self.clock() < self.refused.get((peer.token, target.token), 0.0):
            raise GameError("duel_cooldown", "")

    async def invite(self, room_id: str, peer: Peer, target_id: str, bet: int) -> None:
        game = self.game
        cfg = game.duel_cfg()
        stake = game.duel_stake(bet)
        room = self.manager.rooms.get(room_id)
        target = room.peers.get(target_id) if room else None
        if target is None:
            raise GameError("no_member", "no such member")
        if target is peer or (peer.token and target.token == peer.token):
            raise GameError("duel_self", "")
        self._check_free(peer, target)
        await run_in_threadpool(game.duel_check, peer.token, target.token, bet)
        # Either side may have left, or started another duel, while the database was read.
        room = self.manager.rooms.get(room_id)
        if (room is None or not peer.active or not target.active or room.peers.get(peer.id) is not peer
                or room.peers.get(target.id) is not target):
            raise GameError("no_member", "no such member")
        self._check_free(peer, target)
        duel = Duel(id=secrets.token_hex(4), room=room_id, a=peer, b=target, bet=bet, prize=stake["prize"])
        self.by_id[duel.id] = duel
        self.by_save[peer.token] = self.by_save[target.token] = duel
        invited = DuelInvited(duel=duel.id, from_=peer.id, to=target.id, bet=bet, prize=duel.prize,
                              sec=cfg["inviteSec"]).model_dump(by_alias=True)
        peer.enqueue(invited)
        if target.dnd:
            # Turned down for the member, who never sees it; the inviter hears a plain refusal.
            self._end(duel, "declined", refused=True, tell=(peer,))
            return
        target.enqueue(invited)
        duel.timer = self.timers.later(cfg["inviteSec"], lambda: self._invite_expired(duel))

    async def _invite_expired(self, duel: Duel) -> None:
        if duel.phase == "invite":
            self._end(duel, "timeout", refused=True)

    def set_dnd(self, peer: Peer, on: bool) -> None:
        peer.dnd = on
        duel = self.by_save.get(peer.token) if peer.token else None
        if on and duel is not None and duel.b is peer and duel.phase == "invite":
            self._end(duel, "declined", refused=True)

    async def answer(self, peer: Peer, duel_id: str, accept: bool) -> None:
        duel = self.by_id.get(duel_id)
        if duel is None or duel.b is not peer or duel.phase != "invite":
            raise GameError("duel_gone", "")
        if not accept:
            self._end(duel, "declined", refused=True)
            return
        duel.phase = "starting"
        self._cancel_timer(duel)
        try:
            duel.row = await run_in_threadpool(self.game.duel_start, duel.a.token, duel.b.token, duel.bet)
        except GameError as e:
            self._end(duel, e.code)
            return
        except BaseException:
            # The transaction rolled back, so nothing was taken: end the duel and free both saves, then let the
            # error be reported as usual.
            self._end(duel, "error")
            raise
        if duel.gone:
            # Leaving while the bets were taken loses like leaving mid-round; both gone get their bets back.
            stayed = [p for p in (duel.a, duel.b) if p.id not in duel.gone]
            await self._settle(duel, stayed[0] if len(stayed) == 1 else None, "gone")
            return
        duel.phase = "throw"
        self._next_round(duel)
        duel.tell(DuelStarted(duel=duel.id, round=duel.round, sec=self.game.duel_cfg()["throwSec"]).model_dump())

    # ------------------------------------------------------------------- rounds
    def _next_round(self, duel: Duel) -> None:
        self._cancel_timer(duel)
        duel.round += 1
        duel.hands = {}
        number = duel.round
        duel.timer = self.timers.later(self.game.duel_cfg()["throwSec"], lambda: self._round_expired(duel, number))

    async def throw(self, peer: Peer, duel_id: str, hand: str) -> None:
        duel = self.by_id.get(duel_id)
        if duel is None or not duel.has(peer) or duel.phase != "throw":
            raise GameError("duel_gone", "")
        if peer.id in duel.hands:
            return  # one hand a round; the first one stands
        duel.hands[peer.id] = hand
        if len(duel.hands) < 2:
            return
        ha, hb = duel.hands[duel.a.id], duel.hands[duel.b.id]
        if ha != hb:
            await self._settle(duel, duel.a if BEATS[ha] == hb else duel.b)
            return
        duel.draws += 1
        if duel.draws >= MAX_DRAWS:
            await self._settle(duel, None, "draws")
            return
        hands = dict(duel.hands)
        self._next_round(duel)
        duel.tell(DuelRound(duel=duel.id, round=duel.round, sec=self.game.duel_cfg()["throwSec"],
                            hands=hands).model_dump())

    async def _round_expired(self, duel: Duel, number: int) -> None:
        if duel.phase != "throw" or duel.round != number:
            return
        thrown = [p for p in (duel.a, duel.b) if p.id in duel.hands]
        # One hand in: the side that did not throw loses. None: both bets go back.
        await self._settle(duel, thrown[0] if len(thrown) == 1 else None, "idle")

    async def departed(self, room_id: str, peer: Peer) -> None:
        """A member left the room (leave, kick, lost connection): a duel in play is lost, an invite dropped."""
        duel = self.by_save.get(peer.token) if peer.token else None
        if duel is None or not duel.has(peer):
            return
        if duel.phase == "invite":
            # An inviter leaving waits as after a refusal, so leaving and coming back cannot repeat the invite.
            self._end(duel, "gone", refused=peer is duel.a)
        elif duel.phase == "starting":
            duel.gone.add(peer.id)
        elif duel.phase == "throw":
            await self._settle(duel, duel.other(peer))

    # ------------------------------------------------------------------- ending
    def _cancel_timer(self, duel: Duel) -> None:
        if duel.timer is not None:
            duel.timer.cancel()
            duel.timer = None

    def _drop(self, duel: Duel) -> None:
        self._cancel_timer(duel)
        self.by_id.pop(duel.id, None)
        for p in (duel.a, duel.b):
            if p.token and self.by_save.get(p.token) is duel:
                del self.by_save[p.token]

    def _end(self, duel: Duel, reason: str, refused: bool = False, tell: tuple[Peer, ...] | None = None) -> None:
        """Ends an invite, or a duel whose bets were never taken; [tell] narrows who hears it (default both)."""
        if duel.phase == "done":
            return
        duel.phase = "done"
        self._drop(duel)
        if refused:
            now = self.clock()
            self.refused = {k: t for k, t in self.refused.items() if t > now}
            self.refused[(duel.a.token, duel.b.token)] = now + RETRY_SEC
        over = DuelOver(duel=duel.id, reason=reason).model_dump()
        for p in tell if tell is not None else (duel.a, duel.b):
            p.enqueue(over)

    async def _settle(self, duel: Duel, winner: Peer | None, reason: str = "") -> None:
        """Pays a duel whose bets are taken: the prize to [winner], or both bets back. Marked done before the
        first await, so a throw, a timeout and a departure arriving together settle it once; the database
        refuses a second payment as well."""
        if duel.phase == "done":
            return
        duel.phase = "done"
        hands: dict[str, str | None] = {p.id: duel.hands.get(p.id) for p in (duel.a, duel.b)}
        self._drop(duel)
        game = self.game
        if not await run_in_threadpool(game.duel_settle, duel.row, winner.token if winner else None):
            return
        if winner is None:
            duel.tell(DuelOver(duel=duel.id, reason=reason).model_dump())
            return
        loser = duel.other(winner)
        manager = self.manager
        await manager.broadcast(duel.room, DuelResult(duel=duel.id, winner=winner.id, loser=loser.id,
                                                      prize=duel.prize, hands=hands).model_dump())
        room = manager.rooms.get(duel.room)
        keys = game.manifest.duel_stickers
        if room is None or not keys or not loser.token:
            return
        key = keys[min(int(self.rng.random() * len(keys)), len(keys) - 1)]
        sec = game.duel_cfg()["sticker"]["sec"]
        room.stickers[loser.token] = (key, self.clock() + sec)
        for p in list(room.peers.values()):
            if p.token == loser.token:
                await manager.broadcast(duel.room, StickerBroadcast(id=p.id, key=key, sec=sec).model_dump())

    # ----------------------------------------------------------------- stickers
    def stickers(self, room_id: str) -> list[dict]:
        """`sticker` messages for every member still wearing one, for a member who just joined."""
        room = self.manager.rooms.get(room_id)
        if room is None:
            return []
        now = self.clock()
        for save in [s for s, (_, until) in room.stickers.items() if until <= now]:
            del room.stickers[save]
        out = []
        for p in room.peers.values():
            if p.token in room.stickers:
                key, until = room.stickers[p.token]
                out.append(StickerBroadcast(id=p.id, key=key, sec=max(1, math.ceil(until - now))).model_dump())
        return out

    def sticker_of(self, room_id: str, peer: Peer) -> dict | None:
        return next((m for m in self.stickers(room_id) if m["id"] == peer.id), None)
