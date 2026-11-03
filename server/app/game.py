"""Server-authoritative progression: input activity -> loot boxes -> cards.

The client only reports *counts* of taps (never key content).  The server clips
the credited taps to a plausible rate, decides when a box is earned, rolls the
card and stores everything in SQLite.  Identity is a client-generated secret
token; the player id is a hash of it.
"""
from __future__ import annotations

import hashlib
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
FIRST_REPORT_ELAPSED = 10.0


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
    def report_activity(self, token: str, taps: int) -> dict[str, Any]:
        pid = player_id_for(token)
        taps = max(0, min(int(taps), MAX_REPORT_TAPS))
        now = self.now()
        cfg = self.cfg
        with self.store.transaction() as st:
            p = st.get_player(pid, now)
            elapsed = FIRST_REPORT_ELAPSED if p["last_activity"] <= 0 else now - p["last_activity"]
            elapsed = min(max(elapsed, 1.0), MAX_ELAPSED)
            credited = min(taps, math.ceil(cfg.max_taps_per_sec * elapsed))

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
                boxes_day=day, boxes_today=boxes_today, last_activity=now,
                minute_bucket=bucket, minute_taps=minute_taps, minute_counted=counted)
        out = self.status(token)
        out["credited"] = credited
        out["newBoxes"] = gained
        return out

    # ------------------------------------------------------------------- boxes
    def open_box(self, token: str) -> dict[str, Any]:
        pid = player_id_for(token)
        now = self.now()
        with self.store.transaction() as st:
            p = st.get_player(pid, now)
            if p["boxes"] <= 0:
                raise GameError("no_box", "no box to open")
            owned = st.owned(pid)
            rarity = cardlogic.roll_rarity(
                self.manifest.weights, p["since_epic"], p["since_legend"], self.cfg, self.rng)
            card = cardlogic.pick_card(self.manifest.by_rarity, owned, rarity, self.cfg, self.rng)
            got = card["rarity"]
            is_new = card["id"] not in owned
            count = st.add_card(pid, card["id"], now)
            st.log_drop(pid, card["id"], got, is_new, now)
            se, sl = cardlogic.next_pity(got, p["since_epic"], p["since_legend"])
            st.update_player(pid, boxes=p["boxes"] - 1, opened_total=p["opened_total"] + 1,
                             since_epic=se, since_legend=sl)
        out = self.status(token)
        out.update({"card": card["id"], "rarity": got, "new": is_new, "count": count})
        return out

    # ------------------------------------------------------------------ status
    def unlocked_decor(self, owned: dict[str, int]) -> list[str]:
        per_series: dict[str, int] = {}
        for cid in owned:
            c = self.manifest.cards.get(cid)
            if c:
                per_series[c["series"]] = per_series.get(c["series"], 0) + 1
        return sorted(d["id"] for d in self.manifest.decor.values()
                      if per_series.get(d["unlock"]["series"], 0) >= d["unlock"]["min"])

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
            "progress": {"taps": p["progress_taps"], "tapsPerBox": cfg.taps_per_box,
                         "minutes": p["progress_minutes"], "minutesPerBox": cfg.minutes_per_box},
            "boxesToday": boxes_today, "dailyCap": cfg.daily_box_cap,
            "totals": {"taps": p["taps_total"], "activeMinutes": p["active_minutes"],
                       "opened": p["opened_total"], "owned": len(owned),
                       "cards": len(self.manifest.cards)},
            "pity": {"epic": p["since_epic"], "legendary": p["since_legend"]},
            "unlocked": self.unlocked_decor(owned),
            "frame": p["frame"], "badge": p["badge"],
        }

    def collection(self, token: str) -> dict[str, Any]:
        pid = player_id_for(token)
        self.store.get_player(pid, self.now())
        return {"owned": self.store.owned(pid), "recent": self.store.recent_drops(pid)}

    # ------------------------------------------------------------------- decor
    def set_decor(self, token: str, frame: str | None, badge: str | None) -> dict[str, Any]:
        """Select frame/badge ("" or None clears).  Must be unlocked."""
        pid = player_id_for(token)
        self.store.get_player(pid, self.now())
        unlocked = set(self.unlocked_decor(self.store.owned(pid)))
        updates: dict[str, Any] = {}
        for field, value, kind in (("frame", frame, "frame"), ("badge", badge, "badge")):
            if value is None:
                continue
            if value == "":
                updates[field] = None
                continue
            item = self.manifest.decor.get(value)
            if item is None or item["kind"] != kind:
                raise GameError("bad_decor", f"unknown {kind}")
            if value not in unlocked:
                raise GameError("locked", f"{kind} not unlocked")
            updates[field] = value
        if updates:
            self.store.update_player(pid, **updates)
        return self.status(token)

    def decor_for(self, token: str | None) -> tuple[str | None, str | None]:
        """Selected (frame, badge) of a token for the room member list, validated against unlocks."""
        if not token:
            return None, None
        try:
            pid = player_id_for(token)
        except GameError:
            return None, None
        p = self.store.get_player(pid, self.now())
        unlocked = set(self.unlocked_decor(self.store.owned(pid)))
        frame = p["frame"] if p["frame"] in unlocked else None
        badge = p["badge"] if p["badge"] in unlocked else None
        return frame, badge
