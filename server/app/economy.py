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
  into at once (emotes, cards by tier, ``holo`` for holo cards and ``dance`` for dance cards, both optional).
  ``repeatTiers`` keep their odds once
  everything in them is owned; their repeats turn into shards. ``rates.limited`` is the limited tier (the 衣橱 cards):
  without it those cards stay out of the pool. A tier a client's pool leaves empty (the limited tier for a client
  older than its cards) gives its odds to common, and ``GET /api/economy`` shows that client the rates so folded.
  ``holoChance`` is the chance (0 to 100) that a draw of a card with a holo version (镭射款) is that version; without it
  there are none. Clients older than the holo versions never get one and are not sent it. ``banners`` are the limited
  pools (see ``app/banners.py``): each {id, name, start, end, items, rate, rates, share, pity}. A client is sent the ones it can
  draw from, and the ids of every item a banner keeps out of the standing pool as ``held``.
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
- ``doudizhu``: 斗地主 between three room members; without it the game is off. ``stakes`` are the base stakes to
  choose from. When the three have accepted, each pays a deposit of base × ``capMult`` × 2, the most a landlord can
  lose, and gets back what the game leaves of it. The multiplier is the winning bid (1 to 3), doubled by every bomb and
  rocket and by a spring, at most ``capMult``; a farmer wins or loses base × multiplier and the landlord both farmers'
  amounts. ``rake`` percent of what the winners win is burnt. An invite waits ``inviteSec``, a bid ``bidSec``, a play
  ``playSec``, and the three have ``againSec`` after a game to ask for another. A save whose games of the China day
  have won it ``dailyWinCap`` or more starts no further game that day; losses are not capped. The three saves need
  ``minTaps`` taps in all. With ``counter`` {coins, games} the card counter is sold: ``coins`` park coins buy
  ``games`` games of it (a coin the save lacks is bought with shards at ``park.coin.price``), and one is used on each
  game the save plays with it; without ``counter`` it is free.
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
    square turns its stack upside down. ``roomAt`` is in coins. With ``maps`` ([{id, name, track, squares: [{at,
    kind, by?, to?}]}]) each race is run on one of them, on its own track and squares; with ``skills`` ([{id, dice,
    chance?, by?}], ids in race.SKILLS) each race deals them instead of forms. Clients before 1.2.5 are given only
    the result of such a race (see race.py and PROTOCOL.md).
  - ``lottery``: ``daily`` tickets a save for each draw; the draw is at minute ``drawAt`` of the China day and sales
    close at ``closeAt``. The top prize is the server-wide pool: it starts at ``pool.seed``, every coin spent in the
    park adds ``pool.perCoin``, and it rolls over until a draw has a top winner. The second prize is ``secondEach``
    shards each (without it, the rule before: ``second`` of the day's sales split between winners, rolling over when
    nobody wins it), the third ``third`` shards each.
  - ``link``: 连连看 (park_link.py), one player against the clock, paid in shards. A game costs ``entry`` shards,
    which are burnt; a save plays at most len(``levels``) games a China day (counted by the day a game starts,
    abandoned ones too), the n-th on ``levels[n-1]``: {rows, cols, kinds, seconds, shift, max, hints}. The board holds
    ``kinds`` emotes four times each (rows × cols = kinds × 4), static ones from the emote sets in ``sets``; after
    each pair the tiles move by ``shift`` (none, down, left or center; center needs an even ``cols``). A game pays
    max × counted² // total² shards (pairs), ``max`` when cleared; counted leaves out pairs played faster than
    the antiCheat setting ``link_min_pair_ms`` allows. Moves that reach the server up to ``grace``
    seconds after the deadline still count. ``hints`` are counted by the client only. With ``account`` a save needs
    a main-site account to start a game (on a server with accounts).

- ``photocards``: boxes of photocards (photocards.py), a list in shelf order with one entry for each of the manifest's
  ``series`` on the shelf; missing or empty, there are no photocards. A box costs ``price`` shards and holds ``size``
  cards; a save buys ``daily`` boxes of a series a China day, and 0 keeps the series on the shelf but sells none. One
  card of a box is rare for certain and each other one at ``rare`` percent; what a rare card is goes by the weights of
  ``split`` ({duo, group, sign}), and neither a duo nor a group card repeats before the save holds all of its kind. The
  ``signPity``-th box since the last one with a signed card has one for certain until the save holds them all. A repeat
  solo card turns into ``refund.solo`` shards, a repeat duo or group card into ``refund.rare``; ``swap`` repeats of
  signed cards are traded for one the save lacks, and turn into ``refund.rare`` shards each once it holds them all. All
  of it is counted by series.
