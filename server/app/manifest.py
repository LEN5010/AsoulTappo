"""Asset manifest loader (assets-packs/manifest.json, produced by scripts/build_assets.py).

The server only needs the *metadata* (items, rarities, economy); the image
and video files are served statically from the packs directory.

Collectible items have namespaced ids:
  card:<card id>   emote:<emote key>   char:<skin name>
Starter items (see ``starter`` in the manifest) are owned by every player and never drop.
An emote set with a ``source`` (scratch) is won there only: its emotes are neither in the resonance pool nor crafted.
"""
from __future__ import annotations

import json
import os
from functools import cached_property
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent


def find_packs_dir() -> Path:
    """ASOULTAPPO_PACKS, else ./assets-packs next to the app dir (docker) or the repo root (dev)."""
    env = os.environ.get("ASOULTAPPO_PACKS")
    if env:
        return Path(env)
    for cand in (APP_DIR.parent / "assets-packs", APP_DIR.parent.parent / "assets-packs"):
        if (cand / "manifest.json").exists():
            return cand
    return APP_DIR.parent.parent / "assets-packs"


class Manifest:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Manifest":
        p = Path(path) if path else find_packs_dir() / "manifest.json"
        return cls(json.loads(p.read_text(encoding="utf-8")))

    @cached_property
    def cards(self) -> dict[str, dict]:
        return {c["id"]: c for c in self.data["cards"]}

    @cached_property
    def items(self) -> dict[str, dict]:
        """Every collectible item: id -> {id, kind, rarity, name, source}; source is None for resonance items."""
        out: dict[str, dict] = {}

        def add(kind: str, iid: str, rarity: str | None, name: str, source: str | None = None) -> None:
            out[f"{kind}:{iid}"] = {"id": f"{kind}:{iid}", "kind": kind, "rarity": rarity, "name": name,
                                    "source": source}

        for c in self.data["cards"]:
            add("card", c["id"], c["rarity"], c["name"])
        for s in self.data.get("emoteSets", []):
            for e in s["emotes"]:
                add("emote", e["key"], s.get("rarity", "common"), e["name"], s.get("source"))
        for skin in self.data["skins"]:
            add("char", skin["name"], "skin", skin["name"])
        return out

    @cached_property
    def starter(self) -> frozenset[str]:
        st = self.data.get("starter", {})
        ids = {f"emote:{k}" for k in st.get("emotes", [])}
        return frozenset(i for i in ids if i in self.items)

    @cached_property
    def skins(self) -> dict[str, dict]:
        return {s["name"]: s for s in self.data["skins"]}

    @cached_property
    def resonance_pool(self) -> dict[str, list[dict]]:
        pool = {r: [] for r in self.resonance["rates"]}
        for item in self.items.values():
            if item["id"] not in self.starter and not item["source"]:
                pool[item["rarity"]].append(item)
        return pool

    @cached_property
    def income(self) -> dict:
        return self.data["economy"]["income"]

    @cached_property
    def resonance(self) -> dict:
        return self.data["economy"]["resonance"]

    @cached_property
    def craft_cost(self) -> dict[str, int]:
        return dict(self.data.get("economy", {}).get("craftCost", {}))

    @cached_property
    def checkin(self) -> dict:
        """The daily check-in: prizes by amount, each {shards, weight}; weights are percentages."""
        return self.data["economy"]["checkin"]

    @cached_property
    def scratch(self) -> dict | None:
        """Scratch cards: {price, daily, prizes: [{shards, weight}], emote: {set, weight, pity}, announce};
        weights are percentages. None on a manifest without them. An older manifest's `emote.fallback` is
        ignored: a whole set has no emote tier."""
        return self.data["economy"].get("scratch")

    @cached_property
    def duel(self) -> dict | None:
        """Rock-paper-scissors in rooms: {stakes: [{bet, prize}], inviteSec, throwSec, dailyWinCap, minTaps}.
        None on a manifest without it, which turns the game off."""
        return self.data.get("economy", {}).get("duel")

    @cached_property
    def scratch_emotes(self) -> tuple[str, ...]:
        """Emote keys of the set scratch cards give out, in set order."""
        cfg = self.scratch
        return tuple(e["key"] for s in self.data.get("emoteSets", []) if cfg and s["id"] == cfg["emote"]["set"]
                     for e in s["emotes"])

    @cached_property
    def plates(self) -> dict[str, list[str]]:
        """Name plates besides the big hidden cards: plate id -> the emote item ids that unlock it (every emote
        of its `emoteSet`). A plate whose set is unknown or empty is left out; older manifests have none."""
        sets = {s["id"]: s["emotes"] for s in self.data.get("emoteSets", [])}
        out: dict[str, list[str]] = {}
        for p in self.data.get("plates", []):
            emotes = sets.get(p["emoteSet"])
            if emotes:
                out[p["id"]] = [f"emote:{e['key']}" for e in emotes]
        return out

    @cached_property
    def series_total(self) -> dict[str, int]:
        return {s["id"]: s["total"] for s in self.data["series"]}

    @cached_property
    def character_names(self) -> set[str]:
        return {c["name"] for c in self.data["characters"]}
