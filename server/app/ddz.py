"""Dou dizhu (斗地主) between three members of a room, played for shards.

One member invites two others at a base stake. When both accept, each pays a deposit (the most a landlord can lose),
the cards are dealt and the three bid for the landlord's seat, play, and are paid. The table, the hands and the timers
live in memory; the deposits and the outcome live in the database (ddz_games), which pays every game at most once
and hands the deposits of games a restart cut short back at startup.

A seat belongs to a save, not to a connection: a member who leaves the room mid-game is played for (by
ddz_rules.choose) and takes the seat again by joining the room with the same save. Two turns in a row left to run out
put a seat on the same autopilot until its member turns it off; a turn played for bids nothing.

The queue: a member of any room, on a client that said `ddzMatch` when joining, waits for a table at one stake instead
of inviting. The saves waiting at a stake form one line, oldest first, kept in memory; when three in it may sit down
together, they get a table that belongs to no room, through the same invite, which all three have to accept. A save
that declines, leaves or lets the time run out is out of the queue (one that declined or let the time run out may
queue again only after MATCH_RETRY_SEC); the others go back into the line where their wait puts them, ahead of anyone
who came after them. Once all three accept, the game goes on as an invited one; a seat's member who leaves takes the
seat again by joining any room with the same save. Leaving the room, turning invites down (dnd), starting an invite or
accepting one takes a save out of the queue.

Messages to the three seats (all carry `table`); seats are numbered 0 to 2 in turn order, 0 the inviter (the save
that waited longest at a table the queue made):

- ``ddz_invite`` {from, ids, base, deposit, sec}: member `from` invited the two other members of `ids`. A table the
  queue made has no `from`, and has `match` true and `seats` [{id, nick, character}] (the members may be in other
  rooms).
- ``ddz_answer`` {id}: member `id` accepted.
- ``ddz_over`` {reason, by?}: the invite or the game ended with nothing won: declined | timeout | gone (`by` is the
  member) | nobid (three deals nobody bid on) | no_shards | ddz_cap | ddz_locked | ddz_account (a seat's save is not
  linked to a main-site account, on a server with accounts) | error. Deposits taken went back.
- ``ddz_deal`` {seats: [{id, nick, character, auto, away}], you, hand, base, cap, deal, turn, sec, dealSec}: a deal;
  the clients deal the cards out over `dealSec` seconds, then `turn` bids first with `sec` seconds.
- ``ddz_bid`` {seat, bid, turn?, sec?}: a bid (0 passes); `turn` bids next when the bidding goes on.
- ``ddz_landlord`` {seat, bid, bottom, mult, turn, sec}: `seat` is the landlord, takes `bottom` and leads.
- ``ddz_play`` {seat, cards, left, mult, bombs, turn?, sec?, lead?}: a play ([] passes); `turn` plays next and leads
  when `lead`.
- ``ddz_seat`` {seat, id, away, auto, turn?, sec?}: a seat's member left or came back (with a new member id), or its
  autopilot changed; with `turn` the seat's turn starts over with `sec` seconds.
- ``ddz_result`` {winner: landlord | farmers, landlord, bid, bombs, spring: 0 | 1 spring | 2 counter-spring, mult,
  base, deltas, hands, sec}: paid; `hands` are the cards left in each seat, `sec` the time to ask for another game.
- ``ddz_again`` {seat}: `seat` asks for another game; when the three have, the next ``ddz_deal`` follows.
- ``ddz_closed`` {}: the table is gone (the time ran out, or someone left it).
- ``ddz_state`` {...}: the whole game for a seat that came back (see Tables._state).

To the room: ``ddz_live`` {table, ids, on, gains?}: the three members started (on) or ended a game; `gains` are the
shards the winners won, by member id. A table the queue made tells every room its members are in.

The queue, with members whose client said `ddzMatch` only (`joined.features` then lists "ddz_match"):

- ``ddz_queue`` {base} from the member: wait at stake `base`, or at 0 stop waiting. Refused with ddz_locked |
  ddz_account | no_shards | ddz_cap | ddz_busy (at a table or invite) | ddz_queued (the save waits on another
  connection) | ddz_dnd | ddz_match_cooldown | rate_limited (within QUEUE_INTERVAL of the last time it joined or
  moved) | bad_message (not a stake).
- ``ddz_queue`` {base, waited?, reason?, retry?} to the member: it waits at `base`, for `waited` seconds so far;
  `base` null when it does not (cancelled, matched, out). `reason` says why the server took it out: ddz_locked |
  ddz_account | no_shards | ddz_cap | ddz_dnd | error, or ddz_match_cooldown with `retry`, the seconds until it may
  queue again (it declined a table of the queue or let its time run out).
- ``ddz_waiting`` {counts: [[base, saves], ...]}: how many saves wait at each stake (stakes nobody waits at left out),
  to every member that queues, at most every COUNTS_SEC; on joining a room, the counts last sent, unless nobody
  waited then.
"""
from __future__ import annotations

import asyncio
import logging
import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from starlette.concurrency import run_in_threadpool

from . import ddz_rules as rules
from .duel import Timers
from .game import Game, GameError, day_of
from .rooms import Peer, RoomManager

log = logging.getLogger(__name__)

# After a refusal or an unanswered invite, the inviter waits this long before inviting the same save again.
RETRY_SEC = 30.0
# A seat on autopilot, or whose member is away, moves after this long.
AUTO_SEC = 1.2
# Turns in a row left to run out that put a seat on autopilot.
AUTO_AFTER = 2
# Deals nobody bids on before the table is given up and the deposits go back.
MAX_DEALS = 3
# The clients deal the cards out face down and turn them over in this long; the first bid's time starts after it.
DEAL_SEC = 2.2
# The queue's waiting counts go out at most this often.
COUNTS_SEC = 1.0
# A save that declined a table of the queue, or let its time run out, waits this long before it may queue again.
MATCH_RETRY_SEC = 60.0
# A connection joins the queue or moves to another stake at most this often (each time reads the save); stopping is
# never held up.
QUEUE_INTERVAL = 1.0

INVITE, STARTING, BID, PLAY, SETTLING, OVER, DONE = "invite", "starting", "bid", "play", "settling", "over", "done"