- ``antiCheat``: fields of ``cards.DropConfig`` by name; missing ones keep their defaults. Never sent to clients.
  The rules that tell automatic input from a hand are not here: see ``app/guard.py``.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import fields
from pathlib import Path
from typing import Any

from .cards import DropConfig
from .photo_deal import RARE_KINDS

ENV = "ASOULTAPPO_ECONOMY"
EXAMPLE = Path(__file__).resolve().parent.parent / "economy.example.json"
SERVER_ONLY = "antiCheat"
# Settings of rules that moved to the guard (app/guard.py): an economy file that still has them loads as before.
RETIRED = "steady_"


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
    """Refuses settings that would roll nonsense: the holo chance, a percentage, the card counter's price, photocard
    boxes that could not be dealt and a 连连看 board that cannot be laid (check_link, without the emote sets)."""
    chance = data.get("resonance", {}).get("holoChance")
    if chance is not None and (isinstance(chance, bool) or not isinstance(chance, (int, float))
                               or not 0 <= chance <= 100):
        raise ValueError(f"resonance.holoChance must be a percentage from 0 to 100, not {chance!r}")
    counter = (data.get("doudizhu") or {}).get("counter")
    if counter is not None:
        for key in ("coins", "games"):
            n = counter.get(key) if isinstance(counter, dict) else None
            if isinstance(n, bool) or not isinstance(n, int) or n < 1:
                raise ValueError(f"doudizhu.counter.{key} must be a whole number of 1 or more, not {n!r}")
        if not (data.get("park") or {}).get("coin"):
            raise ValueError("doudizhu.counter is paid in park coins: it needs park.coin")
    if data.get("photocards") is not None:
        check_photocards(data["photocards"])
    link = (data.get("park") or {}).get("link")
    if link is not None:
        check_link(link)
        # A game needs the park open (park.coin.minTaps taps).
        taps = (data["park"].get("coin") or {}).get("minTaps")
        if isinstance(taps, bool) or not isinstance(taps, int) or taps < 0:
            raise ValueError(f"park.link needs park.coin.minTaps, a whole number of 0 or more, not {taps!r}")


LINK_SHIFTS = ("none", "down", "left", "center")


