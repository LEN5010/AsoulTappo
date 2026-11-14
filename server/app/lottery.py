"""The daily lottery of the park: tickets 000 to 999 for a coin each, one draw a day at `drawAt` (China clock).

A lottery day runs from one draw to the next and is named by the China date it is drawn on (draw_day()): a ticket
bought after today's draw goes into tomorrow's. Sales close at `closeAt`, a few minutes before the draw. Each day's
winning number and a random salt are made before its first ticket (at the previous draw by the loop, or on the first
request after it, whichever comes first), and only SHA-256(number + salt) is public until the draw; the draw then
publishes both, so anyone can check that the number was fixed in advance.

Prizes (manifest economy.park.lottery):
- top, all three digits: the server-wide pool (park_counters park.POOL). It starts at `pool.seed`, every coin spent in
  the park (scratch cards, the race, the lottery) adds `pool.perCoin` through Park.spend, and the race's refunds take
  theirs back. A draw with top winners splits the pool equally, rounded down to whole shards, and the pool starts
  again at `pool.seed` plus the remainder; without one it carries over whole.
- second, the last two digits: `second` of the day's sales plus the second rollover, split equally; the remainder, or
  the whole amount when no ticket wins it, rolls over into the next draw's second.
- third, the last digit: `third` shards a ticket.
A ticket wins only its best tier.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable

from .game import BOARD_DEFAULT_NICK, Game, GameError, _loadout_json, board_id, player_id_for
from .park import POOL, Park
from .store import DAY_OFFSET, Store, day_of

# Shard ledger source of the prizes; coin ledger source of the tickets.
PRIZE = "lottery_prize"
SPEND = "lottery"
# park_counters key of the second prize's rollover into the next draw (the top prize is park.POOL).
ROLL_SECOND = "lottery_roll_second"
TIERS = {1: "top", 2: "second", 3: "third"}
# Drawn days the state lists in `history` and in `draws`.
HISTORY_DAYS = 7
# Top prize nicks a draw's news carries.
NEWS_NICKS = 5
NUMBER = re.compile(r"[0-9]{3}")
# The loop checks at least this often (seconds), and at each midnight and draw time.
LOOP_MAX_SLEEP = 60.0


def commitment(number: str, salt: str) -> str:
    """The published hash: SHA-256 of the number's three digits followed by the salt's hex text."""
    return hashlib.sha256((number + salt).encode()).hexdigest()


def tier_of(number: str, winning: str) -> int:
    """1 for all three digits, 2 for the last two, 3 for the last one, else 0."""
    if number == winning:
        return 1
    if number[1:] == winning[1:]:
        return 2
    if number[2] == winning[2]:
        return 3
    return 0


def second_pool(cfg: dict[str, Any], price: int, sales: int, roll_second: int) -> int:
    """The second prize of a draw with [sales] tickets: `second` of the sales in shards plus the rollover."""
    return int(Fraction(str(cfg["second"])) * sales * price) + roll_second


@dataclass
class Settlement:
    pools: dict[str, int]  # top, second: what was shared out (before rounding)
    winners: dict[str, int]  # tickets per tier
    each: dict[str, int]  # shards per winning ticket per tier
    roll: dict[str, int]  # second: carried into the next draw's second prize
    pool: int  # the top prize pool after the draw
    prizes: list[tuple[int, int, int]] = field(default_factory=list)  # (ticket id, tier, prize) of winning tickets


def settle(cfg: dict[str, Any], price: int, winning: str, tickets: list[tuple[int, str]], pool: int,
           roll_second: int) -> Settlement:
    """The draw of [tickets] ((id, number) each) against [winning], with the top prize [pool] and the second
    prize's rollover coming in."""
    second = second_pool(cfg, price, len(tickets), roll_second)
    tiers = [(tid, tier_of(n, winning)) for tid, n in tickets]
    count = {t: sum(1 for _, x in tiers if x == t) for t in TIERS}
    each = {1: pool // count[1] if count[1] else 0, 2: second // count[2] if count[2] else 0, 3: cfg["third"]}
    after = cfg["pool"]["seed"] + pool - each[1] * count[1] if count[1] else pool
    return Settlement(
        pools={"top": pool, "second": second},
        winners={TIERS[t]: count[t] for t in TIERS}, each={TIERS[t]: each[t] if count[t] else 0 for t in TIERS},
        roll={"second": second - each[2] * count[2]}, pool=after,
        prizes=[(tid, t, each[t]) for tid, t in tiers if t])


def day_start(ts: float) -> float:
    """The unix time of the China midnight that starts [ts]'s day."""
    return (ts + DAY_OFFSET) // 86400 * 86400 - DAY_OFFSET


def draw_time(cfg: dict[str, Any], ts: float) -> float:
    """The unix time of the draw that [ts]'s tickets go into: today's drawAt (China clock), or tomorrow's once
    today's has come."""
    t = day_start(ts) + cfg["drawAt"] * 60
    return t if ts < t else t + 86400


def draw_day(cfg: dict[str, Any], ts: float) -> str:
    """The lottery day of [ts]: the China date of its draw."""
    return day_of(draw_time(cfg, ts))


def close_time(cfg: dict[str, Any], ts: float) -> float:
    """The unix time sales close for the draw of [ts]: closeAt, the same day as the draw."""
    return draw_time(cfg, ts) - (cfg["drawAt"] - cfg["closeAt"]) * 60


class Lottery:
    def __init__(self, game: Callable[[], Game], park: Park,
                 pick: Callable[[], str] = lambda: f"{secrets.randbelow(1000):03d}") -> None:
        self._game = game
        self.park = park
        # The winning number of a new day; tests fix it.
        self.pick = pick

    @property
    def game(self) -> Game:
        return self._game()

    @property
    def cfg(self) -> dict[str, Any]:
        cfg = self.park.cfg.get("lottery")
        if not cfg:
            raise GameError("no_park", "这个服务器没有每日夺宝")
        return cfg

    @property
    def price(self) -> int:
        return self.park.coin["price"]

    # ------------------------------------------------------------- the day
    def ensure_day(self, st: Store, day: str, now: float) -> dict[str, Any]:
        """[day]'s row, made now with a fresh number and salt if it is missing."""
        row = st.lottery_day(day)
        if row is None:
            number = self.pick()
            salt = secrets.token_hex(32)
            st.add_lottery_day(day, number, salt, commitment(number, salt), now)
            row = st.lottery_day(day)
        return row

    def is_open(self, now: float) -> bool:
        return now < close_time(self.cfg, now)

    def state_of(self, st: Store, pid: str, now: float) -> dict[str, Any]:
        cfg = self.cfg
        day = draw_day(cfg, now)
        row = self.ensure_day(st, day, now)
        mine = st.lottery_tickets(day, pid)
        drawn = row["drawn"] is not None
        # Once today is drawn, the second is what has rolled into tomorrow's draw so far. The top is the pool now.
        second = second_pool(cfg, self.price, 0 if drawn else st.lottery_sales(day), st.park_counter(ROLL_SECOND))
        return {
            "day": day,
            "hash": row["hash"],
            "closeAt": close_time(cfg, now),
            "drawAt": draw_time(cfg, now),
            "open": self.is_open(now) and not drawn,
            "drawn": drawn,
            "sales": st.lottery_sales(day),
            "prize": {"top": self.park.pool(st), "second": second, "third": cfg["third"]},
            "daily": cfg["daily"],
            "left": max(0, cfg["daily"] - len(mine)),
            "tickets": [t["number"] for t in mine],
            "last": self._last(st, pid),
            "history": st.lottery_history(pid, HISTORY_DAYS),
            "draws": self._draws(st),
        }

    def _draws(self, st: Store) -> list[dict[str, Any]]:
        """The latest drawn days, newest first, with their top prize winners (board ids and nicks, one per save) and
        what each top ticket was paid (0 without a winner)."""
        draws = st.lottery_draws(HISTORY_DAYS)
        nicks = self._nicks(st, list(dict.fromkeys(pid for d in draws for pid in d["top"])))
        out = []
        for d in draws:
            each = json.loads(d["result"]).get("each", {}).get("top", 0)
            out.append({"day": d["day"], "number": d["number"],
                        "top": [{"id": board_id(pid), "nick": nicks[pid]} for pid in d["top"]],
                        "each": int(each) if d["top"] else 0})
        return out

    def _nicks(self, st: Store, pids: list[str]) -> dict[str, str]:
        """Park.nick of each of [pids], in two queries."""
        loadouts = st.loadouts(pids)
        rooms = st.room_nicks(pids)
        out = {}
        for pid in pids:
            lo = _loadout_json(loadouts.get(pid, ""))
            nick = lo.get("nick") if isinstance(lo.get("nick"), str) else ""
            out[pid] = self.park.mask(nick or rooms.get(pid) or BOARD_DEFAULT_NICK)
        return out

    def _last(self, st: Store, pid: str) -> dict[str, Any] | None:
        row = st.lottery_last_drawn()
        if row is None:
            return None
        result = json.loads(row["result"])
        mine = [{"number": t["number"], "tier": TIERS.get(t["tier"]), "prize": t["prize"]}
                for t in st.lottery_tickets(row["day"], pid)]
        return {"day": row["day"], "number": row["number"], "salt": row["salt"], "hash": row["hash"],
                "drawnAt": row["drawn"], "sales": result.get("sales", 0), "winners": result.get("winners", {}),
                "each": result.get("each", {}), "mine": mine, "won": sum(t["prize"] for t in mine)}

    def state(self, token: str) -> dict[str, Any]:
        self.cfg
        g = self.game
        pid = player_id_for(token)
        # Right after a draw time a request may come before the loop: the day just ended is drawn first, so the new
        # day never shows the one before it as the last draw.
        self.tick()
        with g.store.transaction() as st:
            return self.state_of(st, pid, g.now())

    # ------------------------------------------------------------- tickets
    def buy(self, token: str, numbers: list[str], count: int = 0) -> dict[str, Any]:
        """Buys a ticket for each of [numbers] and [count] more on random numbers, all or none."""
        cfg = self.cfg
        g = self.game
        pid = player_id_for(token)
        if any(not isinstance(n, str) or not NUMBER.fullmatch(n) for n in numbers):
            raise GameError("bad_number", "号码是 000 到 999")
        n = len(numbers) + count
        if count < 0 or n < 1:
            raise GameError("bad_count", "数量不对")
        with g.store.transaction() as st:
            now = g.now()
            day = draw_day(cfg, now)
            row = self.ensure_day(st, day, now)
            if row["drawn"] is not None or not self.is_open(now):
                raise GameError("lottery_closed", "本期已停售")
            held = [t["number"] for t in st.lottery_tickets(day, pid)]
            if len(held) + n > cfg["daily"]:
                raise GameError("lottery_cap", f"本期还能买 {max(0, cfg['daily'] - len(held))} 注")
            bought = list(numbers) + self._random(count, set(held) | set(numbers))
            self.park.spend(st, pid, n, SPEND, now)
            st.add_lottery_tickets(day, pid, bought, now)
            state = self.state_of(st, pid, now)
        return {**g.status(token), "park": self.park.state(token), "lottery": state, "bought": bought}

    @staticmethod
    def _random(count: int, avoid: set[str]) -> list[str]:
        """[count] random numbers, distinct and outside [avoid] (the save's numbers of the day)."""
        free = [f"{i:03d}" for i in range(1000) if f"{i:03d}" not in avoid]
        return secrets.SystemRandom().sample(free, count)

    # ---------------------------------------------------------------- draw
    def draw(self, day: str) -> dict[str, Any] | None:
        """Draws [day] unless it is drawn already (or has no row); returns the stored result."""
        cfg = self.cfg
        g = self.game
        with g.store.transaction() as st:
            row = st.lottery_day(day)
            if row is None or row["drawn"] is not None:
                return None
            now = g.now()
            tickets = st.lottery_tickets(day)
            s = settle(cfg, self.price, row["number"], [(t["id"], t["number"]) for t in tickets],
                       self.park.pool(st), st.park_counter(ROLL_SECOND))
            st.set_lottery_prizes(s.prizes)
            owner = {t["id"]: t["player_id"] for t in tickets}
            paid: dict[str, int] = {}
            for tid, _, prize in s.prizes:
                paid[owner[tid]] = paid.get(owner[tid], 0) + prize
            pay_day = day_of(now)
            for pid, shards in paid.items():
                p = st.get_player(pid, now)
                st.update_player(pid, shards=p["shards"] + shards)
                st.add_ledger(pid, pay_day, PRIZE, shards)
            st.set_park_counter(POOL, s.pool)
            st.set_park_counter(ROLL_SECOND, s.roll["second"])
            result = {"sales": len(tickets), "pools": s.pools, "winners": s.winners, "each": s.each, "roll": s.roll,
                      "pool": s.pool, "paid": sum(paid.values())}
            st.set_lottery_drawn(day, now, json.dumps(result))
            if tickets:
                self._announce(st, day, row["number"], s, owner, now)
        return result

    def _announce(self, st: Store, day: str, number: str, s: Settlement, owner: dict[int, str], now: float) -> None:
        """One news item a draw. News carries one save, so the first top winner (earliest ticket) is its nick, and
        every top winner's nick is in `nicks`, one per save; without a top winner the nick is empty."""
        top = list(dict.fromkeys(owner[tid] for tid, tier, _ in s.prizes if tier == 1))
        detail = {"day": day, "number": number, "winners": s.winners, "each": s.each,
                  "nicks": [self.park.nick(st, pid) for pid in top[:NEWS_NICKS]]}
        if top:
            self.park.announce(st, "lottery_draw", top[0], now, **detail)
        else:
            st.add_park_news(now, "lottery_draw", "", "", json.dumps(detail, ensure_ascii=False))

    def tick(self) -> list[str]:
        """Makes the current day's row and draws every earlier day not drawn yet: a day ends at its draw time, so the
        days before the current one are the ones due (past days the server missed included). Safe to call any time: a
        drawn day is never drawn again."""
        cfg = (self.game.manifest.park or {}).get("lottery")
        if not cfg:
            return []
        g = self.game
        now = g.now()
        today = draw_day(cfg, now)
        with g.store.transaction() as st:
            self.ensure_day(st, today, now)
            due = [d for d in st.lottery_undrawn() if d < today]
        return [d for d in due if self.draw(d) is not None]

    def sleep_for(self) -> float:
        """Seconds until the next draw time, at most LOOP_MAX_SLEEP."""
        cfg = (self.game.manifest.park or {}).get("lottery")
        if not cfg:
            return LOOP_MAX_SLEEP
        now = self.game.now()
        return max(0.5, min(LOOP_MAX_SLEEP, draw_time(cfg, now) - now + 0.5))
