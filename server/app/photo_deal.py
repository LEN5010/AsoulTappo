"""What a box of photocards holds (官周小卡): the series from the manifest and the deal of one box, without storage.

Item ids: ``photo:<series>/<card>`` for a card and ``sign:<series>/<card>`` for the signed version of a solo card. They
are kept with the other items of a save but are not in Manifest.items: they count in no total, progress or board, are
in no resonance pool and are not crafted.
"""
from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from .cards import Rng, pick_weighted

#: What a rare card can be; economy photocards.split gives their weights.
RARE_KINDS = ("duo", "group", "sign")
#: The rare kinds of which no card comes again before the save holds all of them.
UNREPEATED = ("duo", "group")
KINDS = ("solo", "duo", "group")
PREFIXES = ("photo:", "sign:")
#: A series' or a card's id. The longest item id of two stays within what the calls take (PhotoSwapBody).
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,27}")


@dataclass(frozen=True)
class Series:
    """The item ids of one series by kind, in manifest order."""
    id: str
    solo: tuple[str, ...]
    duo: tuple[str, ...]
    group: tuple[str, ...]
    sign: tuple[str, ...]

    def of(self, kind: str) -> tuple[str, ...]:
        return {"solo": self.solo, "duo": self.duo, "group": self.group, "sign": self.sign}[kind]

    @cached_property
    def items(self) -> tuple[str, ...]:
        return self.solo + self.duo + self.group + self.sign


@dataclass(frozen=True)
class Pull:
    item: str
    kind: str
    #: The save did not hold it before this bag.
    new: bool


def load(raw: Any) -> dict[str, Series]:
    """The manifest's photocard series by id; refuses one a box could not be dealt from."""
    out: dict[str, Series] = {}
    for entry in raw or []:
        sid = entry["id"]
        ids = [c["id"] for c in entry["cards"]]
        for i in (sid, *ids):
            if not isinstance(i, str) or not ID.fullmatch(i):
                raise ValueError(f"photocards: {i!r} in {sid!r} is not an id of small letters, digits, - and _")
        if sid in out or len(set(ids)) != len(ids):
            raise ValueError(f"photocards: {sid} repeats an id")
        by_kind: dict[str, list[str]] = {k: [] for k in KINDS}
        for c in entry["cards"]:
            if c["kind"] not in by_kind:
                raise ValueError(f"photocards: {sid}/{c['id']} is a {c['kind']!r}, not one of {', '.join(KINDS)}")
            by_kind[c["kind"]].append(c["id"])
        empty = [k for k, cards in by_kind.items() if not cards]
        if empty:
            raise ValueError(f"photocards: {sid} has no {', '.join(empty)} card")
        out[sid] = Series(sid, *(tuple(f"photo:{sid}/{c}" for c in by_kind[k]) for k in KINDS),
                          tuple(f"sign:{sid}/{c}" for c in by_kind["solo"]))
    return out


def _pick(rng: Rng, n: int) -> int:
    return min(int(rng.random() * n), n - 1)


def deal(cfg: dict[str, Any], series: Series, owned: Collection[str], dry: int, rng: Rng) -> list[Pull]:
    """The cards of one box in the order they are opened, for a save that holds [owned] and bought [dry] boxes since
    the last one with a signed card.

    One bag, at a random place, is rare for certain and each other one at `rare` percent. A rare card's kind is drawn
    by the weights of `split`. A duo or group card is one the save lacks while its kind has one left, so a box repeats
    neither kind before it is whole; after that it is any of the kind, as a signed card always is. The other bags hold
    any of the solo cards. The signPity-th box since the last signed card has one for certain in the bag that is rare
    for certain, until the save holds every signed card; it may be one the save holds."""
    size = cfg["size"]
    sure = _pick(rng, size)
    weights = [cfg["split"][k] for k in RARE_KINDS]
    kinds = ["solo"] * size
    for i in range(size):
        if i == sure or rng.random() * 100 < cfg["rare"]:
            kinds[i] = RARE_KINDS[pick_weighted(weights, rng)]
    have = set(owned)
    if dry + 1 >= cfg["signPity"] and "sign" not in kinds and not have.issuperset(series.sign):
        kinds[sure] = "sign"
    out = []
    for kind in kinds:
        cards = series.of(kind)
        if kind in UNREPEATED:
            cards = [c for c in cards if c not in have] or cards
        item = cards[_pick(rng, len(cards))]
        out.append(Pull(item, kind, item not in have))
        have.add(item)
    return out
