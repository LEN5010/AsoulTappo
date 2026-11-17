"""The economy: prices, odds, caps and anti-cheat thresholds, kept out of the public repository.

The server reads the JSON file named by ``ASOULTAPPO_ECONOMY`` and refuses to start without it. The live file sits next
to the database on the server (``server/config/economy.json`` locally, ignored by git); ``server/economy.example.json``
has the same shape with example numbers for development and tests. The client receives everything but ``antiCheat``
from ``GET /api/economy``, with the input guard's three thresholds added as ``tapGuard``.

Weights are percentages unless said otherwise.

- ``income``: shards come from taps only: ``dailyCap`` × (1 − e^−x) over one China day, x = a·m + b·m² + c·m³ for m
  thousand taps (``curve`` = [a, b, c]); a minute pays for its first ``tapsPerMinute`` taps.
- ``resonance``: one draw costs ``cost`` shards; ``rates`` by tier, hard ``pity`` for the legendary and skin tiers,
  ``commonKindWeights`` split the common tier between cards and emotes. ``duplicateRefund`` is what a duplicate turns
  into at once (emotes, and cards by tier; big hidden cards never repeat; ``holo`` is a repeat holo version, which
  pays what its card does when the key is missing). ``repeatTiers`` keep their odds once
  everything in them is owned; their repeats turn into shards. ``rates.limited`` is the limited tier (the 衣橱 cards):
  without it those cards stay out of the pool. A tier a client's pool leaves empty (the limited tier for a client
  older than its cards) gives its odds to common, and ``GET /api/economy`` shows that client the rates so folded.
  ``holoChance`` is the chance (0 to 100) that a draw of a card with a holo version (镭射款) is that version; without it
  there are none. Clients older than the holo versions never get one and are not sent it.
- ``craftCost``: shards to craft a missing item, by rarity.
- ``checkin``: daily check-in prizes by amount; a prize pays its shards give or take ``spread`` (uniform), so the
  amounts are seldom round while the mean is unchanged.
- ``scratch``: the old shard scratch card: ``price`` shards each, ``daily`` a China day; what is left of 100 wins
  nothing. The emote tier gives one emote of ``set`` the save lacks, for certain on the ``pity``-th card since the
  last one; once the set is whole the tier and its pity are gone and its weight wins nothing. The room hears of
  ``announce`` shards or more.
- ``duel``: rock-paper-scissors between two room members. Both pay ``bet`` when the invite is accepted and the winner
  gets ``prize``. An invite waits ``inviteSec``, each round ``throwSec``. A save's net win in a China day stays at or
  below ``dailyWinCap``; losses are not capped. Both saves need ``minTaps`` taps in all.
- ``park``, paid in coins:

  - ``coin``: ``price`` shards each; ``gift`` free a day with the save's first status that day; buying and the gift
    need ``minTaps`` taps in all. Every coin spent is a stamp; every ``stampsPerCoin`` stamps turn into a coin, and
    ``badges`` are the stamp totals that earn the three badges.
  - ``scratch``: cards by their price in ``coins``. ``again`` hands the price back. The basic card has the old card's
    emote tier and pity, and once the set is whole that weight wins nothing. A premium ``skin`` or ``big`` card is one
    the save lacks, else its ``shards``. A save's first card of each kind wins ``first`` shards. Wins of ``roomAt``
    shards are told to the room, of ``serverAt`` to every running pet. A ``hidden`` card is off sale: the server
    refuses to sell it and the client does not show it, but one already bought is still revealed and paid.
  - ``race``: one every ``interval`` seconds, bets taken for the first ``betting``; with ``startAt`` (minute of the
    China day) each race starts then. The five dumplings start on square 0 of a lap of ``track`` squares, roll for
    the order of play and move by a face of their die, carrying those stacked on them; a group must land on the
    finish exactly. Each race deals the members the ``forms`` ({id, dice}: the faces of the die that member rolls for
    the race), one each in random order, and counts over ``sims`` simulated races each member's chance p of each
    place; w = p is its weight in the opening odds. A member's share is (its coins + ``depth`` × w / Σw) / (all coins
    on that kind + ``depth``), the odds ``payout`` / (share × places), rounded down to a tenth, at least ``minOdds``
    and at most ``fairCap`` / p; a bet keeps the odds it was placed at. ``dice`` is the die of races dealt before
    forms, which drew a popularity in ``popularity`` (inclusive) as w instead; their p is places / 5 under
    ``fairCap``. A save stakes at most ``maxCoins`` a race, any number when it is 0 or missing (clients before 1.2.4
    need a number there). ``squares``: five special squares in ``range``; boost
    and trip move a landing group by ``boost`` and ``trip``, the portal's ends are ``portalGap`` apart, the flip
    square turns its stack upside down. ``roomAt`` is in coins.
  - ``lottery``: ``daily`` tickets a save for each draw; the draw is at minute ``drawAt`` of the China day and sales
    close at ``closeAt``. The top prize is the server-wide pool: it starts at ``pool.seed``, every coin spent in the
    park adds ``pool.perCoin``, and it rolls over until a draw has a top winner. The second prize is ``secondEach``
    shards each (without it, the rule before: ``second`` of the day's sales split between winners, rolling over when
    nobody wins it), the third ``third`` shards each.

- ``antiCheat``: fields of ``cards.DropConfig`` by name; missing ones keep their defaults. Never sent to clients.
"""
from __future__ import annotations

