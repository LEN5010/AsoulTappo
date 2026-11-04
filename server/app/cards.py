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
    x = rng.random() * 100
    edge = rates["legendary"]
    if "legendary" in available and (pity["legendary"] + 1 >= hard_pity["legendary"] or x < edge):
        return "legendary"
    if "skin" in available and (pity["skin"] + 1 >= hard_pity["skin"] or edge <= x < edge + rates["skin"]):
        return "skin"
    edge += rates["skin"]
    if "epic" in available and edge <= x < edge + rates["epic"]:
        return "epic"
    edge += rates["epic"]
    if "rare" in available and edge <= x < edge + rates["rare"]:
        return "rare"
    return "common"


def default_rng() -> Rng:
    return random.SystemRandom()
