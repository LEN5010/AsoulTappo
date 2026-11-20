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
that declines, leaves or lets the time run out is out of the queue, and may queue again only after MATCH_RETRY_SEC;
the others go back into the line where their wait puts them, ahead of anyone who came after them. Once all three
accept, the game goes on as an invited one; a seat's member who leaves takes the seat again by joining any room with
the same save. Leaving the room, turning invites down (dnd), starting an invite or accepting one takes a save out of
the queue.

Open tables: a member on a client that said `ddzMatch` opens a table at a stake in its room and takes seat 0; members
of the room sit down at its empty seats, and sitting is consent. The third to sit starts the game: the three deposits
go in one transaction, and a seat whose save may no longer play is let go, told why, while the table waits again (the
opener's puts it away). Before the start a member stands up by leaving the table or the room; the opener doing so puts
the table away, as does OPEN_SEC without the three seats taken. An empty seat that has waited FILL_SEC is offered to
the save that waited longest in the queue at the table's stake, one seat at a time; it accepts as at a table the queue
made (the seats taken do not answer again) and its seat is taken again from any room, and one that declines, leaves or
lets the time run out may queue again only after MATCH_RETRY_SEC, the seat going to the next. Nothing is taken before
the start: one that leaves the table while the deposits are being taken, or leaves the room and is not back once they
are, gives them back and stands up (the opener puts the table away), as decided once they are taken. After a game, those who ask for another keep their seats; when the opener did and someone did
not (or left), the table opens again with them, at the same stake and by the same rules, else it closes as an invited
one does.

Messages to the three seats (all carry `table`); seats are numbered 0 to 2 in turn order, 0 the inviter (the save
that waited longest at a table the queue made, the opener of an open table):

- ``ddz_invite`` {from, ids, base, deposit, sec}: member `from` invited the two other members of `ids`. A table the
  queue made has no `from`, and has `match` true and `seats` [{id, nick, character}] (the members may be in other
  rooms). The seat of an open table offered to a save of the queue comes the same way to that save alone, with
  `accepted` the ids of the seats taken, an empty seat as "" in `ids` and null in `seats`; it answers with
  ``ddz_answer``.
- ``ddz_answer`` {id}: member `id` accepted.
- ``ddz_over`` {reason, by?}: the invite or the game ended with nothing won: declined | timeout | gone (`by` is the
  member) | nobid (three deals nobody bid on) | no_shards | ddz_cap | ddz_locked | ddz_account (a seat's save is not
  linked to a main-site account, on a server with accounts) | error; at an open table also disband (`by` the
  opener) | expired, and a seat let go at the start hears why its save may not play. Deposits taken went back.
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
- ``ddz_again`` {seat}: `seat` asks for another game; when the three have, the next ``ddz_deal`` follows (at an open
  table, ``ddz_open`` when it opens again instead).
- ``ddz_closed`` {}: the table is gone (the time ran out, or someone left it); at an open table, to the seat that
  stood up or put it away.
- ``ddz_state`` {...}: the whole game for a seat that came back (see Tables._state).

To the room: ``ddz_live`` {table, ids, on, gains?}: the three members started (on) or ended a game; `gains` are the
shards the winners won, by member id. A table the queue made tells every room its members are in.

The queue, with members whose client said `ddzMatch` only (`joined.features` then lists "ddz_match"):

- ``ddz_queue`` {base} from the member: wait at stake `base`, or at 0 stop waiting. Refused with ddz_locked |
  ddz_account | no_shards | ddz_cap | ddz_busy (at a table or invite) | ddz_queued (the save waits on another
  connection) | ddz_dnd | ddz_match_cooldown | rate_limited (within QUEUE_INTERVAL of the last time the save joined
  or moved, on any of its connections) | bad_message (not a stake).
- ``ddz_queue`` {base, waited?, reason?, retry?} to the member: it waits at `base`, for `waited` seconds so far;
  `base` null when it does not (cancelled, matched, out). `reason` says why the server took it out: ddz_locked |
  ddz_account | no_shards | ddz_cap | ddz_dnd | error, or ddz_match_cooldown with `retry`, the seconds until it may
  queue again (it declined a table of the queue, left it or let its time run out).
- ``ddz_waiting`` {counts: [[base, saves], ...]}: how many saves wait at each stake (stakes nobody waits at left out),
  to every member that queues, at most every COUNTS_SEC; on joining a room, the counts last sent, unless nobody
  waited then.

Open tables, with members whose client said `ddzMatch` only:

- ``ddz_open`` {base} from the member: open a table at stake `base` in the room. Refused with ddz_locked |
  ddz_account | no_shards | ddz_cap | ddz_busy (at a table or invite) | ddz_dnd | ddz_gone (not in the room) |
  rate_limited (the queue's QUEUE_INTERVAL, shared with it) | bad_message (not a stake).
- ``ddz_sit`` {table, seat?} from the member: sit down at the open table `table` of the room, at `seat` when it is
  empty, else at the first empty one. Refused as ``ddz_open``, and with ddz_gone when the table is not open in the
  room or no seat is empty.
- ``ddz_leave`` {table} from a seat of an open table: stand up; the opener's puts the table away. While the
  deposits are being taken (after ``ddz_open`` with `starting`) it is answered with ``ddz_closed`` at once and holds
  once they are.
- ``ddz_call`` {table, id} from the opener: call member `id` of the room to the table. Refused with ddz_gone (not
  the opener, or no seat empty) | no_member | ddz_target_locked | ddz_self | ddz_target_old (its client does not
  open tables) | ddz_target_busy | ddz_cooldown (called within RETRY_SEC). A member turning invites down is not
  called, and the opener is not told.
- ``ddz_call`` {table, from, base, deposit, sec, seats} to the member called: it may sit down (``ddz_sit``); `sec` is
  how long to show the call.
- ``ddz_open`` {table, base, deposit, you, seats: [{id, nick, character} | {pending} | null, ...], sec, starting?} to
  each seat of an open table whenever it changes: `you` is the seat, null an empty seat, {pending: true} one offered
  to a save of the queue, `sec` the time until it is put away; with `starting` the three seats are taken and the
  deposits are being taken (the deal, or the table waiting again, follows).
- ``ddz_tables`` {tables: [{table, base, seats}, ...]}: the open tables of the room, oldest first, seats as in
  ``ddz_open``; to its members whenever they change, at most every COUNTS_SEC, an empty list once the last goes; on
  joining the room, the list it was told last, unless it was told of none.
"""
from __future__ import annotations

import asyncio
import logging
import random
import secrets
import threading
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
# A save that declined a table of the queue, left it or let its time run out waits this long before it may queue
# again.
MATCH_RETRY_SEC = 60.0
# A save joins the queue or moves to another stake at most this often, over all its connections (each time reads the
# save); stopping is never held up.
QUEUE_INTERVAL = 1.0
# An open table not filled this long after it opened is put away.
OPEN_SEC = 600.0
# An empty seat of an open table that has waited this long is offered to the queue at the table's stake.
FILL_SEC = 60.0

OPEN, INVITE, STARTING, BID, PLAY, SETTLING, OVER, DONE = (
    "open", "invite", "starting", "bid", "play", "settling", "over", "done")


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
            return self._take(st, list(pids), base, deposit, day, now)

    def try_start(self, pids: list[str], base: int) -> tuple[int | None, list[str | None]]:
        """start for an open table: in one transaction, why each save of [pids] may not play, as its own asking
        would be told (see refusals); when none falls short, the deposits are taken and the game's id comes first,
        else nothing is taken and it is None."""
        deposit = self.deposit(base)
        with self.game.store.transaction() as st:
            now = self.game.now()
            day = day_of(now)
            codes: list[str | None] = []
            for pid in pids:
                try:
                    self._ready(st, [pid], deposit, day, now)
                    codes.append(None)
                except GameError as e:
                    codes.append(e.code)
            if any(codes):
                return None, codes
            return self._take(st, list(pids), base, deposit, day, now), codes

    @staticmethod
    def _take(st: Any, pids: list[str], base: int, deposit: int, day: str, now: float) -> int:
        for pid in pids:
            st.update_player(pid, shards=st.get_player(pid, now)["shards"] - deposit)
            st.add_ledger(pid, day, "ddz_deposit", -deposit)
        return st.add_ddz_game(pids, base, deposit, day, now)

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
    # At a table the queue made: when the save started waiting (Waiting.since, Waiting.seq), kept should it go back
    # to the line.
    since: float | None = None
    seq: int = 0
    # The seat came from the queue: its member takes it again from any room, as at a table the queue made.
    roam: bool = False
    # An empty seat of an open table (no save): since when it is empty.
    empty_since: float = 0.0
    # A seat of an open table offered to a save of the queue, not accepted yet: until when it may answer.
    until: float = 0.0

    @property
    def empty(self) -> bool:
        return not self.token

    @property
    def asked(self) -> bool:
        """Offered to a save of the queue that has not accepted yet (open tables)."""
        return bool(self.token) and not self.accepted


@dataclass(eq=False)
class Waiting:
    """A save in the queue: the connection it waits on, at which stake, and since when (the clock of Tables)."""
    peer: Peer
    base: int
    since: float
    # Order of joining the queue, among saves with the same `since`.
    seq: int = 0
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
    # Opened by seat 0 in its room for anyone of the room to sit down at (open tables), and since when it waits.
    open: bool = False
    opened_at: float = 0.0

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


class _Start:
    """The transaction that starts the game of an open table (Bank.try_start), run in a thread. Given up before it is
    done (Tables._take cancelled), it hands back what it took itself; given up after, drop returns the game to hand
    back."""

    def __init__(self, bank: Bank, pids: list[str], base: int) -> None:
        self.bank, self.pids, self.base = bank, pids, base
        self._lock = threading.Lock()
        self._dropped = False
        self._row: int | None = None

    def run(self) -> tuple[int | None, list[str | None]]:
        row, codes = self.bank.try_start(self.pids, self.base)
        with self._lock:
            self._row, dropped = row, self._dropped
        if dropped and row is not None:
            self.bank.refund(row)
        return row, codes

    def drop(self) -> int | None:
        """Gives the start up; returns the game whose deposits were taken already, None while the transaction runs
        (it then hands them back itself) or when it took nothing."""
        with self._lock:
            self._dropped = True
            return self._row


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
        # Save -> clock time from which it may queue again, after declining a table of the queue, leaving it or letting
        # it lapse.
        self.match_refused: dict[str, float] = {}
        # Save -> clock time it last joined the queue or moved in it (QUEUE_INTERVAL).
        self._queue_at: dict[str, float] = {}
        # Last Waiting.seq given out.
        self._seq = 0
        # The waiting counts last sent, when, and the timer of the next send.
        self._counts_sent: dict[int, int] = {}
        self._counts_at = float("-inf")
        self._counts_timer: Any = None
        # The open tables each room was told of last (rooms told of none left out), the rooms whose tables changed
        # since, when the rooms were last told, and the timer of the next telling (_tables_changed).
        self._tables_sent: dict[str, list[dict]] = {}
        self._tables_dirty: set[str] = set()
        self._tables_at = float("-inf")
        self._tables_timer: Any = None

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
        self._queue_at.clear()
        self._matching.clear()
        if self._counts_timer is not None:
            self._counts_timer.cancel()
            self._counts_timer = None
        self._counts_sent = {}
        self._counts_at = float("-inf")
        if self._tables_timer is not None:
            self._tables_timer.cancel()
            self._tables_timer = None
        self._tables_sent = {}
        self._tables_dirty = set()
        self._tables_at = float("-inf")

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
        if table is not None and seat is not None and table.phase == OPEN and table.seats[seat].asked:
            self._unseat_asked(table, seat, "declined")
            return
        if table is None or seat is None or table.phase != INVITE or table.seats[seat].accepted:
            return
        if table.match:
            self._end_match(table, "declined", by=peer)
        elif seat:
            self._end(table, "declined", by=peer, refused=[peer])

    async def answer(self, peer: Peer, table_id: str, accept: bool) -> None:
        open_table = self.by_id.get(table_id)
        if open_table is not None and open_table.open and open_table.phase == OPEN:
            await self._answer_seat(open_table, peer, accept)
            return
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

    # -------------------------------------------------------------- open tables
    def _check_seat(self, room_id: str, peer: Peer) -> None:
        """What keeps [peer] from opening a table in room [room_id] or sitting down at one there, its save's shards
        and taps aside (Bank.check)."""
        if not peer.ddz_match:
            raise GameError("bad_message", "join with ddzMatch to open tables")
        if not peer.token:
            raise GameError("ddz_locked", "")
        room = self.manager.rooms.get(room_id)
        if not peer.active or room is None or room.peers.get(peer.id) is not peer:
            raise GameError("ddz_gone", "")
        if peer.token in self.by_save:
            raise GameError("ddz_busy", "")
        if peer.dnd:
            raise GameError("ddz_dnd", "")

    def _open_table(self, room_id: str, table_id: str) -> Table:
        """The open table [table_id] of room [room_id], while it waits with a seat empty."""
        table = self.by_id.get(table_id)
        if (table is None or not table.open or table.phase != OPEN or table.room != room_id
                or not any(s.empty for s in table.seats)):
            raise GameError("ddz_gone", "")
        return table

    def _seat_for(self, peer: Peer, **kw: Any) -> Seat:
        return Seat(token=peer.token or "", peer=peer, id=peer.id, nick=peer.nick, character=peer.character,
                    **{"accepted": True, **kw})

    def _empty_seat(self) -> Seat:
        return Seat(token="", peer=None, id="", nick="", character="", empty_since=self.clock())

    async def open(self, room_id: str, peer: Peer, base: int) -> None:
        """[peer] opens a table at stake [base] in room [room_id] and takes seat 0. Members of the room sit down at
        it (sit); the third to sit starts the game (_begin)."""
        bank = self.bank
        if base not in bank.cfg()["stakes"]:
            raise GameError("bad_message", "unknown stake")
        self._check_seat(room_id, peer)
        self._limit(peer)
        deposit = await run_in_threadpool(bank.check, [peer.token], base)
        # It may have left, sat down elsewhere or turned invites down while the database was read.
        self._check_seat(room_id, peer)
        table = Table(id=secrets.token_hex(4), room=room_id, base=base, deposit=deposit, phase=OPEN, open=True,
                      opened_at=self.clock(), seats=[self._seat_for(peer), self._empty_seat(), self._empty_seat()])
        self.by_id[table.id] = table
        self.by_save[peer.token or ""] = table
        self._leave_queue(peer, save=True)
        self._open_changed(table)

    async def sit(self, room_id: str, peer: Peer, table_id: str, seat: int | None = None) -> None:
        """[peer] sits down at the open table [table_id] of room [room_id]: at [seat] when it is empty, else at the
        first empty one. Sitting is consent: the third to sit starts the game (_begin)."""
        self._check_seat(room_id, peer)
        table = self._open_table(room_id, table_id)
        self._limit(peer)
        await run_in_threadpool(self.bank.check, [peer.token], table.base)
        # Anything may have moved while the database was read, the last seat taken included.
        self._check_seat(room_id, peer)
        table = self._open_table(room_id, table_id)
        empty = [i for i, s in enumerate(table.seats) if s.empty]
        at = seat if seat in empty else empty[0]
        table.seats[at] = self._seat_for(peer)
        self.by_save[peer.token or ""] = table
        self._leave_queue(peer, save=True)
        if all(not s.empty and s.accepted for s in table.seats):
            self._begin(table)
        else:
            self._open_changed(table)

    def call(self, room_id: str, peer: Peer, table_id: str, target_id: str) -> None:
        """The opener of the open table [table_id] calls member [target_id] of the room to it (``ddz_call``); the
        member sits down with ``ddz_sit``. A member turning invites down is not called, and the opener is not told.
        The same save is called again only after RETRY_SEC."""
        table = self.by_id.get(table_id)
        if (table is None or not table.open or table.phase != OPEN or table.room != room_id
                or table.seat_of(peer) != 0 or not any(s.empty for s in table.seats)):
            raise GameError("ddz_gone", "")
        room = self.manager.rooms.get(room_id)
        target = room.peers.get(target_id) if room else None
        if target is None or not target.active:
            raise GameError("no_member", "no such member")
        if not target.token:
            raise GameError("ddz_target_locked", "")
        if target.token == peer.token:
            raise GameError("ddz_self", "")
        if not target.ddz_match:
            raise GameError("ddz_target_old", "")
        if target.token in self.by_save:
            raise GameError("ddz_target_busy", "")
        now = self.clock()
        key = (peer.token or "", target.token)
        if now < self.refused.get(key, 0.0):
            raise GameError("ddz_cooldown", "")
        self.refused = {k: t for k, t in self.refused.items() if t > now}
        self.refused[key] = now + RETRY_SEC
        if target.dnd:
            return
        target.enqueue({"type": "ddz_call", "table": table.id, "from": peer.id, "base": table.base,
                        "deposit": table.deposit, "sec": self.bank.cfg()["inviteSec"],
                        "seats": self._shown_seats(table)})

    def _shown_seats(self, table: Table) -> list[dict | None]:
        """The seats of an open table as its members see them: None for an empty one, {pending} for one offered to
        a save of the queue (who it is stays unsaid until it accepts)."""
        return [None if s.empty else {"pending": True} if s.asked else {"id": s.id, "nick": s.nick,
                                                                          "character": s.character}
                for s in table.seats]

    def _open_changed(self, table: Table) -> None:
        """Tells the seats of an open table how it stands, and times what comes next (_open_due); first, an empty
        seat due for the queue is offered (_fill)."""
        if self._fill(table):
            return  # told by _fill
        self._tell_open(table)
        self._tables_changed(table.room)
        self._schedule_open(table)

    def _tell_open(self, table: Table, **extra: Any) -> None:
        seats = self._shown_seats(table)
        sec = max(0.0, round(table.opened_at + OPEN_SEC - self.clock(), 1))
        for i, s in enumerate(table.seats):
            if s.peer is not None and s.accepted:
                s.peer.enqueue({"type": "ddz_open", "table": table.id, "base": table.base, "deposit": table.deposit,
                                "you": i, "seats": seats, "sec": sec, **extra})

    def _schedule_open(self, table: Table) -> None:
        """One timer for whatever comes first: the table's time running out, an offered seat's answer, or an empty
        seat becoming due for the queue (one already due waits for someone to queue)."""
        self._cancel_timer(table)
        table.step += 1
        step = table.step
        now = self.clock()
        times = [table.opened_at + OPEN_SEC] + [s.until for s in table.seats if s.asked]
        if not any(s.asked for s in table.seats):
            times += [t for s in table.seats if s.empty and (t := s.empty_since + FILL_SEC) > now]
        table.timer = self.timers.later(max(0.0, min(times) - now), lambda: self._open_due(table, step))

    async def _open_due(self, table: Table, step: int) -> None:
        if table.step != step or table.phase != OPEN:
            return
        now = self.clock()
        if now >= table.opened_at + OPEN_SEC:
            self._disband(table, "expired")
            return
        lapsed = next((i for i, s in enumerate(table.seats) if s.asked and now >= s.until), None)
        if lapsed is not None:
            self._unseat_asked(table, lapsed, "timeout")
        else:
            self._open_changed(table)

    def _fill(self, table: Table) -> bool:
        """Offers an empty seat of an open table that has waited FILL_SEC to the save that waited longest in the
        queue at the table's stake, one seat at a time: it leaves the queue and is asked as at a table the queue
        made (``ddz_invite``); the seats taken do not answer again. Returns whether it did (and told the table)."""
        if table.phase != OPEN or any(s.asked for s in table.seats):
            return False
        now = self.clock()
        at = next((i for i, s in enumerate(table.seats) if s.empty and now >= s.empty_since + FILL_SEC), None)
        if at is None:
            return False
        w = next((w for w in self.lines.get(table.base, [])
                  if w.token not in self.by_save and w.peer.active and not w.peer.dnd), None)
        if w is None:
            return False
        sec = self.bank.cfg()["inviteSec"]
        self._dequeue(w)
        table.seats[at] = self._seat_for(w.peer, accepted=False, roam=True, since=w.since, seq=w.seq,
                                         until=now + sec)
        self.by_save[w.token] = table
        w.peer.enqueue({"type": "ddz_invite", "table": table.id, "ids": [s.id for s in table.seats],
                        "base": table.base, "deposit": table.deposit, "sec": sec, "match": True,
                        "seats": [None if s.empty else {"id": s.id, "nick": s.nick, "character": s.character}
                                  for s in table.seats],
                        "accepted": [s.id for s in table.seats if not s.empty and s.accepted]})
        self._open_changed(table)
        return True

    def _fill_line(self, base: int) -> None:
        """The line of [base] grew: open tables at that stake with a seat due take from it, oldest table first."""
        for t in sorted((t for t in self.by_id.values() if t.open and t.phase == OPEN and t.base == base),
                        key=lambda t: (t.opened_at, t.id)):
            self._fill(t)

    async def _answer_seat(self, table: Table, peer: Peer, accept: bool) -> None:
        """A save of the queue answers the seat of an open table offered to it."""
        seat = table.seat_of(peer)
        if seat is None or not table.seats[seat].asked:
            raise GameError("ddz_gone", "")
        if not accept:
            self._unseat_asked(table, seat, "declined")
            return
        s = table.seats[seat]
        s.accepted, s.until = True, 0.0
        if all(not x.empty and x.accepted for x in table.seats):
            self._begin(table)
        else:
            self._open_changed(table)

    def _unseat_asked(self, table: Table, seat: int, reason: str) -> None:
        """The save asked to take seat [seat] declined it, let the time run out or left: as at a table the queue
        made, it may queue again only after MATCH_RETRY_SEC. The seat is offered to the next at once."""
        s = table.seats[seat]
        if self.by_save.get(s.token) is table:
            del self.by_save[s.token]
        now = self.clock()
        self.match_refused = {k: t for k, t in self.match_refused.items() if t > now}
        self.match_refused[s.token] = now + MATCH_RETRY_SEC
        if s.peer is not None:
            s.peer.enqueue({"type": "ddz_over", "table": table.id, "reason": reason})
            s.peer.enqueue({"type": "ddz_queue", "base": None, "reason": "ddz_match_cooldown",
                            "retry": MATCH_RETRY_SEC})
        table.seats[seat] = self._empty_seat()
        table.seats[seat].empty_since = now - FILL_SEC
        self._open_changed(table)

    def _stand(self, table: Table, seat: int) -> None:
        """Seat [seat] of an open table stands up: it is empty again, and its member hears the table is gone."""
        s = table.seats[seat]
        if self.by_save.get(s.token) is table:
            del self.by_save[s.token]
        if s.peer is not None:
            s.peer.enqueue({"type": "ddz_closed", "table": table.id})
        table.seats[seat] = self._empty_seat()
        self._open_changed(table)

    def _disband(self, table: Table, reason: str, by: Seat | None = None, quiet: frozenset[int] | set[int] = frozenset()
                 ) -> None:
        """Puts an open table away before its game: the seat [by] that did it hears the table is gone, the others
        why (seats in [quiet] nothing). Nothing was taken."""
        if table.phase == DONE:
            return
        table.phase = DONE
        self._drop(table)
        self._tables_changed(table.room)
        over: dict[str, Any] = {"type": "ddz_over", "table": table.id, "reason": reason}
        if by is not None:
            over["by"] = by.id
        for i, s in enumerate(table.seats):
            if s.peer is not None and i not in quiet:
                s.peer.enqueue({"type": "ddz_closed", "table": table.id} if s is by else over)
        # A save of the queue asked to sit down goes back to its place in the line.
        self._requeue(table.base, [s for s in table.seats if s.asked])

    def _room_tables(self, room_id: str) -> list[dict]:
        """The open tables of room [room_id] as its members see them, oldest first."""
        tables = sorted((t for t in self.by_id.values() if t.open and t.phase == OPEN and t.room == room_id),
                        key=lambda t: (t.opened_at, t.id))
        return [{"table": t.id, "base": t.base, "seats": self._shown_seats(t)} for t in tables]

    def _tables_changed(self, room_id: str | None) -> None:
        """The open tables of room [room_id] changed: its members hear them now, or COUNTS_SEC after the rooms were
        last told."""
        if room_id is None:
            return
        self._tables_dirty.add(room_id)
        if self._tables_timer is not None:
            return
        wait = self._tables_at + COUNTS_SEC - self.clock()
        if wait > 0:
            self._tables_timer = self.count_timers.later(wait, self._tables_due)
        else:
            self._send_tables()

    async def _tables_due(self) -> None:
        self._tables_timer = None
        self._send_tables()

    def _send_tables(self) -> None:
        """Tells the members of each room whose open tables changed, on clients that know of them, the room's open
        tables (``ddz_tables``), when they differ from what the room was told last; an empty list once the last goes."""
        dirty, self._tables_dirty = self._tables_dirty, set()
        told = False
        for room_id in sorted(dirty):
            room = self.manager.rooms.get(room_id)
            shown = self._room_tables(room_id) if room is not None else []
            if shown == self._tables_sent.get(room_id, []):
                continue
            if shown:
                self._tables_sent[room_id] = shown
            else:
                self._tables_sent.pop(room_id, None)
            if room is None:
                continue
            told = True
            msg = {"type": "ddz_tables", "tables": shown}
            for p in list(room.peers.values()):
                if p.ddz_match:
                    p.enqueue(msg)
        if told:
            self._tables_at = self.clock()

    def _begin(self, table: Table) -> None:
        """The three seats of an open table are taken: the deposits are taken and the cards dealt (_take) on a task of
        the table's own, so the connection of the last to sit goes on being read meanwhile."""
        table.phase = STARTING
        self._cancel_timer(table)
        self._tables_changed(table.room)
        # The full table, while the deposits are taken.
        self._tell_open(table, starting=True)
        self._spawn(self._take(table))

    async def _take(self, table: Table) -> None:
        """Takes the deposits of an open table in one transaction (Bank.try_start) and deals. A member that stood up,
        or left the room and is not back, by the time the transaction is done stood up before the start: what was
        taken goes back and the table waits again without it (_let_go). Who that is is settled then, once; one back
        later finds its seat given up. Should this task be cancelled, the table goes and the transaction, which runs
        on, hands back what it took (_Start)."""
        start = _Start(self.bank, [s.token for s in table.seats], table.base)
        loop = asyncio.get_running_loop()
        try:
            row, codes = await loop.run_in_executor(None, start.run)
        except asyncio.CancelledError:
            taken = start.drop()
            if taken is not None:
                loop.run_in_executor(None, self.bank.refund, taken)
            self._disband(table, "error")
            raise
        except Exception:
            # The transaction rolled back: nothing was taken.
            log.exception("ddz: taking the deposits at %s failed", table.id)
            self._disband(table, "error")
            return
        if table.phase != STARTING or self.by_id.get(table.id) is not table:
            if row is not None:
                await self._refund(row)
            return
        gone = [i for i, s in enumerate(table.seats) if s.peer is None or s.quit]
        if row is not None and not gone:
            table.row = row
            for s in table.seats:
                s.auto, s.timeouts = False, 0
            table.deal = 0
            await self._live(table, True)
            self._deal(table)
            return
        for i in gone:
            self._give_up(table, i)
        if row is not None:
            try:
                await self._refund(row)
            except asyncio.CancelledError:
                self._disband(table, "error")
                raise
        self._let_go(table, codes if row is None else [None, None, None])

    def _give_up(self, table: Table, seat: int) -> None:
        """Seat [seat] of an open table being started is given up: its save is free at once, and its member, back in
        the room, does not take it again."""
        s = table.seats[seat]
        if self.by_save.get(s.token) is table:
            del self.by_save[s.token]
        s.peer, s.quit = None, True

    async def _refund(self, row: int) -> None:
        """Hands the deposits of game [row] back, in a thread that goes on should the task awaiting it be cancelled."""
        await asyncio.get_running_loop().run_in_executor(None, self.bank.refund, row)

    def _let_go(self, table: Table, codes: list[str | None]) -> None:
        """After a start that fell short or was taken back: a seat whose save may no longer play hears why and is
        emptied, as is one whose member left meanwhile, and the table waits again; when the opener's is one of them,
        it goes."""
        gone = {i for i, (s, code) in enumerate(zip(table.seats, codes)) if code or s.peer is None or s.quit}
        for i in gone:
            s = table.seats[i]
            if codes[i] and s.peer is not None:
                s.peer.enqueue({"type": "ddz_over", "table": table.id, "reason": codes[i]})
        if 0 in gone:
            self._disband(table, "disband", by=table.seats[0], quiet=gone)
            return
        table.phase = OPEN
        table.row, table.deal, table.live_rooms = None, 0, set()
        for i, s in enumerate(table.seats):
            if i not in gone:
                s.again, s.hand, s.bid, s.plays, s.auto, s.timeouts = False, [], None, 0, False, 0
                continue
            if self.by_save.get(s.token) is table:
                del self.by_save[s.token]
            table.seats[i] = self._empty_seat()
        self._open_changed(table)

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
        if table.open and not self._gone(table.seats[0]):
            # An open table goes on without those who left: they are free now, and their seats empty on reopening.
            for s in table.seats:
                if self._gone(s):
                    self._let_seat_go(table, s)
        elif any(self._gone(s) for s in table.seats):
            self._close(table)
            return
        table.timer = self.timers.later(cfg["againSec"], lambda: self._again_expired(table))

    async def _again_expired(self, table: Table) -> None:
        if table.phase != OVER:
            return
        if table.open and table.seats[0].again:
            self._reopen(table)
        else:
            self._close(table)

    @staticmethod
    def _gone(s: Seat) -> bool:
        return s.peer is None or s.quit

    def _let_seat_go(self, table: Table, s: Seat) -> None:
        """After a game at an open table: the save of seat [s] is free again; the seat empties on reopening."""
        if self.by_save.get(s.token) is table:
            del self.by_save[s.token]
        s.quit, s.again = True, False

    def _reopen(self, table: Table) -> None:
        """After a game at an open table whose opener asked for another: those who asked keep their seats and the
        table is open again, with the same stake and rules; anyone else hears the table is gone."""
        self._cancel_timer(table)
        table.phase = OPEN
        table.row, table.deal, table.live_rooms, table.opened_at = None, 0, set(), self.clock()
        for i, s in enumerate(table.seats):
            if not self._gone(s) and s.again:
                s.again, s.hand, s.bid, s.plays, s.auto, s.timeouts = False, [], None, 0, False, 0
                continue
            if self.by_save.get(s.token) is table:
                del self.by_save[s.token]
            if not self._gone(s) and s.peer is not None:
                s.peer.enqueue({"type": "ddz_closed", "table": table.id})
            table.seats[i] = self._empty_seat()
        self._open_changed(table)

    def _reopen_due(self, table: Table) -> bool:
        """After a game at an open table: whether the opener and everyone still at the table asked for another,
        someone having left (all three asking start the next game instead)."""
        return (table.open and table.phase == OVER and table.seats[0].again
                and all(s.again for s in table.seats if not self._gone(s))
                and any(self._gone(s) for s in table.seats))

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
        if self._reopen_due(table):
            self._reopen(table)
            return
        if not all(x.again for x in table.seats):
            return
        if table.open:
            # As at the first start: one that may no longer play is let go and the table waits again, for as long
            # as a table just opened.
            table.opened_at = self.clock()
            self._begin(table)
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
        table, seat = self._table(peer, table_id, OPEN, STARTING, INVITE, BID, PLAY, OVER)
        if table.phase == STARTING and not table.open:
            raise GameError("ddz_gone", "")
        if table.phase == STARTING:
            # Standing up, or putting the table away, while the deposits are taken: it holds once they are (_take).
            peer.enqueue({"type": "ddz_closed", "table": table.id})
            self._give_up(table, seat)
        elif table.phase == OPEN:
            # The opener puts the table away; anyone else stands up, or declines the seat it was offered.
            if seat == 0:
                self._disband(table, "disband", by=table.seats[0])
            elif table.seats[seat].asked:
                self._unseat_asked(table, seat, "declined")
            else:
                self._stand(table, seat)
        elif table.phase == INVITE and table.match:
            self._end_match(table, "declined", by=peer)
        elif table.phase == INVITE:
            self._end(table, "gone" if seat == 0 else "declined", by=peer, refused=[peer] if seat else [])
        elif table.phase == OVER and table.open and seat:
            peer.enqueue({"type": "ddz_closed", "table": table.id})
            self._leave_over(table, seat)
        elif table.phase == OVER:
            self._close(table)
        else:
            self._quit(table, seat)

    def _leave_over(self, table: Table, seat: int) -> None:
        """After a game at an open table, seat [seat] (not the opener's) leaves: its save is free, and the table
        opens again once everyone still there asked for another."""
        s = table.seats[seat]
        self._let_seat_go(table, s)
        s.peer = None
        if self._reopen_due(table):
            self._reopen(table)

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
        if table.phase == OPEN:
            if seat == 0:
                self._disband(table, "disband", by=s)
            elif s.asked:
                # Leaving counts as declining, as at a table the queue made.
                self._unseat_asked(table, seat, "gone")
            else:
                self._stand(table, seat)
        elif table.phase == INVITE and table.match:
            self._end_match(table, "gone", by=peer)
        elif table.phase == INVITE:
            # An inviter leaving waits as after a refusal, so leaving and coming back cannot repeat the invite.
            self._end(table, "gone", by=peer, refused=[x.peer for x in table.seats[1:] if x.peer] if seat == 0 else [])
        elif table.phase == OVER and table.open and seat:
            self._leave_over(table, seat)
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
        has one at a table of this room (an open table's on a client that opens tables), or at a table the queue made
        (from any room, on a client that queues). Back while the deposits are being taken, it takes the seat and hears
        the deal like the others."""
        room = self.manager.rooms.get(room_id)
        if room is None or room.peers.get(peer.id) is not peer:
            return  # gone again before it got through joining
        table = self.by_save.get(peer.token) if peer.token else None
        seat = None
        if table is not None and table.phase in (OPEN, STARTING, BID, PLAY):
            # A seat of the queue is taken again from any room, on a client that queues; any other in the table's room,
            # on a client that opens tables when the table is an open one.
            mine = [i for i, s in enumerate(table.seats) if s.token == peer.token and not s.asked and (
                peer.ddz_match if table.match or s.roam
                else (peer.ddz_match if table.open else peer.ddz) and table.room == room_id)]
            seat = next((i for i in mine if table.seats[i].peer is None), None)
            if seat is None:
                # An older connection of the save still holds the seat: its leaving is not seen yet (a client back
                # on a new connection), or it is another device. The newest connection takes the seat; joins finish
                # in any order, so one that finishes late leaves a newer one there, unless that one is gone.
                seat = next((i for i in mine if (o := table.seats[i].peer) is not None and o is not peer
                             and (o.join_seq < peer.join_seq or not o.active)), None)
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
        # The same for the room's open tables.
        if peer.ddz_match and room_id in self._tables_sent:
            peer.enqueue({"type": "ddz_tables", "tables": self._tables_sent[room_id]})
        if seat is not None and table.phase == OPEN:
            self._open_changed(table)
        if seat is None or table.phase in (OPEN, STARTING):
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
        """The rooms that see the table: its own room (an invited or open table's), and the rooms the members of
        its seats of the queue are in now (one that walked away from the table included)."""
        rooms = {table.room} if table.room is not None else set()
        return rooms | {s.peer.room for s in table.seats
                        if s.peer is not None and s.peer.active and (table.match or s.roam)}

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
            self._limit(peer)
            await run_in_threadpool(bank.check, [peer.token], base)
            # It may have left, sat down or queued elsewhere while the database was read.
            self._check_queue(peer)
            held = self.waiting.get(peer.token)
        if held is not None and held.base == base:
            self._tell_queue(held)
            return
        if held is not None:
            self._dequeue(held, tell=False)
        self._seq += 1
        w = Waiting(peer, base, self.clock(), self._seq)
        self.waiting[w.token] = w
        self.lines.setdefault(base, []).append(w)
        self._tell_queue(w)
        self._counts_changed()
        self._fill_line(base)
        await self._match(base)

    def _limit(self, peer: Peer) -> None:
        """Reading a save to queue it, open a table or sit down at one: at most once per QUEUE_INTERVAL by save,
        counted before the database is read, so a new connection of the save, or a second one asking at the same
        time, is held up too."""
        now = self.clock()
        if now - self._queue_at.get(peer.token or "", float("-inf")) < QUEUE_INTERVAL:
            raise GameError("rate_limited", "too many requests")
        self._queue_at = {k: t for k, t in self._queue_at.items() if now - t < QUEUE_INTERVAL}
        self._queue_at[peer.token or ""] = now

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

    def _spawn(self, work: Any) -> asyncio.Task:
        """Runs [work] (matching, the start of an open table and its transactions) on the loop without awaiting it."""
        task = asyncio.get_running_loop().create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def idle(self) -> None:
        """Waits until nothing started by _spawn runs (tests); the first error of one, cancelling aside, is raised."""
        while self._tasks:
            done = await asyncio.gather(*list(self._tasks), return_exceptions=True)
            error = next((e for e in done if isinstance(e, BaseException) and not isinstance(e, asyncio.CancelledError)),
                         None)
            if error is not None:
                raise error

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
                    # Back in the line: a seat of an open table that came due while they were read goes to them.
                    self._fill_line(base)
        finally:
            self._matching.discard(base)

    def _form(self, base: int, three: list[Waiting]) -> None:
        """Seats [three] at a new table of no room and asks all three, as an invite does."""
        cfg = self.bank.cfg()
        deposit = self.bank.deposit(base)
        table = Table(id=secrets.token_hex(4), room=None, base=base, deposit=deposit, seats=[
            Seat(token=w.token, peer=w.peer, id=w.peer.id, nick=w.peer.nick, character=w.peer.character, since=w.since,
                 seq=w.seq)
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
        saves back from tables that fell through, in whatever order those did, stay ahead of those who came later.
        Saves that started waiting at the same time keep the order they joined in (Waiting.seq)."""
        line = self.lines.setdefault(base, [])
        back = sorted(entries, key=lambda x: (x.since, x.seq))
        merged: list[Waiting] = []
        i = j = 0
        while i < len(back) and j < len(line):
            if (back[i].since, back[i].seq) <= (line[j].since, line[j].seq):
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
            if s.since is not None:
                w = Waiting(p, base, s.since, s.seq)
            else:
                self._seq += 1
                w = Waiting(p, base, self.clock(), self._seq)
            self.waiting[w.token] = w
            back.append(w)
        if not back:
            return
        self._merge(base, back)
        for w in back:
            self._tell_queue(w)
        self._counts_changed()
        self._fill_line(base)
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
        # Invited saves that kept waiting in the queue may take a seat of an open table waiting for one, or be matched
        # again.
        for base in {w.base for s in table.seats if (w := self.waiting.get(s.token)) is not None}:
            self._fill_line(base)
            self._spawn(self._match(base))

    def _end_match(self, table: Table, reason: str, by: Peer | None = None) -> None:
        """Ends the invite of a table the queue made: the seat that declined or left ([by]), or every seat that let
        the time run out, is out of the queue, and may queue again only after MATCH_RETRY_SEC; the others go back
        into the line (_requeue)."""
        if table.phase == DONE:
            return
        if reason == "timeout":
            back = [s for s in table.seats if s.accepted]
            out = [s for s in table.seats if not s.accepted]
        else:
            back = [s for s in table.seats if s.peer is not by]
            # Leaving the room counts as declining: leaving and coming back would rematch the same two at once.
            out = [s for s in table.seats if s.peer is by]
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
