"""The park's coins: buying them with shards, the free one a day, spending them with stamps, the lottery pool every
spent coin feeds, and the news of big wins every running pet hears of. The games (scratch cards, the race, the
lottery) and redeem codes take and give coins through Park.spend, Park.grant and Park.refund inside their own
transactions."""
from __future__ import annotations

import json
from typing import Any, Callable

from .game import BOARD_DEFAULT_NICK, Game, GameError, _loadout_json, player_id_for
from .store import Store, day_of

# Shard ledger sources. COIN_BUY is what coins cost; PRIZE_SOURCES are the park's shard prizes, which the page sets
# against it as the day's result. Redeem codes are gifts, not winnings, and stay out of that result; the race pays in
# coins (coin ledger race_prize), so it is not in it either.
COIN_BUY = "coin_buy"
PRIZE_SOURCES = ("park_scratch", "lottery_prize")
REDEEM = "redeem"
# Coin ledger sources besides the spending of each game (named by the game: "scratch", "race", "lottery").
COIN_SOURCES = ("buy", "gift", "stamp", "scratch_again", "race_refund", "race_prize", "redeem", "admin")
# park_counters key of the lottery's top prize pool: lottery.pool.seed when absent, fed by every coin spent in the park
# (spend), paid out by the lottery's draw.
POOL = "lottery_pool"
# News older than this goes on the next start.
NEWS_KEEP_DAYS = 7


