"""Asset manifest loader (assets-packs/manifest.json, produced by scripts/build_assets.py).

The server only needs the *metadata* (items, rarities, economy); the image
and video files are served statically from the packs directory.

Collectible items have namespaced ids:
  card:<card id>   emote:<emote key>   char:<skin name>
Starter items (see ``starter`` in the manifest) are owned by every player and never drop.
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
        """Every collectible item: id -> {id, kind, rarity, name}."""
        out: dict[str, dict] = {}

        def add(kind: str, iid: str, rarity: str | None, name: str) -> None:
            out[f"{kind}:{iid}"] = {"id": f"{kind}:{iid}", "kind": kind, "rarity": rarity, "name": name}

        for c in self.data["cards"]:
            add("card", c["id"], c["rarity"], c["name"])
        for s in self.data.get("emoteSets", []):
            for e in s["emotes"]:
                add("emote", e["key"], s.get("rarity", "common"), e["name"])
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
            if item["id"] not in self.starter:
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
    def series_total(self) -> dict[str, int]:
        return {s["id"]: s["total"] for s in self.data["series"]}

    @cached_property
    def character_names(self) -> set[str]:
        return {c["name"] for c in self.data["characters"]}
