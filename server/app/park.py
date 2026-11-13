"""The park's coins: buying them with shards, the free one a day, spending them with stamps, and the news of big
wins every running pet hears of. The games (scratch cards, the race, the lottery) and redeem codes take and give
coins through Park.spend, Park.grant and Park.refund inside their own transactions."""
from __future__ import annotations

import json
from typing import Any, Callable

from .game import BOARD_DEFAULT_NICK, Game, GameError, _loadout_json, player_id_for
from .store import Store, day_of

# Shard ledger sources. COIN_BUY is what coins cost; PRIZE_SOURCES are the park's prizes, which the page sets against
# it as the day's result. Redeem codes are gifts, not winnings, and stay out of that result.
COIN_BUY = "coin_buy"
PRIZE_SOURCES = ("park_scratch", "jackpot", "race_prize", "lottery_prize")
REDEEM = "redeem"
# Coin ledger sources besides the spending of each game (named by the game: "scratch", "race", "lottery").
COIN_SOURCES = ("buy", "gift", "stamp", "scratch_again", "race_refund", "redeem", "admin")
# park_counters key of the scratch jackpot (the scratch module keeps it).
JACKPOT = "jackpot"
# News older than this goes on the next start.
NEWS_KEEP_DAYS = 7


class Park:
    def __init__(self, game: Callable[[], Game], mask: Callable[[str], str] = lambda s: s) -> None:
        # The game may be replaced (tests), so it is looked up on every call, as in Duels.
        self._game = game
        self.mask = mask
        # Set by the scratch cards: the pot a save's unrevealed jackpot card took, None when it holds none. view shows
        # that save this amount instead of the restarted pot, so the restart gives nothing away before the reveal.
        self.held_pot: Callable[[Store, str], int | None] = lambda st, pid: None

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
        """The save's coins, today's free coin, stamps and today's result, and the jackpot."""
        c = self.coin
        total = p["stamps_total"]
        scratch = self.cfg.get("scratch") or {}
        seed = (scratch.get("jackpot") or {}).get("seed", 0)
        return {
            "coins": p["coins"],
            "unlocked": p["taps_total"] >= c["minTaps"],
            "gift": p["gift_day"] != day,
            "stamps": total % c["stampsPerCoin"],
            "stampsTotal": total,
            "badge": sum(1 for n in c["badges"] if total >= n),
            "today": {"spent": -st.ledger_sum(p["id"], day, (COIN_BUY,)),
                      "won": st.ledger_sum(p["id"], day, PRIZE_SOURCES)},
            "jackpot": held if (held := self.held_pot(st, p["id"])) is not None else st.park_counter(JACKPOT, seed),
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
        """The free coin of the day, on the first visit; later visits that day get none (`gift` 0)."""
        c = self.coin
        g = self.game
        pid = player_id_for(token)
        with g.store.transaction() as st:
            now = g.now()
            day = day_of(now)
            p = st.get_player(pid, now)
            if p["taps_total"] < c["minTaps"]:
                raise GameError("park_locked", "累计敲击 1 万下后开放")
            got = 0
            if p["gift_day"] != day:
                got = c["gift"]
                st.update_player(pid, coins=p["coins"] + got, gift_day=day)
                st.add_coin_ledger(pid, day, "gift", got)
        return self._answer(token, gift=got)

    # ------------------------------------------- for the games, in their transaction
    def spend(self, st: Store, pid: str, n: int, source: str, now: float) -> int:
        """Takes [n] coins and stamps each. Every stampsPerCoin stamps turn into a coin at once; returns how many
        did. Raises no_coins when the save holds fewer."""
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
        return back

    def grant(self, st: Store, pid: str, n: int, source: str, now: float) -> None:
        """Gives [n] coins whatever the save holds (prizes, codes)."""
        if n < 1:
            return
        p = st.get_player(pid, now)
        st.update_player(pid, coins=p["coins"] + n)
        st.add_coin_ledger(pid, day_of(now), source, n)

    def refund(self, st: Store, pid: str, n: int, source: str, now: float) -> None:
        """Undoes spend(n): the coins come back and their stamps go, with any coin those stamps had turned into."""
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
