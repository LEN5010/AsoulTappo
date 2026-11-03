"""Asset manifest loader (assets-packs/manifest.json, produced by scripts/build_assets.py).

The server only needs the *metadata* (items, rarities, frames/badges); the image
and video files are served statically from the packs directory.

Collectible items have namespaced ids:
  card:<card id>   emote:<emote key>   acc:<accessory id>   theme:<theme id>
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
        return out

    @cached_property
    def starter(self) -> frozenset[str]:
        st = self.data.get("starter", {})
        ids = {f"emote:{k}" for k in st.get("emotes", [])}
        return frozenset(i for i in ids if i in self.items)

    @cached_property
    def by_rarity(self) -> dict[str, list[dict]]:
        """Droppable items (everything except starters) grouped by rarity."""
        out: dict[str, list[dict]] = {r: [] for r in self.data["rarities"]}
        for item in self.items.values():
            if item["kind"] == "emote" and item["id"] not in self.starter and item["rarity"] in out:
                out[item["rarity"]].append(item)
        return out

    @cached_property
    def card_pools(self) -> dict[str, dict[str, list[dict]]]:
        pools: dict[str, dict[str, list[dict]]] = {}
        for card in self.cards.values():
            pool = pools.setdefault(card["series"], {"big": [], "small": [], "normal": []})
            pool[card.get("tier", "normal")].append(card)
        return pools

    @cached_property
    def accessories(self) -> dict[str, dict]:
        return {a["id"]: a for a in self.data.get("accessories", [])}

    @cached_property
    def themes(self) -> dict[str, dict]:
        return {t["id"]: t for t in self.data.get("themes", [])}

    @cached_property
    def default_theme(self) -> str:
        return self.data.get("defaultTheme", "")

    @cached_property
    def dup_shards(self) -> dict[str, int]:
        return dict(self.data.get("economy", {}).get("dupShards", {}))

    @cached_property
    def craft_cost(self) -> dict[str, int]:
        return dict(self.data.get("economy", {}).get("craftCost", {}))

    @cached_property
    def weights(self) -> dict[str, float]:
        return {k: float(v["weight"]) for k, v in self.data["rarities"].items()}

    @cached_property
    def series_total(self) -> dict[str, int]:
        return {s["id"]: s["total"] for s in self.data["series"]}

    @cached_property
    def decor(self) -> dict[str, dict]:
        return {d["id"]: d for d in self.data["decor"]}

    @cached_property
    def character_names(self) -> set[str]:
        return {c["name"] for c in self.data["characters"]}