def _whole(value: Any, name: str, least: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < least:
        raise ValueError(f"{name} must be a whole number of {least} or more, not {value!r}")
    return value


def _number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


#: The most cards a box holds.
PHOTO_SIZE_MAX = 100


def check_photocards(shelf: Any) -> None:
    """Refuses photocard boxes that could not be dealt, and those whose repeats pay their price back;
    Manifest.load checks that their series exist."""
    if not isinstance(shelf, list):
        raise ValueError("photocards must be a list")
    listed: set[str] = set()
    for i, cfg in enumerate(shelf):
        name = f"photocards[{i}]"
        if not isinstance(cfg, dict):
            raise ValueError(f"{name} must be an object")
        series = cfg.get("series")
        if not isinstance(series, str) or not series:
            raise ValueError(f"{name}.series must name a photocard series")
        if series in listed:
            raise ValueError(f"{name}.series: {series!r} is listed twice")
        listed.add(series)
        for key in ("price", "size", "signPity", "swap"):
            _whole(cfg.get(key), f"{name}.{key}")
        if cfg["size"] > PHOTO_SIZE_MAX:
            raise ValueError(f"{name}.size must be {PHOTO_SIZE_MAX} or less, not {cfg['size']!r}")
        _whole(cfg.get("daily"), f"{name}.daily", 0)
        if not _number(cfg.get("rare")) or cfg["rare"] > 100:
            raise ValueError(f"{name}.rare must be a percentage from 0 to 100, not {cfg.get('rare')!r}")
        split = cfg.get("split")
        if not isinstance(split, dict) or set(split) != set(RARE_KINDS) or not all(map(_number, split.values())):
            raise ValueError(f"{name}.split must give a weight to each of {', '.join(RARE_KINDS)}")
        if not 0 < sum(split.values()) < math.inf:
            raise ValueError(f"{name}.split must not be all zero or add up to more than a number holds")
        refund = cfg.get("refund")
        for key in ("solo", "rare"):
            _whole(refund.get(key) if isinstance(refund, dict) else None, f"{name}.refund.{key}", 0)
        # What a box of nothing but repeats pays back on average.
        rares = 1 + (cfg["size"] - 1) * cfg["rare"] / 100
        back = rares * refund["rare"] + (cfg["size"] - rares) * refund["solo"]
        if back >= cfg["price"]:
            raise ValueError(f"{name}.refund pays {back:g} a box back on average, not less than its price {cfg['price']}")


def check_link(link: Any, emote_sets: list[dict[str, Any]] | None = None) -> None:
    """Refuses a park.link the game could not be played with. With the manifest's [emote_sets], also that every set
    in ``sets`` exists and their static emotes cover the largest ``kinds``; the server runs that part at start."""
    if not isinstance(link, dict):
        raise ValueError("park.link must be an object")
    for key in ("entry", "grace"):
        _whole(link.get(key), f"park.link.{key}")
    if not isinstance(link.get("account", False), bool):
        raise ValueError("park.link.account must be true or false")
    sets = link.get("sets")
    if not isinstance(sets, list) or not sets or not all(isinstance(s, str) for s in sets):
        raise ValueError("park.link.sets must list emote set ids")
    levels = link.get("levels")
    if not isinstance(levels, list) or not levels:
        raise ValueError("park.link.levels must list at least one level")
    for i, level in enumerate(levels):
        name = f"park.link.levels[{i}]"
        if not isinstance(level, dict):
            raise ValueError(f"{name} must be an object")
        rows, cols, kinds = (_whole(level.get(k), f"{name}.{k}") for k in ("rows", "cols", "kinds"))
        for key in ("seconds", "max", "hints"):
            _whole(level.get(key), f"{name}.{key}")
        if rows * cols != kinds * 4:
            raise ValueError(f"{name}: rows × cols must be kinds × 4")
        shift = level.get("shift")
        if shift not in LINK_SHIFTS:
            raise ValueError(f"{name}.shift must be one of {', '.join(LINK_SHIFTS)}, not {shift!r}")
        if shift == "center" and cols % 2:
            raise ValueError(f"{name}: shift center needs an even number of cols")
    if emote_sets is None:
        return
    by_id = {s["id"]: s for s in emote_sets}
    missing = [s for s in sets if s not in by_id]
    if missing:
        raise ValueError(f"park.link.sets: no emote set {', '.join(missing)}")
    static = len({e["key"] for s in sets for e in by_id[s]["emotes"] if not e.get("animated")})
    most = max(level["kinds"] for level in levels)
    if static < most:
        raise ValueError(f"park.link.sets hold {static} static emotes, fewer than the {most} kinds of a level")


def drop_config(anti: dict[str, Any]) -> DropConfig:
    known = {f.name for f in fields(DropConfig)}
    anti = {k: v for k, v in anti.items() if not k.startswith(RETIRED)}
    unknown = sorted(set(anti) - known)
    if unknown:
        raise ValueError(f"unknown {SERVER_ONLY} settings: {', '.join(unknown)}")
    return DropConfig(**anti)


def client_view(economy: dict[str, Any], cfg: DropConfig,
                pool: dict[str, list[dict]] | None = None, holo: bool = True,
                banners: list[dict[str, Any]] | None = None, held: list[str] | None = None) -> dict[str, Any]:
    """What GET /api/economy answers: the economy and the thresholds of the client's own input guard. With the
    client's resonance [pool], a tier it leaves empty is folded into common, as its draws do. Without [holo] (a client
    that gets no holo versions) the holo chance is left out. The economy's own list of limited pools never goes out:
    the client gets [banners], those it can draw from now or within the hour, and [held], the items kept out of the
    standing pool for a banner."""
    out = {**economy, "tapGuard": {"fastPerSecond": cfg.fast_taps_per_sec, "fastStreakSec": cfg.fast_streak_sec,
                                   "cooldownSec": cfg.tap_cooldown_sec}}
    res = economy.get("resonance")
    if not res:
        return out
    view = res
    if "banners" in res or banners or held:
        view = {k: v for k, v in res.items() if k != "banners"}
        if banners:
            view["banners"] = banners
        if held:
            view["held"] = held
    if not holo and "holoChance" in res:
        view = {k: v for k, v in view.items() if k != "holoChance"}
    if pool is not None:
        rates = dict(res["rates"])
        for tier in [t for t in rates if t != "common" and not pool.get(t)]:
            rates["common"] = round(rates["common"] + rates.pop(tier), 6)
        if rates != res["rates"]:
            view = {**view, "rates": rates}
    if view is not res:
        out["resonance"] = view
    return out
