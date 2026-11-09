"""Server-authoritative tap income, resonance and item ownership."""
from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Callable

from . import cards as cardlogic
from .cards import DropConfig, Rng
from .manifest import Manifest
from .store import Store

TOKEN_MIN, TOKEN_MAX = 16, 128
# Statistics count days in China Standard Time.
DAY_OFFSET = 8 * 3600
MAX_REPORT_TAPS = 5000
MAX_ELAPSED = 120.0
MAX_FAVORITES = 8
# emote keys every member may send besides the starter emotes: the theme like
FREE_EMOTES = frozenset({"thumbup"})
LOADOUT_KEYS = ("character", "favorites", "plate")


class GameError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class PlayerId(str):
    """A player ID already resolved from a guest token or a linked main-site account."""


def day_of(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts + DAY_OFFSET))


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
        self.collectible_ids = tuple(i for i in manifest.items if i not in manifest.starter)

    # ---------------------------------------------------------------- activity
    def report_activity(self, token: str, taps: int, session: str | None = None,
                        sequence: int = 0, cooldown: int = 0) -> dict[str, Any]:
        pid = player_id_for(token)
        taps = max(0, min(int(taps), MAX_REPORT_TAPS))
        cfg = self.cfg
        with self.store.transaction() as st:
            now = self.now()
            p = st.get_player(pid, now)
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
                st.save_activity_sequence(pid, session, sequence, now, fast_since)
            # A cooldown the client's guard started: it only costs the player, so it is taken as sent.
            if cooldown and now + min(cooldown, cfg.tap_cooldown_sec) > p["tap_cooldown_until"]:
                p["tap_cooldown_until"] = now + min(cooldown, cfg.tap_cooldown_sec)
                st.update_player(pid, tap_cooldown_until=p["tap_cooldown_until"])
            if now < p["tap_cooldown_until"]:
                return {**self.status(token), "credited": 0}
            previous = p["last_activity"] or p["created"]
            elapsed = min(max(now - previous, 0.0), MAX_ELAPSED)
            budget = min(st.activity_budget(pid) + cfg.max_taps_per_sec * elapsed,
                         cfg.max_taps_per_sec * MAX_ELAPSED)
            credited = min(taps, math.floor(budget))

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

            today = day_of(now)
            day_taps = p["day_taps"] if p["tap_day"] == today else 0
            earned = p["shard_remainder"] + self._tap_shards(day_taps + paid_taps) - self._tap_shards(day_taps)
            # Absorb floating-point noise at whole-shard boundaries.
            whole = int(earned + 1e-9)
            st.update_player(
                pid, taps_total=p["taps_total"] + credited, active_minutes=active_minutes,
                last_activity=max(now, previous), last_minute_taps=last_minute_taps,
                minute_bucket=bucket, minute_taps=minute_taps, minute_counted=counted,
                shards=p["shards"] + whole, shard_remainder=max(0.0, earned - whole),
                tap_day=today, day_taps=day_taps + paid_taps)
            st.save_activity_budget(pid, budget - credited)
            if credited:
                st.mark_active(pid, day_of(now))
        out = self.status(token)
        out["credited"] = credited
        return out

    # ------------------------------------------------------------------ income
    def presence(self, token: str, session: str) -> dict[str, Any]:
        """Marks a running client online for today's statistics. Being online pays nothing; taps do."""
        pid = player_id_for(token)
        with self.store.transaction() as st:
            now = self.now()
            st.get_player(pid, now)
            st.presence(pid, session, now)
            st.mark_active(pid, day_of(now))
        return self.status(token)

    def _tap_shards(self, taps: float) -> float:
        """Shards one China day's paid taps earn in all: a log curve that stops at the daily cap."""
        inc = self.manifest.income
        return min(inc["shardScale"] * math.log1p(taps / inc["tapScale"]), inc["dailyCap"])

    def _income(self, p, now) -> dict[str, Any]:
        inc = self.manifest.income
        day = day_of(now)
        taps = p["day_taps"] if p["tap_day"] == day else 0
        today = self._tap_shards(taps)
        per_tap = inc["shardScale"] / (inc["tapScale"] + taps) if today < inc["dailyCap"] else 0.0
        return {"day": day, "today": int(today + 1e-9), "cap": inc["dailyCap"], "taps": taps, "perTap": round(per_tap, 3),
                # Shown by 1.0 clients, which predate the tap curve: no multiplier, and what a minute of
                # typing at 60 taps pays from here.
                "multiplier": 1, "perMinute": round(per_tap * 60, 1)}

    def resonate(self, token: str, count: int = 1) -> dict[str, Any]:
        pool = self.manifest.resonance_pool
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

    def craft(self, token: str, item_id: str) -> dict[str, Any]:
        """Spend shards on a chosen missing item."""
        pid = player_id_for(token)
        now = self.now()
        item = self.manifest.items.get(item_id)
        cost = self.manifest.craft_cost.get(item["rarity"] or "") if item else None
        if item is None or item["kind"] not in ("emote", "card") or item_id in self.manifest.starter or cost is None:
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
        return {**self.status(token), "prize": {"index": index, "shards": gained, "day": today}}

    def checkin_month(self, token: str) -> dict[str, Any]:
        """Today and this China Standard Time month's check-ins, for the calendar."""
        pid = player_id_for(token)
        today = day_of(self.now())
        days = self.store.checkins_since(pid, today[:8] + "01")
        return {"today": today, "available": all(d["day"] != today for d in days), "days": days}

    # ------------------------------------------------------------------ status
    def status(self, token: str) -> dict[str, Any]:
        pid = player_id_for(token)
        now = self.now()
        p = self.store.get_player(pid, now)
        owned_count = self.store.count_items(pid, self.collectible_ids)
        return {
            "player": pid,
            "shards": p["shards"],
            "income": self._income(p, now),
            "resonance": {"pity": {"legendary": p["draw_pity"], "skin": p["skin_pity"]},
                          "hardPity": self.manifest.resonance["pity"], "total": p["drawn_total"]},
            "totals": {"taps": p["taps_total"], "activeMinutes": p["active_minutes"],
                       "owned": owned_count,
                       "items": len(self.manifest.items) - len(self.manifest.starter)},
            "checkin": {"available": not self.store.checked_in(pid, day_of(now))},
            "tapCooldown": max(0, math.ceil(p["tap_cooldown_until"] - now)),
        }

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

    def admin_adjust_shards(self, main_user_id: str, delta: int) -> dict[str, Any]:
        pid = self.store.linked_player(main_user_id)
        if pid is None:
            raise GameError("account_not_linked", "这个账号没有桌宠存档")
        with self.store.transaction() as st:
            shards = st.get_player(pid, self.now())["shards"] + delta
            if shards < 0:
                raise GameError("no_shards", "碎片不够扣")
            st.update_player(pid, shards=shards)
        return {"shards": shards}

    def admin_unlink(self, main_user_id: str) -> None:
        """The save stays; its guest token works again and the account may link another save."""
        if not self.store.unlink_account(main_user_id):
            raise GameError("account_not_linked", "这个账号没有桌宠存档")

    def collection(self, token: str) -> dict[str, Any]:
        pid = player_id_for(token)
        self.store.get_player(pid, self.now())
        return {"owned": self.store.owned(pid), "recent": self.store.recent_drops(pid)}

    # ----------------------------------------------------------------- loadout
    def _owns(self, owned: dict[str, int], item_id: str) -> bool:
        return item_id in owned or item_id in self.manifest.starter

    def _check_loadout(self, patch: dict[str, Any], owned: dict[str, int]) -> dict[str, Any]:
        """Validate the given loadout keys; raises GameError.  "" / None clear head and desk."""
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
        return out

    def plate_set(self, card: dict[str, Any]) -> list[str]:
        """Cards a name plate asks for: those of its collection that show one of its members. A collection of
        several members asks only for the plate member's cards; a duo card asks for the whole duo collection."""
        members = set(card["characters"])
        return [c["id"] for c in self.manifest.cards.values()
                if c["series"] == card["series"] and members & set(c["characters"])]

    def _check_plate(self, card_id: Any, owned: dict[str, int]) -> str | None:
        """A big hidden card worn as a name plate once its set is collected; empty means none."""
        if not card_id:
            return None
        card = self.manifest.cards.get(card_id) if isinstance(card_id, str) else None
        if card is None or card.get("tier") != "big":
            raise GameError("bad_item", "not a big hidden card")
        if any(f"card:{cid}" not in owned for cid in self.plate_set(card)):
            raise GameError("locked", "set not collected")
        return card_id

    def _stored_loadout(self, p: dict[str, Any], owned: dict[str, int]) -> dict[str, Any]:
        try:
            raw = json.loads(p["loadout"]) if p["loadout"] else {}
        except ValueError:
            raw = {}
        out: dict[str, Any] = {"character": None, "favorites": [], "plate": None}
        for key in LOADOUT_KEYS:  # drop parts that the manifest no longer knows
            try:
                out.update(self._check_loadout({key: raw.get(key)}, owned))
            except GameError:
                pass
        return out

    def get_loadout(self, token: str) -> dict[str, Any]:
        pid = player_id_for(token)
        p = self.store.get_player(pid, self.now())
        owned = self.store.owned(pid)
        return self._stored_loadout(p, owned)

    def set_loadout(self, token: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Update the selected character, favorite emotes and name plate."""
        pid = player_id_for(token)
        with self.store.transaction() as st:
            p = st.get_player(pid, self.now())
            owned = st.owned(pid)
            loadout = {**self._stored_loadout(p, owned), **self._check_loadout(patch, owned)}
            st.update_player(pid, loadout=json.dumps(loadout, ensure_ascii=False))
        return self.get_loadout(token)

    # -------------------------------------------------------------------- room
    def profile_for(self, token: str | None, room: str) -> dict[str, Any]:
        if not token:
            return {"uid": None}
        try:
            pid = player_id_for(token)
        except GameError:
            return {"uid": None}
        return {"uid": hashlib.sha256(f"{pid}:{room}".encode()).hexdigest()[:10]}

    def room_plate(self, token: str | None, card_id: str | None) -> str | None:
        """The name plate a room member shows: the card when their save has its set, else none."""
        if not token or not card_id:
            return None
        try:
            return self._check_plate(card_id, self.store.owned(player_id_for(token)))
        except GameError:
            return None

    def owns_emote(self, token: str | None, key: str) -> bool:
        if key in FREE_EMOTES or f"emote:{key}" in self.manifest.starter:
            return True
        if not token:
            return False
        try:
            pid = player_id_for(token)
        except GameError:
            return False
        return f"emote:{key}" in self.store.owned(pid)
