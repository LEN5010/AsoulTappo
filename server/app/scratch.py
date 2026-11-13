"""Pure scratch card rolls: the prize first, then nine cells that show it."""
from __future__ import annotations

from typing import Collection, Sequence

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


def layout(win: str | None, amounts: Sequence[int], emotes: Sequence[str], rng: Rng,
           top: Collection[str] | None = None, extra: Sequence[str] = ()) -> list[str]:
    """Nine symbols, shard amounts as digits, emotes by key and any `extra` symbols as they are: `win` three times
    when given, and no other symbol more than twice, so a card shows one prize or none. Of the `top` symbols (by
    default the largest amount) at most one shows besides the win, once: a losing card never shows two of them."""
    decoys = _take([e for e in emotes if e != win], DECOY_EMOTES, rng)
    top = {str(max(amounts))} if top is None else set(top)
    symbols = [s for s in [str(a) for a in amounts] + list(extra) + decoys if s != win]
    bag = [s for s in symbols if s not in top] * 2 + _take([s for s in symbols if s in top], 1, rng)
    cells = [win] * 3 if win else []
    cells += _take(bag, CELLS - len(cells), rng)
    return _take(cells, len(cells), rng)


def prize_of(cells: Sequence[str]) -> str | None:
    """The symbol a card shows three times."""
    return next((s for s in cells if cells.count(s) >= 3), None)