# ------------------------------------------------------------------ the bank
class Bank:
    """The shards of a game: who may sit down, the deposits and the payment. Every method is one transaction."""

    def __init__(self, game: Game, require_account: bool = False) -> None:
        self.game = game
        # A server with main-site accounts seats saves linked to one only (_ready).
        self.require_account = require_account

    def cfg(self) -> dict[str, Any]:
        cfg = self.game.manifest.ddz
        if not cfg:
            raise GameError("no_ddz", "这个服务器没有斗地主")
        return cfg

    def deposit(self, base: int) -> int:
        cfg = self.cfg()
        if base not in cfg["stakes"]:
            raise GameError("bad_message", "unknown stake")
        return base * cfg["capMult"] * 2

    def _ready(self, st: Any, pids: list[str | None], deposit: int, day: str, now: float) -> None:
        """Every seat needs a save with the taps, the deposit, and room under the day's cap, and with
        require_account a save linked to a main-site account: guest saves cost a script nothing to make, and a game
        lost on purpose moves shards between saves. The first seat is the one asking, so its own shortfalls are told
        apart from the others'."""
        cfg = self.cfg()
        for i, pid in enumerate(pids):
            other = "_target" if i else ""
            taps = st.player_taps(pid) if pid else None
            if taps is None or taps < cfg["minTaps"]:
                raise GameError(f"ddz{other}_locked", "")
            if self.require_account and not st.account_for_player(pid):
                raise GameError(f"ddz{other}_account",
                                "有人还没有登录 Asasfans 账号" if other else "登录 Asasfans 账号后才能斗地主")
            if st.get_player(pid, now)["shards"] < deposit:
                raise GameError(f"ddz{other}_poor" if other else "no_shards", "")
            if st.ddz_net(pid, day) >= cfg["dailyWinCap"]:
                raise GameError(f"ddz{other}_cap" if other else "ddz_cap", "")

    def check(self, pids: list[str | None], base: int) -> int:
        """Whether the saves [pids] (the first invites) may play at [base]; returns the deposit. Takes nothing."""
        deposit = self.deposit(base)
        with self.game.store.transaction() as st:
            now = self.game.now()
            self._ready(st, pids, deposit, day_of(now), now)
        return deposit

    def refusals(self, pids: list[str], base: int) -> list[str | None]:
        """Why each save of [pids] may not sit down at [base], as its own asking would be told (ddz_locked,
        ddz_account, no_shards, ddz_cap), None where it may. One transaction; takes nothing."""
        deposit = self.deposit(base)
        out: list[str | None] = []
        with self.game.store.transaction() as st:
            now = self.game.now()
            day = day_of(now)
            for pid in pids:
                try:
                    self._ready(st, [pid], deposit, day, now)
                    out.append(None)
                except GameError as e:
                    out.append(e.code)
        return out

    def start(self, pids: list[str], base: int) -> int:
        """Takes the three deposits in one transaction and records the game; returns its id. When a seat falls
        short nothing is taken."""
        deposit = self.deposit(base)
        with self.game.store.transaction() as st:
            now = self.game.now()
            day = day_of(now)
            self._ready(st, list(pids), deposit, day, now)
            for pid in pids:
                st.update_player(pid, shards=st.get_player(pid, now)["shards"] - deposit)
                st.add_ledger(pid, day, "ddz_deposit", -deposit)
            return st.add_ddz_game(list(pids), base, deposit, day, now)

    def deltas(self, base: int, mult: int, landlord: int, landlord_won: bool) -> tuple[list[int], int]:
        """What each seat wins (after the cut) or loses, and the shards burnt."""
        per = base * mult
        raw = [(2 * per if i == landlord else -per) * (1 if landlord_won else -1) for i in range(3)]
        rake = self.cfg()["rake"]
        cut = [d * rake // 100 if d > 0 else 0 for d in raw]
        return [d - c for d, c in zip(raw, cut)], sum(cut)

    def settle(self, game_id: int, landlord: int, landlord_won: bool, mult: int) -> list[int] | None:
        """Pays an open game: every seat gets its deposit back plus or minus its result. Only the first call for a
        game pays; later ones return None."""
        with self.game.store.transaction() as st:
            now = self.game.now()
            g = st.ddz_game(game_id)
            if g is None:
                return None
            deltas, burnt = self.deltas(g["base"], mult, landlord, landlord_won)
            if not st.close_ddz_game(game_id, "settled", landlord, mult, burnt, now):
                return None
            st.set_ddz_deltas(game_id, deltas)
            day = day_of(now)
            for pid, delta in zip(g["players"], deltas):
                back = g["deposit"] + delta
                st.update_player(pid, shards=st.get_player(pid, now)["shards"] + back)
                st.add_ledger(pid, day, "ddz_return", back)
        return deltas

    def refund(self, game_id: int) -> bool:
        """Hands the three deposits of an open game back; False when it was closed already."""
        with self.game.store.transaction() as st:
            now = self.game.now()
            g = st.ddz_game(game_id)
            if g is None or not st.close_ddz_game(game_id, "refunded", -1, 0, 0, now):
                return False
            for pid in g["players"]:
                st.update_player(pid, shards=st.get_player(pid, now)["shards"] + g["deposit"])
                st.add_ledger(pid, day_of(now), "ddz_refund", g["deposit"])
        return True

    def refund_open(self) -> int:
        """At startup: games the last run left open cannot go on (tables live in memory), so the deposits go back.
        Returns the games refunded."""
        return sum(self.refund(i) for i in self.game.store.open_ddz_games())

    def net(self, pid: str) -> int:
        return self.game.store.ddz_net(pid, day_of(self.game.now()))


# ------------------------------------------------------------------ the table
@dataclass(eq=False)
class Seat:
    token: str
    # The member's connection; None while it is away from the room.
    peer: Peer | None
    # The member id the seat is known by: the connection's, kept while it is away.
    id: str
    nick: str
    character: str
    accepted: bool = False
    hand: list[int] = field(default_factory=list)
    bid: int | None = None
    # Hands played this game, passes not counted (a spring is told by them).
    plays: int = 0
    auto: bool = False
    timeouts: int = 0
    again: bool = False
    # Left the table for good while the game went on: played for to the end, and hears nothing more of it.
    quit: bool = False
    # At a table the queue made: when the save started waiting (Waiting.since), kept should it go back to the line.
    since: float | None = None


@dataclass(eq=False)
class Waiting:
    """A save in the queue: the connection it waits on, at which stake, and since when (the clock of Tables)."""
    peer: Peer
    base: int
    since: float
    # Out of the line while a table is being made with it (Tables._match).
    checking: bool = False

    @property
    def token(self) -> str:
        return self.peer.token or ""


@dataclass(eq=False)
class Table:
    id: str
    # The room of an invited table; None for a table the queue made, whose members may sit in different rooms.
    room: str | None
    seats: list[Seat]
    base: int
    deposit: int
    phase: str = INVITE
    row: int | None = None
    deal: int = 0
    bottom: list[int] = field(default_factory=list)
    turn: int = 0
    # The highest bid so far and who made it.
    bid: int = 0
    bidder: int | None = None
    bids_made: int = 0
    landlord: int | None = None
    # The last cards played and by which seat; None when the seat to move leads.
    last: tuple[int, list[int]] | None = None
    # What each seat did since the last lead: its cards, [] for a pass, None for nothing yet.
    trick: list[list[int] | None] = field(default_factory=lambda: [None, None, None])
    bombs: int = 0
    timer: Any = None
    # Counts every turn given out, so a timer that fires late knows its turn is over.
    step: int = 0
    deadline: float = 0.0
    turn_sec: float = 0.0
    # Rooms told the game is on, told again when it ends (Tables._live).
    live_rooms: set[str] = field(default_factory=set)

    @property
    def match(self) -> bool:
        """The queue made this table: no seat invited the others."""
        return self.room is None

    def seat_of(self, peer: Peer) -> int | None:
        return next((i for i, s in enumerate(self.seats) if s.peer is peer), None)

    def tell(self, data: dict, but: int | None = None, quit: bool = False) -> None:
        """Queued for every seat with a member at the table; one that is away hears nothing, one that quit only
        what is told with [quit]."""
        for i, s in enumerate(self.seats):
            if i != but and s.peer is not None and (quit or not s.quit):
                s.peer.enqueue(data)

    def mult(self, cap: int, spring: bool = False) -> int:
        return min(max(self.bid, 1) * 2 ** self.bombs * (2 if spring else 1), cap)


class Tables:
    """Every table on the server: one at a time per save (invites included), across all rooms; and the queue."""

    def __init__(self, game: Callable[[], Game], manager: Callable[[], RoomManager], timers: Any = None,
                 clock: Callable[[], float] = time.monotonic, rng: random.Random | None = None,
                 require_account: Callable[[], bool] = lambda: False, count_timers: Any = None) -> None:
        # Read on every use: tests replace the module's game and room manager.
        self._game = game
        self._manager = manager
        # Whether the server has main-site accounts (Bank._ready).
        self.require_account = require_account
        self.timers = timers or Timers()
        # For the waiting counts' next send; tests keep it apart from the tables' timers.
        self.count_timers = count_timers or self.timers
        self.clock = clock
        self.rng = rng or random.SystemRandom()
        self.by_save: dict[str, Table] = {}
        self.by_id: dict[str, Table] = {}
        # (inviter save, invited save) -> monotonic time from which a new invite is allowed
        self.refused: dict[tuple[str, str], float] = {}
        # The queue: each stake's line, oldest first, and every save waiting (in a line or being matched) by save.
        self.lines: dict[int, list[Waiting]] = {}
        self.waiting: dict[str, Waiting] = {}
        # Stakes whose line is being matched now (_match).
        self._matching: set[int] = set()
        # Matching started where nothing awaits it (_spawn).
        self._tasks: set[asyncio.Task] = set()
        # Save -> clock time from which it may queue again, after declining a table of the queue or letting it lapse.
        self.match_refused: dict[str, float] = {}
        # The waiting counts last sent, when, and the timer of the next send.
        self._counts_sent: dict[int, int] = {}
        self._counts_at = float("-inf")
        self._counts_timer: Any = None

    @property
    def bank(self) -> Bank:
        return Bank(self._game(), self.require_account())

    @property
    def manager(self) -> RoomManager:
        return self._manager()

    def clear(self) -> None:
        for table in list(self.by_id.values()):
            self._drop(table)
        self.refused.clear()
        self.lines.clear()
        self.waiting.clear()
        self.match_refused.clear()
        self._matching.clear()
        if self._counts_timer is not None:
            self._counts_timer.cancel()
            self._counts_timer = None
        self._counts_sent = {}
        self._counts_at = float("-inf")

    def in_game(self, peer: Peer) -> bool:
        """Whether the connection sits at a table whose deposits are taken (or being taken)."""
        table = self.by_save.get(peer.token) if peer.token else None
        return (table is not None and table.seat_of(peer) is not None
                and table.phase in (STARTING, BID, PLAY, SETTLING))

    def _table(self, peer: Peer, table_id: str, *phases: str) -> tuple[Table, int]:
        table = self.by_id.get(table_id)
        seat = table.seat_of(peer) if table else None
        if table is None or seat is None or table.phase not in phases or table.seats[seat].quit:
            raise GameError("ddz_gone", "")
        return table, seat

    # ------------------------------------------------------------------ invites
    def _check_free(self, peers: list[Peer]) -> None:
        me = peers[0]
        if not me.token:
            raise GameError("ddz_locked", "")
        if me.token in self.by_save:
            raise GameError("ddz_busy", "")
        now = self.clock()
        for p in peers[1:]:
            if not p.token:
                raise GameError("ddz_target_locked", "")
            if p.token in self.by_save:
                raise GameError("ddz_target_busy", "")
            if not p.ddz:
                raise GameError("ddz_target_old", "")
            if now < self.refused.get((me.token, p.token), 0.0):
                raise GameError("ddz_cooldown", "")

    def _peers(self, room_id: str, peer: Peer, ids: list[str]) -> list[Peer]:
        room = self.manager.rooms.get(room_id)
        others = [room.peers.get(i) if room else None for i in ids]
        if room is None or not peer.active or room.peers.get(peer.id) is not peer or any(
                p is None or not p.active for p in others):
            raise GameError("no_member", "no such member")
        peers = [peer, *others]
        if len({p.id for p in peers}) != 3 or len({p.token for p in peers if p.token}) != sum(
                1 for p in peers if p.token):
            raise GameError("ddz_self", "")
        return peers

    async def invite(self, room_id: str, peer: Peer, ids: list[str], base: int) -> None:
        bank = self.bank
        cfg = bank.cfg()
        peers = self._peers(room_id, peer, ids)
        self._check_free(peers)
        deposit = await run_in_threadpool(bank.check, [p.token for p in peers], base)
        # Any of the three may have left, or sat down elsewhere, while the database was read.
        peers = self._peers(room_id, peer, ids)
        self._check_free(peers)
        table = Table(id=secrets.token_hex(4), room=room_id, base=base, deposit=deposit, seats=[
            Seat(token=p.token, peer=p, id=p.id, nick=p.nick, character=p.character, accepted=p is peer)
            for p in peers])
        self.by_id[table.id] = table
        for p in peers:
            self.by_save[p.token] = table
        # Inviting takes the inviter out of the queue; the two invited keep waiting (skipped while the invite is out)
        # until one of them accepts.
        self._leave_queue(peer, save=True)
        invited = {"type": "ddz_invite", "table": table.id, "from": peer.id, "ids": [p.id for p in peers],
                   "base": base, "deposit": deposit, "sec": cfg["inviteSec"]}
        quiet = [p for p in peers[1:] if p.dnd]
        if quiet:
            # Turned down for the member, who never sees it; the inviter hears a plain refusal.
            peer.enqueue(invited)
            self._end(table, "declined", by=quiet[0], refused=quiet, tell=(peer,))
            return
        table.tell(invited)
        table.timer = self.timers.later(cfg["inviteSec"], lambda: self._invite_expired(table))

    async def _invite_expired(self, table: Table) -> None:
        if table.phase != INVITE:
            return
        if table.match:
            self._end_match(table, "timeout")
        else:
            self._end(table, "timeout", refused=[s.peer for s in table.seats[1:] if not s.accepted and s.peer])

    def set_dnd(self, peer: Peer, on: bool) -> None:
        """Called with the duels' own: an invite waiting for this member is turned down, and it stops waiting in the
        queue."""
        if not on:
            return
        self._leave_queue(peer, reason="ddz_dnd")
        table = self.by_save.get(peer.token) if peer.token else None
        seat = table.seat_of(peer) if table else None
        if table is None or seat is None or table.phase != INVITE or table.seats[seat].accepted:
            return
        if table.match:
            self._end_match(table, "declined", by=peer)
        elif seat:
            self._end(table, "declined", by=peer, refused=[peer])

    async def answer(self, peer: Peer, table_id: str, accept: bool) -> None:
        table, seat = self._table(peer, table_id, INVITE)
        if (seat == 0 and not table.match) or table.seats[seat].accepted:
            raise GameError("ddz_gone", "")
        if not accept:
            if table.match:
                self._end_match(table, "declined", by=peer)
            else:
                self._end(table, "declined", by=peer, refused=[peer])
            return
        # Accepting an invite takes the save out of the queue.
        self._leave_queue(peer, save=True)
        table.seats[seat].accepted = True
        table.tell({"type": "ddz_answer", "table": table.id, "id": peer.id})
        if all(s.accepted for s in table.seats):
            await self._start(table)

    # ------------------------------------------------------------------- a game
    async def _start(self, table: Table) -> None:
        """Takes the deposits and deals. The members may leave while the database works: they are played for."""
        table.phase = STARTING
        self._cancel_timer(table)
        try:
            table.row = await run_in_threadpool(self.bank.start, [s.token for s in table.seats], table.base)
        except GameError as e:
            code = {"ddz_target_poor": "no_shards", "ddz_target_cap": "ddz_cap",
                    "ddz_target_locked": "ddz_locked", "ddz_target_account": "ddz_account"}.get(e.code, e.code)
            self._end(table, code)
            return
        except BaseException:
            # The transaction rolled back, so nothing was taken: free the three saves, then let the error be
            # reported as usual.
            self._end(table, "error")
            raise
        if all(s.peer is None for s in table.seats):
            await self._abort(table, "gone")
            return
        table.deal = 0
        await self._live(table, True)
        self._deal(table)

    def _deal(self, table: Table) -> None:
        deck = list(rules.DECK)
        self.rng.shuffle(deck)
        table.deal += 1
        table.phase = BID
        table.bottom = sorted(deck[51:])
        table.bid, table.bidder, table.bids_made, table.landlord = 0, None, 0, None
        table.last, table.trick, table.bombs = None, [None, None, None], 0
        for i, s in enumerate(table.seats):
            s.hand = sorted(deck[i * 17:(i + 1) * 17])
            s.bid, s.plays, s.again = None, 0, False
        first = self.rng.randrange(3)
        sec = self._give_turn(table, first, self.bank.cfg()["bidSec"], wait=DEAL_SEC)
        seats = [{"id": s.id, "nick": s.nick, "character": s.character, "auto": s.auto,
                  "away": s.peer is None or s.quit} for s in table.seats]
        cfg = self.bank.cfg()
        for i, s in enumerate(table.seats):
            if s.peer is not None and not s.quit:
                s.peer.enqueue({"type": "ddz_deal", "table": table.id, "seats": seats, "you": i, "hand": s.hand,
                                "base": table.base, "cap": cfg["capMult"], "deal": table.deal, "turn": first,
                                "sec": sec, "dealSec": DEAL_SEC})

    def _give_turn(self, table: Table, seat: int, sec: float, wait: float = 0.0) -> float:
        """Hands the move to [seat] for [sec] seconds, starting [wait] seconds from now (a seat played for moves at
        once); returns the seconds of the move."""
        self._cancel_timer(table)
        s = table.seats[seat]
        if s.auto or s.peer is None:
            sec = AUTO_SEC
        table.turn = seat
        table.step += 1
        table.turn_sec = sec
        table.deadline = self.clock() + wait + sec
        step = table.step
        table.timer = self.timers.later(wait + sec, lambda: self._expired(table, step))
        return sec

    async def _expired(self, table: Table, step: int) -> None:
        if table.step != step or table.phase not in (BID, PLAY):
            return
        s = table.seats[table.turn]
        if not s.auto and s.peer is not None:
            s.timeouts += 1
            if s.timeouts >= AUTO_AFTER:
                self._set_auto(table, table.turn, True)
        if table.phase == BID:
            await self._bid(table, table.turn, 0)
        else:
            await self._play(table, table.turn, self._choose(table, table.turn))

    def _choose(self, table: Table, seat: int) -> list[int]:
        """The cards played for [seat] (see ddz_rules.choose). Should the chooser fail or pick cards that may not be
        played, the seat passes, or leads its lowest card, so the table never waits."""
        s = table.seats[seat]
        last = table.last[1] if table.last is not None else None
        lord = table.landlord
        partner_led = table.last is not None and lord not in (seat, table.last[0])
        danger = any(len(x.hand) <= rules.DANGER for i, x in enumerate(table.seats)
                     if i != seat and (seat == lord or i == lord))
        try:
            cards = rules.choose(s.hand, last, partner_led=partner_led, danger=danger)
            if cards:
                ok = (len(set(cards)) == len(cards) and set(cards) <= set(s.hand) and bool(rules.classify(cards))
                      and (last is None or rules.beats(cards, last)))
            else:
                ok = last is not None
            if ok:
                return sorted(cards)
            log.error("ddz: chose %s for hand %s on %s", cards, s.hand, last)
        except Exception:
            log.exception("ddz: choosing a play failed for hand %s on %s", s.hand, last)
        return [] if last is not None else [s.hand[0]]

    def _set_auto(self, table: Table, seat: int, on: bool) -> None:
        s = table.seats[seat]
        if s.auto == on:
            return
        s.auto = on
        table.tell({"type": "ddz_seat", "table": table.id, "seat": seat, "id": s.id, "away": s.peer is None,
                    "auto": s.auto})

    async def bid(self, peer: Peer, table_id: str, bid: int) -> None:
        table, seat = self._table(peer, table_id, BID)
        if seat != table.turn:
            raise GameError("ddz_turn", "")
        if bid and bid <= table.bid:
            raise GameError("ddz_bad", "")
        table.seats[seat].timeouts = 0
        await self._bid(table, seat, bid)

    async def _bid(self, table: Table, seat: int, bid: int) -> None:
        cfg = self.bank.cfg()
        s = table.seats[seat]
        s.bid = bid
        table.bids_made += 1
        if bid > table.bid:
            table.bid, table.bidder = bid, seat
        said = {"type": "ddz_bid", "table": table.id, "seat": seat, "bid": bid}
        if bid < 3 and table.bids_made < 3:
            nxt = (seat + 1) % 3
            said["turn"] = nxt
            said["sec"] = self._give_turn(table, nxt, cfg["bidSec"])
            table.tell(said)
            return
        table.tell(said)
        if table.bidder is None:
            if table.deal >= MAX_DEALS:
                await self._abort(table, "nobid")
            else:
                self._deal(table)
            return
        lord = table.bidder
        table.landlord = lord
        table.phase = PLAY
        table.seats[lord].hand = sorted(table.seats[lord].hand + table.bottom)
        sec = self._give_turn(table, lord, cfg["playSec"])
        table.tell({"type": "ddz_landlord", "table": table.id, "seat": lord, "bid": table.bid, "bottom": table.bottom,
                    "mult": table.mult(cfg["capMult"]), "turn": lord, "sec": sec})

    async def play(self, peer: Peer, table_id: str, cards: list[int]) -> None:
        table, seat = self._table(peer, table_id, PLAY)
        if seat != table.turn:
            raise GameError("ddz_turn", "")
        s = table.seats[seat]
        if not cards:
            if table.last is None:
                raise GameError("ddz_bad", "")
        elif (len(set(cards)) != len(cards) or not set(cards) <= set(s.hand) or not rules.classify(cards)
              or (table.last is not None and not rules.beats(cards, table.last[1]))):
            raise GameError("ddz_bad", "")
        s.timeouts = 0
        await self._play(table, seat, sorted(cards))

    async def _play(self, table: Table, seat: int, cards: list[int]) -> None:
        cfg = self.bank.cfg()
        s = table.seats[seat]
        if cards:
            gone = set(cards)
            s.hand = [c for c in s.hand if c not in gone]
            s.plays += 1
            table.bombs += rules.bombs(cards)
            table.last = (seat, cards)
        table.trick[seat] = cards
        said = {"type": "ddz_play", "table": table.id, "seat": seat, "cards": cards, "left": len(s.hand),
                "mult": table.mult(cfg["capMult"]), "bombs": table.bombs}
        if not s.hand:
            table.tell(said)
            await self._finish(table, seat)
            return
        nxt = (seat + 1) % 3
        lead = table.last is not None and table.last[0] == nxt
        if lead:
            # Both others passed: the seat that played last leads again.
            table.last = None
            table.trick = [None, None, None]
        said["turn"] = nxt
        said["lead"] = lead
        said["sec"] = self._give_turn(table, nxt, cfg["playSec"])
        table.tell(said)

    async def _finish(self, table: Table, winner: int) -> None:
        """Pays the game [winner] just won. Marked before the first await, so nothing else moves the table."""
        table.phase = SETTLING
        self._cancel_timer(table)
        bank = self.bank
        cfg = bank.cfg()
        lord = table.landlord
        landlord_won = winner == lord
        farmers = [s for i, s in enumerate(table.seats) if i != lord]
        spring = 1 if landlord_won and all(f.plays == 0 for f in farmers) else (
            2 if not landlord_won and table.seats[lord].plays == 1 else 0)
        mult = table.mult(cfg["capMult"], spring=bool(spring))
        deltas = await run_in_threadpool(bank.settle, table.row, lord, landlord_won, mult)
        if deltas is None:
            self._close(table, tell=False)
            return
        table.phase = OVER
        for s in table.seats:
            s.again = False
        table.tell({"type": "ddz_result", "table": table.id, "winner": "landlord" if landlord_won else "farmers",
                    "landlord": lord, "bid": table.bid, "bombs": table.bombs, "spring": spring, "mult": mult,
                    "base": table.base, "deltas": deltas, "hands": [s.hand for s in table.seats],
                    "sec": cfg["againSec"]}, quit=True)
        await self._live(table, False, gains={s.id: d for s, d in zip(table.seats, deltas) if d > 0})
        if any(s.peer is None or s.quit for s in table.seats):
            self._close(table)
            return
        table.timer = self.timers.later(cfg["againSec"], lambda: self._again_expired(table))

    async def _again_expired(self, table: Table) -> None:
        if table.phase == OVER:
            self._close(table)

    async def _abort(self, table: Table, reason: str) -> None:
        """Ends a game whose deposits are taken with nothing won: they go back."""
        table.phase = SETTLING
        self._cancel_timer(table)
        await run_in_threadpool(self.bank.refund, table.row)
        table.phase = DONE
        self._drop(table)
        table.tell({"type": "ddz_over", "table": table.id, "reason": reason}, quit=True)
        await self._live(table, False)

    # ------------------------------------------------------------ around a game
    def auto(self, peer: Peer, table_id: str, on: bool) -> None:
        """A member turns its seat's autopilot on or off; off on its own turn gives the turn its full time again."""
        table, seat = self._table(peer, table_id, BID, PLAY)
        s = table.seats[seat]
        s.timeouts = 0
        if s.auto == on:
            return
        s.auto = on
        said = {"type": "ddz_seat", "table": table.id, "seat": seat, "id": s.id, "away": False, "auto": on}
        if table.turn == seat:
            cfg = self.bank.cfg()
            said["turn"] = seat
            said["sec"] = self._give_turn(table, seat, cfg["bidSec"] if table.phase == BID else cfg["playSec"])
        table.tell(said)

    async def again(self, peer: Peer, table_id: str) -> None:
        table, seat = self._table(peer, table_id, OVER)
        s = table.seats[seat]
        if s.again:
            return
        s.again = True
        table.tell({"type": "ddz_again", "table": table.id, "seat": seat})
        if not all(x.again for x in table.seats):
            return
        table.phase = STARTING
        self._cancel_timer(table)
        try:
            table.row = await run_in_threadpool(self.bank.start, [x.token for x in table.seats], table.base)
        except GameError as e:
            code = {"ddz_target_poor": "no_shards", "ddz_target_cap": "ddz_cap",
                    "ddz_target_locked": "ddz_locked", "ddz_target_account": "ddz_account"}.get(e.code, e.code)
            self._end(table, code)
            return
        except BaseException:
            self._end(table, "error")
            raise
        if all(x.peer is None for x in table.seats):
            # All three left while the deposits were taken: nobody to play for.
            await self._abort(table, "gone")
            return
        for x in table.seats:
            x.auto, x.timeouts = x.peer is None, 0
        table.deal = 0
        await self._live(table, True)
        self._deal(table)

    async def leave(self, peer: Peer, table_id: str) -> None:
        """A member walks away from the table but stays in the room."""
        table, seat = self._table(peer, table_id, INVITE, BID, PLAY, OVER)
        if table.phase == INVITE and table.match:
            self._end_match(table, "declined", by=peer)
        elif table.phase == INVITE:
            self._end(table, "gone" if seat == 0 else "declined", by=peer, refused=[peer] if seat else [])
        elif table.phase == OVER:
            self._close(table)
        else:
            self._quit(table, seat)

    def _quit(self, table: Table, seat: int) -> None:
        s = table.seats[seat]
        s.quit, s.auto = True, True
        table.tell({"type": "ddz_seat", "table": table.id, "seat": seat, "id": s.id, "away": True, "auto": True})
        if table.turn == seat and table.phase in (BID, PLAY):
            self._give_turn(table, seat, AUTO_SEC)

    async def departed(self, room_id: str, peer: Peer) -> None:
        """A member left the room (leave, kick, lost connection): it stops waiting in the queue, an invite is dropped,
        a seat in a game is played for until its save comes back."""
        self._leave_queue(peer, tell=False)
        table = self.by_save.get(peer.token) if peer.token else None
        seat = table.seat_of(peer) if table else None
        if table is None or seat is None:
            return
        s = table.seats[seat]
        if table.phase == INVITE and table.match:
            self._end_match(table, "gone", by=peer)
        elif table.phase == INVITE:
            # An inviter leaving waits as after a refusal, so leaving and coming back cannot repeat the invite.
            self._end(table, "gone", by=peer, refused=[x.peer for x in table.seats[1:] if x.peer] if seat == 0 else [])
        elif table.phase == OVER:
            self._close(table)
        elif table.phase in (STARTING, SETTLING):
            s.peer = None
        elif table.phase in (BID, PLAY):
            s.peer = None
            if all(x.peer is None for x in table.seats):
                # Nobody is left to watch it played out.
                await self._abort(table, "gone")
                return
            table.tell({"type": "ddz_seat", "table": table.id, "seat": seat, "id": s.id, "away": True, "auto": s.auto})
            if table.turn == seat:
                self._give_turn(table, seat, AUTO_SEC)

    async def joined(self, room_id: str, peer: Peer) -> None:
        """A member joined the room: it hears of the games under way there, and takes its seat again if its save
        has one at a table of this room, or at a table the queue made (from any room, on a client that queues). Back
        while the deposits are being taken, it takes the seat and hears the deal like the others."""
        room = self.manager.rooms.get(room_id)
        if room is None or room.peers.get(peer.id) is not peer:
            return  # gone again before it got through joining
        table = self.by_save.get(peer.token) if peer.token else None
        seat = None
        if table is not None and table.phase in (STARTING, BID, PLAY) and (
                peer.ddz_match if table.match else peer.ddz and table.room == room_id):
            seat = next((i for i, s in enumerate(table.seats) if s.token == peer.token and s.peer is None), None)
            if seat is None:
                # An older connection of the save still holds the seat: its leaving is not seen yet (a client back
                # on a new connection), or it is another device. The newest connection takes the seat; joins finish
                # in any order, so one that finishes late leaves a newer one there, unless that one is gone.
                seat = next((i for i, s in enumerate(table.seats) if s.token == peer.token and s.peer is not None
                             and s.peer is not peer and (s.peer.join_seq < peer.join_seq or not s.peer.active)),
                            None)
        # Taken from a connection that played the seat itself: the seat goes on as it was, its turn included.
        handoff = False
        if seat is not None:
            s = table.seats[seat]
            handoff = s.peer is not None and not s.auto
            if s.peer is not None and s.peer is not peer:
                # The old connection lets go of the table; its leaving, seen later, finds no seat of its own.
                s.peer.enqueue({"type": "ddz_closed", "table": table.id})
            s.peer, s.id, s.nick, s.character = peer, peer.id, peer.nick, peer.character
            if not handoff:
                s.auto, s.timeouts, s.quit = False, 0, False
        for live in list(self.by_id.values()):
            if live.phase not in (BID, PLAY, SETTLING):
                continue
            if seat is not None and live is table:
                # Every room of the table hears the seat's new member id.
                await self._live(live, True)
            elif room_id in self._rooms(live):
                live.live_rooms.add(room_id)
                peer.enqueue({"type": "ddz_live", "table": live.id, "ids": [s.id for s in live.seats], "on": True})
        # The counts the others were sent last: a change since then is on its way to everyone (_counts_changed), the
        # newcomer included, which a send of the counts as they are now could leave behind.
        if peer.ddz_match and self._counts_sent:
            peer.enqueue(self._counts_msg(self._counts_sent))
        if seat is None or table.phase == STARTING:
            return
        msg = {"type": "ddz_seat", "table": table.id, "seat": seat, "id": s.id, "away": False, "auto": False}
        if table.turn == seat:
            cfg = self.bank.cfg()
            msg["turn"] = seat
            if handoff:
                # A fresh time on each handoff would let two devices hold the other two up for good.
                msg["sec"] = max(0.0, round(table.deadline - self.clock(), 1))
            else:
                msg["sec"] = self._give_turn(table, seat, cfg["bidSec"] if table.phase == BID else cfg["playSec"])
        table.tell(msg, but=seat)
        peer.enqueue(self._state(table, seat))

    def _state(self, table: Table, seat: int) -> dict:
        """The whole game as [seat] may see it."""
        cfg = self.bank.cfg()
        return {
            "type": "ddz_state", "table": table.id, "phase": table.phase, "you": seat, "hand": table.seats[seat].hand,
            "seats": [{"id": s.id, "nick": s.nick, "character": s.character, "left": len(s.hand), "bid": s.bid,
                       "auto": s.auto, "away": s.peer is None or s.quit} for s in table.seats],
            "base": table.base, "cap": cfg["capMult"], "deal": table.deal, "bid": table.bid,
            "landlord": table.landlord, "bottom": table.bottom if table.landlord is not None else [],
            "mult": table.mult(cfg["capMult"]), "bombs": table.bombs, "turn": table.turn,
            "lead": table.phase == PLAY and table.last is None, "trick": table.trick,
            "sec": max(0.0, round(table.deadline - self.clock(), 1)), "of": table.turn_sec,
        }

    def _rooms(self, table: Table) -> set[str]:
        """The rooms that see the table: an invited table's own room; for a table the queue made, the rooms its
        seats' members are in now (one that walked away from the table included)."""
        if table.room is not None:
            return {table.room}
        return {s.peer.room for s in table.seats if s.peer is not None and s.peer.active}

    async def _live(self, table: Table, on: bool, gains: dict[str, int] | None = None) -> None:
        """Tells the table's rooms (_rooms) that its game started (on) or ended; the end also goes to every room
        told of the start, so one its members all left does not keep showing the game."""
        msg: dict[str, Any] = {"type": "ddz_live", "table": table.id, "ids": [s.id for s in table.seats], "on": on}
        if gains is not None:
            msg["gains"] = gains
        rooms = self._rooms(table)
        if on:
            table.live_rooms |= rooms
        else:
            rooms |= table.live_rooms
            table.live_rooms = set()
        for room_id in sorted(rooms):
            await self.manager.broadcast(room_id, msg)

    # -------------------------------------------------------------------- queue
    def _check_queue(self, peer: Peer) -> None:
        """What keeps [peer] out of the queue, its own save's shards and taps aside (Bank.check)."""
        if not peer.token:
            raise GameError("ddz_locked", "")
        if not peer.active:
            raise GameError("ddz_gone", "")
        if peer.token in self.by_save:
            raise GameError("ddz_busy", "")
        held = self.waiting.get(peer.token)
        if held is not None and held.peer is not peer:
            raise GameError("ddz_queued", "")
        if peer.dnd:
            raise GameError("ddz_dnd", "")
        if self.clock() < self.match_refused.get(peer.token, float("-inf")):
            raise GameError("ddz_match_cooldown", "")

    async def queue(self, peer: Peer, base: int) -> None:
        """[peer] waits for a table at stake [base]; waiting at another stake already, it moves to the end of this
        one's line. Then a table is made if three in the line may sit down together."""
        if not peer.ddz_match:
            raise GameError("bad_message", "join with ddzMatch to queue")
        bank = self.bank
        if base not in bank.cfg()["stakes"]:
            raise GameError("bad_message", "unknown stake")
        self._prune()
        self._check_queue(peer)
        held = self.waiting.get(peer.token)
        if held is None or held.base != base:
            now = self.clock()
            if now - peer.ddz_queue_at < QUEUE_INTERVAL:
                raise GameError("rate_limited", "too many queue requests")
            peer.ddz_queue_at = now
            await run_in_threadpool(bank.check, [peer.token], base)
            # It may have left, sat down or queued elsewhere while the database was read.
            self._check_queue(peer)
            held = self.waiting.get(peer.token)
        if held is not None and held.base == base:
            self._tell_queue(held)
            return
        if held is not None:
            self._dequeue(held, tell=False)
        w = Waiting(peer, base, self.clock())
        self.waiting[w.token] = w
        self.lines.setdefault(base, []).append(w)
        self._tell_queue(w)
        self._counts_changed()
        await self._match(base)

    def unqueue(self, peer: Peer) -> None:
        """[peer] stops waiting. It hears that it waits no more even when it did not, so the client keeps in step."""
        if not self._leave_queue(peer):
            peer.enqueue({"type": "ddz_queue", "base": None})

    def _leave_queue(self, peer: Peer, reason: str | None = None, tell: bool = True, save: bool = False) -> bool:
        """Takes [peer] out of the queue when it waits there; with [save] also its save waiting on another
        connection."""
        held = self.waiting.get(peer.token) if peer.token else None
        if held is None or (held.peer is not peer and not save):
            return False
        self._dequeue(held, reason=reason, tell=tell)
        return True

    def _dequeue(self, w: Waiting, reason: str | None = None, tell: bool = True) -> None:
        if self.waiting.get(w.token) is w:
            del self.waiting[w.token]
        line = self.lines.get(w.base)
        if line is not None and w in line:
            line.remove(w)
            if not line:
                del self.lines[w.base]
        if tell:
            msg: dict[str, Any] = {"type": "ddz_queue", "base": None}
            if reason:
                msg["reason"] = reason
            w.peer.enqueue(msg)
        self._counts_changed()

    def _tell_queue(self, w: Waiting) -> None:
        w.peer.enqueue({"type": "ddz_queue", "base": w.base, "waited": round(max(0.0, self.clock() - w.since), 1)})

    def _prune(self) -> None:
        """Drops the saves waiting at a stake the economy no longer has."""
        cfg = self._game().manifest.ddz
        stakes = set(cfg["stakes"]) if cfg else set()
        for w in [w for w in self.waiting.values() if w.base not in stakes]:
            self._dequeue(w)

    def _spawn(self, work: Any) -> None:
        """Runs [work] (matching) on the loop without awaiting it."""
        task = asyncio.get_running_loop().create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def idle(self) -> None:
        """Waits until no matching started by _spawn runs (tests)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks))

    async def _match(self, base: int) -> None:
        """Makes tables from the line of [base] while three saves in it may sit down together: the oldest three that
        hold no invite. One that may no longer sit down leaves the queue, told why; the others of its three go back
        into the line (_merge). One line is matched at a time."""
        if base in self._matching:
            return
        self._matching.add(base)
        try:
            while True:
                self._prune()
                line = self.lines.get(base, [])
                three = [w for w in line if w.token not in self.by_save][:3]
                if len(three) < 3:
                    return
                for w in three:
                    line.remove(w)
                    w.checking = True
                if not line:
                    self.lines.pop(base, None)
                try:
                    codes = await run_in_threadpool(self.bank.refusals, [w.token for w in three], base)
                except Exception:
                    log.exception("ddz: matching at %s failed", base)
                    codes = ["error"] * 3
                ready, back = [], []
                for w, code in zip(three, codes):
                    w.checking = False
                    if self.waiting.get(w.token) is not w:
                        continue  # cancelled, left or turned invites down meanwhile
                    code = code or ("ddz_dnd" if w.peer.dnd else None)
                    if code:
                        self._dequeue(w, reason=code)
                    elif w.token in self.by_save:
                        back.append(w)  # invited meanwhile: keeps waiting
                    else:
                        ready.append(w)
                        back.append(w)
                if len(ready) == 3:
                    self._form(base, ready)
                elif back:
                    self._merge(base, back)
        finally:
            self._matching.discard(base)

    def _form(self, base: int, three: list[Waiting]) -> None:
        """Seats [three] at a new table of no room and asks all three, as an invite does."""
        cfg = self.bank.cfg()
        deposit = self.bank.deposit(base)
        table = Table(id=secrets.token_hex(4), room=None, base=base, deposit=deposit, seats=[
            Seat(token=w.token, peer=w.peer, id=w.peer.id, nick=w.peer.nick, character=w.peer.character, since=w.since)
            for w in three])
        for w in three:
            self._dequeue(w)
        self.by_id[table.id] = table
        for s in table.seats:
            self.by_save[s.token] = table
        table.tell({"type": "ddz_invite", "table": table.id, "ids": [s.id for s in table.seats], "base": base,
                    "deposit": deposit, "sec": cfg["inviteSec"], "match": True,
                    "seats": [{"id": s.id, "nick": s.nick, "character": s.character} for s in table.seats]})
        table.timer = self.timers.later(cfg["inviteSec"], lambda: self._invite_expired(table))

    def _merge(self, base: int, entries: list[Waiting]) -> None:
        """Puts [entries] into the line of [base] by when each started waiting, so the line stays oldest first:
        saves back from tables that fell through, in whatever order those did, stay ahead of those who came later. On
        a tie the one coming back goes first: it was ahead before."""
        line = self.lines.setdefault(base, [])
        back = sorted(entries, key=lambda x: x.since)
        merged: list[Waiting] = []
        i = j = 0
        while i < len(back) and j < len(line):
            if back[i].since <= line[j].since:
                merged.append(back[i])
                i += 1
            else:
                merged.append(line[j])
                j += 1
        line[:] = merged + back[i:] + line[j:]

    def _requeue(self, base: int, seats: list[Seat]) -> None:
        """Puts the saves of [seats] back into the line of [base] (_merge), each waiting since it first did; one
        whose member left, sits elsewhere, waits again already or turns invites down is not."""
        cfg = self._game().manifest.ddz
        if not cfg or base not in cfg["stakes"]:
            return
        back = []
        for s in seats:
            p = s.peer
            if (p is None or not p.active or not p.ddz_match or p.dnd or not p.token or p.token in self.by_save
                    or p.token in self.waiting):
                continue
            w = Waiting(p, base, s.since if s.since is not None else self.clock())
            self.waiting[w.token] = w
            back.append(w)
        if not back:
            return
        self._merge(base, back)
        for w in back:
            self._tell_queue(w)
        self._counts_changed()
        self._spawn(self._match(base))

    def counts(self) -> dict[int, int]:
        """How many saves wait at each stake (being matched included)."""
        out: dict[int, int] = {}
        for w in self.waiting.values():
            out[w.base] = out.get(w.base, 0) + 1
        return out

    @staticmethod
    def _counts_msg(counts: dict[int, int]) -> dict:
        return {"type": "ddz_waiting", "counts": [[base, n] for base, n in sorted(counts.items())]}

    def _counts_changed(self) -> None:
        """The counts go out now, or COUNTS_SEC after the last time they did."""
        if self._counts_timer is not None:
            return
        wait = self._counts_at + COUNTS_SEC - self.clock()
        if wait > 0:
            self._counts_timer = self.count_timers.later(wait, self._counts_due)
        else:
            self._send_counts()

    async def _counts_due(self) -> None:
        self._counts_timer = None
        self._send_counts()

    def _send_counts(self) -> None:
        """Tells every member that queues, in every room, the counts, when they changed since the last time."""
        counts = self.counts()
        if counts == self._counts_sent:
            return
        self._counts_sent = counts
        self._counts_at = self.clock()
        msg = self._counts_msg(counts)
        for room in list(self.manager.rooms.values()):
            for p in list(room.peers.values()):
                if p.ddz_match:
                    p.enqueue(msg)

    # ------------------------------------------------------------------- ending
    def _cancel_timer(self, table: Table) -> None:
        if table.timer is not None:
            table.timer.cancel()
            table.timer = None

    def _drop(self, table: Table) -> None:
        self._cancel_timer(table)
        self.by_id.pop(table.id, None)
        for s in table.seats:
            if self.by_save.get(s.token) is table:
                del self.by_save[s.token]

    def _refuse(self, table: Table, peers: list[Peer]) -> None:
        now = self.clock()
        self.refused = {k: t for k, t in self.refused.items() if t > now}
        for p in peers:
            if p.token and p.token != table.seats[0].token:
                self.refused[(table.seats[0].token, p.token)] = now + RETRY_SEC

    def _end(self, table: Table, reason: str, by: Peer | None = None, refused: list[Peer] | None = None,
             tell: tuple[Peer, ...] | None = None) -> None:
        """Ends an invite, or a table whose deposits were never taken; [tell] narrows who hears it."""
        if table.phase == DONE:
            return
        table.phase = DONE
        self._drop(table)
        self._refuse(table, refused or [])
        over = {"type": "ddz_over", "table": table.id, "reason": reason}
        if by is not None:
            over["by"] = by.id
        if tell is not None:
            for p in tell:
                p.enqueue(over)
        else:
            table.tell(over)
        # Invited saves that kept waiting in the queue may be matched again.
        for base in {w.base for s in table.seats if (w := self.waiting.get(s.token)) is not None}:
            self._spawn(self._match(base))

    def _end_match(self, table: Table, reason: str, by: Peer | None = None) -> None:
        """Ends the invite of a table the queue made: the seat that declined or left ([by]), or every seat that let
        the time run out, is out of the queue; the others go back into the line (_requeue). One that declined or let
        the time run out may queue again only after MATCH_RETRY_SEC."""
        if table.phase == DONE:
            return
        if reason == "timeout":
            back = [s for s in table.seats if s.accepted]
            out = [s for s in table.seats if not s.accepted]
        else:
            back = [s for s in table.seats if s.peer is not by]
            out = [s for s in table.seats if s.peer is by] if reason == "declined" else []
        self._end(table, reason, by=by)
        now = self.clock()
        self.match_refused = {k: t for k, t in self.match_refused.items() if t > now}
        for s in out:
            self.match_refused[s.token] = now + MATCH_RETRY_SEC
            if s.peer is not None:
                s.peer.enqueue({"type": "ddz_queue", "base": None, "reason": "ddz_match_cooldown",
                                "retry": MATCH_RETRY_SEC})
        self._requeue(table.base, back)

    def _close(self, table: Table, tell: bool = True) -> None:
        """Clears a table whose game is paid."""
        if table.phase == DONE:
            return
        table.phase = DONE
        self._drop(table)
        if tell:
            table.tell({"type": "ddz_closed", "table": table.id})
