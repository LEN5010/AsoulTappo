"""Server-authoritative activity income, resonance and item ownership."""
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
MAX_REPORT_TAPS = 5000
MAX_ELAPSED = 120.0
MAX_FAVORITES = 8
# emote keys every member may send besides the starter emotes: the theme like
FREE_EMOTES = frozenset({"thumbup"})
LOADOUT_KEYS = ("character", "favorites")


class GameError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def player_id_for(token: str) -> str:
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

    # ---------------------------------------------------------------- activity
    def report_activity(self, token: str, taps: int, session: str | None = None,
                        sequence: int = 0) -> dict[str, Any]:
        pid = player_id_for(token)
        taps = max(0, min(int(taps), MAX_REPORT_TAPS))
        cfg = self.cfg
        with self.store.transaction() as st:
            now = self.now()
            p = st.get_player(pid, now)
            if session is not None and sequence <= st.activity_sequence(pid, session):
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
            minute_taps += credited
            active_minutes = p["active_minutes"]
            if not counted and minute_taps >= cfg.min_taps_active_minute:
                counted = 1
                active_minutes += 1

            st.update_player(
                pid, taps_total=p["taps_total"] + credited, active_minutes=active_minutes,
                last_activity=max(now, previous), last_minute_taps=last_minute_taps,
                minute_bucket=bucket, minute_taps=minute_taps, minute_counted=counted)
            st.save_activity_budget(pid, budget - credited)
            if session is not None:
                st.save_activity_sequence(pid, session, sequence)
        out = self.status(token)
        out["credited"] = credited
        return out

    # ------------------------------------------------------------------ income
    def presence(self, token: str, session: str) -> dict[str, Any]:
        """Accumulate connected running time, shared across simultaneous clients."""
        pid = player_id_for(token)
        with self.store.transaction() as st:
            now = self.now()
            p = st.get_player(pid, now)
            previous = st.presence(pid, session, now)
            elapsed = 0.0
            if previous is not None and 0 <= now - previous <= 60:
                elapsed = max(0.0, now - max(previous, p["presence_last"]))
            inc = self.manifest.income
            earned = p["shard_remainder"] + elapsed / 60 * inc["perMinute"] * self._multiplier(p, now)
            # Absorb floating-point noise at whole-shard boundaries.
            whole = int(earned + 1e-9)
            st.update_player(pid, shards=p["shards"] + whole, shard_remainder=max(0.0, earned - whole),
                             presence_last=max(now, p["presence_last"]) if previous is not None else p["presence_last"])
        return self.status(token)

    def _multiplier(self, p, now):
        bucket = int(now // 60)
        if p["minute_bucket"] == bucket:
            taps = p["last_minute_taps"]
        elif p["minute_bucket"] == bucket - 1:
            taps = p["minute_taps"]
        else:
            taps = 0
        inc = self.manifest.income
        return 1 + (inc["maxMultiplier"] - 1) * min(taps, inc["fullTapsPerMinute"]) / inc["fullTapsPerMinute"]

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
            for _ in range(n):
                missing = {r: [item for item in items if item["id"] not in owned] for r, items in pool.items()}
                available = {r for r in missing if missing[r]}
                rarity = cardlogic.roll_tier(cfg["rates"], available, pity, cfg["pity"], self.rng)
                candidates = missing[rarity] or pool[rarity]
                item = candidates[min(int(self.rng.random() * len(candidates)), len(candidates) - 1)]
                iid = item["id"]
                fresh = iid not in owned
                gained = 0 if fresh else cfg["duplicateRefund"]
                refund += gained
                owned[iid] = st.add_item(pid, iid, now)
                st.log_drop(pid, iid, rarity, fresh, now)
                for r in pity:
                    pity[r] = 0 if rarity == r else pity[r] + 1
                drop = {"item": iid, "rarity": rarity, "new": fresh, "count": owned[iid], "shards": gained}
                if item["kind"] == "card":
                    drop["tier"] = self.manifest.cards[iid[5:]]["tier"]
                drops.append(drop)
            st.update_player(pid, shards=p["shards"] - n * cfg["cost"] + refund,
                             draw_pity=pity["legendary"], skin_pity=pity["skin"], drawn_total=p["drawn_total"] + n)
        return {**self.status(token), "drops": drops}

    # ------------------------------------------------------------------- craft
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

    # ------------------------------------------------------------------ status
    def status(self, token: str) -> dict[str, Any]:
        pid = player_id_for(token)
        now = self.now()
        p = self.store.get_player(pid, now)
        owned = self.store.owned(pid)
        multiplier = self._multiplier(p, now)
        return {
            "player": pid,
            "shards": p["shards"],
            "income": {"multiplier": round(multiplier, 2),
                       "perMinute": round(self.manifest.income["perMinute"] * multiplier, 1)},
            "resonance": {"pity": {"legendary": p["draw_pity"], "skin": p["skin_pity"]},
                          "hardPity": self.manifest.resonance["pity"], "total": p["drawn_total"]},
            "totals": {"taps": p["taps_total"], "activeMinutes": p["active_minutes"],
                       "owned": sum(1 for i in owned if i in self.manifest.items and i not in self.manifest.starter),
                       "items": len(self.manifest.items) - len(self.manifest.starter)},
        }

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
        return out

    def _stored_loadout(self, p: dict[str, Any], owned: dict[str, int]) -> dict[str, Any]:
        try:
            raw = json.loads(p["loadout"]) if p["loadout"] else {}
        except ValueError:
            raw = {}
        out: dict[str, Any] = {"character": None, "favorites": []}
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
        """Update the selected character and favorite emotes."""
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
