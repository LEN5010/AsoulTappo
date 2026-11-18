"""Limited pools (限定卡池): resonance pools with a start and an end, listed in the economy as ``resonance.banners``.

A banner features some items of the catalog (cards, skins). Until it ends they are found there only: they stay out
of the standing pool from the moment the economy names them, so a banner that has not started yet keeps its items
back too. Once it ends they join the standing pool in their own tier, at its odds.

While a banner runs, a draw there is a draw from the standing pool, changed in up to three ways:

- ``rates`` gives some tiers odds of the banner's own (percent; common takes what is left of 100).
- ``share``: when the tier rolled is one a featured item the save lacks belongs to, that percent of the time the
  drop is one of those featured items instead of the tier's standing ones. A standing one there makes the save's next
  draw of that tier in this banner a featured one for certain (大保底); the guarantee stays with the banner.
- ``rate`` puts one more tier in front of common: that percent of draws are a featured item the save lacks.

A banner names ``share`` or ``rate`` (or both), or its featured items could not be found. With ``pity`` the draw
that many draws after the last featured item is one for certain. The legendary and skin pity counters are the
save's, whatever pool it draws from; a featured skin counts as a skin for them. Featured items never repeat: once
the save has them all the banner draws as the standing pool does, at the banner's odds.

``start`` and ``end`` are ISO 8601 times with an offset (``2026-11-21T12:00:00+08:00``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# A client is told of a banner this long before it starts, so the pool opens on time between two economy fetches.
ANNOUNCE_SECONDS = 3600.0
#: The tiers a banner may give odds of its own. Common is what the others leave.
TIERS = ("legendary", "skin", "epic", "rare", "uncommon", "limited")


@dataclass(frozen=True)
class Banner:
    id: str
    name: str
    start: float
    end: float
    items: tuple[str, ...]
    rate: float = 0.0
    pity: int | None = None
    #: Tier -> percent, for the tiers whose odds are the banner's own.
    rates: tuple[tuple[str, float], ...] = ()
    share: float = 0.0

    def running(self, now: float) -> bool:
        return self.start <= now < self.end

    def tier_rates(self, base: dict[str, float]) -> dict[str, float]:
        """The odds of a draw here by tier: [base] with the banner's own, common taking what is left."""
        if not self.rates:
            return base
        out = {**base, **dict(self.rates)}
        out["common"] = max(0.0, 100 - sum(v for k, v in out.items() if k != "common"))
        return out

    def view(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "name": self.name, "start": self.start, "end": self.end,
                               "items": list(self.items)}
        if self.rate:
            out["rate"] = self.rate
        if self.rates:
            out["rates"] = dict(self.rates)
        if self.share:
            out["share"] = self.share
        if self.pity:
            out["pity"] = self.pity
        return out


def _time(value: Any, what: str) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        at = datetime.fromisoformat(str(value))
    except ValueError as e:
        raise ValueError(f"{what} is not a time: {value!r}") from e
    if at.tzinfo is None:
        raise ValueError(f"{what} needs an offset (…+08:00): {value!r}")
    return at.timestamp()


def _percent(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and 0 <= value <= 100


def load(raw: Any, items: dict[str, dict], base: dict[str, float] | None = None) -> tuple[Banner, ...]:
    """The economy's banners, checked against the catalog's [items] and the standing pool's [base] rates: a banner
    the server could not run as written stops the start, like the rest of the economy file."""
    out: list[Banner] = []
    seen: set[str] = set()
    for b in raw or ():
        bid = b.get("id")
        if not isinstance(bid, str) or not bid or bid in seen:
            raise ValueError(f"banner id missing or repeated: {bid!r}")
        seen.add(bid)
        start, end = _time(b.get("start"), f"banner {bid} start"), _time(b.get("end"), f"banner {bid} end")
        if end <= start:
            raise ValueError(f"banner {bid} ends before it starts")
        featured = tuple(b.get("items") or ())
        unknown = [i for i in featured if i not in items or items[i]["kind"] not in ("card", "char")
                   or items[i]["source"]]
        if not featured or unknown or len(set(featured)) != len(featured):
            raise ValueError(f"banner {bid} features nothing, or items the pool cannot give: {unknown}")
        rate, share = b.get("rate", 0), b.get("share", 0)
        if not _percent(rate) or not _percent(share):
            raise ValueError(f"banner {bid} rate and share must be percentages, not {rate!r} and {share!r}")
        if not rate and not share:
            raise ValueError(f"banner {bid} needs a rate or a share above 0, or its items cannot be found")
        rates = b.get("rates") or {}
        if not isinstance(rates, dict) or any(k not in TIERS or not _percent(v) for k, v in rates.items()):
            raise ValueError(f"banner {bid} rates must be percentages for some of {TIERS}, not {rates!r}")
        # Common keeps what the other tiers and the featured tier leave: they cannot take more than there is.
        if rates and sum({**{k: v for k, v in (base or {}).items() if k != "common"}, **rates}.values()) + rate > 100:
            raise ValueError(f"banner {bid} rates add up to more than 100")
        pity = b.get("pity")
        if pity is not None and (isinstance(pity, bool) or not isinstance(pity, int) or pity < 1):
            raise ValueError(f"banner {bid} pity must be a whole number of draws, not {pity!r}")
        out.append(Banner(bid, str(b.get("name") or bid), start, end, featured, float(rate), pity,
                          tuple((k, float(v)) for k, v in rates.items()), float(share)))
    # Two banners that overlap in time cannot share an item: each would take it out of the other's reach.
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            if a.start < b.end and b.start < a.end and set(a.items) & set(b.items):
                raise ValueError(f"banners {a.id} and {b.id} run together and share items")
    return tuple(out)


def held(banners: tuple[Banner, ...], now: float) -> frozenset[str]:
    """Items out of the standing pool at [now]: those of every banner that has not ended."""
    return frozenset(i for b in banners if now < b.end for i in b.items)
