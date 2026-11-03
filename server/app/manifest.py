"""Asset manifest loader (assets-packs/manifest.json, produced by scripts/build_assets.py).

The server only needs the *metadata* (cards, rarities, frames/badges); the image
and video files are served statically from the packs directory.
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
    def by_rarity(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {r: [] for r in self.data["rarities"]}
        for c in self.data["cards"]:
            out[c["rarity"]].append(c)
        return out

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