class Park:
    def __init__(self, game: Callable[[], Game], mask: Callable[[str], str] = lambda s: s) -> None:
        # The game may be replaced (tests), so it is looked up on every call, as in Duels.
        self._game = game
        self.mask = mask

    @property
    def game(self) -> Game:
        return self._game()

    @property
    def cfg(self) -> dict[str, Any]:
        cfg = self.game.manifest.park
        if not cfg:
            raise GameError("no_park", "这个服务器没有乐园")
        return cfg

    @property
    def coin(self) -> dict[str, Any]:
        return self.cfg["coin"]

    # ------------------------------------------------------------------ state
    def view(self, st: Store, p: dict[str, Any], day: str) -> dict[str, Any]:
        """The save's coins, today's free coin, stamps and today's result, and the lottery pool (`jackpot`)."""
        c = self.coin
        total = p["stamps_total"]
        return {
            "coins": p["coins"],
            "unlocked": p["taps_total"] >= c["minTaps"],
            "gift": p["gift_day"] != day,
            "stamps": total % c["stampsPerCoin"],
            "stampsTotal": total,
            "badge": sum(1 for n in c["badges"] if total >= n),
            "today": {"spent": -st.ledger_sum(p["id"], day, (COIN_BUY,)),
                      "won": st.ledger_sum(p["id"], day, PRIZE_SOURCES)},
            "jackpot": self.pool(st),
        }

    def state(self, token: str) -> dict[str, Any]:
        self.cfg
        g = self.game
        pid = player_id_for(token)
        now = g.now()
        p = g.store.get_player(pid, now)
        return self.view(g.store, p, day_of(now))

    def _answer(self, token: str, **extra: Any) -> dict[str, Any]:
        return {**self.game.status(token), "park": self.state(token), **extra}

    # ----------------------------------------------------------------- buying
    def buy(self, token: str, count: int) -> dict[str, Any]:
        """Buys [count] coins with shards: as many as the shards pay for, with no daily or holding limit."""
        c = self.coin
        g = self.game
        pid = player_id_for(token)
        if count < 1:
            raise GameError("bad_count", "数量不对")
        with g.store.transaction() as st:
            now = g.now()
            day = day_of(now)
            p = st.get_player(pid, now)
            if p["taps_total"] < c["minTaps"]:
                raise GameError("park_locked", "累计敲击 1 万下后开放")
            cost = count * c["price"]
            if p["shards"] < cost:
                raise GameError("no_shards", "碎片不足")
            st.update_player(pid, shards=p["shards"] - cost, coins=p["coins"] + count)
            st.add_ledger(pid, day, COIN_BUY, -cost, count)
            st.add_coin_ledger(pid, day, "buy", count, count)
        return self._answer(token)

    def gift(self, token: str) -> dict[str, Any]:
        """The free coin of the day. Status gives it already (Game.park_gift), so this answers `gift` 0 once the day's
        coin was given either way."""
        c = self.coin
        g = self.game
        pid = player_id_for(token)
        with g.store.transaction() as st:
            now = g.now()
            p = st.get_player(pid, now)
            if p["taps_total"] < c["minTaps"]:
                raise GameError("park_locked", "累计敲击 1 万下后开放")
            got = g.park_gift(p, day_of(now))
        return self._answer(token, gift=got)

    # ------------------------------------------------------------------ pool
    def pool(self, st: Store) -> int:
        """The lottery's top prize pool now; 0 on a park without the lottery."""
        cfg = (self.cfg.get("lottery") or {}).get("pool")
        return st.park_counter(POOL, cfg["seed"]) if cfg else 0

    def _feed(self, st: Store, coins: int) -> None:
        """Adds pool.perCoin shards per coin to the pool (takes them out for negative [coins]), never below 0."""
        cfg = (self.cfg.get("lottery") or {}).get("pool")
        if cfg:
            st.set_park_counter(POOL, max(0, self.pool(st) + coins * cfg["perCoin"]))

    # ------------------------------------------- for the games, in their transaction
    def spend(self, st: Store, pid: str, n: int, source: str, now: float) -> int:
        """Takes [n] coins, stamps each and feeds the lottery pool. Every stampsPerCoin stamps turn into a coin at
        once; returns how many did. Raises no_coins when the save holds fewer."""
        if n < 1:
            raise ValueError("spend at least one coin")
        p = st.get_player(pid, now)
        if p["coins"] < n:
            raise GameError("no_coins", "驼币不足")
        per = self.coin["stampsPerCoin"]
        total = p["stamps_total"] + n
        back = total // per - p["stamps_total"] // per
        st.update_player(pid, coins=p["coins"] - n + back, stamps_total=total)
        day = day_of(now)
        st.add_coin_ledger(pid, day, source, -n)
        if back:
            st.add_coin_ledger(pid, day, "stamp", back, back)
        self._feed(st, n)
        return back

    def grant(self, st: Store, pid: str, n: int, source: str, now: float) -> None:
        """Gives [n] coins whatever the save holds (prizes, codes)."""
        if n < 1:
            return
        p = st.get_player(pid, now)
        st.update_player(pid, coins=p["coins"] + n)
        st.add_coin_ledger(pid, day_of(now), source, n)

    def refund(self, st: Store, pid: str, n: int, source: str, now: float) -> None:
        """Undoes spend(n): the coins come back and their stamps go, with any coin those stamps had turned into, and
        the pool gives back what they fed it."""
        if n < 1:
            return
        p = st.get_player(pid, now)
        per = self.coin["stampsPerCoin"]
        total = max(0, p["stamps_total"] - n)
        lost = p["stamps_total"] // per - total // per
        st.update_player(pid, coins=max(0, p["coins"] + n - lost), stamps_total=total)
        day = day_of(now)
        st.add_coin_ledger(pid, day, source, n)
        if lost:
            st.add_coin_ledger(pid, day, "stamp", -lost, 0)
        self._feed(st, -n)

    # ------------------------------------------------------------------- news
    def nick(self, st: Store, pid: str) -> str:
        """The nick a win is told under: the board's (or room's) nick, masked."""
        lo = _loadout_json(st.loadouts([pid]).get(pid, ""))
        nick = lo.get("nick") if isinstance(lo.get("nick"), str) else ""
        return self.mask(nick or st.room_nicks([pid]).get(pid) or BOARD_DEFAULT_NICK)

    def announce(self, st: Store, kind: str, pid: str, now: float, **detail: Any) -> int:
        """Tells every running pet of a win (status `park.news`), in the caller's transaction."""
        return st.add_park_news(now, kind, pid, self.nick(st, pid), json.dumps(detail, ensure_ascii=False))

    def prune_news(self) -> int:
        g = self.game
        return g.store.prune_park_news(g.now() - NEWS_KEEP_DAYS * 86400)
