"""Small synthetic manifest + helpers shared by the game/API tests."""
from __future__ import annotations

from app.manifest import Manifest


def _card(cid, rarity, series="s1", chars=("嘉然",)):
    return {"id": cid, "name": cid, "series": series, "sub": None, "characters": list(chars),
            "rarity": rarity, "thumb": f"bundle:cards/thumb/{cid}.webp",
            "full": f"pack:cards/{series}/{cid}.webp", "video": None}


def tiny_manifest() -> Manifest:
    cards = [_card("c1", "common"), _card("c2", "common"), _card("c3", "rare"),
             _card("c4", "epic", "s2"), _card("c5", "legendary", "s2")]
    return Manifest({
        "version": 1,
        "characters": [{"id": "jiaran", "name": "嘉然", "color": "#e799b0"}],
        "rarities": {"common": {"name": "普通", "weight": 70}, "rare": {"name": "稀有", "weight": 22},
                     "epic": {"name": "史诗", "weight": 7}, "legendary": {"name": "传说", "weight": 1}},
        "series": [{"id": "s1", "name": "S1", "total": 3}, {"id": "s2", "name": "S2", "total": 2}],
        "cards": cards,
        "decor": [
            {"id": "badge-s1", "kind": "badge", "name": "b", "img": "bundle:x", "unlock": {"series": "s1", "min": 1}},
            {"id": "frame-s1", "kind": "frame", "name": "f", "img": "bundle:x", "unlock": {"series": "s1", "min": 3}},
        ],
        "themes": [{"id": "x", "name": "X", "default": True, "rarity": None},
                   {"id": "y", "name": "Y", "default": False, "rarity": "rare"}],
        "defaultTheme": "x",
        "emoteSets": [{"id": "e", "name": "E", "character": "嘉然", "rarity": "common", "emotes": [
            {"key": "e.01", "name": "a", "img": "bundle:x"}, {"key": "e.02", "name": "b", "img": "bundle:x"},
            {"key": "e.03", "name": "c", "img": "bundle:x"}]}],
        "accessories": [
            {"id": "hat", "name": "hat", "kind": "figure", "slot": "head", "characters": ["嘉然"],
             "rarity": "rare", "img": "bundle:x"},
            {"id": "cat", "name": "cat", "kind": "anim", "slot": "desk", "characters": ["嘉然"],
             "rarity": "epic", "img": "bundle:x"},
        ],
        "starter": {"emotes": ["e.01"], "theme": "x"},
        "economy": {"dupShards": {"common": 1, "rare": 3, "epic": 8, "legendary": 20},
                    "craftCost": {"common": 10, "rare": 30, "epic": 80, "legendary": 200}},
    })


class SeqRng:
    """rng.random() returns the given values in order (then repeats the last)."""

    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


class Clock:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t
