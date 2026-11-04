"""Server-authoritative progression: input activity -> loot boxes -> items.

The client only reports *counts* of taps (never key content).  The server clips
the credited taps to a plausible rate, decides when a box is earned, rolls the
item and stores everything in SQLite.  Duplicates become shards that craft a
chosen missing item.  Identity is a client-generated secret token; the player id
is a hash of it.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from typing import Any, Callable

from . import cards as cardlogic
from .cards import DropConfig, Rng
from .manifest import Manifest
from .store import Store

TOKEN_MIN, TOKEN_MAX = 16, 128
MAX_REPORT_TAPS = 5000
MAX_ELAPSED = 120.0
MAX_FAVORITES = 8
DRAW_SECONDS = 5 * 60
DRAW_PITY = 400
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
                return {**self.status(token), "credited": 0, "newBoxes": 0}
            previous = p["last_activity"] or p["created"]
            elapsed = min(max(now - previous, 0.0), MAX_ELAPSED)
            budget = min(st.activity_budget(pid) + cfg.max_taps_per_sec * elapsed,
                         cfg.max_taps_per_sec * MAX_ELAPSED)
            credited = min(taps, math.floor(budget))

            bucket = int(now // 60)
            minute_taps, counted = p["minute_taps"], p["minute_counted"]
            if bucket != p["minute_bucket"]:
                minute_taps, counted = 0, 0
            minute_taps += credited
            active_minutes, progress_minutes = p["active_minutes"], p["progress_minutes"]
            if not counted and minute_taps >= cfg.min_taps_active_minute:
                counted = 1
                active_minutes += 1
                progress_minutes += 1

            progress_taps = p["progress_taps"] + credited
            earned = progress_taps // cfg.taps_per_box + progress_minutes // cfg.minutes_per_box
            progress_taps %= cfg.taps_per_box
            progress_minutes %= cfg.minutes_per_box

            day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
            boxes, boxes_today = p["boxes"], p["boxes_today"]
            if p["boxes_day"] != day:
                boxes_today = 0
            gained = 0
            for _ in range(earned):
                if boxes_today < cfg.daily_box_cap and boxes < cfg.inventory_cap:
                    boxes += 1
                    boxes_today += 1
                    gained += 1
            st.update_player(
                pid, taps_total=p["taps_total"] + credited, active_minutes=active_minutes,
                progress_taps=progress_taps, progress_minutes=progress_minutes, boxes=boxes,
                boxes_day=day, boxes_today=boxes_today, last_activity=max(now, previous),
                minute_bucket=bucket, minute_taps=minute_taps, minute_counted=counted)
            st.save_activity_budget(pid, budget - credited)
            if session is not None:
                st.save_activity_sequence(pid, session, sequence)
        out = self.status(token)
        out["credited"] = credited
        out["newBoxes"] = gained
        return out

    # ------------------------------------------------------------------- boxes
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
            seconds = p["draw_seconds"] + elapsed
            earned = int(seconds // DRAW_SECONDS)
            st.update_player(pid, draw_tickets=p["draw_tickets"] + earned,
                             draw_seconds=seconds % DRAW_SECONDS,
                             presence_last=max(now, p["presence_last"]) if previous is not None else p["presence_last"])
        return self.status(token)

    def draw_cards(self, token: str, pool_id: str, count: int = 1) -> dict[str, Any]:
        pool = self.manifest.card_pools.get(pool_id)
        if not pool or not all(pool.values()):
            raise GameError("bad_pool", "请选择收藏集")
        pid = player_id_for(token)
        drops: list[dict[str, Any]] = []
        with self.store.transaction() as st:
            now = self.now()
            p = st.get_player(pid, now)
            if p["draw_tickets"] < 1:
                raise GameError("no_ticket", "抽卡次数不足")
            n = min(max(1, count), 100, p["draw_tickets"])
            pity = p["draw_pity"]
            owned = st.owned(pid)
            for _ in range(n):
                roll = self.rng.random()
                tier = "big" if pity + 1 >= DRAW_PITY or roll < 0.005 else "small" if roll < 0.05 else "normal"
                candidates = pool[tier]
                card = candidates[min(int(self.rng.random() * len(candidates)), len(candidates) - 1)]
                iid = f"card:{card['id']}"
                fresh = iid not in owned
                owned[iid] = st.add_item(pid, iid, now)
                st.log_drop(pid, iid, card["rarity"], fresh, now)
                pity = 0 if tier == "big" else pity + 1
                drops.append({"item": iid, "rarity": card["rarity"], "tier": tier,
                              "new": fresh, "count": owned[iid], "shards": 0})
            st.update_player(pid, draw_tickets=p["draw_tickets"] - n,
                             draw_pity=pity, drawn_total=p["drawn_total"] + n)
        return {**self.status(token), "drops": drops}

    def open_boxes(self, token: str, count: int = 1) -> dict[str, Any]:
        """Open up to ``count`` boxes (at most ``cfg.max_open_batch``); returns status + drops."""
        pid = player_id_for(token)
        now = self.now()
        cfg = self.cfg
        drops: list[dict[str, Any]] = []
        with self.store.transaction() as st:
            p = st.get_player(pid, now)
            if p["boxes"] <= 0:
                raise GameError("no_box", "no box to open")
            n = max(1, min(int(count), p["boxes"], cfg.max_open_batch))
            owned = st.owned(pid)
            since_epic, since_legend, shards = p["since_epic"], p["since_legend"], p["shards"]
            for _ in range(n):
                rarity = cardlogic.roll_rarity(self.manifest.weights, since_epic, since_legend, cfg, self.rng)
                item = cardlogic.pick_item(self.manifest.by_rarity, owned, rarity, cfg, self.rng)
                got = item["rarity"]
                is_new = item["id"] not in owned
                gained = 0 if is_new else self.manifest.dup_shards.get(got, 0)
                shards += gained
                owned[item["id"]] = st.add_item(pid, item["id"], now)
                st.log_drop(pid, item["id"], got, is_new, now)
                since_epic, since_legend = cardlogic.next_pity(got, since_epic, since_legend)
                drops.append({"item": item["id"], "rarity": got, "new": is_new,
                              "count": owned[item["id"]], "shards": gained})
            st.update_player(pid, boxes=p["boxes"] - n, opened_total=p["opened_total"] + n,
                             since_epic=since_epic, since_legend=since_legend, shards=shards)
        out = self.status(token)
        out["drops"] = drops
        return out

    # ------------------------------------------------------------------- craft
    def craft(self, token: str, item_id: str) -> dict[str, Any]:
        """Spend shards on a chosen missing item."""
        pid = player_id_for(token)
        now = self.now()
        item = self.manifest.items.get(item_id)
        cost = self.manifest.craft_cost.get(item["rarity"] or "") if item else None
        if item is None or item["kind"] != "emote" or item_id in self.manifest.starter or cost is None:
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
        cfg = self.cfg
        day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
        boxes_today = p["boxes_today"] if p["boxes_day"] == day else 0
        return {
            "player": pid,
            "boxes": p["boxes"],
            "shards": p["shards"],
            "draw": {"tickets": p["draw_tickets"], "seconds": p["draw_seconds"],
                     "secondsPerDraw": DRAW_SECONDS, "pity": p["draw_pity"],
                     "hardPity": DRAW_PITY, "total": p["drawn_total"]},
            "progress": {"taps": p["progress_taps"], "tapsPerBox": cfg.taps_per_box,
                         "minutes": p["progress_minutes"], "minutesPerBox": cfg.minutes_per_box},
            "boxesToday": boxes_today, "dailyCap": cfg.daily_box_cap,
            "totals": {"taps": p["taps_total"], "activeMinutes": p["active_minutes"],
                       "opened": p["opened_total"],
                       "owned": sum(1 for i in owned if i in self.manifest.items),
                       "items": len(self.manifest.items)},
            "pity": {"epic": p["since_epic"], "legendary": p["since_legend"]},
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
            if not self.manifest.knows_character(patch["character"]):
                raise GameError("bad_item", "unknown character")
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
