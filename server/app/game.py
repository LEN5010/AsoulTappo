"""Server-authoritative tap income, resonance and item ownership."""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import date
from typing import Any, Callable, Literal

from . import cards as cardlogic
from . import scratch as scratchlogic
from .cards import DropConfig, Rng
from .manifest import Manifest
from .notice import version_key
from .store import DAY_OFFSET, Store, day_of
from .tracking import Tracker

TOKEN_MIN, TOKEN_MAX = 16, 128
MAX_REPORT_TAPS = 5000
MAX_ELAPSED = 120.0
MAX_FAVORITES = 8
# A tap session silent this long is pruned at startup; if it reports again it starts a new row.
SESSION_DAYS = 30
# Revealed scratch cards are kept this long; only the current day's are ever counted.
SCRATCH_DAYS = 30
# Days of shard ledger the admin save view shows.
ADMIN_LEDGER_DAYS = 7
# Admin log entries a save's admin page shows.
ADMIN_SAVE_LOG = 20
# Hex characters of a player id prefix the admin save search accepts (ids have 16).
SAVE_PREFIX_MIN, SAVE_PREFIX_MAX = 4, 16
# emote keys every member may send besides the starter emotes: thumbup, the theme's like burst
FREE_EMOTES = frozenset({"thumbup"})
# Cheer rounds in rooms (rooms.py pays per cheering save): a save gets at most CHEER_DAILY_CAP shards from them a China
# day; only saves with CHEER_MIN_TAPS taps in all put taps into rounds.
CHEER_DAILY_CAP = 1000
CHEER_MIN_TAPS = 10000
# Cards a player may pin to the profile room members open.
MAX_SHOWCASE = 3
# The nickname a save shows on the boards, as long as room nicknames.
MAX_BOARD_NICK = 24
# `nick` and `board` (false keeps the save off the boards) are only sent, never applied back by clients.
LOADOUT_KEYS = ("character", "favorites", "plate", "showcase", "nick", "board")
# Rows of the collection board, and how long a worked-out board is served before it is worked out again.
BOARD_SIZE = 50
BOARD_SECONDS = 300
BOARD_DEFAULT_NICK = "匿名小面包"
# Collection score: points for each item a save holds, about the draws it takes on average to find one (1 point is
# about 1 draw). Big hidden cards: 0.1% with a 400-draw pity, about 330 draws. Skins: 0.2% with a 200-draw pity,
# about 165. Epic cards (small hidden cards and epic normal cards share one 4.5% tier): about 22. Common cards: about
# 2. Emotes count about half their craft price (480, 960 and 1600 shards), so the 475 of them do not outweigh the
# cards; scratch emotes count as rare ones. Starter emotes count nothing.
BOARD_POINTS = {"big": 300, "skin": 150, "epic": 20, "card": 2,
                "emoteRare": 3, "emoteScratch": 3, "emoteUncommon": 2, "emote": 1}


def board_id(pid: str) -> str:
    """What the boards call a save: stable, and not its player id."""
    return hashlib.sha256(f"{pid}:board".encode()).hexdigest()[:12]


def board_kind(item: dict[str, Any], manifest: Manifest) -> str:
    """The BOARD_POINTS key of a collectible item (an entry of Manifest.items)."""
    if item["kind"] == "char":
        return "skin"
    if item["kind"] == "card":
        card = manifest.cards[item["id"][5:]]
        return "big" if card.get("tier") == "big" else "epic" if card.get("rarity") == "epic" else "card"
    if item["source"]:
        return "emoteScratch"
    return {"uncommon": "emoteUncommon", "rare": "emoteRare"}.get(item["rarity"], "emote")


def board_points(manifest: Manifest) -> dict[str, int]:
    """item id -> collection-score points, for every item that counts."""
    return {iid: BOARD_POINTS[board_kind(item, manifest)]
            for iid, item in manifest.items.items() if iid not in manifest.starter}


def _board_counts() -> dict[str, Any]:
    """A save's board counts before any item: [last] is when the last scoring item came, [last_card] the last card."""
    return {"cards": 0, "big": 0, "skins": 0, "score": 0, "last": 0.0, "last_card": 0.0}


def _loadout_json(raw: str) -> dict[str, Any]:
    try:
        out = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


class GameError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _nearest_rank(values: list[int], pct: int) -> int:
    """The [pct]th percentile of sorted [values] by nearest rank; 0 when empty."""
    if not values:
        return 0
    return values[max(1, math.ceil(pct / 100 * len(values))) - 1]


class PlayerId(str):
    """A player ID already resolved from a guest token or a linked main-site account."""


def player_id_for(token: str) -> str:
    if isinstance(token, PlayerId):
        return token
    if not (TOKEN_MIN <= len(token) <= TOKEN_MAX):
        raise GameError("bad_token", f"token must be {TOKEN_MIN}-{TOKEN_MAX} chars")
    return hashlib.sha256(token.encode()).hexdigest()[:16]


