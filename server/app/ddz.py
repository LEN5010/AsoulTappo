"""Dou dizhu (斗地主) between three members of a room, played for shards.

One member invites two others at a base stake. When both accept, each pays a deposit (the most a landlord can lose),
the cards are dealt and the three bid for the landlord's seat, play, and are paid. The table, the hands and the timers
live in memory; the deposits and the outcome live in the database (ddz_games), which pays every game at most once
and hands the deposits of games a restart cut short back at startup.

A seat belongs to a save, not to a connection: a member who leaves the room mid-game is played for (by
ddz_rules.choose) and takes the seat again by joining the room with the same save. Two turns in a row left to run out
put a seat on the same autopilot until its member turns it off; a turn played for bids nothing.

The queue: a save waits for a table at one stake on a dou dizhu connection of its own (``ddz_hello``, Peer.lobby),
which is in no room, whether or not the save is in a room on another connection. The saves waiting at a stake form
one line, oldest first, kept in memory; when three in it may sit down together, they get a table that belongs to no
room, through the same invite, which all three have to accept. A save that declines, closes the connection or lets
the time run out is out of the queue, and may queue again only after MATCH_RETRY_SEC; the others go back into the line
where their wait puts them, ahead of anyone who came after them. Once all three accept, the game goes on as an invited
one; when the deposits cannot be taken, the three go back into the line, and one that may no longer play leaves it,
told why. A seat whose connection closes is played for, and a new dou dizhu connection of the save takes it again
(hello), as it takes over the save's place in the line from an older one. Closing the connection, turning invites down
(dnd, on any connection of the save), starting an invite, accepting one, or opening or sitting down at an open table
takes a save out of the queue.

Open tables: a member on a client that said `ddzMatch` opens a table at a stake in its room and takes seat 0; members
of the room sit down at its empty seats, and sitting is consent. The third to sit starts the game: the three deposits
go in one transaction, and a seat whose save may no longer play is let go, told why, while the table waits again (the
opener's puts it away). Before the start a member stands up by leaving the table or the room; the opener doing so puts
the table away, as does OPEN_SEC without the three seats taken. An empty seat that has waited FILL_SEC is offered to
the save that waited longest in the queue at the table's stake, one seat at a time; it accepts as at a table the queue
made (the seats taken do not answer again), plays on its dou dizhu connection and takes the seat again on a new one,
and one that declines, leaves or
lets the time run out may queue again only after MATCH_RETRY_SEC, the seat going to the next. Nothing is taken before
the start: one that leaves the table while the deposits are being taken, or leaves the room and is not back once they
are, gives them back and stands up (the opener puts the table away), as decided once they are taken; its save sits
nowhere else (ddz_busy) until they are back. A save of the queue that waits at a table put away before its first game
there goes back to its place in the line. After a game, those who ask for another keep their seats; when the opener did
and someone did not (or left), the table opens again with them, at the same stake and by the same rules, else it closes
as an invited one does.

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
- ``ddz_deal`` {seats: [{id, nick, character, plate?, auto, away}], you, hand, base, cap, deal, turn, sec, dealSec,
  counter?}: a deal (`plate` when one is worn, in every seat list); the clients deal the cards out over `dealSec`
  seconds, then `turn` bids first with `sec` seconds. `counter` {on, left}, where the card counter is sold: whether
  the seat's is on for this game and the games of it its save has left.
- ``ddz_bid`` {seat, bid, turn?, sec?}: a bid (0 passes); `turn` bids next when the bidding goes on.
- ``ddz_landlord`` {seat, bid, bottom, mult, turn, sec}: `seat` is the landlord, takes `bottom` and leads.
- ``ddz_play`` {seat, cards, left, mult, bombs, turn?, sec?, lead?}: a play ([] passes); `turn` plays next and leads
  when `lead`.
- ``ddz_seat`` {seat, id, away, auto, turn?, sec?, nick?, character?, plate?}: a seat's member left or came back
  (with a new member id, and its nick, pet and plate when the new connection shows others), or its autopilot changed;
  with `turn` the seat's turn starts over with `sec` seconds.
- ``ddz_result`` {winner: landlord | farmers, landlord, bid, bombs, spring: 0 | 1 spring | 2 counter-spring, mult,
  base, deltas, hands, sec}: paid; `hands` are the cards left in each seat, `sec` the time to ask for another game.
- ``ddz_again`` {seat}: `seat` asks for another game; when the three have, the next ``ddz_deal`` follows (at an open
  table, ``ddz_open`` when it opens again instead).
- ``ddz_closed`` {}: the table is gone (the time ran out, or someone left it); at an open table, to the seat that
  stood up or put it away.
- ``ddz_state`` {...}: the whole game for a seat that came back (see Tables._state).
- ``ddz_emote`` {seat, emote} (to the other seats, in any room): `seat` shows emote `emote` (``ddz_emote`` {table,
  emote} from the seat, owned and rate-limited as a room emote). A seat whose client does not say `ddzMatch` (1.2.5)
  hears it as the room's ``emote`` {id, emote} instead, sent to it alone, when both sit in the table's room.

The card counter (the client's count of the cards the other two seats still hold), where the economy sells it
(`doudizhu.counter`; elsewhere it is free and none of this is sent): a save holds games of it, and a seat's counter is
on for a game once one of them was used on it. That happens when the landlord is known, for every seat whose member is
at the table and whose save has a game left, and when a member with a game left comes back to its seat later.

- ``ddz_counter`` {table} from a seat, while the seats bid or play: turn the counter on. A save with no game left buys
  `games` of them for `coins` park coins first, a coin it lacks being bought with shards at the park's price.
- ``ddz_counter`` {table, on, left, error?} to that seat alone: its counter now, also sent unasked when it is turned
  on; `error` no_shards when the save could not pay, error when the purchase failed.

To the room: ``ddz_live`` {table, ids, on, base?, gains?}: the three members started (on) or ended a game; `base`
is the stake, with on only (clients before watching read table, ids, on and gains alone); `gains` are the shards the
winners won, by member id. The ids are the room's: a seat whose save is in the room on another connection
(a dou dizhu one) goes by that connection's member id. A table the queue made tells every room its seats' saves are
in. A room told of the start that none of the saves is in by the end hears only {table, on: false}.
``ddz_live_state`` {table, landlord, seats: [{left}], mult, watching} to the room's members whose client watches
(``join``'s ddzWatch), while a game it was told of is on: the landlord's seat (null while the seats bid), the cards
each seat has left, in the order of ``ddz_live``'s ids, the multiplier so far and how many watch it. Sent when the game is dealt and as bids and plays
change it, at most once every COUNTS_SEC, while such a member is in one of its rooms, and to such a member when it
joins.

The dou dizhu connection: ``ddz_hello`` {nick, character, token?, accountToken?, plate?, dnd?} as its first message,
checked as ``join`` is (refused with no_ddz on a server without the game); it may then send ``ddz_queue``, the moves
of its table, ``ddz_emote``, ``dnd``, ``state`` and ``leave``, anything else answered with not_joined.

- ``ddz_ready`` {you, base, waited?, table} to it: its member id; the stake its save waits at (taken over from an
  older connection of the save, `waited` seconds so far), null when it does not; the table whose seat it takes again,
  null for none (what it held there before is gone), the seat following (``ddz_state``, or ``ddz_open``).

The queue, on dou dizhu connections only (a room connection's ``ddz_queue`` is a bad_message):

- ``ddz_queue`` {base} from the connection: wait at stake `base`, or at 0 stop waiting. Refused with ddz_locked |
  ddz_account | no_shards | ddz_cap | ddz_busy (at a table or invite) | ddz_queued (the save waits on another
  connection) | ddz_dnd | ddz_match_cooldown | rate_limited (within QUEUE_INTERVAL of the last time the save joined
  or moved, on any of its connections) | bad_message (not a stake).
- ``ddz_queue`` {base, waited?, reason?, retry?} to the member: it waits at `base`, for `waited` seconds so far;
  `base` null when it does not (cancelled, matched, out). `reason` says why the server took it out: ddz_locked |
  ddz_account | no_shards | ddz_cap | ddz_dnd | error, or ddz_match_cooldown with `retry`, the seconds until it may
  queue again (it declined a table of the queue, left it or let its time run out).
- ``ddz_waiting`` {counts: [[base, saves], ...]}: how many saves wait at each stake (stakes nobody waits at left out),
  to every room member on a client that queues and every dou dizhu connection, at most every COUNTS_SEC; on joining
  a room or saying hello, the counts last sent, unless nobody waited then.

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

Watching, for room members whose client said `ddzMatch` and `ddzWatch` (``joined`` then lists "ddz_watch" in
`features`; a dou dizhu connection says `ddzWatch` in ``ddz_hello``, which only lets its seat be watched). A member
watches a game the room is told of (``ddz_live``, see Tables._rooms) once it is dealt, from one seat's side: the hand of
that seat is shown when the seat's client says `ddzWatch` too (Seat.watchable, the last connection that held the seat)
and the seat plays in the watcher's room (the table's own room and not a seat from the queue, or the seat's save is in
the room on any connection); the other two hands never are, nor the card counter. A watcher takes no seat and nothing
of its save: it queues, opens, sits and is invited as anyone else, and watches at most WATCH_MAX to a table.

- ``ddz_watch`` {table, seat?} from a room connection (a dou dizhu connection's is not_joined): watch `table` from
  seat `seat` (0 when left out); another seat or table replaces what the connection watched, a table "" stops
  watching (always, told nothing). At most once every WATCH_INTERVAL, stopping aside. Refused with ddz_gone (the
  table is not bidding, playing or paid, or the room does not see it) | ddz_busy (the save sits at the table, or at
  any table that is starting, bidding, playing or paid) | ddz_watch_full | rate_limited | bad_message (the client
  did not say `ddzMatch` and `ddzWatch`, or `seat` is not 0 to 2); a refusal leaves what it watched as it was.
- ``ddz_watch`` {table, seat, hand, phase, seats: [{id, nick, character, plate?, left, bid, auto, away, again}], base,
  cap, deal, bid, landlord, bottom, mult, bombs, turn, lead, trick, sec, of, result} to the watcher, on every
  ``ddz_watch`` that holds: the game as ``ddz_state`` has it, without `you`, `played` and `counter`; `hand` the
  seat's cards now, null when not shown; `result` the last ``ddz_result`` while the phase is over, else null.
- To the watchers as to the seats, with `watch` true: ``ddz_bid``, ``ddz_landlord``, ``ddz_play``, ``ddz_seat``,
  ``ddz_result``, ``ddz_again`` and ``ddz_emote``. Each deal comes to each watcher as ``ddz_deal`` {seats, hand, base,
  cap, deal, turn, sec, dealSec, watch}, without `you` and `counter`, `hand` the seat's 17 cards or null. Member ids
  (the seats of ``ddz_watch`` and ``ddz_deal``, ``ddz_seat``'s `id`) are those of the watcher's room (Tables._ids_in).
  The watcher keeps the seat's hand itself from then on: a ``ddz_play`` of the seat takes its cards out, the
  ``ddz_landlord`` of the seat adds `bottom`.
- ``ddz_watch_end`` {table, reason, over?} to the watcher: it watches no more, as the table closed (closed), opened
  again for players after the game (reopen), ended with nothing won or another game at it did not start (gone, with
  `over` the reason of the ``ddz_over`` the seats hear: nobid, gone, no_shards, ddz_cap, ddz_locked, ddz_account,
  error, ...), or the watcher's save is dealt in at a table (playing). Stopping, leaving the room and losing the connection end it
  without a word.
- ``ddz_watchers`` {table, faces: [{nick, character, seat}], you?}: who watches, oldest first, `seat` the seat whose
  hand each sees (null for none), and in a watcher's copy only `you`, its own place in `faces`; to the watchers and to
  the seats whose client says `ddzWatch` (one that quit aside),
  whenever it changes, at most every COUNTS_SEC, an empty list once the last goes; to a seat taken again (after its
  ``ddz_state``) at once while anyone watches.
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
from .park import COIN_BUY, Park
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
# Handing the deposits of an open table's start back failed (the database busy): tried again after each of these
# waits, in seconds; after the last the game is left open for the next start of the server (Bank.refund_open).
REFUND_RETRY_SEC = (0.5, 2.0)

OPEN, INVITE, STARTING, BID, PLAY, SETTLING, OVER, DONE = (
    "open", "invite", "starting", "bid", "play", "settling", "over", "done")
# Coin ledger source of the coins the card counter costs.
COUNTER = "ddz_counter"
# Watchers a table has at most (a watcher moving to another seat's hand is not a new one).
WATCH_MAX = 20
# A connection asks to watch at most this often (stopping is never held up).
WATCH_INTERVAL = 1.0
# The messages of a game its watchers hear as the seats do (Tables._show); anything else is never copied to them.
SHOWN = frozenset({"ddz_bid", "ddz_landlord", "ddz_play", "ddz_seat", "ddz_result", "ddz_again", "ddz_emote"})
# Of those, the ones that change the game as its rooms see it (``ddz_live_state``).
LIVE_CHANGES = frozenset({"ddz_bid", "ddz_landlord", "ddz_play"})


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

    def counter(self) -> dict[str, Any] | None:
        """What the card counter costs: {coins, games}. None where it is free."""
        return self.cfg().get("counter")

    def counters(self, pids: list[str]) -> list[int]:
        """The games of the card counter each save has left."""
        return self.game.store.ddz_counters(pids)

    def use_counter(self, pid: str) -> None:
        self.game.store.use_ddz_counter(pid)

    def buy_counter(self, pid: str) -> int:
        """Buys the card counter's games for its coins, spent as any coin of the park is (a stamp each, and the
        lottery's pool is fed). A coin the save lacks is bought with shards at the park's price first; no_shards when
        it cannot pay that. Returns the games the save has then."""
        c = self.counter()
        if not c:
            raise GameError("bad_message", "the card counter is not sold here")
        park = Park(lambda: self.game)
        with self.game.store.transaction() as st:
            now = self.game.now()
            day = day_of(now)
            p = st.get_player(pid, now)
            short = c["coins"] - p["coins"]
            if short > 0:
                cost = short * park.coin["price"]
                if p["shards"] < cost:
                    raise GameError("no_shards", "碎片不足")
                st.update_player(pid, shards=p["shards"] - cost, coins=p["coins"] + short)
                st.add_ledger(pid, day, COIN_BUY, -cost, short)
                st.add_coin_ledger(pid, day, "buy", short, short)
            park.spend(st, pid, c["coins"], COUNTER, now)
            left = st.get_player(pid, now)["ddz_counter"] + c["games"]
            st.update_player(pid, ddz_counter=left)
        return left

    def lobby(self, pid: str) -> dict[str, Any]:
        """What the lobby shows save [pid], in one transaction: each stake, its deposit and whether the save can pay
        it; today's net win, the cap and what is left of it; the taps it has and needs; whether it meets the account
        rule (require_account)."""
        cfg = self.cfg()
        with self.game.store.transaction() as st:
            now = self.game.now()
            taps = st.player_taps(pid) or 0
            shards = st.get_player(pid, now)["shards"]
            net = st.ddz_net(pid, day_of(now))
            account = not self.require_account or bool(st.account_for_player(pid))
        cap = cfg["dailyWinCap"]
        return {"tiers": [{"base": b, "deposit": self.deposit(b), "afford": shards >= self.deposit(b)}
                          for b in cfg["stakes"]],
                "net": net, "cap": cap, "left": max(0, cap - net), "taps": taps, "minTaps": cfg["minTaps"],
                "account": account}


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
    # The name plate its member wears (Peer.plate), shown at the table.
    plate: str | None = None
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
    # Taken again (Tables._retake) by a connection with another nick, pet or plate.
    restyled: bool = False
    # The nick as its member's client sent it (Peer.raw_nick), masked again into `nick` when the blocklist changes.
    raw: str = ""
    # The card counter, where it is sold: on for this game, the games of it the save has left (read when the game
    # starts, kept here while it sits), and whether a purchase is under way.
    counter: bool = False
    counter_left: int = 0
    buying: bool = False
    # The connection that held the seat last said `ddzWatch`: it shows who watches the seat, so watchers may be
    # shown its hand. Kept while the seat's member is away.
    watchable: bool = False

    @property
    def empty(self) -> bool:
        return not self.token

    @property
    def asked(self) -> bool:
        """Offered to a save of the queue that has not accepted yet (open tables)."""
        return bool(self.token) and not self.accepted


def _face(s: Seat) -> dict:
    """Who sits in seat [s], as the seats see it: the plate only when one is worn."""
    out = {"id": s.id, "nick": s.nick, "character": s.character}
    if s.plate:
        out["plate"] = s.plate
    return out


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
    # Every card played this deal, in order: the clients' count of the cards still out.
    played: list[int] = field(default_factory=list)
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
    # An invite's invited saves were waiting in the queue: their places, given back should no game come of it
    # (Tables._restore).
    held: list[Waiting] = field(default_factory=list)
    # Watching: the connections watching the game, by member id, each with the seat whose hand it looks at; the
    # last ``ddz_result`` of the game (for one that starts watching after it); and the watchers' faces as the table
    # was told them last (``ddz_watchers``), when, the timer of the next telling, and the member ids of the watchers
    # not told them yet (Tables._watchers_changed).
    watchers: dict[str, tuple[Peer, int]] = field(default_factory=dict)
    result: dict | None = None
    watch_sent: list[dict] = field(default_factory=list)
    watch_at: float = float("-inf")
    watch_timer: Any = None
    watch_owed: set[str] = field(default_factory=set)
    # The game as its rooms were told it last (``ddz_live_state``), when, and the timer of the next telling
    # (Tables._live_changed).
    live_sent: dict | None = None
    live_at: float = float("-inf")
    live_timer: Any = None

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
    """The transaction that starts a game, run in a thread: Bank.try_start for an open table, Bank.start ([strict],
    raising GameError) for an invited table or one the queue made. Given up before it is done (the task awaiting it
    cancelled), it hands back what it took itself; given up after, drop returns the game to hand back."""

    def __init__(self, bank: Bank, pids: list[str], base: int, strict: bool = False) -> None:
        self.bank, self.pids, self.base, self.strict = bank, pids, base, strict
        self._lock = threading.Lock()
        self._dropped = False
        self._row: int | None = None
        # The games of the card counter each save has left, read once the deposits are taken.
        self.lefts = [0] * len(pids)

    def run(self) -> tuple[int | None, list[str | None]]:
        if self.strict:
            row, codes = self.bank.start(self.pids, self.base), [None, None, None]
        else:
            row, codes = self.bank.try_start(self.pids, self.base)
        with self._lock:
            self._row, dropped = row, self._dropped
        if dropped and row is not None:
            self.bank.refund(row)
        elif row is not None and self.bank.counter():
            try:
                self.lefts = self.bank.counters(self.pids)
            except Exception:
                # The game starts all the same, the counters off.
                log.exception("ddz: reading the card counters failed")
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
        # The dou dizhu connections (Peer.lobby), by member id: they queue, and hear the waiting counts.
        self.lobby: dict[str, Peer] = {}
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
            self._end_watch(table, None)
            self._drop(table)
        self.refused.clear()
        self.lobby.clear()
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

    def _quiet_saves(self) -> set[str]:
        """The saves turning invites down: those with any connection, a room's or a dou dizhu one, that does."""
        out = {p.token for p in self.lobby.values() if p.active and p.dnd and p.token}
        for room in self.manager.rooms.values():
            out |= {p.token for p in room.peers.values() if p.active and p.dnd and p.token}
        return out

    def _quiet(self, token: str | None) -> bool:
        return bool(token) and token in self._quiet_saves()

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
            Seat(token=p.token, peer=p, id=p.id, nick=p.nick, character=p.character, plate=p.plate, accepted=p is peer,
                 raw=p.raw_nick, watchable=p.ddz_watch)
            for p in peers])
        self.by_id[table.id] = table
        for p in peers:
            self.by_save[p.token] = table
        # Inviting takes the inviter out of the queue.
        self._leave_queue(peer, save=True)
        invited = {"type": "ddz_invite", "table": table.id, "from": peer.id, "ids": [p.id for p in peers],
                   "base": base, "deposit": deposit, "sec": cfg["inviteSec"]}
        quiet = [p for p in peers[1:] if p.dnd or self._quiet(p.token)]
        if quiet:
            # Turned down for the member, who never sees it; the inviter hears a plain refusal.
            peer.enqueue(invited)
            self._end(table, "declined", by=quiet[0], refused=quiet, tell=(peer,))
            return
        # A save holds one place at a time: the invited leave the queue while the invite is out, and get their places
        # back should no game come of it (_end).
        for p in peers[1:]:
            w = self.waiting.get(p.token)
            if w is not None:
                self._dequeue(w)
                table.held.append(w)
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
        # Any connection of the save turning invites down takes the save out of the queue, a place an invite holds for
        # it too, and turns down what waits for the save's answer, on whichever connection it was asked.
        self._leave_queue(peer, reason="ddz_dnd", save=True)
        if not peer.token:
            return
        self._drop_held(peer.token)
        table = self.by_save.get(peer.token)
        seat = next((i for i, s in enumerate(table.seats) if s.token == peer.token), None) if table else None
        if table is None or seat is None:
            return
        s = table.seats[seat]
        if table.phase == OPEN and s.asked:
            self._unseat_asked(table, seat, "declined")
            return
        if table.phase != INVITE or s.accepted or s.peer is None:
            return
        if table.match:
            self._end_match(table, "declined", by=s.peer)
        elif seat:
            self._end(table, "declined", by=s.peer, refused=[s.peer])

    def _drop_held(self, token: str) -> None:
        """The place in the queue an invite holds for save [token] (Table.held) is given up."""
        table = self.by_save.get(token)
        if table is not None and table.held:
            table.held = [w for w in table.held if w.token != token]

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
        if peer.dnd or self._quiet(peer.token):
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
                    plate=peer.plate, raw=peer.raw_nick, watchable=peer.ddz_watch,
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
        if target.dnd or self._quiet(target.token):
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
        quiet = self._quiet_saves()
        w = next((w for w in self.lines.get(table.base, [])
                  if w.token not in self.by_save and w.peer.active and not w.peer.dnd and w.token not in quiet), None)
        if w is None:
            return False
        sec = self.bank.cfg()["inviteSec"]
        self._dequeue(w)
        table.seats[at] = self._seat_for(w.peer, accepted=False, roam=True, since=w.since, seq=w.seq,
                                         until=now + sec)
        self.by_save[w.token] = table
        w.peer.enqueue({"type": "ddz_invite", "table": table.id, "ids": [s.id for s in table.seats],
                        "base": table.base, "deposit": table.deposit, "sec": sec, "match": True,
                        "seats": [None if s.empty else _face(s) for s in table.seats],
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
        # The saves of the queue go back to their places in the line: one asked to sit down, and one that sat here
        # waiting for the others (a game at the table ends its wait: _take).
        self._requeue(table.base, [s for i, s in enumerate(table.seats) if s.since is not None and i not in quiet])

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
        taken goes back and the table waits again without it (_let_go). Who that is is settled then, once (_here);
        one back later finds its seat given up, and its save is held until what was taken is back. Should this task be
        cancelled, the table goes and the transaction, which runs on, hands back what it took (_Start); what a stop
        of the server leaves taken, its next start hands back (Bank.refund_open)."""
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
        gone = [i for i, s in enumerate(table.seats) if not self._here(table, s)]
        if row is not None and not gone:
            table.row = row
            for s, left in zip(table.seats, start.lefts):
                s.auto, s.timeouts = False, 0
                s.counter, s.counter_left = False, left
                # A seat of the queue got its game: should the table open again and be put away, its save does not
                # go back to the line (_disband).
                s.since = None
            table.deal = 0
            await self._live(table, True)
            self._deal(table)
            return
        for i in gone:
            self._give_up(table, i)
        if row is not None:
            try:
                back = await self._refund(row)
            except asyncio.CancelledError:
                self._disband(table, "error")
                raise
            if not back:
                # The game stays open with the deposits taken: the next start of the server hands them back. The
                # table goes, and the saves are free.
                self._disband(table, "error")
                return
        self._let_go(table, codes if row is None else [None, None, None])

    def _here(self, table: Table, s: Seat) -> bool:
        """Whether the member of seat [s] of an open table is there for its start: it did not stand up, and its
        connection is still in the room (any room for a seat of the queue). A connection that left is out of the room
        before the tables hear of it (departed), which may be later."""
        p = s.peer
        if p is None or s.quit or not p.active:
            return False
        if s.roam:
            return True
        room = self.manager.rooms.get(table.room or "")
        return room is not None and room.peers.get(p.id) is p

    def _give_up(self, table: Table, seat: int) -> None:
        """Seat [seat] of an open table being started is given up: its member is off it and, back in the room, does
        not take it again (joined). The save stays held (by_save) until what may have been taken from it is back; the
        table lets it go then (_let_go)."""
        s = table.seats[seat]
        s.peer, s.quit = None, True

    async def _refund(self, row: int) -> bool:
        """Hands the deposits of game [row] back, in a thread that goes on should the task awaiting it be cancelled.
        A failure is tried again after each of REFUND_RETRY_SEC; returns False when the last try failed too, the game
        then still open with its deposits taken (Bank.refund moves them and closes the game in one transaction)."""
        loop = asyncio.get_running_loop()
        for wait in (*REFUND_RETRY_SEC, None):
            try:
                await loop.run_in_executor(None, self.bank.refund, row)
                return True
            except Exception:
                log.exception("ddz: handing back the deposits of game %s failed", row)
                if wait is None:
                    return False
                await asyncio.sleep(wait)
        return False

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
        # Watchers of the game before (another game asked for) stop: the table waits for players again.
        self._end_watch(table, "reopen")
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
    async def _start(self, table: Table, again: bool = False) -> None:
        """Takes the deposits of an invited table or one the queue made and deals ([again]: another game at it). The
        work runs on a task of the table's own (_open_game), so a cancelled connection handler (the last to accept,
        or to ask for another game) cannot leave deposits taken with nobody dealing; the handler waits for it."""
        table.phase = STARTING
        self._cancel_timer(table)
        task = self._spawn(self._open_game(table, again))
        task.add_done_callback(lambda t: self._start_stopped(table) if t.cancelled() else None)
        await asyncio.shield(task)

    def _start_stopped(self, table: Table) -> None:
        """_open_game's task was cancelled where it does not settle the table itself (before it ran, or while it told
        the rooms of the game): a table still starting ends, its deposits handed back when they were taken."""
        if table.phase != STARTING or self.by_id.get(table.id) is not table:
            return
        if table.row is None:
            self._end(table, "error")
            return
        table.phase = SETTLING
        self._spawn(self._settle_abort(table, "error"))

    async def _open_game(self, table: Table, again: bool) -> None:
        """_start's task. The members may leave while the database works: they are played for. Should the task be
        cancelled, the table ends and the transaction, which runs on, hands back what it took (_Start)."""
        start = _Start(self.bank, [s.token for s in table.seats], table.base, strict=True)
        loop = asyncio.get_running_loop()
        try:
            row, _ = await loop.run_in_executor(None, start.run)
        except asyncio.CancelledError:
            taken = start.drop()
            if taken is not None:
                loop.run_in_executor(None, self.bank.refund, taken)
            self._end(table, "error")
            raise
        except GameError as e:
            code = {"ddz_target_poor": "no_shards", "ddz_target_cap": "ddz_cap",
                    "ddz_target_locked": "ddz_locked", "ddz_target_account": "ddz_account"}.get(e.code, e.code)
            self._fell_short(table, code, again)
            return
        except Exception:
            # The transaction rolled back: nothing was taken.
            log.exception("ddz: taking the deposits at %s failed", table.id)
            self._fell_short(table, "error", again)
            return
        if table.phase != STARTING or self.by_id.get(table.id) is not table:
            # The table went while the deposits were taken (the server cleared its tables).
            if row is not None:
                await self._refund(row)
            return
        table.row = row
        if all(s.peer is None for s in table.seats):
            # All three left while the deposits were taken: nobody to play for. The invited saves get their places in
            # the queue back once the deposits are (_settle_abort).
            await self._abort(table, "gone")
            return
        # A game comes of the invite: the invited saves' places in the queue are gone.
        table.held = []
        if again:
            for x in table.seats:
                x.auto, x.timeouts = x.peer is None, 0
        for x, left in zip(table.seats, start.lefts):
            x.counter, x.counter_left = False, left
        table.deal = 0
        await self._live(table, True)
        self._deal(table)

    def _fell_short(self, table: Table, reason: str, again: bool) -> None:
        """The deposits of an invited table or one the queue made could not be taken: it ends. The saves of a table
        the queue made go back to their places in the line; the one that may no longer play leaves it there, told why
        (_match). After a game at the table ([again]) their wait is over."""
        self._end(table, reason)
        if table.match and not again:
            self._requeue(table.base, table.seats)

    def _deal(self, table: Table) -> None:
        # A save of the table watching a game anywhere plays now instead.
        self._unwatch_saves({s.token for s in table.seats if s.token}, "playing")
        deck = list(rules.DECK)
        self.rng.shuffle(deck)
        table.deal += 1
        table.phase = BID
        table.result = None
        table.bottom = sorted(deck[51:])
        table.bid, table.bidder, table.bids_made, table.landlord = 0, None, 0, None
        table.last, table.trick, table.bombs = None, [None, None, None], 0
        table.played = []
        for i, s in enumerate(table.seats):
            s.hand = sorted(deck[i * 17:(i + 1) * 17])
            s.bid, s.plays, s.again = None, 0, False
        first = self.rng.randrange(3)
        sec = self._give_turn(table, first, self.bank.cfg()["bidSec"], wait=DEAL_SEC)
        seats = [{**_face(s), "auto": s.auto, "away": s.peer is None or s.quit} for s in table.seats]
        cfg = self.bank.cfg()
        for i, s in enumerate(table.seats):
            if s.peer is not None and not s.quit:
                s.peer.enqueue({"type": "ddz_deal", "table": table.id, "seats": seats, "you": i, "hand": s.hand,
                                "base": table.base, "cap": cfg["capMult"], "deal": table.deal, "turn": first,
                                "sec": sec, "dealSec": DEAL_SEC, **self._counter(s)})
        # Each watcher its own: the seats by the member ids its room knows, the hand of the seat it looks at.
        for peer, at in list(table.watchers.values()):
            ids = self._watch_ids(table, peer)
            peer.enqueue({"type": "ddz_deal", "table": table.id,
                          "seats": [{**x, "id": i} for x, i in zip(seats, ids)],
                          "hand": self._hand_for(table, at, peer), "base": table.base, "cap": cfg["capMult"],
                          "deal": table.deal, "turn": first, "sec": sec, "dealSec": DEAL_SEC, "watch": True})
        self._live_changed(table)

    def _counter(self, s: Seat) -> dict:
        """A seat's card counter as its own messages carry it; nothing where the counter is free."""
        return {"counter": {"on": s.counter, "left": s.counter_left}} if self.bank.counter() else {}

    def _counter_on(self, table: Table, s: Seat) -> bool:
        """Turns the card counter of seat [s] on for the game being played, using one of its save's games: only
        for a member at the table on a client that shows the counter (one that said ``ddzMatch``; 1.2.5 has no
        counter), and once a game. The seat is told; the game used is written down on a task of its own, the table
        not waiting for it."""
        if (s.counter or s.counter_left < 1 or s.peer is None or not s.peer.ddz_match or s.quit
                or table.phase != PLAY or not self.bank.counter()):
            return False
        s.counter, s.counter_left = True, s.counter_left - 1
        self._spawn(self._use_counter(s.token))
        s.peer.enqueue({"type": "ddz_counter", "table": table.id, **self._counter(s)["counter"]})
        return True

    async def _use_counter(self, pid: str) -> None:
        try:
            await run_in_threadpool(self.bank.use_counter, pid)
        except Exception:
            log.exception("ddz: writing down a game of the card counter failed")

    async def counter(self, peer: Peer, table_id: str) -> None:
        """A member turns its seat's card counter on. A save with no game of it left buys its games first
        (Bank.buy_counter); while the seats still bid, the game is used once the landlord is known. Answered with
        ``ddz_counter``, with `error` when nothing was bought."""
        table, seat = self._table(peer, table_id, BID, PLAY)
        bank = self.bank
        if not bank.counter():
            raise GameError("bad_message", "the card counter is not sold here")
        s = table.seats[seat]
        if s.buying:
            return
        error = None
        if not s.counter and s.counter_left < 1:
            s.buying = True
            try:
                s.counter_left = await run_in_threadpool(bank.buy_counter, s.token)
            except GameError as e:
                error = e.code
            except Exception:
                log.exception("ddz: buying the card counter at %s failed", table.id)
                error = "error"
            finally:
                s.buying = False
            if self.by_id.get(table.id) is not table or table.seats[seat] is not s:
                # The table went meanwhile: the games bought are the save's for its next one.
                return
        if not self._counter_on(table, s) and s.peer is not None:
            s.peer.enqueue({"type": "ddz_counter", "table": table.id, **self._counter(s)["counter"],
                            **({"error": error} if error else {})})

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
        said = {"type": "ddz_seat", "table": table.id, "seat": seat, "id": s.id, "away": s.peer is None, "auto": s.auto}
        table.tell(said)
        self._show(table, said)

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
            self._show(table, said)
            return
        table.tell(said)
        self._show(table, said)
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
        # Before the landlord is told: the counter is on by the time the client shows the play.
        for x in table.seats:
            self._counter_on(table, x)
        said = {"type": "ddz_landlord", "table": table.id, "seat": lord, "bid": table.bid, "bottom": table.bottom,
                "mult": table.mult(cfg["capMult"]), "turn": lord, "sec": sec}
        table.tell(said)
        self._show(table, said)

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
            table.played.extend(cards)
            table.bombs += rules.bombs(cards)
            table.last = (seat, cards)
        table.trick[seat] = cards
        said = {"type": "ddz_play", "table": table.id, "seat": seat, "cards": cards, "left": len(s.hand),
                "mult": table.mult(cfg["capMult"]), "bombs": table.bombs}
        if not s.hand:
            table.tell(said)
            self._show(table, said)
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
        self._show(table, said)

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
        table.result = {"type": "ddz_result", "table": table.id, "winner": "landlord" if landlord_won else "farmers",
                        "landlord": lord, "bid": table.bid, "bombs": table.bombs, "spring": spring, "mult": mult,
                        "base": table.base, "deltas": deltas, "hands": [s.hand for s in table.seats],
                        "sec": cfg["againSec"]}
        table.tell(table.result, quit=True)
        self._show(table, table.result)
        await self._live(table, False, deltas=deltas)
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
        self._end_watch(table, "reopen")
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
        """Ends a game whose deposits are taken with nothing won: they go back. That runs on a task of its own
        (_settle_abort), which the caller's cancellation does not stop; the caller waits for it."""
        table.phase = SETTLING
        self._cancel_timer(table)
        await asyncio.shield(self._spawn(self._settle_abort(table, reason)))

    async def _settle_abort(self, table: Table, reason: str) -> None:
        """_abort's task: hands the deposits back (_refund, tried again on failure), then lets the three saves go and
        tells the seats and the rooms. When every try failed, or the task is cancelled, the saves are let go all the
        same and the game stays open in the database: the next start of the server hands its deposits back
        (Bank.refund_open)."""
        try:
            if table.row is not None and not await self._refund(table.row):
                log.error("ddz: game %s keeps its deposits until the next start", table.row)
        finally:
            table.phase = DONE
            self._end_watch(table, "gone", over=reason)
            self._drop(table)
            table.tell({"type": "ddz_over", "table": table.id, "reason": reason}, quit=True)
            held, table.held = table.held, []
            self._restore(held)
            self._spawn(self._live(table, False))

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
        self._show(table, said)

    async def again(self, peer: Peer, table_id: str) -> None:
        table, seat = self._table(peer, table_id, OVER)
        s = table.seats[seat]
        if s.again:
            return
        s.again = True
        said = {"type": "ddz_again", "table": table.id, "seat": seat}
        table.tell(said)
        self._show(table, said)
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
        await self._start(table, again=True)

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
        said = {"type": "ddz_seat", "table": table.id, "seat": seat, "id": s.id, "away": True, "auto": True}
        table.tell(said)
        self._show(table, said)
        if table.turn == seat and table.phase in (BID, PLAY):
            self._give_turn(table, seat, AUTO_SEC)

    async def departed(self, room_id: str, peer: Peer) -> None:
        """A member left the room (leave, kick, lost connection): it stops waiting in the queue, an invite is dropped,
        a seat in a game is played for until its save comes back. A connection watching a game stops, told nothing;
        whether watchers elsewhere may see a seat's hand may have changed."""
        self._unwatch(peer)
        self._rooms_changed()
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
            said = {"type": "ddz_seat", "table": table.id, "seat": seat, "id": s.id, "away": True, "auto": s.auto}
            table.tell(said)
            self._show(table, said)
            if table.turn == seat:
                self._give_turn(table, seat, AUTO_SEC)

    async def joined(self, room_id: str, peer: Peer) -> None:
        """A member joined the room: it hears of the games under way there, and takes its seat again if its save
        has one at an invited or open table of this room (an open table's on a client that opens tables). A seat of a
        table the queue made, or one an open table took from the queue, is taken again on a dou dizhu connection
        instead (hello). Back while the deposits are being taken, it takes the seat and hears the deal like the
        others."""
        room = self.manager.rooms.get(room_id)
        if room is None or room.peers.get(peer.id) is not peer:
            return  # gone again before it got through joining
        table = self.by_save.get(peer.token) if peer.token else None
        seat = self._mine(table, peer, lambda t, s: not (t.match or s.roam) and t.room == room_id and (
            peer.ddz_match if t.open else peer.ddz))
        handoff = self._retake(table, seat, peer) if table is not None and seat is not None else False
        self._rooms_changed()
        for live in list(self.by_id.values()):
            if live.phase not in (BID, PLAY, SETTLING):
                continue
            if peer.token and any(x.token == peer.token for x in live.seats):
                # The save plays there: every room of the table hears its new member id (this room the first time,
                # should the save have played from no room till now).
                await self._live(live, True)
            elif room_id in self._rooms(live):
                live.live_rooms.add(room_id)
                peer.enqueue({"type": "ddz_live", "table": live.id, "ids": self._ids_in(room, live), "on": True,
                              "base": live.base})
                if peer.ddz_watch and live.phase in (BID, PLAY):
                    peer.enqueue(self._live_state_msg(live))
        # The counts the others were sent last: a change since then is on its way to everyone (_counts_changed), the
        # newcomer included, which a send of the counts as they are now could leave behind.
        if peer.ddz_match and self._counts_sent:
            peer.enqueue(self._counts_msg(self._counts_sent))
        # The same for the room's open tables.
        if peer.ddz_match and room_id in self._tables_sent:
            peer.enqueue({"type": "ddz_tables", "tables": self._tables_sent[room_id]})
        if table is not None and seat is not None:
            self._back(table, seat, peer, handoff)

    def _mine(self, table: Table | None, peer: Peer, fits: Callable[[Table, Seat], bool]) -> int | None:
        """The seat of [table] that [peer] takes again: one of its save's that [fits], free, or held by an older
        connection of the save (or one that is gone). A seat given up while the deposits are taken stays given up."""
        if table is None or table.phase not in (OPEN, STARTING, BID, PLAY):
            return None
        mine = [i for i, s in enumerate(table.seats) if s.token == peer.token and not s.asked
                and not (s.quit and table.phase == STARTING) and fits(table, s)]
        seat = next((i for i in mine if table.seats[i].peer is None), None)
        if seat is None:
            # An older connection of the save still holds the seat: its leaving is not seen yet (a client back on a
            # new connection), or it is another device. The newest connection takes the seat; joins finish in any
            # order, so one that finishes late leaves a newer one there, unless that one is gone.
            seat = next((i for i in mine if (o := table.seats[i].peer) is not None and o is not peer
                         and (o.join_seq < peer.join_seq or not o.active)), None)
        return seat

    def _retake(self, table: Table, seat: int, peer: Peer) -> bool:
        """[peer] takes seat [seat] of [table]; returns whether it took it from a connection that played the seat
        itself, the seat then going on as it was, its turn included."""
        s = table.seats[seat]
        handoff = s.peer is not None and not s.auto
        if s.peer is not None and s.peer is not peer:
            # The old connection lets go of the table; its leaving, seen later, finds no seat of its own.
            s.peer.enqueue({"type": "ddz_closed", "table": table.id})
        face = (s.nick, s.character, s.plate)
        s.peer, s.id, s.nick, s.character, s.plate = peer, peer.id, peer.nick, peer.character, peer.plate
        s.raw, s.watchable = peer.raw_nick, peer.ddz_watch
        # The others hear the seat's new face with its new member id (_back).
        s.restyled = face != (s.nick, s.character, s.plate)
        if not handoff:
            s.auto, s.timeouts, s.quit = False, 0, False
        return handoff

    def _back(self, table: Table, seat: int, peer: Peer, handoff: bool) -> None:
        """Tells the table, and [peer] itself, that [peer] took seat [seat] again (_retake)."""
        if table.phase == OPEN:
            self._open_changed(table)
        if table.phase in (OPEN, STARTING):
            return
        s = table.seats[seat]
        msg = {"type": "ddz_seat", "table": table.id, "seat": seat, "id": s.id, "away": False, "auto": False}
        if s.restyled:
            msg.update({"nick": s.nick, "character": s.character, "plate": s.plate})
        if table.turn == seat:
            cfg = self.bank.cfg()
            msg["turn"] = seat
            if handoff:
                # A fresh time on each handoff would let two devices hold the other two up for good.
                msg["sec"] = max(0.0, round(table.deadline - self.clock(), 1))
            else:
                msg["sec"] = self._give_turn(table, seat, cfg["bidSec"] if table.phase == BID else cfg["playSec"])
        table.tell(msg, but=seat)
        self._show(table, msg)
        # A game of the counter the save has left is used now, should the landlord have been found without it.
        self._counter_on(table, s)
        peer.enqueue(self._state(table, seat))
        # Whether watchers may see the seat's hand may have changed with its connection; the member hears who watches
        # at once.
        if table.watchers and peer.ddz_watch:
            peer.enqueue(self._watchers_msg(table, self._faces(table)))
        self._watchers_changed(table)

    # ------------------------------------------------------- dou dizhu connections
    async def hello(self, peer: Peer) -> None:
        """A dou dizhu connection (Peer.lobby) said hello: it hears ``ddz_ready``, takes over the save's place in the
        queue from an older connection of the save, takes its seat again at a table the queue made or at the seat an
        open table took from the queue, and hears the waiting counts."""
        self.lobby[peer.id] = peer
        held = self.waiting.get(peer.token) if peer.token else None
        if held is not None and held.peer is not peer and held.peer.lobby and (
                held.peer.join_seq < peer.join_seq or not held.peer.active):
            if peer.dnd:
                self._dequeue(held)
                held = None
            else:
                old, held.peer = held.peer, peer
                old.enqueue({"type": "ddz_queue", "base": None})
        elif held is not None and held.peer is not peer:
            held = None
        table = self.by_save.get(peer.token) if peer.token else None
        asked = self._asked_of(table, peer)
        seat = asked if asked is not None else self._mine(table, peer, lambda t, s: t.match or s.roam)
        ready: dict[str, Any] = {"type": "ddz_ready", "you": peer.id, "base": held.base if held else None,
                                 "table": table.id if table is not None and seat is not None else None}
        if held is not None:
            ready["waited"] = round(max(0.0, self.clock() - held.since), 1)
        peer.enqueue(ready)
        if self._counts_sent:
            peer.enqueue(self._counts_msg(self._counts_sent))
        if table is None or seat is None:
            return
        if asked is not None:
            self._hand_over_asked(table, seat, peer)
            return
        handoff = self._retake(table, seat, peer)
        self._back(table, seat, peer, handoff)

    def _asked_of(self, table: Table | None, peer: Peer) -> int | None:
        """The seat [peer]'s save is still being asked to take, on an older dou dizhu connection: at a table the
        queue made that waits for its answers, or the seat of an open table offered to it from the queue."""
        if table is None:
            return None
        for i, s in enumerate(table.seats):
            o = s.peer
            if s.token != peer.token or o is None or o is peer or not o.lobby or not (
                    o.join_seq < peer.join_seq or not o.active):
                continue
            if (table.phase == INVITE and table.match) or (table.phase == OPEN and s.asked):
                return i
        return None

    def _hand_over_asked(self, table: Table, seat: int, peer: Peer) -> None:
        """A new connection of the save takes over the asking of seat [seat] (_asked_of) as it stands: its answer
        if it gave one, and the time left to answer. The old connection's leaving, seen later, finds no seat of its
        own and declines nothing. The new one hears the ask again; the others hear the seat's new member id."""
        s = table.seats[seat]
        s.peer, s.id = peer, peer.id
        s.nick, s.character, s.plate, s.raw = peer.nick, peer.character, peer.plate, peer.raw_nick
        s.watchable = peer.ddz_watch
        if table.phase == OPEN:
            sec = max(0.0, round(s.until - self.clock(), 1))
            peer.enqueue({"type": "ddz_invite", "table": table.id, "ids": [x.id for x in table.seats],
                          "base": table.base, "deposit": table.deposit, "sec": sec, "match": True,
                          "seats": [None if x.empty else _face(x) for x in table.seats],
                          "accepted": [x.id for x in table.seats if not x.empty and x.accepted]})
            self._open_changed(table)
            return
        sec = max(0.0, round(table.deadline - self.clock(), 1))
        peer.enqueue({"type": "ddz_invite", "table": table.id, "ids": [x.id for x in table.seats],
                      "base": table.base, "deposit": table.deposit, "sec": sec, "match": True,
                      "seats": [_face(x) for x in table.seats],
                      "accepted": [x.id for x in table.seats if x.accepted]})
        self._tell_face(table, seat)
        if s.accepted:
            table.tell({"type": "ddz_answer", "table": table.id, "id": s.id}, but=seat)

    def restyle(self, peer: Peer) -> None:
        """[peer]'s nick, pet or plate changed (its own state, or the blocklist masking its nick again): the seat it
        plays shows the new face, and the table hears it (ddz_seat with the face; an open table's list and seats). The
        table it watches hears it with its watchers."""
        watched = self.by_id.get(peer.watching) if peer.watching else None
        if watched is not None and peer.id in watched.watchers:
            self._watchers_changed(watched)
        table = self.by_save.get(peer.token) if peer.token else None
        seat = table.seat_of(peer) if table is not None else None
        if table is None or seat is None:
            return
        s = table.seats[seat]
        if (s.nick, s.character, s.plate) == (peer.nick, peer.character, peer.plate):
            return
        s.nick, s.character, s.plate, s.raw = peer.nick, peer.character, peer.plate, peer.raw_nick
        self._tell_face(table, seat)

    def _tell_face(self, table: Table, seat: int) -> None:
        """Tells whoever holds [table] (its invite, its open seats or its game) the face seat [seat] shows now."""
        s = table.seats[seat]
        if table.phase == OPEN:
            self._open_changed(table)
        elif table.phase in (INVITE, STARTING, BID, PLAY, SETTLING, OVER):
            said = {"type": "ddz_seat", "table": table.id, "seat": seat, "id": s.id,
                    "away": s.quit or (table.phase != INVITE and s.peer is None), "auto": s.auto,
                    "nick": s.nick, "character": s.character, "plate": s.plate}
            table.tell(said)
            self._show(table, said)

    def remask(self, mask: Callable[[str], str]) -> None:
        """The blocklist changed: every seat shown at a table, its member there or away, shows its nick masked again
        (from Seat.raw), and the table hears of each that changed."""
        for table in list(self.by_id.values()):
            for i, s in enumerate(table.seats):
                if s.empty:
                    continue
                if s.peer is not None and s.peer.raw_nick:
                    s.raw = s.peer.raw_nick
                nick = mask(s.raw or s.nick)
                if nick != s.nick:
                    s.nick = nick
                    self._tell_face(table, i)
            # The watchers' nicks are their connections', masked again by then.
            if table.watchers:
                self._watchers_changed(table)

    async def bye(self, peer: Peer) -> None:
        """A dou dizhu connection closed: as a member leaving its room (departed)."""
        if self.lobby.get(peer.id) is peer:
            del self.lobby[peer.id]
        await self.departed("", peer)

    def holds(self, pid: str) -> bool:
        """Whether save [pid] holds a seat that a dou dizhu connection takes again (hello): at a table the queue
        made, or one an open table took from the queue, before its game is paid."""
        table = self.by_save.get(pid)
        return table is not None and table.phase in (OPEN, STARTING, BID, PLAY) and any(
            s.token == pid and (table.match or s.roam) and not s.asked and not (s.quit and table.phase == STARTING)
            for s in table.seats)

    def emote(self, peer: Peer, table_id: str, emote: str) -> None:
        """[peer] shows emote [emote] at its table, to the other seats in any room (``ddz_emote``). A seat whose
        client knows only room emotes (1.2.5, at an invited table of the same room) hears it as the room's own
        ``emote`` from the sender's member id, sent to it alone."""
        table, seat = self._table(peer, table_id, BID, PLAY, SETTLING, OVER)
        for i, s in enumerate(table.seats):
            p = s.peer
            if i == seat or p is None or s.quit or not p.active:
                continue
            if p.ddz_match:
                p.enqueue({"type": "ddz_emote", "table": table.id, "seat": seat, "emote": emote})
            elif table.room is not None and p.room == table.room == peer.room:
                p.enqueue({"type": "emote", "id": peer.id, "emote": emote})
        self._show(table, {"type": "ddz_emote", "table": table.id, "seat": seat, "emote": emote})

    def _state(self, table: Table, seat: int) -> dict:
        """The whole game as [seat] may see it."""
        cfg = self.bank.cfg()
        return {
            "type": "ddz_state", "table": table.id, "phase": table.phase, "you": seat,
            "hand": list(table.seats[seat].hand),
            "seats": [{**_face(s), "left": len(s.hand), "bid": s.bid, "auto": s.auto, "away": s.peer is None or s.quit}
                      for s in table.seats],
            "base": table.base, "cap": cfg["capMult"], "deal": table.deal, "bid": table.bid,
            "landlord": table.landlord, "bottom": table.bottom if table.landlord is not None else [],
            "mult": table.mult(cfg["capMult"]), "bombs": table.bombs, "turn": table.turn,
            "lead": table.phase == PLAY and table.last is None,
            # Copies: the message waits in the send queue while the table goes on changing these lists.
            "trick": [None if x is None else list(x) for x in table.trick],
            "sec": max(0.0, round(table.deadline - self.clock(), 1)), "of": table.turn_sec,
            "played": list(table.played),
            **self._counter(table.seats[seat]),
        }

    def _rooms(self, table: Table) -> set[str]:
        """The rooms that see the table: its own room (an invited or open table's), and the rooms the saves of its
        seats of the queue are in now, on any of their connections (one that walked away from the table included)."""
        rooms = {table.room} if table.room is not None else set()
        saves = {s.token for s in table.seats if s.token and (table.match or s.roam)}
        if saves:
            rooms |= {rid for rid, room in self.manager.rooms.items()
                      if any(p.token in saves for p in room.peers.values())}
        return rooms

    @staticmethod
    def _ids_in(room: Any, table: Table) -> list[str]:
        """The seats of [table] by the member ids [room] knows them by: a seat's own member when it is in the room,
        else the newest connection of its save there; the seat's own id when its save is not in the room."""
        out = []
        for s in table.seats:
            p = s.peer
            if p is not None and p.active and room.peers.get(p.id) is p:
                out.append(p.id)
                continue
            there = max((x for x in room.peers.values() if s.token and x.token == s.token),
                        key=lambda x: x.join_seq, default=None)
            out.append(there.id if there is not None else s.id)
        return out

    async def _live(self, table: Table, on: bool, deltas: list[int] | None = None) -> None:
        """Tells the table's rooms (_rooms) that its game started (on) or ended, each with the seats' member ids
        there (_ids_in); the end also goes to every room told of the start, so one its members all left does not keep
        showing the game. `gains` are the shards the winners won ([deltas] above 0). A room none of the seats' saves
        is in now hears only that it ended, not who played or won."""
        rooms = self._rooms(table)
        if on:
            new = rooms - table.live_rooms
            table.live_rooms |= rooms
            for room_id in sorted(rooms):
                room = self.manager.rooms.get(room_id)
                if room is not None:
                    await self.manager.broadcast(room_id, {"type": "ddz_live", "table": table.id,
                                                           "ids": self._ids_in(room, table), "on": True,
                                                           "base": table.base})
            if new and table.phase in (BID, PLAY):
                # A room told of the game only now hears how it stands.
                msg = self._live_state_msg(table)
                for room_id in sorted(new):
                    self._tell_live_state(room_id, msg)
            return
        self._stop_live_state(table)
        saves = {s.token for s in table.seats if s.token}
        rooms |= table.live_rooms
        table.live_rooms = set()
        for room_id in sorted(rooms):
            room = self.manager.rooms.get(room_id)
            if room is None:
                continue
            if not any(p.token in saves for p in room.peers.values()):
                await self.manager.broadcast(room_id, {"type": "ddz_live", "table": table.id, "on": False})
                continue
            ids = self._ids_in(room, table)
            msg: dict[str, Any] = {"type": "ddz_live", "table": table.id, "ids": ids, "on": False}
            if deltas is not None:
                msg["gains"] = {i: d for i, d in zip(ids, deltas) if d > 0}
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
        if peer.dnd or self._quiet(peer.token):
            raise GameError("ddz_dnd", "")
        if self.clock() < self.match_refused.get(peer.token, float("-inf")):
            raise GameError("ddz_match_cooldown", "")

    async def queue(self, peer: Peer, base: int) -> None:
        """[peer] waits for a table at stake [base]; waiting at another stake already, it moves to the end of this
        one's line. Then a table is made if three in the line may sit down together."""
        if not peer.lobby or not peer.ddz_match:
            raise GameError("bad_message", "queue on a dou dizhu connection (ddz_hello)")
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
        # A place an invite holds for the save goes too: the invite coming to nothing does not give it back.
        if peer.token:
            self._drop_held(peer.token)
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
                quiet = self._quiet_saves()
                for w, code in zip(three, codes):
                    w.checking = False
                    if self.waiting.get(w.token) is not w:
                        continue  # cancelled, left or turned invites down meanwhile
                    code = code or ("ddz_dnd" if w.peer.dnd or w.token in quiet else None)
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
            Seat(token=w.token, peer=w.peer, id=w.peer.id, nick=w.peer.nick, character=w.peer.character,
                 plate=w.peer.plate, since=w.since, seq=w.seq, raw=w.peer.raw_nick, watchable=w.peer.ddz_watch)
            for w in three])
        for w in three:
            self._dequeue(w)
        self.by_id[table.id] = table
        for s in table.seats:
            self.by_save[s.token] = table
        table.tell({"type": "ddz_invite", "table": table.id, "ids": [s.id for s in table.seats], "base": base,
                    "deposit": deposit, "sec": cfg["inviteSec"], "match": True,
                    "seats": [_face(s) for s in table.seats]})
        table.deadline = self.clock() + cfg["inviteSec"]
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
        quiet = self._quiet_saves()
        for s in seats:
            p = s.peer
            if (p is None or not p.active or not p.ddz_match or p.dnd or not p.token or p.token in self.by_save
                    or p.token in self.waiting or p.token in quiet):
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
        """Tells every member that queues, in every room, and every dou dizhu connection the counts, when they changed
        since the last time."""
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
        for p in list(self.lobby.values()):
            p.enqueue(msg)

    # ----------------------------------------------------------------- watching
    def watch(self, peer: Peer, table_id: str, seat: int = 0) -> None:
        """Room member [peer] (its client said `ddzMatch` and `ddzWatch`) watches the game at [table_id] with the hand
        of [seat] shown when it may be (_hand_for), and hears it whole (``ddz_watch``); or, [table_id] empty, stops
        watching, told nothing. Another table or seat replaces what it watched; a refusal leaves that as it was."""
        if not table_id:
            self._unwatch(peer)
            return
        now = self.clock()
        if now - peer.watch_at < WATCH_INTERVAL:
            raise GameError("rate_limited", "too many requests")
        peer.watch_at = now
        table = self.by_id.get(table_id)
        room = self.manager.rooms.get(peer.room)
        if (table is None or table.phase not in (BID, PLAY, SETTLING, OVER) or room is None or not peer.active
                or room.peers.get(peer.id) is not peer or peer.room not in self._rooms(table)):
            raise GameError("ddz_gone", "")
        if peer.token:
            own = self.by_save.get(peer.token)
            if any(s.token == peer.token for s in table.seats) or (
                    own is not None and own.phase in (STARTING, BID, PLAY, SETTLING, OVER)):
                raise GameError("ddz_busy", "")
        if peer.id not in table.watchers and len(table.watchers) >= WATCH_MAX:
            raise GameError("ddz_watch_full", "")
        if peer.watching != table.id:
            self._unwatch(peer)
        table.watchers[peer.id] = (peer, seat)
        peer.watching = table.id
        peer.enqueue(self._watch_state(table, seat, peer))
        table.watch_owed.add(peer.id)
        self._watchers_changed(table)

    def _unwatch(self, peer: Peer) -> None:
        """[peer] stops watching, told nothing."""
        table = self.by_id.get(peer.watching) if peer.watching else None
        peer.watching = None
        if table is not None and table.watchers.get(peer.id, (None,))[0] is peer:
            del table.watchers[peer.id]
            table.watch_owed.discard(peer.id)
            self._watchers_changed(table)

    def _end_watch(self, table: Table, reason: str | None, over: str | None = None) -> None:
        """Every watcher of [table] stops, told why (``ddz_watch_end``) unless [reason] is None; [over] is the reason
        of the ``ddz_over`` the seats hear, when they hear one."""
        if not table.watchers:
            return
        end: dict[str, Any] = {"type": "ddz_watch_end", "table": table.id, "reason": reason}
        if over:
            end["over"] = over
        for peer, _ in list(table.watchers.values()):
            if reason:
                peer.enqueue(end)
            if peer.watching == table.id:
                peer.watching = None
        table.watchers.clear()
        table.watch_owed.clear()
        self._watchers_changed(table)

    def _unwatch_saves(self, saves: set[str], reason: str) -> None:
        """The connections of [saves] watching a game stop, told why: their saves play."""
        if not saves:
            return
        for table in list(self.by_id.values()):
            for peer, _ in [w for w in table.watchers.values() if w[0].token and w[0].token in saves]:
                peer.enqueue({"type": "ddz_watch_end", "table": table.id, "reason": reason})
                peer.watching = None
                del table.watchers[peer.id]
                table.watch_owed.discard(peer.id)
                self._watchers_changed(table)

    def _rooms_changed(self) -> None:
        """A connection joined or left a room: which hands watchers may see may have changed (_hand_for)."""
        for table in list(self.by_id.values()):
            if table.watchers or table.watch_sent:
                self._watchers_changed(table)

    def _shows(self, table: Table, seat: int, peer: Peer) -> bool:
        """Whether watcher [peer] may see the hand of seat [seat]: the seat's client shows who watches it
        (Seat.watchable), and the seat plays in the watcher's room (the table's own room, not a seat from the queue) or
        its save is in that room on some connection."""
        s = table.seats[seat]
        if not s.watchable or not s.token:
            return False
        if table.room is not None and table.room == peer.room and not s.roam:
            return True
        room = self.manager.rooms.get(peer.room)
        return room is not None and any(p.token == s.token for p in room.peers.values())

    def _hand_for(self, table: Table, seat: int, peer: Peer) -> list[int] | None:
        """The hand of seat [seat] as watcher [peer] gets it: a copy, None when it may not see it (_shows). The only
        way a hand reaches a watcher before the result."""
        return list(table.seats[seat].hand) if self._shows(table, seat, peer) else None

    def _watch_ids(self, table: Table, peer: Peer) -> list[str]:
        """The seats of [table] by the member ids the room of watcher [peer] knows them by (_ids_in)."""
        room = self.manager.rooms.get(peer.room)
        return self._ids_in(room, table) if room is not None else [s.id for s in table.seats]

    def _show(self, table: Table, data: dict) -> None:
        """Copies a message every seat may hear (one of SHOWN) to the watchers of [table], with `watch` true; a
        ``ddz_seat``'s member id as the watcher's room knows it. Only messages passed here reach watchers, so what is
        added to the seats' messages (Table.tell) stays theirs. A bid or a play also changes what the rooms are told
        of the game (_live_changed)."""
        if data["type"] in LIVE_CHANGES:
            self._live_changed(table)
        if not table.watchers:
            return
        if data["type"] not in SHOWN:
            log.error("ddz: %s is not shown to watchers", data["type"])
            return
        for peer, _ in list(table.watchers.values()):
            msg = {**data, "watch": True}
            if data["type"] == "ddz_seat":
                msg["id"] = self._watch_ids(table, peer)[data["seat"]]
            peer.enqueue(msg)

    def _watch_state(self, table: Table, seat: int, peer: Peer) -> dict:
        """The whole game as watcher [peer] may see it, with the hand of [seat] (_hand_for)."""
        cfg = self.bank.cfg()
        ids = self._watch_ids(table, peer)
        return {
            "type": "ddz_watch", "table": table.id, "seat": seat, "hand": self._hand_for(table, seat, peer),
            "phase": table.phase,
            "seats": [{**_face(s), "id": i, "left": len(s.hand), "bid": s.bid, "auto": s.auto,
                       "away": s.peer is None or s.quit, "again": s.again}
                      for s, i in zip(table.seats, ids)],
            "base": table.base, "cap": cfg["capMult"], "deal": table.deal, "bid": table.bid,
            "landlord": table.landlord, "bottom": list(table.bottom) if table.landlord is not None else [],
            "mult": table.mult(cfg["capMult"]), "bombs": table.bombs, "turn": table.turn,
            "lead": table.phase == PLAY and table.last is None,
            "trick": [None if x is None else list(x) for x in table.trick],
            "sec": max(0.0, round(table.deadline - self.clock(), 1)), "of": table.turn_sec,
            "result": table.result if table.phase == OVER else None,
        }

    def _faces(self, table: Table) -> list[dict]:
        """The watchers of [table] as the table sees them: nick, pet, and the seat whose hand each sees (None when it
        sees none)."""
        return [{"nick": p.nick, "character": p.character, "seat": at if self._shows(table, at, p) else None}
                for p, at in table.watchers.values()]

    @staticmethod
    def _watchers_msg(table: Table, faces: list[dict]) -> dict:
        return {"type": "ddz_watchers", "table": table.id, "faces": faces}

    def _watchers_changed(self, table: Table) -> None:
        """The watchers of [table], or what they see, may have changed: the table hears them now, or COUNTS_SEC after
        it was last told; its rooms hear how many watch (_live_changed)."""
        self._live_changed(table)
        if table.phase == DONE or self.by_id.get(table.id) is not table or table.watch_timer is not None:
            return
        wait = table.watch_at + COUNTS_SEC - self.clock()
        if wait > 0:
            table.watch_timer = self.count_timers.later(wait, lambda: self._watchers_due(table))
        else:
            self._send_watchers(table)

    async def _watchers_due(self, table: Table) -> None:
        table.watch_timer = None
        self._send_watchers(table)

    def _send_watchers(self, table: Table) -> None:
        """Tells the seats whose client shows watchers, and the watchers, who watches (``ddz_watchers``), when it
        differs from what they were told last (an empty list once the last goes); a watcher not told yet hears it all
        the same. A watcher's copy has `you`, its own place in the list."""
        if table.phase == DONE or self.by_id.get(table.id) is not table:
            return
        faces = self._faces(table)
        owed, table.watch_owed = table.watch_owed, set()
        msg = self._watchers_msg(table, faces)
        # The faces follow table.watchers' order.
        watchers = [(i, peer) for i, (peer, _) in enumerate(table.watchers.values())]
        if faces == table.watch_sent:
            for i, peer in watchers:
                if peer.id in owed:
                    peer.enqueue({**msg, "you": i})
            return
        table.watch_sent = faces
        table.watch_at = self.clock()
        for s in table.seats:
            if s.peer is not None and not s.quit and s.peer.ddz_watch:
                s.peer.enqueue(msg)
        for i, peer in watchers:
            peer.enqueue({**msg, "you": i})

    def _live_state_msg(self, table: Table) -> dict:
        return {"type": "ddz_live_state", "table": table.id, "landlord": table.landlord,
                "seats": [{"left": len(s.hand)} for s in table.seats], "mult": table.mult(self.bank.cfg()["capMult"]),
                "watching": len(table.watchers)}

    def _tell_live_state(self, room_id: str, msg: dict) -> None:
        """[msg] to the members of [room_id] whose client watches games (the others do not know the message)."""
        room = self.manager.rooms.get(room_id)
        if room is None:
            return
        for p in list(room.peers.values()):
            if p.ddz_watch:
                p.enqueue(msg)

    def _watching_rooms(self, table: Table) -> bool:
        """Whether a member of a room told of [table]'s game is on a client that watches."""
        return any(p.ddz_watch for rid in table.live_rooms if (room := self.manager.rooms.get(rid)) is not None
                   for p in room.peers.values())

    def _live_changed(self, table: Table) -> None:
        """How the game of [table] stands may have changed: its rooms hear it now, or COUNTS_SEC after they were last
        told; nothing while none of their members is on a client that watches (one joining hears it then)."""
        if (table.phase not in (BID, PLAY) or self.by_id.get(table.id) is not table or table.live_timer is not None
                or not self._watching_rooms(table)):
            return
        wait = table.live_at + COUNTS_SEC - self.clock()
        if wait > 0:
            table.live_timer = self.count_timers.later(wait, lambda: self._live_due(table))
        else:
            self._send_live_state(table)

    async def _live_due(self, table: Table) -> None:
        table.live_timer = None
        self._send_live_state(table)

    def _send_live_state(self, table: Table) -> None:
        """Tells the rooms of [table]'s game (``ddz_live_state``) how it stands, when that differs from what they were
        told last."""
        if table.phase not in (BID, PLAY) or self.by_id.get(table.id) is not table:
            return
        msg = self._live_state_msg(table)
        if msg == table.live_sent:
            return
        table.live_sent = msg
        table.live_at = self.clock()
        for room_id in sorted(table.live_rooms):
            self._tell_live_state(room_id, msg)

    @staticmethod
    def _stop_live_state(table: Table) -> None:
        """The game of [table] is over or gone: nothing more is told of it, and a next game starts afresh."""
        if table.live_timer is not None:
            table.live_timer.cancel()
            table.live_timer = None
        table.live_sent = None
        table.live_at = float("-inf")

    # ------------------------------------------------------------------- ending
    def _cancel_timer(self, table: Table) -> None:
        if table.timer is not None:
            table.timer.cancel()
            table.timer = None

    def _drop(self, table: Table) -> None:
        self._cancel_timer(table)
        self.by_id.pop(table.id, None)
        self._end_watch(table, "closed")
        if table.watch_timer is not None:
            table.watch_timer.cancel()
            table.watch_timer = None
        self._stop_live_state(table)
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
        # Watchers are there only when another game at the table fails to start.
        self._end_watch(table, "gone", over=reason)
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
        # The invited that were waiting in the queue get their places back, one that declined itself too (the invite's
        # own cooldown, RETRY_SEC, holds for the inviter); one that turned invites down for good does not (_restore).
        held, table.held = table.held, []
        self._restore(held)

    def _restore(self, held: list[Waiting]) -> None:
        """Gives saves taken out of the queue by an invite their places back, as they were (since, seq), when their
        connection is still there and the save may still wait: free, not turning invites down, at a stake there is."""
        cfg = self._game().manifest.ddz
        stakes = set(cfg["stakes"]) if cfg else set()
        quiet = self._quiet_saves()
        back: dict[int, list[Waiting]] = {}
        for old in held:
            # The save's dou dizhu connection now: the one it waited on, or a newer one that took over meanwhile.
            p = max((x for x in self.lobby.values() if x.token == old.token and x.active), key=lambda x: x.join_seq,
                    default=None)
            if (p is None or old.base not in stakes or old.token in self.by_save or old.token in self.waiting
                    or old.token in quiet):
                continue
            # A new entry: a match that was reading the old one finds it gone and leaves it be.
            w = Waiting(p, old.base, old.since, old.seq)
            self.waiting[w.token] = w
            back.setdefault(w.base, []).append(w)
        for base, entries in back.items():
            self._merge(base, entries)
            for w in entries:
                self._tell_queue(w)
            self._counts_changed()
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