import json
import os
from dataclasses import fields
from pathlib import Path
from typing import Any

from .cards import DropConfig

ENV = "ASOULTAPPO_ECONOMY"
EXAMPLE = Path(__file__).resolve().parent.parent / "economy.example.json"
SERVER_ONLY = "antiCheat"


def economy_path() -> Path:
    path = os.environ.get(ENV)
    if not path:
        raise RuntimeError(f"{ENV} is not set: point it at the economy file ({EXAMPLE.name} for development)")
    return Path(path)


def load(path: Path | str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The economy the client may see, and the server-only anti-cheat settings."""
    data = json.loads(Path(path or economy_path()).read_text(encoding="utf-8"))
    data = {k: v for k, v in data.items() if not k.startswith("_")}
    anti = data.pop(SERVER_ONLY, None) or {}
    check(data)
    return data, anti


def check(data: dict[str, Any]) -> None:
    """Refuses settings that would roll nonsense: so far the holo chance, a percentage."""
    chance = data.get("resonance", {}).get("holoChance")
    if chance is not None and (isinstance(chance, bool) or not isinstance(chance, (int, float))
                               or not 0 <= chance <= 100):
        raise ValueError(f"resonance.holoChance must be a percentage from 0 to 100, not {chance!r}")


def drop_config(anti: dict[str, Any]) -> DropConfig:
    known = {f.name for f in fields(DropConfig)}
    unknown = sorted(set(anti) - known)
    if unknown:
        raise ValueError(f"unknown {SERVER_ONLY} settings: {', '.join(unknown)}")
    return DropConfig(**anti)


def client_view(economy: dict[str, Any], cfg: DropConfig,
                pool: dict[str, list[dict]] | None = None, holo: bool = True) -> dict[str, Any]:
    """What GET /api/economy answers: the economy and the thresholds of the client's own input guard. With the
    client's resonance [pool], a tier it leaves empty is folded into common, as its draws do. Without [holo] (a client
    that gets no holo versions) the holo chance is left out."""
    out = {**economy, "tapGuard": {"fastPerSecond": cfg.fast_taps_per_sec, "fastStreakSec": cfg.fast_streak_sec,
                                   "cooldownSec": cfg.tap_cooldown_sec}}
    res = economy.get("resonance")
    if not res:
        return out
    view = res
    if not holo and "holoChance" in res:
        view = {k: v for k, v in res.items() if k != "holoChance"}
    if pool is not None:
        rates = dict(res["rates"])
        for tier in [t for t in rates if t != "common" and not pool.get(t)]:
            rates["common"] = round(rates["common"] + rates.pop(tier), 6)
        if rates != res["rates"]:
            view = {**view, "rates": rates}
    if view is not res:
        out["resonance"] = view
    return out
