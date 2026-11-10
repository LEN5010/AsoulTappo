"""Pure scratch card rolls: the prize first, then nine cells that show it."""
from __future__ import annotations

from typing import Sequence

from .cards import Rng

CELLS = 9
# Emotes of the set shown among the losing symbols of one card.
DECOY_EMOTES = 3


def roll_prize(cfg: dict, pity: int, rng: Rng, complete: bool = False) -> tuple[str, int]:
    """One draw: ("emote", 0), ("shards", amount) or ("miss", 0). The emote tier comes first and is certain
    on the pity-th card since the last one, counted as in cards.roll_tier. With the set `complete` there is
    no emote tier and no pity: only the shard prizes, and the tier's weight wins nothing."""
    x = rng.random()
    emote = cfg["emote"]
    edge = 0 if complete else emote["weight"]
    if not complete and (pity + 1 >= emote["pity"] or x < edge / 100):
        return "emote", 0
    for prize in cfg["prizes"]:
        if edge / 100 <= x < (edge + prize["weight"]) / 100:
            return "shards", prize["shards"]
        edge += prize["weight"]
    return "miss", 0


def _take(items: Sequence[str], n: int, rng: Rng) -> list[str]:
    """`n` of `items` in random order, none twice."""
    pool = list(items)
    out = []
    for _ in range(min(n, len(pool))):
        out.append(pool.pop(min(int(rng.random() * len(pool)), len(pool) - 1)))
    return out


def layout(win: str | None, amounts: Sequence[int], emotes: Sequence[str], rng: Rng) -> list[str]:
    """Nine symbols, shard amounts as digits and emotes by key: `win` three times when given, and no other
    symbol more than twice, so a card shows one prize or none."""
    decoys = _take([e for e in emotes if e != win], DECOY_EMOTES, rng)
    bag = [s for s in [str(a) for a in amounts] + decoys if s != win] * 2
    cells = [win] * 3 if win else []
    cells += _take(bag, CELLS - len(cells), rng)
    return _take(cells, len(cells), rng)


def prize_of(cells: Sequence[str]) -> str | None:
    """The symbol a card shows three times."""
    return next((s for s in cells if cells.count(s) >= 3), None)
