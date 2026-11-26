"""Asset manifest loader (assets-packs/manifest.json, produced by scripts/build_assets.py).

The server only needs the *metadata* (items, rarities); the image and video files are served statically from the
packs directory. The economy comes from its own private file (app/economy.py) and is merged in as ``economy``.

Collectible items have namespaced ids:
  card:<card id>   emote:<emote key>   char:<skin name>   holo:<card id>
A card with a ``holo`` has a holo version (镭射款), an item of its own: resonance turns a draw of the card into it at
``resonance.holoChance`` (see Game.resonate); it is never in a tier of the pool and never crafted.
Starter items (see ``starter`` in the manifest) are owned by every player and never drop.
An emote set with a ``source`` (scratch) is won there only: its emotes are neither in the resonance pool nor crafted.
A card or skin with a ``since`` ships with that release: older clients' pools leave it out.
Photocards (``photocards``) are kept apart from these items: see photo_deal.py.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable
from functools import cached_property
from pathlib import Path
from typing import Any

from . import banners as banner_file
from . import economy as economy_file
from . import photo_deal
from . import race as race_rules
from .notice import version_key

APP_DIR = Path(__file__).resolve().parent


def find_packs_dir() -> Path:
    """ASOULTAPPO_PACKS, else ./assets-packs next to the app dir (docker) or the repo root (dev)."""
    env = os.environ.get("ASOULTAPPO_PACKS")
    if env:
        return Path(env)
    for cand in (APP_DIR.parent / "assets-packs", APP_DIR.parent.parent / "assets-packs"):
        if (cand / "manifest.json").exists():
            return cand
    return APP_DIR.parent.parent / "assets-packs"


class Manifest:
    def __init__(self, data: dict[str, Any], anti_cheat: dict[str, Any] | None = None) -> None:
        self.data = data
        #: Server-only settings from the economy file's antiCheat (economy.drop_config).
        self.anti_cheat = anti_cheat or {}

    @classmethod
    def load(cls, path: Path | str | None = None, economy: Path | str | None = None) -> "Manifest":
        """The asset manifest with the economy file merged in (ASOULTAPPO_ECONOMY unless [economy] is given)."""
        p = Path(path) if path else find_packs_dir() / "manifest.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["economy"], anti = economy_file.load(economy)
        m = cls(data, anti)
        m.banners  # a banner the server could not run stops the start
        for i, series in enumerate(m.photo_shelf):
            if series not in m.photo_series:
                raise ValueError(f"photocards[{i}].series: no photocard series {series!r}")
            cards = m.photo_series[series].cards
            for card in m.photo_shelf[series].get("weight", {}):
                if card not in cards:
                    raise ValueError(f"photocards[{i}].weight: no card {card!r} in {series}")
        if (m.park or {}).get("race"):
            # So does a race map or skill the race could not be run with.
            race_rules.Rules.of(m.park["race"], [c["id"] for c in data["characters"]])
        return m

    @cached_property
    def economy(self) -> dict:
        return self.data["economy"]

    @cached_property
    def cards(self) -> dict[str, dict]:
        return {c["id"]: c for c in self.data["cards"]}

    @cached_property
    def items(self) -> dict[str, dict]:
        """Every collectible item: id -> {id, kind, rarity, name, source}; source is None for resonance items."""
        out: dict[str, dict] = {}

        def add(kind: str, iid: str, rarity: str | None, name: str, source: str | None = None) -> None:
            out[f"{kind}:{iid}"] = {"id": f"{kind}:{iid}", "kind": kind, "rarity": rarity, "name": name,
                                    "source": source}

        for c in self.data["cards"]:
            add("card", c["id"], c["rarity"], c["name"])
        for s in self.data.get("emoteSets", []):
            for e in s["emotes"]:
                add("emote", e["key"], s.get("rarity", "common"), e["name"], s.get("source"))
        for skin in self.data["skins"]:
            add("char", skin["name"], "skin", skin.get("title") or skin["name"])
        for c in self.data["cards"]:
            if c.get("holo"):
                add("holo", c["id"], "holo", c["name"])
        return out

    @cached_property
    def starter(self) -> frozenset[str]:
        st = self.data.get("starter", {})
        ids = {f"emote:{k}" for k in st.get("emotes", [])}
        return frozenset(i for i in ids if i in self.items)

    @cached_property
    def skins(self) -> dict[str, dict]:
        return {s["name"]: s for s in self.data["skins"]}

    @cached_property
    def skin_since(self) -> dict[str, tuple]:
        """char:<name> -> (major, minor, patch) of the release that ships the skin, for skins that name one."""
        return {f"char:{s['name']}": version_key(s["since"])[:3] for s in self.data["skins"] if s.get("since")}

    @cached_property
    def item_since(self) -> dict[str, tuple]:
        """Item id -> (major, minor, patch) of the release that ships it, for the cards, holo versions and skins that
        name one."""
        cards = {f"card:{c['id']}": version_key(c["since"])[:3] for c in self.data["cards"] if c.get("since")}
        holos = {f"holo:{c['id']}": version_key(c["holo"]["since"])[:3] for c in self.data["cards"]
                 if c.get("holo", {}).get("since")}
        return {**cards, **holos, **self.skin_since}

    @cached_property
    def holos(self) -> dict[str, str]:
        """card:<id> -> holo:<id> for every card with a holo version."""
        return {f"card:{c['id']}": f"holo:{c['id']}" for c in self.data["cards"] if c.get("holo")}

    def holos_for(self, version: str | None) -> dict[str, str]:
        """The holo versions a client of [version] can show, by the rule of resonance_pool_for. None: all of them."""
        held = self.held_for(version)
        return {card: holo for card, holo in self.holos.items() if holo not in held}

    def held_for(self, version: str | None) -> frozenset[str]:
        """Item ids a client of [version] cannot show (see resonance_pool_for); empty for None."""
        if version is None:
            return frozenset()
        key = version_key(version)
        have = key[:3] if key else (0, 0, 0)
        return frozenset(iid for iid, since in self.item_since.items() if since > have)

    def resonance_pool_for(self, version: str | None, now: float | None = None, *,
                           tiers: Iterable[str] = ()) -> dict[str, list[dict]]:
        """The standing pool a client of [version] can show: cards and skins from a later release are left out, as
        is every one with a `since` when the version is missing or unreadable. A pre-release counts as its release.
        None: the whole pool. With [now], the items of banners that have not ended are left out too (app/banners.py).
        [tiers] can add tiers that only a limited pool rates."""
        pool = self.resonance_pool
        extra = set(tiers) - pool.keys()
        if extra:
            pool = {**pool, **{tier: self.resonance_catalog.get(tier, []) for tier in extra}}
        held = self.held_for(version)
        if now is not None:
            held |= banner_file.held(self.banners, now)
        if not held:
            return pool
        return {r: [i for i in items if i["id"] not in held] for r, items in pool.items()}

    @cached_property
    def banners(self) -> tuple[banner_file.Banner, ...]:
        """The economy's limited pools (resonance.banners), past, running and to come."""
        return banner_file.load(self.resonance.get("banners"), self.items, self.resonance.get("rates"))

    def banners_for(self, version: str | None, now: float) -> list[banner_file.Banner]:
        """The banners a client of [version] is told of at [now]: running or about to start, and featuring nothing
        it cannot show."""
        held = self.held_for(version)
        return [b for b in self.banners
                if b.start - banner_file.ANNOUNCE_SECONDS <= now < b.end and not held.intersection(b.items)]

    def banner(self, banner_id: str, version: str | None, now: float) -> banner_file.Banner | None:
        """The running banner [banner_id], if a client of [version] can draw from it at [now]."""
        return next((b for b in self.banners_for(version, now) if b.id == banner_id and b.running(now)), None)

    @cached_property
    def resonance_pool(self) -> dict[str, list[dict]]:
        """Items by tier. An item whose tier has no rate in the economy (say the limited tier before its rate is set)
        stays out of the pool, as do holo versions, which come from their card's draws."""
        return {tier: self.resonance_catalog.get(tier, []) for tier in self.resonance["rates"]}

    @cached_property
    def resonance_catalog(self) -> dict[str, list[dict]]:
        pool: dict[str, list[dict]] = {}
        for item in self.items.values():
            if (item["id"] not in self.starter and not item["source"] and item["kind"] != "holo"
                    and item["rarity"] is not None):
                pool.setdefault(item["rarity"], []).append(item)
        return pool

    @cached_property
    def income(self) -> dict:
        return self.data["economy"]["income"]

    @cached_property
    def resonance(self) -> dict:
        return self.data["economy"]["resonance"]

    @cached_property
    def craft_cost(self) -> dict[str, int]:
        return dict(self.data.get("economy", {}).get("craftCost", {}))

    @cached_property
    def checkin(self) -> dict:
        """The daily check-in: prizes by amount, each {shards, weight}; weights are percentages."""
        return self.data["economy"]["checkin"]

    @cached_property
    def scratch(self) -> dict | None:
        """Scratch cards: {price, daily, prizes: [{shards, weight}], emote: {set, weight, pity}, announce};
        weights are percentages. None on a manifest without them. An older manifest's `emote.fallback` is
        ignored: a whole set has no emote tier."""
        return self.data["economy"].get("scratch")

    @cached_property
    def duel(self) -> dict | None:
        """Rock-paper-scissors in rooms: {stakes: [{bet, prize}], inviteSec, throwSec, dailyWinCap, minTaps}.
        None on a manifest without it, which turns the game off."""
        return self.data.get("economy", {}).get("duel")

    @cached_property
    def ddz(self) -> dict | None:
        """Dou dizhu (斗地主) between three room members: {stakes, capMult, rake, inviteSec, bidSec, playSec, againSec,
        dailyWinCap, minTaps} (see economy.py). None on a manifest without it, which turns the game off."""
        return self.data.get("economy", {}).get("doudizhu")

    @cached_property
    def park(self) -> dict | None:
        """The park, paid in coins: {coin, scratch, race, lottery} (see PARK in scripts/asset_catalog.py). None on a
        manifest without it, which turns the park off."""
        return self.data.get("economy", {}).get("park")

    @cached_property
    def photo_shelf(self) -> dict[str, dict]:
        """Photocard boxes by series, in shelf order: {series, price, size, daily, rare, split, signPity, swap, refund}
        each (see economy.py). Empty on an economy without them, which turns photocards off."""
        return {cfg["series"]: cfg for cfg in self.data.get("economy", {}).get("photocards") or []}

    @cached_property
    def photo_series(self) -> dict[str, photo_deal.Series]:
        """Photocard series by id, in manifest order, whether on the shelf or not."""
        return photo_deal.load(self.data.get("photocards"))

    @cached_property
    def scratch_emotes(self) -> tuple[str, ...]:
        """Emote keys of the set scratch cards give out, in set order."""
        cfg = self.scratch
        return tuple(e["key"] for s in self.data.get("emoteSets", []) if cfg and s["id"] == cfg["emote"]["set"]
                     for e in s["emotes"])

    @cached_property
    def plates(self) -> dict[str, list[str]]:
        """Name plates besides the big hidden cards: plate id -> the item ids that unlock it (every emote of its
        `emoteSet`, or every card of its `series`). A plate whose set is unknown or empty is left out; older
        manifests have none."""
        sets = {s["id"]: s["emotes"] for s in self.data.get("emoteSets", [])}
        out: dict[str, list[str]] = {}
        for p in self.data.get("plates", []):
            if p.get("series"):
                needs = [f"card:{c['id']}" for c in self.data["cards"] if c["series"] == p["series"]]
            else:
                needs = [f"emote:{e['key']}" for e in sets.get(p.get("emoteSet"), [])]
            if needs:
                out[p["id"]] = needs
        return out

    @cached_property
    def series_total(self) -> dict[str, int]:
        return {s["id"]: s["total"] for s in self.data["series"]}

    @cached_property
    def character_names(self) -> set[str]:
        return {c["name"] for c in self.data["characters"]}
