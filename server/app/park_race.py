"""The dumpling race's schedule, bets and settlement (design §6); the rules and the odds are in race.py.

Races run on wall-clock boundaries `interval` apart (multiples of it, or placed by `startAt` so that every race starts
at that minute of the China day: one a day at 19:00): bets for the first `betting` seconds, then the race plays and
is settled once its animation is over; the next race's bets open at the next boundary. A race is prepared ahead
(setup, seed, outcome) and stored; while bets are open only SHA-256(seed) is public, and at the start the seed and
the lanes, order, dice and moves it decides are. The setup deals each member a form (its die for the race) and
carries each member's chance of each place under it, counted over `sims` simulated races; the odds open at those
chances and follow the coins staked so far, never past fairCap of the fair odds; each bet keeps the odds it was
placed at. Races dealt before forms open from the members' popularity instead.
Everything is driven by tick(), which main.py calls about once a second off the event loop; tick() is idempotent.

A restart resumes whatever is stored: a race still taking bets goes on, a race that started is settled when due.
A race whose start the server missed by more than START_GRACE is called off and its bets refunded; it never runs
late.

Every race keeps its move list for good, so a finished race can be played again as it ran (history(), replay()).
Servers before 1.2.4 dropped the lists after two days; such a race is played again only when its seed, run by the
current rules, still gives the ranking and the end it was settled with (played()), and otherwise shows its result only.
"""
from __future__ import annotations

import json
import logging
import math
import random
import secrets
from functools import lru_cache
from typing import Any, Callable, Iterable, Literal

from . import race
from .notice import version_key
from .game import Game, GameError, player_id_for
from .park import Park
from .store import DAY_OFFSET, Store, day_of

# Coin ledger sources.
SPEND = "race"
REFUND = "race_refund"
PRIZE = "race_prize"
# Playback (PROTOCOL.md 团子赛跑): the opening (the dice for the order) takes lead_ms(rounds of dice); then each round
# of five moves starts with rollMs, everyone's die thrown together, and its steps follow, stepMs each, and slowMs each
# from slowFrom (the first move of the last round) on; endsAt follows the last step by TAIL_MS. stepMs and slowMs are
# STEP_MS and SLOW_MS unless that would run past the next race's bets less RUN_MARGIN; then both are scaled down
# together, and rollMs with them (roll_ms()). The lead is never scaled.
#
# A step opens with a close-up (cutMs before it moves) the first time a member's skill is at work in the race: the
# skill named and explained, once a member (cuts_of()). cutMs is CUT_MS, scaled as the steps are (cut_ms()).
#
# ROLL_MS, STEP_MS and CUT_MS keep their ratios: a stored race's dice and close-ups are worked out from its step_ms.
#
# A race on a map or with skills is paced by the square instead (paced_times()): a step lasts as long as what it
# shows. The mover is lit for PACE lit, the group hops PACE hop a square, a special square that acts takes PACE gap
# and then PACE hop for each square it pushes (PACE act where it moves no squares: a portal, a flip, a climb), and
# the step rests for PACE rest; the last round's steps are SLOW_MS / STEP_MS as long. Its rounds' dice take
# PACED_ROLL_MS and its close-ups PACED_CUT_MS. The race row keeps these times with its moves (result.times), and
# they are scaled together when the race would run past its window.
LEAD_MS = 4000
REROLL_MS = 1500
ROLL_MS = 4800
STEP_MS = 5000
SLOW_MS = 6600
CUT_MS = 2600
TAIL_MS = 4000
PACE = {"lit": 600, "hop": 360, "gap": 150, "act": 600, "rest": 500}
PACED_ROLL_MS = 2800
PACED_CUT_MS = 2000
# Moves a round: one for each member, in the order.
ROUND = 5
RUN_MARGIN = 10
# A race the server starts this late is still run; later than that it is called off.
START_GRACE = 5.0
# A race is not opened with fewer seconds of bets than this left (a server starting late in the window).
MIN_BETTING = 30
WINNERS = 5
# Finished races the history lists, newest first.
HISTORY = 30
SEED_BYTES = 32
# Simulated races behind a race's chances when the manifest names no `sims`.
SIMS = 20000


# The first client that plays a race run on a map or with skills; older ones get such a race's result only.
MAPS_SINCE = (1, 2, 5)
RaceView = Literal["full", "summary", "schedule"]
log = logging.getLogger(__name__)


