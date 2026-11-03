"""Drop logic: rarity rolls with pity, and item choice that favours new items.

Pure functions with an injectable ``rng`` (anything with ``random()``) so the
behaviour is deterministic in tests.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol

RARITY_ORDER = ["common", "rare", "epic", "legendary"]


class Rng(Protocol):
    def random(self) -> float: ...


@dataclass(frozen=True)
class DropConfig:
    taps_per_box: int = 600            # one box per this many credited taps ...
    minutes_per_box: int = 10          # ... and one per this many active minutes
    min_taps_active_minute: int = 10   # taps needed in a UTC minute for it to count as active
    max_taps_per_sec: int = 15         # anti-cheat: credited taps are clipped to this rate
    daily_box_cap: int = 10
    inventory_cap: int = 20
    epic_soft_pity: int = 10           # opens without epic+ before the epic weight starts ramping
    epic_hard_pity: int = 20           # guaranteed epic+ on this open
    legendary_hard_pity: int = 60      # guaranteed legendary on this open
    soft_pity_step: float = 8.0        # extra epic weight per open beyond the soft threshold
    new_item_boost: float = 3.0        # unowned items weigh this much vs. owned (1.0)
    max_open_batch: int = 10           # boxes opened by one "open all" request


def _pick(weights: Mapping[str, float], rng: Rng) -> str:
    total = sum(w for w in weights.values() if w > 0)
    x = rng.random() * total
    acc = 0.0
    last = None
    for k, w in weights.items():
        if w <= 0:
            continue
        last = k
        acc += w
        if x < acc:
            return k
    assert last is not None
    return last


def roll_rarity(weights: Mapping[str, float], since_epic: int, since_legend: int,
                cfg: DropConfig, rng: Rng) -> str:
    """Pick a rarity. ``since_*`` = number of previous opens without epic+/legendary."""
    n_epic, n_leg = since_epic + 1, since_legend + 1   # this open is number n
    if n_leg >= cfg.legendary_hard_pity:
        return "legendary"
    w = {r: float(weights.get(r, 0.0)) for r in RARITY_ORDER}
    if n_epic >= cfg.epic_hard_pity:
        return _pick({"epic": w["epic"], "legendary": w["legendary"]}, rng)
    if n_epic > cfg.epic_soft_pity:
        w["epic"] += (n_epic - cfg.epic_soft_pity) * cfg.soft_pity_step
    return _pick(w, rng)


def pick_item(by_rarity: Mapping[str, list[dict]], owned: Mapping[str, int] | Iterable[str],
              rarity: str, cfg: DropConfig, rng: Rng) -> dict:
    """Pick an item of ``rarity`` (unowned x boost). Falls back to a lower, then higher rarity."""
    idx = RARITY_ORDER.index(rarity)
    order = RARITY_ORDER[: idx + 1][::-1] + RARITY_ORDER[idx + 1 :]
    for r in order:
        pool = by_rarity.get(r) or []
        if not pool:
            continue
        w = {c["id"]: (1.0 if c["id"] in owned else cfg.new_item_boost) for c in pool}
        cid = _pick(w, rng)
        return next(c for c in pool if c["id"] == cid)
    raise ValueError("no items available")


def next_pity(rarity: str, since_epic: int, since_legend: int) -> tuple[int, int]:
    if rarity == "legendary":
        return 0, 0
    if rarity == "epic":
        return 0, since_legend + 1
    return since_epic + 1, since_legend + 1


def default_rng() -> Rng:
    return random.SystemRandom()
