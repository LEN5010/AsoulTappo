"""The dumpling race's schedule, bets and settlement (design §6); the rules and the odds are in race.py.

Races run on wall-clock multiples of `interval`: bets for the first `betting` seconds, then the race plays and
is settled once its animation is over; the next race's bets open at the next boundary. A race is prepared ahead
(setup, seed, outcome) and stored; while bets are open only SHA-256(seed) is public, and at the start the seed and the
lanes and moves it decides are. The odds follow the coins staked so far; each bet keeps the odds it was placed at.
Everything is driven by tick(), which main.py calls about once a second off the event loop; tick() is idempotent.

A restart resumes whatever is stored: a race still taking bets goes on, a race that started is settled when due.
A race whose start the server missed by more than START_GRACE is called off and its bets refunded; it never runs
late.
"""
from __future__ import annotations

import json
import math
import random
import secrets
from typing import Any, Callable

from . import race
from .game import Game, GameError, player_id_for
from .park import Park
from .store import Store, day_of

# Ledger sources.
SPEND = "race"
REFUND = "race_refund"
PRIZE = "race_prize"
# Playback (PROTOCOL.md 团子赛跑): step i starts at startsAt + LEAD_MS + i × stepMs, and from slowFrom (the first move
# of the last round) on each step lasts slowMs; endsAt follows the last step by TAIL_MS. stepMs and slowMs are STEP_MS
# and SLOW_MS unless that would run past the next race's bets less RUN_MARGIN; then both are scaled down together.
LEAD_MS = 4000
STEP_MS = 2400
SLOW_MS = 3600
TAIL_MS = 4000
RUN_MARGIN = 10
# A race the server starts this late is still run; later than that it is called off.
START_GRACE = 5.0
# A race is not opened with fewer seconds of bets than this left (a server starting late in the window).
MIN_BETTING = 30
# Finished races keep their move list this long; the seed and setup reproduce it afterwards.
RESULT_KEEP_DAYS = 2
WINNERS = 5
SEED_BYTES = 32


class OddsChanged(GameError):
    """The selection's odds dropped below those the client showed; [odds] the current ones."""

    def __init__(self, odds: float) -> None:
        super().__init__("odds_changed", f"赔率变成了 {odds:.1f}")
        self.odds = odds


