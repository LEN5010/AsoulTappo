"""Small synthetic manifest + helpers shared by the game/API tests."""
from __future__ import annotations

from app.manifest import Manifest


def _card(cid, rarity, series="s1", chars=("嘉然",)):
    return {"id": cid, "name": cid, "series": series, "sub": None, "characters": list(chars),
            "rarity": rarity, "thumb": f"bundle:cards/thumb/{cid}.webp",
            "full": f"pack:cards/{series}/{cid}.webp", "video": None, "tier": {"legendary": "big", "epic": "small"}.get(rarity, "normal")}


def tiny_manifest() -> Manifest:
    cards = [_card("c1", "common"), _card("c2", "common"), _card("c3", "common"),
             _card("c4", "epic", "s2"), _card("c5", "legendary", "s2")]
    return Manifest({
        "version": 1,
        "characters": [{"id": "jiaran", "name": "嘉然", "color": "#e799b0"}],
        "skins": [{"name": "嘉然山海经", "member": "嘉然"}],
        "rarities": {"common": {"name": "普通", "weight": 70}, "uncommon": {"name": "罕见"}, "rare": {"name": "稀有", "weight": 22},
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
        "economy": {"income": {"perMinute": 16, "maxMultiplier": 5, "fullTapsPerMinute": 60},
                    "resonance": {"cost": 160, "rates": {"legendary": .5, "skin": .5, "epic": 4.5, "rare": 3, "uncommon": 6, "common": 85.5},
                                  "pity": {"legendary": 400, "skin": 200},
                                  "commonKindWeights": {"card": 45, "emote": 40.5}, "duplicateRefund": 10},
                    "craftCost": {"common": 480, "uncommon": 960, "rare": 1600},
                    "checkin": {"prizes": [{"shards": 80, "weight": 60}, {"shards": 1600, "weight": 40}]}},
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
