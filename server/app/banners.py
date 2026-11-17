"""Limited pools (限定卡池): resonance pools with a start and an end, listed in the economy as ``resonance.banners``.

A banner features some items of the catalog (cards, skins). Until it ends they are found there only: they stay out
of the standing pool from the moment the economy names them, so a banner that has not started yet keeps its items
back too. Once it ends they join the standing pool in their own tier, at its odds.

While a banner runs, a draw there is a draw from the standing pool with one more tier in front of common: ``rate``
percent of draws are a featured item the save lacks, and with ``pity`` the draw that many draws after the last one is
one for certain. The legendary and skin pity counters are the save's, whatever pool it draws from; a featured skin
counts as a skin for them. Featured items never repeat: once the save has them all the banner draws as the standing
pool does.

``start`` and ``end`` are ISO 8601 times with an offset (``2026-11-21T12:00:00+08:00``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# A client is told of a banner this long before it starts, so the pool opens on time between two economy fetches.
ANNOUNCE_SECONDS = 3600.0


@dataclass(frozen=True)
class Banner:
    id: str
    name: str
    start: float
    end: float
    items: tuple[str, ...]
    rate: float
    pity: int | None = None

    def running(self, now: float) -> bool:
        return self.start <= now < self.end

    def view(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "name": self.name, "start": self.start, "end": self.end,
                               "items": list(self.items), "rate": self.rate}
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


def load(raw: Any, items: dict[str, dict]) -> tuple[Banner, ...]:
    """The economy's banners, checked against the catalog's [items]: a banner the server could not run as written
    stops the start, like the rest of the economy file."""
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
        rate = b.get("rate")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 < rate <= 100:
            raise ValueError(f"banner {bid} rate must be a percentage above 0, not {rate!r}")
        pity = b.get("pity")
        if pity is not None and (isinstance(pity, bool) or not isinstance(pity, int) or pity < 1):
            raise ValueError(f"banner {bid} pity must be a whole number of draws, not {pity!r}")
        out.append(Banner(bid, str(b.get("name") or bid), start, end, featured, float(rate), pity))
    # Two banners that overlap in time cannot share an item: each would take it out of the other's reach.
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            if a.start < b.end and b.start < a.end and set(a.items) & set(b.items):
                raise ValueError(f"banners {a.id} and {b.id} run together and share items")
    return tuple(out)


def held(banners: tuple[Banner, ...], now: float) -> frozenset[str]:
    """Items out of the standing pool at [now]: those of every banner that has not ended."""
    return frozenset(i for b in banners if now < b.end for i in b.items)