def slow_from(steps: int) -> int:
    """The first move of the last round (five moves a round)."""
    return 5 * ((steps - 1) // 5) if steps else 0


def playback_ms(steps: int, step_ms: int, slow_ms: int) -> int:
    """From startsAt to endsAt: the lead, the steps before the last round, the slow last round and the tail."""
    first = slow_from(steps)
    return LEAD_MS + first * step_ms + (steps - first) * slow_ms + TAIL_MS


def room_message(peer_id: str, shards: int) -> dict[str, Any]:
    """What a room hears of a member's race win (`race_win`; older clients ignore unknown messages)."""
    return {"type": "race_win", "id": peer_id, "shards": shards}


def _hit(kind: str, member: str, ranking: list[str]) -> bool:
    if kind == "win":
        return ranking[0] == member
    if kind == "top2":
        return member in ranking[:2]
    return ranking[-1] == member


class Races:
    def __init__(self, game: Callable[[], Game], park: Park, dealer: Any = None,
                 seeds: Callable[[], bytes] | None = None) -> None:
        # Tests pass a seeded dealer and fixed seeds.
        self._game = game
        self.park = park
        self.dealer = dealer or random.SystemRandom()
        self.seeds = seeds or (lambda: secrets.token_bytes(SEED_BYTES))

    @property
    def game(self) -> Game:
        return self._game()

    @property
    def cfg(self) -> dict[str, Any]:
        cfg = self.park.cfg.get("race")
        if not cfg:
            raise GameError("no_race", "这个服务器没有团子赛跑")
        return cfg

    @property
    def members(self) -> tuple[str, ...]:
        """The dumplings: the manifest's character ids, in manifest order."""
        return tuple(c["id"] for c in self.game.manifest.data["characters"])

    @property
    def rules(self) -> race.Rules:
        return race.Rules.of(self.cfg, self.members)

    @property
    def enabled(self) -> bool:
        park = self.game.manifest.park
        return bool(park and park.get("race"))

    # ------------------------------------------------------------- schedule
    def prepare(self, race_id: int) -> dict[str, Any]:
        """A new race whose bets open at [race_id] (unix seconds): setup, seed, outcome and playback timing."""
        cfg = self.cfg
        rules = self.rules
        setup = race.deal(rules, self.dealer)
        seed = self.seeds()
        outcome = race.run_seed(rules, setup, seed)
        starts = race_id + int(cfg["betting"])
        steps = len(outcome["moves"])
        window_ms = (int(cfg["interval"]) - int(cfg["betting"]) - RUN_MARGIN) * 1000
        step_ms, slow_ms = STEP_MS, SLOW_MS
        moving = playback_ms(steps, step_ms, slow_ms) - LEAD_MS - TAIL_MS
        room = window_ms - LEAD_MS - TAIL_MS
        if moving > room:
            step_ms = max(1, math.floor(STEP_MS * room / moving))
            slow_ms = max(1, math.floor(SLOW_MS * room / moving))
        return {"id": race_id, "starts_at": float(starts),
                "ends_at": starts + playback_ms(steps, step_ms, slow_ms) / 1000, "step_ms": step_ms,
                "slow_ms": slow_ms, "seed": seed.hex(), "hash": race.seed_hash(seed), "setup": json.dumps(setup),
                "ranking": json.dumps(outcome["ranking"]),
                "result": json.dumps({"start": outcome["start"], "moves": outcome["moves"]})}

    def tick(self) -> list[dict[str, Any]]:
        """Starts, settles or calls off the races that are due, then prepares the current and the next race when
        missing. Returns the wins to tell rooms of: [{pid, shards}]."""
        if not self.enabled:
            return []
        g = self.game
        now = g.now()
        wins: list[dict[str, Any]] = []
        for row in g.store.races_unsettled():
            if row["status"] == "open" and now >= row["starts_at"]:
                if now - row["starts_at"] <= START_GRACE:
                    self._start(row["id"])
                else:
                    self.void(row["id"])
                    continue
                row["status"] = "running"
            if row["status"] == "running" and now >= row["ends_at"]:
                wins += self.settle(row["id"])
        cfg = self.cfg
        interval = int(cfg["interval"])
        current = int(now // interval) * interval
        targets = [current + interval]
        if now < current + int(cfg["betting"]) - MIN_BETTING:
            targets.insert(0, current)
        for rid in targets:
            if g.store.race_get(rid) is None:
                g.store.race_insert(self.prepare(rid))
        g.store.race_prune_results(int(now) - RESULT_KEEP_DAYS * 86400)
        return wins

    def _start(self, race_id: int) -> None:
        with self.game.store.transaction() as st:
            row = st.race_get(race_id)
            if row and row["status"] == "open":
                st.race_set_status(race_id, "running")

    def void(self, race_id: int) -> int:
        """Calls off a race that never started: every save's coins come back (Park.refund). Returns the saves."""
        g = self.game
        with g.store.transaction() as st:
            row = st.race_get(race_id)
            if not row or row["status"] != "open":
                return 0
            now = g.now()
            staked: dict[str, int] = {}
            for bet in st.race_bets(race_id):
                staked[bet["player_id"]] = staked.get(bet["player_id"], 0) + bet["coins"]
            for pid, coins in staked.items():
                self.park.refund(st, pid, coins, REFUND, now)
            st.race_set_status(race_id, "void")
        return len(staked)

    def settle(self, race_id: int) -> list[dict[str, Any]]:
        """Pays a running race's winning bets once: coins × coin price × the bet's own odds shards each. Returns the
        saves whose prizes reach roomAt, with their prizes."""
        g = self.game
        cfg = self.cfg
        price = self.park.coin["price"]
        wins: list[dict[str, Any]] = []
        with g.store.transaction() as st:
            row = st.race_get(race_id)
            if not row or row["status"] != "running":
                return []
            now = g.now()
            day = day_of(now)
            ranking = json.loads(row["ranking"])
            prizes: dict[str, list[int]] = {}
            for bet in st.race_bets(race_id):
                if not _hit(bet["kind"], bet["member"], ranking):
                    continue
                prize = bet["coins"] * price * bet["odds"] // 10
                st.race_set_prize(bet["id"], prize)
                prizes.setdefault(bet["player_id"], []).append(prize)
            for pid, got in prizes.items():
                total = sum(got)
                p = st.get_player(pid, now)
                st.update_player(pid, shards=p["shards"] + total)
                st.add_ledger(pid, day, PRIZE, total, len(got))
                if total >= cfg["roomAt"]:
                    wins.append({"pid": pid, "shards": total})
            st.race_set_status(race_id, "settled")
        return wins

    # ------------------------------------------------------------------ bets
    def bet(self, token: str, race_id: int, kind: str, member: str, coins: int,
            shown: float | None = None) -> dict[str, Any]:
        """Stakes [coins] on (kind, member) of the race taking bets at the odds the stakes so far give; a save stakes
        at most maxCoins a race. [shown]: the odds the client showed; lower current odds refuse the bet (OddsChanged)
        and change nothing, higher ones are taken."""
        cfg = self.cfg
        g = self.game
        pid = player_id_for(token)
        members = self.members
        if kind not in cfg["kinds"] or member not in members:
            raise GameError("bad_bet", "没有这个选项")
        if coins < 1:
            raise GameError("bad_count", "数量不对")
        with g.store.transaction() as st:
            now = g.now()
            row = st.race_get(race_id)
            if row is None or row["id"] > now:
                raise GameError("no_race", "没有这一场")
            if row["status"] != "open" or now >= row["starts_at"]:
                raise GameError("race_closed", "这一场已停止下注")
            staked = sum(b["coins"] for b in st.race_bets(race_id, pid))
            if staked + coins > cfg["maxCoins"]:
                raise GameError("race_cap", f"每场最多押 {cfg['maxCoins']} 枚，这场还能押 "
                                            f"{max(0, cfg['maxCoins'] - staked)} 枚")
            odds = race.odds_tenths(cfg, kind, members, st.race_stakes(race_id).get(kind, {}))[member]
            # In tenths; the margin absorbs float noise in the shown number (1.1 × 10 is 11.000000000000002).
            if shown is not None and odds < shown * 10 - 1e-6:
                raise OddsChanged(odds / 10)
            self.park.spend(st, pid, coins, SPEND, now)
            st.race_add_bet(race_id, pid, kind, member, coins, odds, now)
        return {**g.status(token), "park": self.park.state(token), "race": self._race(g.store.race_get(race_id),
                                                                                       pid, g.now())}

    # ------------------------------------------------------------------ view
    def view(self, token: str) -> dict[str, Any]:
        """The race shown now (taking bets, running or the latest finished), the finished race before it, the
        latest winners, and when the next race's bets open."""
        cfg = self.cfg
        g = self.game
        pid = player_id_for(token)
        st = g.store
        now = g.now()
        interval = int(cfg["interval"])
        shown = st.race_shown(now)
        before = shown["id"] if shown else int(now) + 1
        if shown and shown["status"] == "settled":
            before += 1
        settled = st.races_settled(before, WINNERS)
        last = next((r for r in settled if not shown or r["id"] != shown["id"]), None)
        return {
            "now": now,
            "nextAt": (int(now // interval) + 1) * interval,
            "race": self._race(shown, pid, now) if shown else None,
            "last": self._race(last, pid, now) if last else None,
            "winners": [{"id": r["id"], "member": json.loads(r["ranking"])[0]} for r in settled],
        }

    def _race(self, row: dict[str, Any], pid: str, now: float) -> dict[str, Any]:
        status = row["status"]
        phase = {"open": "betting" if now < row["starts_at"] else "starting", "running": "running",
                 "settled": "done", "void": "void"}[status]
        st = self.game.store
        cfg = self.cfg
        members = self.members
        stakes = st.race_stakes(row["id"])
        odds = race.odds(cfg, members, stakes)
        mine = [{"kind": b["kind"], "member": b["member"], "coins": b["coins"], "odds": b["odds"] / 10,
                 **({"prize": b["prize"]} if status == "settled" else {})}
                for b in st.race_bets(row["id"], pid)]
        out: dict[str, Any] = {
            "id": row["id"], "phase": phase, "opensAt": row["id"], "startsAt": row["starts_at"],
            "hash": row["hash"], "setup": json.loads(row["setup"]),
            "odds": {kind: {m: t / 10 for m, t in per.items()} for kind, per in odds.items()},
            "pool": {kind: {m: stakes.get(kind, {}).get(m, 0) for m in members} for kind in cfg["kinds"]},
            "bettors": st.race_bettors(row["id"]), "mine": mine,
        }
        if status in ("running", "settled"):
            # Public from the start on: the seed and everything it decides.
            if row["result"]:
                result = json.loads(row["result"])
            else:
                outcome = race.run_seed(self.rules, json.loads(row["setup"]), bytes.fromhex(row["seed"]))
                result = {"start": outcome["start"], "moves": outcome["moves"]}
            out.update(seed=row["seed"], endsAt=row["ends_at"], leadMs=LEAD_MS, stepMs=row["step_ms"],
                       slowFrom=slow_from(len(result["moves"])), slowMs=row["slow_ms"], start=result["start"],
                       moves=result["moves"], ranking=json.loads(row["ranking"]))
        if status == "settled" and mine:
            staked = sum(b["coins"] for b in mine) * self.park.coin["price"]
            won = sum(b["prize"] for b in mine)
            out["result"] = {"staked": staked, "won": won, "net": won - staked}
        return out
