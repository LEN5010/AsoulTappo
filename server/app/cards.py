"""Pure resonance rolls with independent pity counters and an injectable RNG."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol


class Rng(Protocol):
    def random(self) -> float: ...


@dataclass(frozen=True)
class DropConfig:
    min_taps_active_minute: int = 10
    max_taps_per_sec: int = 15


def roll_tier(rates, available, pity, hard_pity, rng: Rng) -> str:
    """Unavailable tiers land on common; legendary pity takes precedence."""
    x = rng.random()
    edge = rates["legendary"]
    if "legendary" in available and (pity["legendary"] + 1 >= hard_pity["legendary"] or x < edge / 100):
        return "legendary"
    if "skin" in available and (pity["skin"] + 1 >= hard_pity["skin"] or edge / 100 <= x < (edge + rates["skin"]) / 100):
        return "skin"
    edge += rates["skin"]
    if "epic" in available and edge / 100 <= x < (edge + rates["epic"]) / 100:
        return "epic"
    edge += rates["epic"]
    if "rare" in available and edge / 100 <= x < (edge + rates["rare"]) / 100:
        return "rare"
    edge += rates["rare"]
    if "uncommon" in available and edge / 100 <= x < (edge + rates["uncommon"]) / 100:
        return "uncommon"
    return "common"


def default_rng() -> Rng:
    return random.SystemRandom()


def pick_common(pool, kind_weights, owned, rng: Rng):
    """Keep kind odds fixed and prefer unowned items within the selected kind."""
    groups = [(weight, [item for item in pool if item["kind"] == kind])
              for kind, weight in kind_weights.items()]
    groups = [(weight, items) for weight, items in groups if items]
    return pick_common_group([(weight, [item for item in items if item["id"] not in owned] or items)
                              for weight, items in groups], rng)


def pick_common_group(groups, rng: Rng):
    """Choose from cached kind pools using the same weighted draw."""
    x = rng.random() * sum(weight for weight, _ in groups)
    for weight, items in groups:
        if x < weight:
            return items[min(int(x / weight * len(items)), len(items) - 1)]
        x -= weight


def pick_weighted(weights, rng: Rng) -> int:
    """Index chosen with probability proportional to its weight."""
    x = rng.random() * sum(weights)
    for i, weight in enumerate(weights):
        if x < weight:
            return i
        x -= weight
    return len(weights) - 1