def plays_maps(version: str | None) -> bool:
    """Whether a client reporting [version] can play a race on a map or with skills (a pre-release as its release)."""
    key = version_key(version)
    return key is not None and key[:3] >= MAPS_SINCE


class OddsChanged(GameError):
    """The selection's odds dropped below those the client showed; [odds] the current ones."""

    def __init__(self, odds: float) -> None:
        super().__init__("odds_changed", f"赔率变成了 {odds:.1f}")
        self.odds = odds


def opened_at(cfg: dict[str, Any], now: float) -> int:
    """The boundary at or before [now]: when the race taking bets from then on opened them. Boundaries are `interval`
    apart, shifted by `startAt` (a minute of the China day, optional) so that a race starts at that minute."""
    interval = int(cfg["interval"])
    at = cfg.get("startAt")
    offset = 0 if at is None else (int(at) * 60 - DAY_OFFSET - int(cfg["betting"])) % interval
    return int((now - offset) // interval) * interval + offset


def slow_from(steps: int) -> int:
    """The first move of the last round (five moves a round)."""
    return ROUND * ((steps - 1) // ROUND) if steps else 0


def roll_ms(step_ms: int) -> int:
    """How long a round's dice take, for steps of [step_ms]: ROLL_MS, scaled as the steps are."""
    return step_ms * ROLL_MS // STEP_MS


def cut_ms(step_ms: int) -> int:
    """How long a close-up holds a step back, for steps of [step_ms]: CUT_MS, scaled as the steps are."""
    return step_ms * CUT_MS // STEP_MS


def cuts_of(moves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The steps that open with a close-up, `{at, m}`: the first step in which each member's skill is at work, the
    mover's own before that of a climber the group lands on. One close-up a step: a second member whose skill shows
    for the first time in the same step gets its own the next time."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for i, move in enumerate(moves):
        at_work = ([move["m"]] if move.get("skill") else []) + list(move.get("react") or [])
        for m in at_work:
            if m not in seen:
                seen.add(m)
                out.append({"at": i, "m": m})
                break
    return out


def pushed(move: dict[str, Any]) -> int | None:
    """What a special square does in [move], in squares walked: None when it does nothing, 0 when it moves the
    group without walking it (a portal, a flip, a climb onto the top)."""
    if move.get("end") is None and not move.get("stack"):
        return None
    if move.get("square") in ("boost", "trip", "again", "hook") and move.get("end") is not None:
        return max(1, abs(move["end"] - move["to"]))
    return 0


def paced_times(moves: list[dict[str, Any]], scale: float = 1.0) -> dict[str, Any]:
    """The times of a race paced by the square, ms, at [scale] of full length: `pace` (PACE scaled), each step's
    length in `steps`, a round's dice in `roll` and a close-up in `cut`."""
    pace = {k: max(1, math.floor(v * scale)) for k, v in PACE.items()}
    first = slow_from(len(moves))
    steps = []
    for i, move in enumerate(moves):
        t = pace["lit"] + max(0, int(move["steps"])) * pace["hop"] + pace["rest"]
        push = pushed(move)
        if push is not None:
            t += pace["gap"] + (push * pace["hop"] if push else pace["act"])
        steps.append(t if i < first else t * SLOW_MS // STEP_MS)
    return {"pace": pace, "steps": steps, "roll": max(1, math.floor(PACED_ROLL_MS * scale)),
            "cut": max(1, math.floor(PACED_CUT_MS * scale))}


def paced_ms(times: dict[str, Any], cuts: int) -> int:
    """How long the rounds' dice, the steps and [cuts] close-ups of a paced race take together."""
    rounds = -(-len(times["steps"]) // ROUND)
    return rounds * times["roll"] + sum(times["steps"]) + cuts * times["cut"]


def lead_ms(rounds: int) -> int:
    """From startsAt to the first step: the first round of the order's dice, each round rolled again, then a pause."""
    return LEAD_MS + max(0, rounds - 1) * REROLL_MS


def playback_ms(lead: int, steps: int, step_ms: int, slow_ms: int, roll: int | None = None, cuts: int = 0) -> int:
    """From startsAt to endsAt: the lead, each round's dice ([roll], roll_ms(step_ms) when None), the steps before the
    last round, the slow last round, [cuts] close-ups and the tail."""
    first = slow_from(steps)
    rounds = -(-steps // ROUND)
    roll = roll_ms(step_ms) if roll is None else roll
    return lead + rounds * roll + first * step_ms + (steps - first) * slow_ms + cuts * cut_ms(step_ms) + TAIL_MS


def _result(outcome: dict[str, Any]) -> dict[str, Any]:
    """What a race row keeps of its outcome (the ranking has its own column)."""
    return {**{k: outcome[k] for k in ("start", "order", "rolls", "moves", "rest")}, "cuts": cuts_of(outcome["moves"])}


def room_message(peer_id: str, coins: int) -> dict[str, Any]:
    """What a room hears of a member's race win (`race_win`; older clients ignore unknown messages)."""
    return {"type": "race_win", "id": peer_id, "coins": coins}


def payout(tenths: Iterable[int]) -> int:
    """The coins a save gets for its bets on one race: each winning bet's prize is coins × odds in tenths of a coin
    (0 for a losing bet); their sum is rounded half up to whole coins, in integers. Settlement pays this and the view
    shows it, so the two always agree."""
    return (sum(tenths) + 5) // 10


def _hit(kind: str, member: str, ranking: list[str]) -> bool:
    if kind == "win":
        return ranking[0] == member
    if kind == "top2":
        return member in ranking[:2]
    return ranking[-1] == member


@lru_cache(maxsize=2)
def _settled_market(store: Store, race_id: int) -> tuple[dict[str, dict[str, int]], int]:
    """The settled race's public totals are shared by every viewer."""
    return store.race_stakes(race_id), store.race_bettors(race_id)


class Races:
    def __init__(self, game: Callable[[], Game], park: Park, dealer: Any = None,
                 seeds: Callable[[], bytes] | None = None) -> None:
        # Tests pass a seeded dealer and fixed seeds.
        self._game = game
        self.park = park
        self.dealer = dealer or random.SystemRandom()
        self.seeds = seeds or (lambda: secrets.token_bytes(SEED_BYTES))
        self._failed_slots: set[int] = set()

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
        # Drawn after the squares from the same dealer, so the squares come out as before; public with the setup.
        forms = race.deal_skills(rules, self.dealer) or race.deal_forms(rules, self.dealer)
        if forms:
            setup.update(forms)
        else:
            popularity = race.draw_popularity(cfg, self.members, self.dealer)
            if popularity:
                setup["popularity"] = popularity
        seed = self.seeds()
        outcome = race.run_seed(rules, setup, seed)
        if forms:
            # Simulated on a stream of its own, seeded from the dealer: nothing to do with the race's seed.
            sim = race.SimRng(self.dealer.getrandbits(64))
            setup["chance"] = race.chances(rules, setup, int(cfg.get("sims", SIMS)), sim)
        starts = race_id + int(cfg["betting"])
        steps = len(outcome["moves"])
        lead = lead_ms(len(outcome["rolls"]))
        window_ms = (int(cfg["interval"]) - int(cfg["betting"]) - RUN_MARGIN) * 1000
        step_ms, slow_ms = STEP_MS, SLOW_MS
        cuts = len(cuts_of(outcome["moves"]))
        room = window_ms - lead - TAIL_MS
        result = _result(outcome)
        if setup.get("map") or setup.get("skills"):
            times = paced_times(outcome["moves"])
            moving = paced_ms(times, cuts)
            if moving > room:
                # Every time shrinks by the same factor; rounding down only ever shortens.
                step_ms = max(1, math.floor(STEP_MS * room / moving))
                slow_ms = max(1, math.floor(SLOW_MS * room / moving))
                times = paced_times(outcome["moves"], room / moving)
            result["times"] = times
            length = lead + paced_ms(times, cuts) + TAIL_MS
        else:
            moving = playback_ms(0, steps, step_ms, slow_ms, cuts=cuts) - TAIL_MS
            if moving > room:
                # Every share shrinks by the same factor; rounding down only ever shortens.
                step_ms = max(1, math.floor(STEP_MS * room / moving))
                slow_ms = max(1, math.floor(SLOW_MS * room / moving))
            length = playback_ms(lead, steps, step_ms, slow_ms, cuts=cuts)
        return {"id": race_id, "starts_at": float(starts), "ends_at": starts + length / 1000, "step_ms": step_ms,
                "slow_ms": slow_ms, "seed": seed.hex(), "hash": race.seed_hash(seed), "setup": json.dumps(setup),
                "ranking": json.dumps(outcome["ranking"]), "result": json.dumps(result)}

    def tick(self) -> list[dict[str, Any]]:
        """Starts, settles or calls off the races that are due, then prepares the current and the next race when
        missing. Returns the wins to tell rooms of: [{pid, coins}]."""
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
        current = opened_at(cfg, now)
        self._failed_slots.intersection_update((current, current + interval))
        targets = [current + interval]
        if now < current + int(cfg["betting"]) - MIN_BETTING:
            targets.insert(0, current)
        for rid in targets:
            if rid not in self._failed_slots and g.store.race_get(rid) is None:
                try:
                    prepared = self.prepare(rid)
                except race.UnfinishedRace as e:
                    self._failed_slots.add(rid)
                    log.error("race %s could not be prepared: %s", rid, e)
                    continue
                g.store.race_insert(prepared)
        return wins

    def _start(self, race_id: int) -> None:
        with self.game.store.transaction() as st:
            row = st.race_get(race_id)
            if row and row["status"] == "open":
                st.race_set_status(race_id, "running")

    def void(self, race_id: int) -> int:
        """Calls off a race that never started: every save's coins come back (Park.refund). Returns the saves."""
        g = self.game
        st = g.store
        while True:
            staked, count = st.race_refunds(race_id)
            with st.transaction(immediate=True):
                row = st.race_get(race_id)
                if not row or row["status"] != "open":
                    return 0
                if st.race_bet_count(race_id) != count:
                    continue
                now = g.now()
                for pid, coins in staked.items():
                    self.park.refund(st, pid, coins, REFUND, now)
                st.race_set_status(race_id, "void")
                return len(staked)

    def settle(self, race_id: int) -> list[dict[str, Any]]:
        """Pays a running race's winning bets once, in coins: each bet's prize is coins × its own odds in tenths of a
        coin, and each save gets payout() of its prizes on the race (coin ledger PRIZE). Returns the saves whose
        prizes reach roomAt, with their coins."""
        g = self.game
        cfg = self.cfg
        st = g.store
        row = st.race_get(race_id)
        if not row or row["status"] != "running":
            return []
        # Starting the race closed its bets, so the market stays fixed through settlement.
        ranking = json.loads(row["ranking"])
        prizes: list[tuple[int, int]] = []
        tenths: dict[str, int] = {}
        for bet in st.race_settlement_bets(race_id):
            if _hit(bet["kind"], bet["member"], ranking):
                prize = bet["coins"] * bet["odds"]
                prizes.append((prize, bet["id"]))
                pid = bet["player_id"]
                tenths[pid] = tenths.get(pid, 0) + prize
        paid = {pid: payout((total,)) for pid, total in tenths.items()}
        wins = [{"pid": pid, "coins": coins} for pid, coins in paid.items() if coins >= cfg["roomAt"]]
        with st.transaction(immediate=True):
            row = st.race_get(race_id)
            if not row or row["status"] != "running":
                return []
            now = g.now()
            st.race_set_prizes(prizes)
            st.add_park_payouts("coins", day_of(now), PRIZE, {pid: n for pid, n in paid.items() if n > 0}, now)
            st.race_set_status(race_id, "settled")
        return wins

    # ------------------------------------------------------------------ bets
    def bet(self, token: str, race_id: int, kind: str, member: str, coins: int,
            shown: float | None = None, version: str | None = None) -> dict[str, Any]:
        """Stakes [coins] on (kind, member) of the race taking bets at the odds the stakes so far give; a save stakes
        at most maxCoins a race (no cap when it is 0 or missing). [shown]: the odds the client showed; lower current odds refuse the bet (OddsChanged)
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
            most = cfg.get("maxCoins") or 0
            bets = st.race_bets(race_id, pid)
            staked = sum(b["coins"] for b in bets)
            if most and staked + coins > most:
                raise GameError("race_cap", f"每场最多押 {most} 枚，这场还能押 {max(0, most - staked)} 枚")
            setup = json.loads(row["setup"])
            stakes = st.race_stakes(race_id)
            selection = stakes.setdefault(kind, {})
            odds = race.odds_tenths(cfg, kind, members, selection, setup.get("popularity"), setup.get("chance"))[member]
            # In tenths; the margin absorbs float noise in the shown number (1.1 × 10 is 11.000000000000002).
            if shown is not None and odds < shown * 10 - 1e-6:
                raise OddsChanged(odds / 10)
            self.park.spend(st, pid, coins, SPEND, now)
            st.race_add_bet(race_id, pid, kind, member, coins, odds, now)
            selection[member] = selection.get(member, 0) + coins
            bettors = st.race_bettors(race_id)
            bets.append({"kind": kind, "member": member, "coins": coins, "odds": odds})
        answer = self.park._answer(token)
        return {**answer, "race": self._race(row, pid, g.now(), version, market=(stakes, bettors), bets=bets)}

    # ------------------------------------------------------------------ view
    def view(self, token: str, version: str | None = None, view: RaceView = "full") -> dict[str, Any]:
        """The race shown now (taking bets, running or the latest finished), the finished race before it, the
        latest winners, and when the next race's bets open. [version] is the client's: one from before maps and
        skills gets the result of a race run with them, without the moves it could not play."""
        cfg = self.cfg
        g = self.game
        pid = player_id_for(token)
        st = g.store
        now = g.now()
        interval = int(cfg["interval"])
        shown = st.race_shown(now, schedule=view == "schedule")
        next_at = opened_at(cfg, now) + interval
        if view == "schedule":
            current = None
            if shown:
                phase = self._phase(shown, now)
                current = {"id": shown["id"], "phase": phase, "startsAt": shown["starts_at"]}
                if phase in ("running", "done"):
                    current["endsAt"] = shown["ends_at"]
            return {"now": now, "nextAt": next_at, "race": current}
        before = shown["id"] if shown else int(now) + 1
        if shown and shown["status"] == "settled":
            before += 1
        settled = st.races_settled(before, WINNERS)
        last = next((r for r in settled if not shown or r["id"] != shown["id"]), None)
        return {
            "now": now,
            "nextAt": next_at,
            "race": self._race(shown, pid, now, version, playback=view == "full") if shown else None,
            "last": self._race(last, pid, now, version, playback=view == "full") if last else None,
            "winners": [{"id": r["id"], "member": json.loads(r["ranking"])[0]} for r in settled],
        }

    def played(self, row: dict[str, Any]) -> dict[str, Any] | None:
        """What a started race played ({start, order, rolls, moves, rest}): its stored move list, or, on a row whose
        list a server before 1.2.4 dropped, its seed run again by the current rules, only when that gives the ranking
        and the end the race was settled with. None otherwise: the rules changed since, and only the result stands."""
        if row["result"]:
            return json.loads(row["result"])
        try:
            again = race.run_seed(self.rules, json.loads(row["setup"]), bytes.fromhex(row["seed"]))
        except (KeyError, IndexError, TypeError, ValueError):
            return None
        if again["ranking"] != json.loads(row["ranking"]):
            return None
        # The end pins the number of steps and of the opening's rounds as the race played them.
        ends = row["starts_at"] + playback_ms(lead_ms(len(again["rolls"])), len(again["moves"]), row["step_ms"],
                                              row["slow_ms"], cuts=len(cuts_of(again["moves"]))) / 1000
        if abs(ends - row["ends_at"]) > 1e-3:
            return None
        return _result(again)

    def history(self, token: str, version: str | None = None) -> dict[str, Any]:
        """The latest HISTORY finished races, newest first: each one's China day (of its start), the ranking of a
        settled race and whether it can be played again, and the save's bets on it in coins."""
        g = self.game
        pid = player_id_for(token)
        rows = g.store.races_past(HISTORY)
        bets: dict[int, list[dict[str, Any]]] = {}
        for b in g.store.race_bets_in([r["id"] for r in rows], pid):
            bets.setdefault(b["race_id"], []).append(b)
        out = []
        for r in rows:
            item: dict[str, Any] = {"id": r["id"], "day": day_of(r["starts_at"]), "startsAt": r["starts_at"]}
            mine = bets.get(r["id"], [])
            staked = sum(b["coins"] for b in mine)
            if r["status"] == "void":
                item["phase"] = "void"
                if mine:
                    # Refunded in full.
                    item["mine"] = {"staked": staked, "net": 0}
            else:
                setup = json.loads(r["setup"])
                known = plays_maps(version) or not (setup.get("map") or setup.get("skills"))
                item.update(phase="done", ranking=json.loads(r["ranking"]),
                            replay=known and self.played(r) is not None)
                if mine:
                    won = payout(b["prize"] for b in mine)
                    item["mine"] = {"staked": staked, "won": won, "net": won - staked}
            out.append(item)
        return {"races": out}

    def replay(self, token: str, race_id: int, version: str | None = None) -> dict[str, Any]:
        """A settled race as the view gives it, to play again: 404 no_race unless it is settled, no_replay when its
        move list is gone (played())."""
        g = self.game
        row = g.store.race_get(race_id)
        if not row or row["status"] != "settled":
            raise GameError("no_race", "没有这一场")
        out = self._race(row, player_id_for(token), g.now(), version)
        if not out["replay"]:
            raise GameError("no_replay", "这一场没有回放")
        return {"race": out}

    @staticmethod
    def _phase(row: dict[str, Any], now: float) -> str:
        return {"open": "betting" if now < row["starts_at"] else "starting", "running": "running",
                "settled": "done", "void": "void"}[row["status"]]

    def _race(self, row: dict[str, Any], pid: str, now: float, version: str | None = None,
              playback: bool = True, *, market: tuple[dict[str, dict[str, int]], int] | None = None,
              bets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        status = row["status"]
        st = self.game.store
        cfg = self.cfg
        members = self.members
        if market is not None:
            stakes, bettors = market
        elif status == "settled":
            stakes, bettors = _settled_market(st, row["id"])
        else:
            stakes, bettors = st.race_stakes(row["id"]), st.race_bettors(row["id"])
        setup = json.loads(row["setup"])
        odds = race.odds(cfg, members, stakes, setup.get("popularity"), setup.get("chance"))
        if bets is None:
            bets = st.race_bets(row["id"], pid)
        # A settled bet's prize in coins, to a tenth (coins × odds); the save's total is payout() of them.
        mine = [{"kind": b["kind"], "member": b["member"], "coins": b["coins"], "odds": b["odds"] / 10,
                 **({"prize": b["prize"] / 10} if status == "settled" else {})}
                for b in bets]
        out: dict[str, Any] = {
            "id": row["id"], "phase": self._phase(row, now), "opensAt": row["id"], "startsAt": row["starts_at"],
            "hash": row["hash"], "setup": setup,
            "odds": {kind: {m: t / 10 for m, t in per.items()} for kind, per in odds.items()},
            "pool": {kind: {m: stakes.get(kind, {}).get(m, 0) for m in members} for kind in cfg["kinds"]},
            "bettors": bettors, "mine": mine,
        }
        if status in ("running", "settled"):
            # Public from the start on: the seed and everything it decides.
            out.update(seed=row["seed"], endsAt=row["ends_at"], ranking=json.loads(row["ranking"]))
            known = plays_maps(version) or not (setup.get("map") or setup.get("skills"))
            result = self.played(row) if known and (playback or not row["result"]) else None
            if playback and result is not None:
                # Rows from before the opening dice have no order and no rolls, and played after the plain LEAD_MS;
                # rows from before the rounds' dice have no rest, and played without them (rollMs 0).
                rolls = result.get("rolls")
                rest = result.get("rest")
                out.update(leadMs=lead_ms(len(rolls or [None])),
                           rollMs=roll_ms(row["step_ms"]) if rest is not None else 0, stepMs=row["step_ms"],
                           slowFrom=slow_from(len(result["moves"])), slowMs=row["slow_ms"], start=result["start"],
                           moves=result["moves"], rest=rest or [])
                # Rows from before the close-ups name none, and played without them.
                if result.get("cuts"):
                    out.update(cuts=result["cuts"], cutMs=cut_ms(row["step_ms"]))
                # A race paced by the square: its own times for the dice, the close-ups and every step.
                times = result.get("times")
                if times:
                    out.update(rollMs=times["roll"], stepsMs=times["steps"], pace=times["pace"])
                    if result.get("cuts"):
                        out["cutMs"] = times["cut"]
                if rolls:
                    out.update(order=result["order"], rolls=rolls)
            out["replay"] = known and (result is not None or bool(row["result"]))
        if status == "settled" and bets:
            staked = sum(b["coins"] for b in bets)
            won = payout(b["prize"] for b in bets)
            out["result"] = {"staked": staked, "won": won, "net": won - staked}
        return out
