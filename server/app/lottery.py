"""The daily lottery of the park: tickets 000 to 999 for a coin each, one draw a China day.

Each day's winning number and a random salt are made before the day's first ticket (at China midnight by the loop, or
on the first request that day, whichever comes first), and only SHA-256(number + salt) is public until the draw; the
draw then publishes both, so anyone can check that the number was fixed in advance.

Prizes (manifest economy.park.lottery):
- top, all three digits: `top` of the day's sales in shards plus the top rollover, at most `topCap`; the part above the
  cap joins that day's second prize.
- second, the last two digits: `second` of the sales plus the second rollover (and the top's overflow).
- third, the last digit: `third` shards a ticket.
A ticket wins only its best tier. Top and second are split equally between their winning tickets, rounded down to
whole shards; the remainder, or the whole pool when no ticket wins, rolls over into the same tier of the next draw.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable

from .game import Game, GameError, player_id_for
from .park import Park
from .store import DAY_OFFSET, Store, day_of

# Shard ledger source of the prizes; coin ledger source of the tickets.
PRIZE = "lottery_prize"
SPEND = "lottery"
# park_counters keys of the rollovers into the next draw.
ROLL_TOP = "lottery_roll_top"
ROLL_SECOND = "lottery_roll_second"
TIERS = {1: "top", 2: "second", 3: "third"}
# Drawn days the state lists in `history`.
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


def pools(cfg: dict[str, Any], price: int, sales: int, roll_top: int, roll_second: int) -> tuple[int, int, int]:
    """(top, second, overflow) of a draw with [sales] tickets: the overflow is the part of the top above its cap,
    already counted in the second."""
    shards = sales * price
    raw_top = int(Fraction(str(cfg["top"])) * shards) + roll_top
    top = min(raw_top, cfg["topCap"])
    overflow = raw_top - top
    second = int(Fraction(str(cfg["second"])) * shards) + roll_second + overflow
    return top, second, overflow


@dataclass
class Settlement:
    pools: dict[str, int]  # top, second: what was shared out (before rounding)
    overflow: int
    winners: dict[str, int]  # tickets per tier
    each: dict[str, int]  # shards per winning ticket per tier
    roll: dict[str, int]  # top, second carried into the next draw
    prizes: list[tuple[int, int, int]] = field(default_factory=list)  # (ticket id, tier, prize) of winning tickets


def settle(cfg: dict[str, Any], price: int, winning: str, tickets: list[tuple[int, str]], roll_top: int,
           roll_second: int) -> Settlement:
    """The draw of [tickets] ((id, number) each) against [winning], with the rollovers coming in."""
    top, second, overflow = pools(cfg, price, len(tickets), roll_top, roll_second)
    tiers = [(tid, tier_of(n, winning)) for tid, n in tickets]
    count = {t: sum(1 for _, x in tiers if x == t) for t in TIERS}
    each = {1: top // count[1] if count[1] else 0, 2: second // count[2] if count[2] else 0, 3: cfg["third"]}
    roll = {"top": top - each[1] * count[1], "second": second - each[2] * count[2]}
    return Settlement(
        pools={"top": top, "second": second}, overflow=overflow,
        winners={TIERS[t]: count[t] for t in TIERS}, each={TIERS[t]: each[t] if count[t] else 0 for t in TIERS},
        roll=roll, prizes=[(tid, t, each[t]) for tid, t in tiers if t])


def minute_of(ts: float) -> float:
    """Minutes since China midnight."""
    return ((ts + DAY_OFFSET) % 86400) / 60


def day_start(ts: float) -> float:
    """The unix time of the China midnight that starts [ts]'s day."""
    return (ts + DAY_OFFSET) // 86400 * 86400 - DAY_OFFSET


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
        return minute_of(now) < self.cfg["closeAt"]

    def state_of(self, st: Store, pid: str, now: float) -> dict[str, Any]:
        cfg = self.cfg
        day = day_of(now)
        row = self.ensure_day(st, day, now)
        start = day_start(now)
        mine = st.lottery_tickets(day, pid)
        drawn = row["drawn"] is not None
        if drawn:
            # Today is over: what has rolled into tomorrow's draw so far.
            top, second, _ = pools(cfg, self.price, 0, st.park_counter(ROLL_TOP), st.park_counter(ROLL_SECOND))
        else:
            top, second, _ = pools(cfg, self.price, st.lottery_sales(day), st.park_counter(ROLL_TOP),
                                   st.park_counter(ROLL_SECOND))
        return {
            "day": day,
            "hash": row["hash"],
            "closeAt": start + cfg["closeAt"] * 60,
            "drawAt": start + cfg["drawAt"] * 60,
            "open": self.is_open(now) and not drawn,
            "drawn": drawn,
            "sales": st.lottery_sales(day),
            "prize": {"top": top, "second": second, "third": cfg["third"]},
            "daily": cfg["daily"],
            "left": max(0, cfg["daily"] - len(mine)),
            "tickets": [t["number"] for t in mine],
            "last": self._last(st, pid),
            "history": st.lottery_history(pid, HISTORY_DAYS),
        }

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
            day = day_of(now)
            row = self.ensure_day(st, day, now)
            if row["drawn"] is not None or not self.is_open(now):
                raise GameError("lottery_closed", "今天已停售")
            held = [t["number"] for t in st.lottery_tickets(day, pid)]
            if len(held) + n > cfg["daily"]:
                raise GameError("lottery_cap", f"今天还能买 {max(0, cfg['daily'] - len(held))} 注")
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
                       st.park_counter(ROLL_TOP), st.park_counter(ROLL_SECOND))
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
            st.set_park_counter(ROLL_TOP, s.roll["top"])
            st.set_park_counter(ROLL_SECOND, s.roll["second"])
            result = {"sales": len(tickets), "pools": s.pools, "overflow": s.overflow, "winners": s.winners,
                      "each": s.each, "roll": s.roll, "paid": sum(paid.values())}
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
        """Makes today's row and draws every day whose draw time has passed (past days the server missed included).
        Safe to call any time: a drawn day is never drawn again."""
        cfg = (self.game.manifest.park or {}).get("lottery")
        if not cfg:
            return []
        g = self.game
        now = g.now()
        today = day_of(now)
        with g.store.transaction() as st:
            self.ensure_day(st, today, now)
            due = [d for d in st.lottery_undrawn()
                   if d < today or (d == today and minute_of(now) >= cfg["drawAt"])]
        return [d for d in due if self.draw(d) is not None]

    def sleep_for(self) -> float:
        """Seconds until the next midnight or draw time, at most LOOP_MAX_SLEEP."""
        cfg = (self.game.manifest.park or {}).get("lottery")
        if not cfg:
            return LOOP_MAX_SLEEP
        now = self.game.now()
        start = day_start(now)
        events = [start + cfg["drawAt"] * 60, start + 86400]
        wait = min(t - now for t in events if t > now)
        return max(0.5, min(LOOP_MAX_SLEEP, wait + 0.5))