class Game:
    def __init__(self, store: Store, manifest: Manifest, cfg: DropConfig | None = None,
                 rng: Rng | None = None, now: Callable[[], float] = time.time) -> None:
        self.store = store
        self.manifest = manifest
        self.cfg = cfg or DropConfig()
        self.rng = rng or cardlogic.default_rng()
        self.now = now
        self.collectible_ids = frozenset(manifest.items) - manifest.starter
        self.board_points = board_points(manifest)
        # Counts, room samples and clients for the admin pages.
        self.tracker = Tracker(store, lambda: self.now())

    # ---------------------------------------------------------------- activity
    def report_activity(self, token: str, taps: int, session: str | None = None,
                        sequence: int = 0, cooldown: int = 0) -> dict[str, Any]:
        pid = player_id_for(token)
        taps = max(0, min(int(taps), MAX_REPORT_TAPS))
        cfg = self.cfg
        with self.store.transaction() as st:
            now = self.now()
            p = st.get_player(pid, now)
            today = day_of(now)
            if session is not None:
                last = st.activity_session(pid, session)
                if sequence <= last["sequence"]:
                    return {**self.status(token), "credited": 0}
                # Measured on what the session sent, before the budget clips it, so any rate above it still shows.
                fast_since = 0.0
                if 0 < last["last_at"] < now and taps / (now - last["last_at"]) >= cfg.fast_taps_per_sec:
                    fast_since = last["fast_since"] or last["last_at"]
                if fast_since and now - fast_since >= cfg.fast_streak_sec:
                    st.update_player(pid, tap_cooldown_until=now + cfg.tap_cooldown_sec)
                    p["tap_cooldown_until"], fast_since = now + cfg.tap_cooldown_sec, 0.0
                    st.add_tap_flags(today, pid, server=1)
                st.save_activity_sequence(pid, session, sequence, now, fast_since)
            # A cooldown the client's guard started: it only costs the player, so it is taken as sent.
            if cooldown and now + min(cooldown, cfg.tap_cooldown_sec) > p["tap_cooldown_until"]:
                # The client names the seconds left on every report of its cooldown; only a new one is counted.
                started = p["tap_cooldown_until"] <= now
                p["tap_cooldown_until"] = now + min(cooldown, cfg.tap_cooldown_sec)
                st.update_player(pid, tap_cooldown_until=p["tap_cooldown_until"])
                if started:
                    st.add_tap_flags(today, pid, client=1)
            if now < p["tap_cooldown_until"]:
                st.add_tap_flags(today, pid, dropped=taps)
                return {**self.status(token), "credited": 0}
            previous = p["last_activity"] or p["created"]
            elapsed = min(max(now - previous, 0.0), MAX_ELAPSED)
            budget = min(st.activity_budget(pid) + cfg.max_taps_per_sec * elapsed,
                         cfg.max_taps_per_sec * MAX_ELAPSED)
            credited = min(taps, math.floor(budget))
            st.add_tap_flags(today, pid, dropped=taps - credited)

            bucket = int(now // 60)
            minute_taps, counted = p["minute_taps"], p["minute_counted"]
            last_minute_taps = p["last_minute_taps"]
            if bucket != p["minute_bucket"]:
                last_minute_taps = minute_taps if bucket == p["minute_bucket"] + 1 else 0
                minute_taps, counted = 0, 0
            # Only the first tapsPerMinute taps of a minute pay shards.
            per_minute = self.manifest.income["tapsPerMinute"]
            paid_taps = min(minute_taps + credited, per_minute) - min(minute_taps, per_minute)
            minute_taps += credited
            active_minutes = p["active_minutes"]
            if not counted and minute_taps >= cfg.min_taps_active_minute:
                counted = 1
                active_minutes += 1

            day_taps = p["day_taps"] if p["tap_day"] == today else 0
            day_taps_total = p["day_taps_total"] if p["tap_day"] == today else 0
            earned = p["shard_remainder"] + self._tap_shards(day_taps + paid_taps) - self._tap_shards(day_taps)
            # Absorb floating-point noise at whole-shard boundaries.
            whole = int(earned + 1e-9)
            st.update_player(
                pid, taps_total=p["taps_total"] + credited, active_minutes=active_minutes,
                last_activity=max(now, previous), last_minute_taps=last_minute_taps,
                minute_bucket=bucket, minute_taps=minute_taps, minute_counted=counted,
                shards=p["shards"] + whole, shard_remainder=max(0.0, earned - whole),
                tap_day=today, day_taps=day_taps + paid_taps, day_taps_total=day_taps_total + credited)
            if whole or credited:
                st.add_ledger(pid, today, "tap", whole, credited)
            st.save_activity_budget(pid, budget - credited)
            if credited:
                st.mark_active(pid, today)
        out = self.status(token)
        out["credited"] = credited
        # Taps for the room's cheer round (popped by the server before answering): those that paid shards.
        out["cheerTaps"] = paid_taps if p["taps_total"] + credited >= CHEER_MIN_TAPS else 0
        return out

    def cheer_reward(self, pids: list[str], each: int) -> dict[str, int]:
        """Pays a finished cheer round: [each] shards to each save, less what would pass CHEER_DAILY_CAP today.
        Returns what each save got (0 once its cap is reached)."""
        out: dict[str, int] = {}
        with self.store.transaction() as st:
            now = self.now()
            day = day_of(now)
            for pid in dict.fromkeys(pids):
                if not st.has_player(pid):
                    continue
                got = max(0, min(each, CHEER_DAILY_CAP - st.ledger_amount(pid, day, "cheer")))
                out[pid] = got
                if got:
                    st.update_player(pid, shards=st.get_player(pid, now)["shards"] + got)
                    st.add_ledger(pid, day, "cheer", got)
        return out

    # ------------------------------------------------------------------ income
    def presence(self, token: str, session: str) -> dict[str, Any]:
        """Marks a running client online for today's statistics. Being online pays nothing; taps do.
        [session] is accepted from clients but no longer recorded."""
        pid = player_id_for(token)
        with self.store.transaction() as st:
            now = self.now()
            st.get_player(pid, now)
            st.mark_active(pid, day_of(now))
        return self.status(token)

    def _tap_shards(self, taps: float) -> float:
        """Shards one China day's paid taps earn in all: a log curve that stops at the daily cap."""
        inc = self.manifest.income
        return min(inc["shardScale"] * math.log1p(taps / inc["tapScale"]), inc["dailyCap"])

    def _income(self, p, day: str) -> dict[str, Any]:
        inc = self.manifest.income
        taps = p["day_taps"] if p["tap_day"] == day else 0
        today = self._tap_shards(taps)
        per_tap = inc["shardScale"] / (inc["tapScale"] + taps) if today < inc["dailyCap"] else 0.0
        return {"day": day, "today": int(today + 1e-9), "cap": inc["dailyCap"], "taps": taps, "perTap": round(per_tap, 3),
                # Shown by 1.0 clients, which predate the tap curve: no multiplier, and what a minute of
                # typing at 60 taps pays from here.
                "multiplier": 1, "perMinute": round(per_tap * 60, 1)}

    def resonate(self, token: str, count: int = 1, version: str | None = None) -> dict[str, Any]:
        """[version] is the client's: skins it cannot show stay out of its pool (see Manifest.resonance_pool_for)."""
        pool = self.manifest.resonance_pool_for(version)
        pid = player_id_for(token)
        cfg = self.manifest.resonance
        drops = []
        with self.store.transaction() as st:
            now = self.now()
            p = st.get_player(pid, now)
            if p["shards"] < cfg["cost"]:
                raise GameError("no_shards", "碎片不足")
            n = min(max(1, count), 100, p["shards"] // cfg["cost"])
            pity = {"legendary": p["draw_pity"], "skin": p["skin_pity"]}
            owned = st.owned(pid)
            refund = 0
            increments: dict[str, int] = {}
            missing = {r: [item for item in items if item["id"] not in owned] for r, items in pool.items()}
            common = {kind: [item for item in pool["common"] if item["kind"] == kind]
                      for kind in cfg["commonKindWeights"]}
            common_missing = {kind: [item for item in items if item["id"] not in owned]
                              for kind, items in common.items()}
            # A tier with nothing left to find drops out and its odds go to common, unless it keeps rolling repeats.
            repeating = set(cfg.get("repeatTiers", ()))
            for _ in range(n):
                available = {r for r in missing if missing[r]} | repeating
                rarity = cardlogic.roll_tier(cfg["rates"], available, pity, cfg["pity"], self.rng)
                candidates = missing[rarity] or pool[rarity]
                if rarity == "common":
                    item = cardlogic.pick_common_group(
                        [(weight, common_missing[kind] or common[kind])
                         for kind, weight in cfg["commonKindWeights"].items() if common[kind]], self.rng)
                else:
                    item = candidates[min(int(self.rng.random() * len(candidates)), len(candidates) - 1)]
                iid = item["id"]
                fresh = iid not in owned
                gained = 0 if fresh else self.duplicate_shards(iid)
                refund += gained
                # A repeat that turns into shards is not kept.
                if fresh or not gained:
                    owned[iid] = owned.get(iid, 0) + 1
                    increments[iid] = increments.get(iid, 0) + 1
                if fresh:
                    missing[rarity].remove(item)
                    if rarity == "common":
                        common_missing[item["kind"]].remove(item)
                for r in pity:
                    pity[r] = 0 if rarity == r else pity[r] + 1
                drop = {"item": iid, "rarity": rarity, "new": fresh, "count": owned[iid], "shards": gained}
                if item["kind"] == "card":
                    drop["tier"] = self.manifest.cards[iid[5:]]["tier"]
                drops.append(drop)
            st.add_items(pid, increments, now)
            st.log_drops(pid, drops, now)
            st.update_player(pid, shards=p["shards"] - n * cfg["cost"] + refund,
                             draw_pity=pity["legendary"], skin_pity=pity["skin"], drawn_total=p["drawn_total"] + n)
            day = day_of(now)
            st.add_ledger(pid, day, "draw", -n * cfg["cost"], n)
            if refund:
                st.add_ledger(pid, day, "duplicate", refund, sum(1 for d in drops if d["shards"] > 0))
        return {**self.status(token), "drops": drops}

    # ------------------------------------------------------------------- craft
    def duplicate_shards(self, item_id: str) -> int:
        """Shards a repeat of this item turns into: emotes alike, cards by tier."""
        refunds = self.manifest.resonance["duplicateRefund"]
        if item_id.startswith("emote:"):
            return int(refunds.get("emote", 0))
        card = self.manifest.cards.get(item_id[5:]) if item_id.startswith("card:") else None
        return int(refunds.get(card["tier"], 0)) if card else 0

    def refund_duplicate_cards(self) -> tuple[int, int]:
        """Once per database: cards kept as repeats before 1.1 turn into shards. Returns (players, shards)."""
        return self.store.refund_duplicates("duplicate-cards-1.1", "card:", self.duplicate_shards, self.now())

    def prune_activity_sessions(self) -> int:
        """Forgets tap sessions silent for SESSION_DAYS (one row per client launch). Returns rows removed."""
        return self.store.prune_activity_sessions(self.now() - SESSION_DAYS * 86400)

    def craft(self, token: str, item_id: str) -> dict[str, Any]:
        """Spend shards on a chosen missing item."""
        pid = player_id_for(token)
        now = self.now()
        item = self.manifest.items.get(item_id)
        cost = self.manifest.craft_cost.get(item["rarity"] or "") if item else None
        if (item is None or item["kind"] not in ("emote", "card") or item["source"]
                or item_id in self.manifest.starter or cost is None):
            raise GameError("bad_item", "unknown item")
        with self.store.transaction() as st:
            p = st.get_player(pid, now)
            if item_id in st.owned(pid):
                raise GameError("owned", "already owned")
            if p["shards"] < cost:
                raise GameError("no_shards", "not enough shards")
            st.add_item(pid, item_id, now)
            st.log_drop(pid, item_id, item["rarity"], True, now)
            st.update_player(pid, shards=p["shards"] - cost)
            st.add_ledger(pid, day_of(now), "craft", -cost)
        out = self.status(token)
        out["item"] = item_id
        return out

    # ----------------------------------------------------------------- checkin
    def checkin(self, token: str) -> dict[str, Any]:
        """Check in once per China Standard Time day: one prize drawn by weight, its shards (give or take the
        manifest's spread) credited."""
        pid = player_id_for(token)
        prizes = self.manifest.checkin["prizes"]
        with self.store.transaction() as st:
            now = self.now()
            p = st.get_player(pid, now)
            today = day_of(now)
            if st.checked_in(pid, today):
                raise GameError("checked_in", "今天已经签到了")
            index = cardlogic.pick_weighted([w["weight"] for w in prizes], self.rng)
            spread = self.manifest.checkin.get("spread", 0)
            gained = round(prizes[index]["shards"] * (1 + spread * (2 * self.rng.random() - 1)))
            st.add_checkin(pid, today, index, gained, now)
            st.update_player(pid, shards=p["shards"] + gained)
            st.add_ledger(pid, today, "checkin", gained)
        return {**self.status(token), "prize": {"index": index, "shards": gained, "day": today}}

    def checkin_month(self, token: str) -> dict[str, Any]:
        """Today and this China Standard Time month's check-ins, for the calendar."""
        pid = player_id_for(token)
        today = day_of(self.now())
        days = self.store.checkins_since(pid, today[:8] + "01")
        return {"today": today, "available": all(d["day"] != today for d in days), "days": days}

    # ---------------------------------------------------------- update rewards
    def claim_update_rewards(self, token: str, version: str) -> dict[str, Any]:
        """Pays every open reward the save has not claimed whose version the client's [version] reaches, all at
        once. A client that names no readable version reaches none."""
        pid = player_id_for(token)
        have = version_key(version)
        with self.store.transaction() as st:
            now = self.now()
            p = st.get_player(pid, now)
            due = [r for r in st.open_update_rewards(pid)
                   if have is not None and (need := version_key(r["version"])) is not None and need <= have]
            if not due:
                raise GameError("no_reward", "没有可以领取的更新奖励")
            gained = sum(r["shards"] for r in due)
            for r in due:
                st.add_update_claim(r["id"], pid, now)
            st.update_player(pid, shards=p["shards"] + gained)
            st.add_ledger(pid, day_of(now), "update", gained, len(due))
        return {**self.status(token), "reward": {"shards": gained, "ids": [r["id"] for r in due]}}

    # ----------------------------------------------------------------- scratch
    def _scratch_cfg(self) -> dict[str, Any]:
        cfg = self.manifest.scratch
        if not cfg:
            raise GameError("no_scratch", "这个服务器没有刮刮乐")
        return cfg

    def _scratch_left(self, pid: str, day: str) -> int:
        return max(0, self.manifest.scratch["daily"] - self.store.scratch_count(pid, day))

    @staticmethod
    def _scratch_view(card: dict[str, Any] | None) -> dict[str, Any] | None:
        return {"id": card["id"], "cells": json.loads(card["cells"])} if card else None

    def scratch_state(self, token: str) -> dict[str, Any]:
        """Cards left today (China Standard Time), the count toward the emote pity, and the card still to reveal."""
        self._scratch_cfg()
        pid = player_id_for(token)
        now = self.now()
        p = self.store.get_player(pid, now)
        day = day_of(now)
        return {"day": day, "left": self._scratch_left(pid, day), "pity": p["scratch_pity"],
                "card": self._scratch_view(self.store.pending_scratch(pid))}

    def scratch_buy(self, token: str) -> dict[str, Any]:
        """Buy a card: its prize is decided now and paid by scratch_reveal. A card still to reveal is handed
        back as it is, at no charge, so a save never holds two."""
        cfg = self._scratch_cfg()
        pid = player_id_for(token)
        with self.store.transaction() as st:
            now = self.now()
            p = st.get_player(pid, now)
            card = st.pending_scratch(pid)
            if card is None:
                today = day_of(now)
                if st.scratch_count(pid, today) >= cfg["daily"]:
                    raise GameError("sold_out", "今天的刮刮乐卖完了")
                if p["shards"] < cfg["price"]:
                    raise GameError("no_shards", "碎片不足")
                # The card before was revealed (a save holds one at a time), so its emote is owned by now.
                owned = st.owned(pid)
                missing = [k for k in self.manifest.scratch_emotes if f"emote:{k}" not in owned]
                # A whole set: no emote tier and no pity, which stays where the last emote left it.
                kind, shards = scratchlogic.roll_prize(cfg, p["scratch_pity"], self.rng, complete=not missing)
                item = ""
                if kind == "emote":
                    item = "emote:" + missing[min(int(self.rng.random() * len(missing)), len(missing) - 1)]
                win = item[6:] if item else str(shards) if shards else None
                cells = scratchlogic.layout(win, [x["shards"] for x in cfg["prizes"]],
                                            self.manifest.scratch_emotes, self.rng)
                card_id = st.add_scratch(pid, today, json.dumps(cells), shards, item, now)
                pity = 0 if kind == "emote" else p["scratch_pity"] if not missing else p["scratch_pity"] + 1
                st.update_player(pid, shards=p["shards"] - cfg["price"], scratch_pity=pity)
                st.add_ledger(pid, today, "scratch_buy", -cfg["price"])
                card = st.scratch_card(pid, card_id)
        return {**self.status(token), "card": self._scratch_view(card)}

    def scratch_reveal(self, token: str, card_id: int) -> dict[str, Any]:
        """Pay a card's prize. Revealing it again answers the same prize and pays nothing; `announce` is set
        the first time when the shards are worth telling the room."""
        cfg = self._scratch_cfg()
        pid = player_id_for(token)
        with self.store.transaction() as st:
            now = self.now()
            p = st.get_player(pid, now)
            card = st.scratch_card(pid, card_id)
            if card is None:
                raise GameError("no_card", "没有这张刮刮乐")
            first = not card["revealed"]
            if first:
                st.reveal_scratch(card["id"], now)
                if card["shards"]:
                    st.update_player(pid, shards=p["shards"] + card["shards"])
                    st.add_ledger(pid, day_of(now), "scratch_prize", card["shards"])
                if card["item"]:
                    known = self.manifest.items.get(card["item"])
                    st.add_item(pid, card["item"], now)
                    st.log_drop(pid, card["item"], known["rarity"] if known else "common", True, now)
        return {**self.status(token), "prize": {"shards": card["shards"], "item": card["item"] or None},
                "announce": first and card["shards"] >= cfg["announce"]}

    def prune_scratch_cards(self) -> int:
        """Forgets revealed scratch cards older than SCRATCH_DAYS. Returns rows removed."""
        return self.store.prune_scratch_cards(self.now() - SCRATCH_DAYS * 86400)

    # ------------------------------------------------------------ rock-paper-scissors
    def duel_cfg(self) -> dict[str, Any]:
        cfg = self.manifest.duel
        if not cfg:
            raise GameError("no_duel", "这个服务器没有猜拳")
        return cfg

    def duel_stake(self, bet: int) -> dict[str, int]:
        """The stake tier for [bet]; any other amount is refused."""
        for stake in self.duel_cfg()["stakes"]:
            if stake["bet"] == bet:
                return stake
        raise GameError("bad_message", "unknown bet")

    def _duel_ready(self, st: Store, pid: str | None, code: str) -> None:
        """Both sides need a save with enough taps; [code] says which side failed. Never creates a save."""
        taps = st.player_taps(pid) if pid else None
        if taps is None or taps < self.duel_cfg()["minTaps"]:
            raise GameError(code, "")

    def _duel_net_ok(self, st: Store, pids: tuple[str, ...], stake: dict[str, int], day: str) -> None:
        """A win of this tier may not take either side's net win of [day] past the daily cap."""
        cap = self.duel_cfg()["dailyWinCap"]
        if any(st.duel_net(pid, day) + stake["prize"] - stake["bet"] > cap for pid in pids):
            raise GameError("duel_cap", "")

    def duel_check(self, a: str | None, b: str | None, bet: int) -> dict[str, int]:
        """Whether save [a] may invite save [b] at [bet]; returns the stake. The bets are taken by duel_start."""
        stake = self.duel_stake(bet)
        with self.store.transaction() as st:
            self._duel_ready(st, a, "duel_locked")
            self._duel_ready(st, b, "duel_target_locked")
            if st.get_player(a, self.now())["shards"] < bet:
                raise GameError("no_shards", "")
            self._duel_net_ok(st, (a, b), stake, day_of(self.now()))
        return stake

    def duel_start(self, a: str, b: str, bet: int) -> int:
        """Takes both bets in one transaction and records the duel; returns its id. When either side is short of
        shards nothing is taken (no_shards)."""
        stake = self.duel_stake(bet)
        with self.store.transaction() as st:
            now = self.now()
            self._duel_ready(st, a, "duel_locked")
            self._duel_ready(st, b, "duel_target_locked")
            day = day_of(now)
            self._duel_net_ok(st, (a, b), stake, day)
            pa, pb = st.get_player(a, now), st.get_player(b, now)
            if pa["shards"] < bet or pb["shards"] < bet:
                raise GameError("no_shards", "")
            st.update_player(a, shards=pa["shards"] - bet)
            st.update_player(b, shards=pb["shards"] - bet)
            st.add_ledger(a, day, "duel_bet", -bet)
            st.add_ledger(b, day, "duel_bet", -bet)
            return st.add_duel(a, b, bet, stake["prize"], day, now)

    def duel_settle(self, duel_id: int, winner: str | None) -> bool:
        """Pays the duel's prize to [winner], or returns both bets when there is none. Only the first call for a
        duel pays; later ones return False."""
        with self.store.transaction() as st:
            now = self.now()
            d = st.duel(duel_id)
            if d is None or (winner is not None and winner not in (d["a"], d["b"])):
                return False
            if not st.close_duel(duel_id, "won" if winner else "refunded", winner or "", now):
                return False
            day = day_of(now)
            for pid, gain in ([(winner, d["prize"])] if winner else [(d["a"], d["bet"]), (d["b"], d["bet"])]):
                st.update_player(pid, shards=st.get_player(pid, now)["shards"] + gain)
                st.add_ledger(pid, day, "duel_prize" if winner else "duel_refund", gain)
        return True

    def refund_open_duels(self) -> int:
        """At startup: duels left open by the last run cannot go on (rooms live in memory), so both bets go back.
        Returns the duels refunded."""
        return sum(self.duel_settle(d["id"], None) for d in self.store.open_duels())

    def duel_net(self, pid: str) -> int:
        """The save's net win today (China Standard Time): prizes minus bets of today's settled duels."""
        return self.store.duel_net(pid, day_of(self.now()))

    # ------------------------------------------------------------------ status
    def status(self, token: str) -> dict[str, Any]:
        pid = player_id_for(token)
        now = self.now()
        day = day_of(now)
        p = self.store.get_player(pid, now)
        owned_count = self.store.count_items(pid, self.collectible_ids)
        out = {
            "player": pid,
            "shards": p["shards"],
            "income": self._income(p, day),
            "dailyTaps": {"day": day, "count": p["day_taps_total"] if p["tap_day"] == day else 0},
            "resonance": {"pity": {"legendary": p["draw_pity"], "skin": p["skin_pity"]},
                          "hardPity": self.manifest.resonance["pity"], "total": p["drawn_total"]},
            "totals": {"taps": p["taps_total"], "activeMinutes": p["active_minutes"],
                       "owned": owned_count,
                       "items": len(self.manifest.items) - len(self.manifest.starter)},
            "checkin": {"available": not self.store.checked_in(pid, day)},
            "tapCooldown": max(0, math.ceil(p["tap_cooldown_until"] - now)),
        }
        if self.manifest.scratch:
            out["scratch"] = {"left": self._scratch_left(pid, day), "pity": p["scratch_pity"]}
        if self.manifest.duel:
            out["duel"] = {"net": self.store.duel_net(pid, day)}
        out["cheer"] = {"day": day, "got": self.store.ledger_amount(pid, day, "cheer"), "cap": CHEER_DAILY_CAP,
                        "minTaps": CHEER_MIN_TAPS}
        # Every open reward this save has not claimed; the client offers those its own version reaches.
        out["updateRewards"] = self.store.open_update_rewards(pid)
        return out

    def save_summary(self, pid: str) -> dict[str, Any]:
        """What the account choice dialog shows about one save."""
        p = self.store.get_player(pid, self.now())
        return {"shards": p["shards"], "owned": self.store.count_items(pid, self.collectible_ids),
                "taps": p["taps_total"], "lastActive": p["last_activity"] or p["created"]}

    # ------------------------------------------------------------------ admin
    def admin_stats(self, days: int) -> dict[str, Any]:
        """Totals and one row per China Standard Time day, oldest first."""
        now = self.now()
        labels = [day_of(now - i * 86400) for i in range(days - 1, -1, -1)]
        daily = self.store.daily(labels[0], DAY_OFFSET)
        totals = self.store.totals(labels[-1])
        keys = ("active", "newSaves", "items")
        return {"totals": {**totals, "guests": totals["saves"] - totals["linked"]},
                "series": [{"day": d, **{k: daily.get(d, {}).get(k, 0) for k in keys}} for d in labels]}

    def admin_accounts(self, user_ids: list[str] | None, offset: int, limit: int) -> dict[str, Any]:
        rows, total = self.store.account_links(user_ids, offset, limit)
        return {"total": total, "accounts": [
            {"userId": r["main_user_id"], "linkedAt": r["linked_at"], **self.save_summary(r["player_id"])}
            for r in rows]}

    def admin_adjust_shards(self, main_user_id: str, delta: int, actor: str = "", reason: str = "") -> dict[str, Any]:
        pid = self.store.linked_player(main_user_id)
        if pid is None:
            raise GameError("account_not_linked", "这个账号没有桌宠存档")
        return self.admin_adjust_save_shards(pid, delta, actor, reason)

    def admin_adjust_save_shards(self, pid: str, delta: int, actor: str = "", reason: str = "") -> dict[str, Any]:
        """Adds [delta] shards to an existing save, guest or linked; never below zero. The admin log keeps who
        and why."""
        with self.store.transaction() as st:
            if not st.has_player(pid):
                raise GameError("no_save", "没有这份存档")
            now = self.now()
            shards = st.get_player(pid, now)["shards"] + delta
            if shards < 0:
                raise GameError("no_shards", "碎片不够扣")
            st.update_player(pid, shards=shards)
            if delta:
                st.add_ledger(pid, day_of(now), "admin", delta)
                st.add_admin_log(now, actor, "shards", pid, json.dumps({"delta": delta, "shards": shards}), reason)
        return {"shards": shards}

    def admin_note(self, actor: str, action: str, detail: dict[str, Any], pid: str = "", reason: str = "") -> None:
        """An admin log entry for a change made outside the game's own admin methods."""
        self.store.add_admin_log(self.now(), actor, action, pid, json.dumps(detail, ensure_ascii=False), reason)

    def admin_log(self, pid: str | None, limit: int, before: int | None = None) -> dict[str, Any]:
        rows = self.store.admin_log(pid, limit, before)
        return {"entries": [{"id": r["id"], "ts": r["ts"], "actor": r["actor"], "action": r["action"],
                             "player": r["player_id"] or None, "detail": _loadout_json(r["detail"]),
                             "reason": r["reason"]} for r in rows]}

    def admin_update_rewards(self) -> dict[str, Any]:
        """Every update reward, newest first, with its claims and the shards paid."""
        rows = self.store.update_rewards()
        return {"rewards": [{**r, "paid": r["shards"] * r["claims"]} for r in rows]}

    def admin_add_update_reward(self, version: str, shards: int, actor: str = "") -> dict[str, Any]:
        """Opens a reward for [version] and newer. One open reward per version, so a second submit pays no one twice."""
        key = version_key(version)
        if key is None:
            raise GameError("bad_version", "版本号格式应为 1.2.3")
        with self.store.transaction() as st:
            if any(r["ended"] is None and version_key(r["version"]) == key for r in st.update_rewards()):
                raise GameError("reward_open", "这个版本已有进行中的更新奖励")
            version = version.strip().removeprefix("v")
            st.add_update_reward(version, shards, self.now())
            st.add_admin_log(self.now(), actor, "reward_open", "", json.dumps({"version": version, "shards": shards}))
        return self.admin_update_rewards()

    def admin_end_update_reward(self, reward_id: int, actor: str = "") -> dict[str, Any]:
        """Stops a reward: saves that have not claimed it no longer can."""
        if not self.store.end_update_reward(reward_id, self.now()):
            raise GameError("no_reward", "没有进行中的这个奖励")
        version = next((r["version"] for r in self.store.update_rewards() if r["id"] == reward_id), "")
        self.admin_note(actor, "reward_end", {"id": reward_id, "version": version})
        return self.admin_update_rewards()

    def _admin_save(self, p: dict[str, Any], user_id: str | None) -> dict[str, Any]:
        """One save as the admin save list shows it; [p] is its player row."""
        return {"player": p["id"], "userId": user_id, "created": p["created"],
                "lastActive": p["last_activity"] or p["created"], "shards": p["shards"],
                "owned": self.store.count_items(p["id"], self.collectible_ids), "taps": p["taps_total"],
                "drawn": p["drawn_total"], "tapCooldown": max(0, math.ceil(p["tap_cooldown_until"] - self.now())),
                "clientVersion": p["client_version"] or None}

    def admin_saves(self, q: str, limit: int) -> dict[str, Any]:
        """Saves linked to main-site user id [q], and, when [q] is 4-16 hex characters, saves whose player id
        starts with it; most recently active first."""
        q = q.strip()
        prefix = q.lower()
        hexed = SAVE_PREFIX_MIN <= len(prefix) <= SAVE_PREFIX_MAX and all(c in "0123456789abcdef" for c in prefix)
        rows = self.store.find_saves(prefix if hexed else None, q, limit) if q else []
        return {"saves": [self._admin_save(r, r["main_user_id"]) for r in rows]}

    def admin_save(self, pid: str) -> dict[str, Any]:
        """One save in full: the list summary, pity, today's taps, recent drops and the last days of ledger."""
        if not self.store.has_player(pid):
            raise GameError("no_save", "没有这份存档")
        now = self.now()
        p = self.store.get_player(pid, now)
        today = day_of(now)
        days = [day_of(now - i * 86400) for i in range(ADMIN_LEDGER_DAYS - 1, -1, -1)]
        ledger: dict[str, dict[str, dict[str, int]]] = {d: {} for d in days}
        for r in self.store.ledger_of(pid, days):
            ledger[r["day"]][r["source"]] = {"amount": r["amount"], "count": r["count"]}
        return {**self._admin_save(p, self.store.account_for_player(pid)),
                "pity": {"legendary": p["draw_pity"], "skin": p["skin_pity"], "scratch": p["scratch_pity"]},
                "today": {"day": today, "taps": p["day_taps_total"] if p["tap_day"] == today else 0,
                          "tapShards": ledger[today].get("tap", {}).get("amount", 0)},
                "recent": self.store.recent_drops(pid),
                "ledger": [{"day": d, "sources": ledger[d]} for d in days],
                "log": self.admin_log(pid, ADMIN_SAVE_LOG)["entries"]}

    def admin_economy(self, days: int, scope: Literal["all", "new"] = "all", new_days: int = 7) -> dict[str, Any]:
        """Shard ledger per China Standard Time day, oldest first. scope "new" keeps saves created fewer than
        [new_days] days before the row's day (1: their first day only). Tap percentiles are nearest-rank."""
        now = self.now()
        labels = [day_of(now - i * 86400) for i in range(days - 1, -1, -1)]
        cap = self.manifest.income["dailyCap"]
        by_day: dict[str, list[dict[str, Any]]] = {d: [] for d in labels}
        for r in self.store.ledger_since(labels[0]):
            if r["day"] not in by_day:
                continue
            if scope == "new":
                if r["created"] is None:
                    continue
                age = date.fromisoformat(r["day"]).toordinal() - date.fromisoformat(day_of(r["created"])).toordinal()
                if age >= new_days:
                    continue
            by_day[r["day"]].append(r)
        series = []
        for day in labels:
            rows = by_day[day]
            sources: dict[str, dict[str, int]] = {}
            for r in rows:
                s = sources.setdefault(r["source"], {"amount": 0, "count": 0})
                s["amount"] += r["amount"]
                s["count"] += r["count"]
            taps = [r for r in rows if r["source"] == "tap"]
            counts = sorted(r["count"] for r in taps)
            series.append({
                "day": day, "players": len({r["player_id"] for r in rows}),
                "issued": sum(r["amount"] for r in rows if r["amount"] > 0),
                "spent": -sum(r["amount"] for r in rows if r["amount"] < 0),
                "sources": sources, "draws": sources.get("draw", {}).get("count", 0),
                "taps": {"players": len(counts), "p50": _nearest_rank(counts, 50),
                         "p90": _nearest_rank(counts, 90), "max": counts[-1] if counts else 0},
                "capped": sum(1 for r in taps if r["amount"] >= cap - 1)})
        return {"scope": scope, "newDays": new_days, "cap": cap, "series": series}

    def admin_unlink(self, main_user_id: str, actor: str = "", reason: str = "") -> None:
        """The save stays; its guest token works again and the account may link another save."""
        pid = self.store.linked_player(main_user_id)
        if not self.store.unlink_account(main_user_id):
            raise GameError("account_not_linked", "这个账号没有桌宠存档")
        self.admin_note(actor, "unlink", {"userId": main_user_id}, pid or "", reason)

    def collection(self, token: str) -> dict[str, Any]:
        pid = player_id_for(token)
        self.store.get_player(pid, self.now())
        return {"owned": self.store.owned(pid), "recent": self.store.recent_drops(pid)}

    # ----------------------------------------------------------------- loadout
    def _owns(self, owned: dict[str, int], item_id: str) -> bool:
        return item_id in owned or item_id in self.manifest.starter

    def _check_loadout(self, patch: dict[str, Any], owned: dict[str, int]) -> dict[str, Any]:
        """Validate the given loadout keys; raises GameError.  "" / None take the plate off."""
        out: dict[str, Any] = {}
        if "character" in patch and patch["character"] is not None:
            name = patch["character"]
            if name not in self.manifest.character_names:
                if name not in self.manifest.skins:
                    raise GameError("bad_item", "unknown character")
                if f"char:{name}" not in owned:
                    raise GameError("locked", "skin not owned")
            out["character"] = patch["character"]
        if "favorites" in patch and patch["favorites"] is not None:
            favs = list(dict.fromkeys(patch["favorites"]))
            if len(favs) > MAX_FAVORITES or not all(isinstance(k, str) for k in favs):
                raise GameError("bad_item", f"at most {MAX_FAVORITES} favorites")
            for key in favs:
                if key not in FREE_EMOTES and not self._owns(owned, f"emote:{key}"):
                    raise GameError("locked", "emote not owned")
            out["favorites"] = favs
        if "plate" in patch:
            out["plate"] = self._check_plate(patch["plate"], owned)
        if "showcase" in patch and patch["showcase"] is not None:
            cards = list(dict.fromkeys(patch["showcase"]))
            if len(cards) > MAX_SHOWCASE or not all(isinstance(c, str) and c in self.manifest.cards for c in cards):
                raise GameError("bad_item", f"at most {MAX_SHOWCASE} cards")
            if any(f"card:{c}" not in owned for c in cards):
                raise GameError("locked", "card not owned")
            out["showcase"] = cards
        if "nick" in patch and patch["nick"] is not None:
            if not isinstance(patch["nick"], str) or len(patch["nick"].strip()) > MAX_BOARD_NICK:
                raise GameError("bad_item", f"nick of at most {MAX_BOARD_NICK} characters")
            out["nick"] = patch["nick"].strip()
        if "board" in patch and patch["board"] is not None:
            if not isinstance(patch["board"], bool):
                raise GameError("bad_item", "board is true or false")
            out["board"] = patch["board"]
        return out

    def plate_set(self, card: dict[str, Any]) -> list[str]:
        """Cards a name plate asks for: those of its collection that show one of its members. A collection of
        several members asks only for the plate member's cards; a duo card asks for the whole duo collection."""
        members = set(card["characters"])
        return [c["id"] for c in self.manifest.cards.values()
                if c["series"] == card["series"] and members & set(c["characters"])]

    def plate_needs(self, plate_id: Any) -> list[str] | None:
        """Item ids a name plate asks for: a big hidden card's set, or every emote of a manifest plate's set.
        None when the id is no plate."""
        if not isinstance(plate_id, str):
            return None
        if plate_id in self.manifest.plates:
            return self.manifest.plates[plate_id]
        card = self.manifest.cards.get(plate_id)
        if card is None or card.get("tier") != "big":
            return None
        return [f"card:{cid}" for cid in self.plate_set(card)]

    def _check_plate(self, plate_id: Any, owned: dict[str, int]) -> str | None:
        """A name plate (a big hidden card or a manifest plate) worn once its set is collected; empty means none."""
        if not plate_id:
            return None
        needs = self.plate_needs(plate_id)
        if needs is None:
            raise GameError("bad_item", "not a name plate")
        if any(item not in owned for item in needs):
            raise GameError("locked", "set not collected")
        return plate_id

    def _stored_loadout(self, p: dict[str, Any], owned: dict[str, int]) -> dict[str, Any]:
        try:
            raw = json.loads(p["loadout"]) if p["loadout"] else {}
        except ValueError:
            raw = {}
        out: dict[str, Any] = {"character": None, "favorites": [], "plate": None, "showcase": [], "nick": "", "board": True}
        for key in LOADOUT_KEYS:  # drop parts that the manifest no longer knows
            value = raw.get(key)
            if key == "showcase" and isinstance(value, list):
                # a card the save no longer holds leaves its own slot, not the whole showcase
                value = [c for c in value if isinstance(c, str) and f"card:{c}" in owned]
            try:
                out.update(self._check_loadout({key: value}, owned))
            except GameError:
                pass
        return out

    def get_loadout(self, token: str) -> dict[str, Any]:
        pid = player_id_for(token)
        p = self.store.get_player(pid, self.now())
        owned = self.store.owned(pid)
        return self._stored_loadout(p, owned)

    def set_loadout(self, token: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Update the selected character, favorite emotes, name plate and showcase cards."""
        pid = player_id_for(token)
        with self.store.transaction() as st:
            p = st.get_player(pid, self.now())
            owned = st.owned(pid)
            loadout = {**self._stored_loadout(p, owned), **self._check_loadout(patch, owned)}
            st.update_player(pid, loadout=json.dumps(loadout, ensure_ascii=False))
        return self.get_loadout(token)

    def collection_progress(self, owned: dict[str, int]) -> dict[str, list[int]]:
        """[owned, total] of cards, emotes and skins, counted as the client's album does: starter emotes count."""
        counts = {"card": [0, 0], "emote": [0, 0], "char": [0, 0]}
        for item_id, item in self.manifest.items.items():
            count = counts[item["kind"]]
            count[1] += 1
            if self._owns(owned, item_id):
                count[0] += 1
        return {"cards": counts["card"], "emotes": counts["emote"], "skins": counts["char"]}

    def member_profile(self, token: str | None) -> dict[str, Any]:
        """What a room member's profile shows of a save: its showcase cards and collection progress.
        A member without a save has neither."""
        if not token:
            return {"showcase": [], "progress": None}
        try:
            pid = player_id_for(token)
        except GameError:
            return {"showcase": [], "progress": None}
        # A token no save was ever made for (a client that joined without one) shows nothing and makes no save.
        if not self.store.has_player(pid):
            return {"showcase": [], "progress": None}
        return self._profile_of(pid)

    def _profile_of(self, pid: str) -> dict[str, Any]:
        p = self.store.get_player(pid, self.now())
        owned = self.store.owned(pid)
        return {"showcase": self._stored_loadout(p, owned)["showcase"], "progress": self.collection_progress(owned)}

    # ------------------------------------------------------------------- boards
    def _listed(self, pid: str, loadout: dict[str, Any], linked: set[str] | None) -> str | None:
        """Why a save is off the collection board ("hidden": its own choice, "account": no main-site account);
        None when it is on it. [linked] is None on a server without main-site accounts."""
        if loadout.get("board") is False:
            return "hidden"
        if linked is not None and pid not in linked:
            return "account"
        return None

    def _work_out_board(self, require_account: bool) -> dict[str, Any]:
        now = self.now()
        cached = getattr(self, "_board", None)
        if cached and now - cached["at"] < BOARD_SECONDS and cached["require_account"] == require_account:
            return cached
        saves: dict[str, dict[str, Any]] = {}
        for pid, iid, ts in self.store.held_items():
            if iid not in self.board_points:
                continue
            counts = saves.get(pid)
            if counts is None:
                counts = saves[pid] = _board_counts()
            self._count_item(counts, iid)
            counts["last"] = max(counts["last"], ts)
            if iid.startswith("card:"):
                counts["last_card"] = max(counts["last_card"], ts)
        pids = sorted(saves)
        loadouts = {pid: _loadout_json(raw) for pid, raw in self.store.loadouts(pids).items()}
        room_nicks = self.store.room_nicks(pids)
        linked = self.store.linked_players() if require_account else None
        listed = [(pid, c) for pid, c in saves.items() if self._listed(pid, loadouts.get(pid, {}), linked) is None]
        ranked = {
            # Cards, then big hidden cards, then who had the last of those cards first.
            "cards": sorted((x for x in listed if x[1]["cards"]),
                            key=lambda x: (-x[1]["cards"], -x[1]["big"], x[1]["last_card"])),
            # Score, then big hidden cards, then who reached the score first.
            "score": sorted(listed, key=lambda x: (-x[1]["score"], -x[1]["big"], x[1]["last"])),
        }
        rows: dict[str, list[dict[str, Any]]] = {}
        shown: dict[str, dict[str, Any]] = {}
        for order, in_order in ranked.items():
            rows[order] = []
            for rank, (pid, counts) in enumerate(in_order[:BOARD_SIZE], 1):
                if pid not in shown:
                    shown[pid] = self._board_row(pid, counts, loadouts.get(pid, {}), room_nicks)
                rows[order].append({**shown[pid], "rank": rank})
        self._board = {
            "at": now, "require_account": require_account, "rows": rows,
            "ids": {row["id"]: pid for pid, row in shown.items()},
            "rank": {order: {pid: i for i, (pid, _) in enumerate(in_order, 1)} for order, in_order in ranked.items()},
        }
        return self._board

    def _count_item(self, counts: dict[str, Any], iid: str) -> None:
        """Adds an item a save holds (one with board points) to its board counts."""
        counts["score"] += self.board_points[iid]
        if iid.startswith("card:"):
            counts["cards"] += 1
            counts["big"] += self.manifest.cards[iid[5:]].get("tier") == "big"
        elif iid.startswith("char:"):
            counts["skins"] += 1

    def _board_row(self, pid: str, counts: dict[str, Any], lo: dict[str, Any],
                   room_nicks: dict[str, str]) -> dict[str, Any]:
        plate = lo.get("plate")
        needs = self.plate_needs(plate) if plate else None
        if needs is None or not set(needs) <= set(self.store.owned(pid)):
            plate = None
        # The nick set for the board (1.2.0 on), else the one last used in a room.
        nick = (lo.get("nick") if isinstance(lo.get("nick"), str) else "") or room_nicks.get(pid) or BOARD_DEFAULT_NICK
        return {"id": board_id(pid), "nick": nick, "character": lo.get("character") or "", "plate": plate,
                "cards": counts["cards"], "big": counts["big"], "skins": counts["skins"], "score": counts["score"]}

    def board(self, token: str, require_account: bool, order: str = "cards") -> dict[str, Any]:
        """The collection board's top rows and where the asking save stands, by [order]: "cards" (what clients from
        before the collection score show) or "score". The board is worked out at most every BOARD_SECONDS, so a rank
        may lag a few minutes."""
        data = self._work_out_board(require_account)
        pid = player_id_for(token)
        p = self.store.get_player(pid, self.now())
        loadout = _loadout_json(p["loadout"])
        mine = _board_counts()
        for iid, count in self.store.owned(pid).items():
            if count > 0 and iid in self.board_points:
                self._count_item(mine, iid)
        # Only this save's own link matters here: no need to read every account link.
        linked = ({pid} if self.store.account_for_player(pid) else set()) if require_account else None
        return {
            "total": len(self.manifest.cards), "points": dict(BOARD_POINTS), "cards": data["rows"][order],
            "me": {
                "rank": data["rank"][order].get(pid), "cards": mine["cards"], "big": mine["big"],
                "skins": mine["skins"], "score": mine["score"], "off": self._listed(pid, loadout, linked),
            },
        }

    def board_profile(self, bid: str, require_account: bool) -> dict[str, Any]:
        """The profile of a save on the collection board's top rows; raises GameError("no_member") otherwise."""
        data = self._work_out_board(require_account)
        pid = data["ids"].get(bid)
        if pid is None:
            raise GameError("no_member", "not on the board")
        return self._profile_of(pid)

    # -------------------------------------------------------------------- room
    def note_room_nick(self, token: str | None, nick: str) -> None:
        """Keep the nick a save joins a room with or changes to there; the default one counts as none."""
        if not token:
            return
        try:
            pid = player_id_for(token)
        except GameError:
            return
        nick = nick.strip()[:MAX_BOARD_NICK]
        self.store.set_room_nick(pid, "" if nick == BOARD_DEFAULT_NICK else nick)

    def profile_for(self, token: str | None, room: str) -> dict[str, Any]:
        if not token:
            return {"uid": None}
        try:
            pid = player_id_for(token)
        except GameError:
            return {"uid": None}
        return {"uid": hashlib.sha256(f"{pid}:{room}".encode()).hexdigest()[:10]}

    def room_plate(self, token: str | None, plate_id: str | None) -> str | None:
        """The name plate a room member shows: the plate when their save has its set, else none."""
        if not token or not plate_id:
            return None
        try:
            return self._check_plate(plate_id, self.store.owned(player_id_for(token)))
        except GameError:
            return None

    def owns_character(self, token: str | None, name: str) -> bool:
        """Whether a room member may show this character: members always, a skin only when the save owns it."""
        if name in self.manifest.character_names:
            return True
        if not token or name not in self.manifest.skins:
            return False
        try:
            pid = player_id_for(token)
        except GameError:
            return False
        return self.store.has_item(pid, f"char:{name}")

    def base_character(self, name: str) -> str:
        """The member a skin belongs to (skin names start with it, e.g. 贝拉山海经), else the first member."""
        names = [c["name"] for c in self.manifest.data["characters"]]
        return next((n for n in names if name.startswith(n)), names[0])

    def owns_emote(self, token: str | None, key: str) -> bool:
        if key in FREE_EMOTES or f"emote:{key}" in self.manifest.starter:
            return True
        if not token:
            return False
        try:
            pid = player_id_for(token)
        except GameError:
            return False
        return self.store.has_item(pid, f"emote:{key}")
