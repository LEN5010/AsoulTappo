"""Coin scratch cards in the park: a basic card for 1 coin and a premium one for 5 (manifest economy.park.scratch).

Like the old shard cards (game.scratch_*), a card's prize is decided when it is bought and paid when it is revealed,
so the balance after buying shows only the price, and a save holds one unrevealed card at a time.

The jackpot: every coin spent on a card adds `jackpot.perCoin` shards to the pot (park_counters JACKPOT, `seed` when
absent). The card's own coins go in first, then the jackpot is drawn on its own (`coins / odds`) before the table. A
hit replaces the table roll: the card is a jackpot card and nothing else. The pot is taken in the buy transaction (it
restarts at `seed` then, so a second winner before the reveal never shares it) and paid at the reveal."""
from __future__ import annotations

import json
from typing import Any, Sequence

from . import scratch as scratchlogic
from .cards import Rng
from .game import SCRATCH_DAYS, GameError, player_id_for
from .park import JACKPOT, Park
from .store import Store, day_of

# Symbols besides amounts and emote keys. BLANK fills premium cards, which have too few prizes for nine cells.
AGAIN, SKIN, BIG, POT, BLANK = "again", "skin", "big", "jackpot", "blank"
# Shard ledger sources (park.PRIZE_SOURCES).
PRIZE = "park_scratch"
POT_SOURCE = "jackpot"


def roll(card: dict[str, Any], pity: int, rng: Rng, complete: bool, odds: int) -> tuple[str, int]:
    """One card: (tier, shards) with shards set for the `shards` tier only. The jackpot is drawn first, at
    coins/odds. Then one draw over the table in percent: the emote tier (certain on the pity-th card since the
    last emote, as in scratch.roll_prize; with the set `complete` it is a second `again`), again, the shard
    prizes in order, skin, big; the rest misses."""
    if rng.random() < card["coins"] / odds:
        return "jackpot", 0
    x = rng.random() * 100
    edge = 0.0
    emote = card.get("emote")
    if emote:
        if not complete and pity + 1 >= emote["pity"]:
            return "emote", 0
        edge = emote["weight"]
        if x < edge:
            return ("again" if complete else "emote"), 0
    edge += card["again"]
    if x < edge:
        return "again", 0
    for prize in card["prizes"]:
        edge += prize["weight"]
        if x < edge:
            return "shards", prize["shards"]
    for tier in ("skin", "big"):
        if tier in card:
            edge += card[tier]["weight"]
            if x < edge:
                return tier, 0
    return "miss", 0


def top_symbols(card: dict[str, Any], server_at: int) -> set[str]:
    """Symbols a losing card shows one of at most: amounts told to the whole server, skin, big and the jackpot."""
    return {str(p["shards"]) for p in card["prizes"] if p["shards"] >= server_at} | {SKIN, BIG, POT}


def symbols(card: dict[str, Any]) -> list[str]:
    """Symbols besides the amounts and emotes a card of this table can show."""
    out = [AGAIN] + [t for t in (SKIN, BIG) if t in card] + [POT]
    return out if card.get("emote") else out + [BLANK]


def mean_return(card: dict[str, Any], jackpot: dict[str, Any], complete: bool) -> float:
    """Shards a coin bought for this card returns in the long run, coins from `again` played on until they turn into
    shards, skin and big at their `shards`. The pot pays perCoin for every coin plus its seed once per win."""
    q = card["coins"] / jackpot["odds"]
    emote = card.get("emote")
    # Share of cards the table is rolled on (the pity forces an emote on the rest), as in cards.roll_tier.
    rolled, extra_again = 1.0, 0.0
    if emote and not complete:
        p = emote["weight"] / 100
        cycle = sum((1 - p) ** k for k in range(emote["pity"]))
        rolled = 1 - (1 - p) ** (emote["pity"] - 1) / cycle
    elif emote:
        extra_again = emote["weight"]
    shards = sum(p["shards"] * p["weight"] for p in card["prizes"])
    shards += sum(card[t]["shards"] * card[t]["weight"] for t in ("skin", "big") if t in card)
    shards = shards / 100 * rolled
    again = (card["again"] + extra_again) / 100 * rolled
    pot = jackpot["perCoin"] + jackpot["seed"] / jackpot["odds"]
    return ((1 - q) * shards / card["coins"] + pot) / (1 - (1 - q) * again)


class ParkScratch:
    def __init__(self, park: Park) -> None:
        self.park = park

    @property
    def cfg(self) -> dict[str, Any]:
        cfg = self.park.cfg.get("scratch")
        if not cfg:
            raise GameError("no_park", "这个服务器没有刮刮乐")
        return cfg

    def _card(self, kind: str) -> dict[str, Any]:
        card = self.cfg["cards"].get(kind)
        if card is None:
            raise GameError("no_card", "没有这种刮刮乐")
        return card

    def _emotes(self, card: dict[str, Any]) -> list[str]:
        """Item ids of the emote set the card gives, in set order."""
        emote = card.get("emote")
        if not emote:
            return []
        return [f"emote:{e['key']}" for s in self.park.game.manifest.data.get("emoteSets", [])
                if s["id"] == emote["set"] for e in s["emotes"]]

    @staticmethod
    def _view(card: dict[str, Any] | None) -> dict[str, Any] | None:
        return {"id": card["id"], "kind": card["kind"], "cells": json.loads(card["cells"])} if card else None

    def _pot(self, st: Store) -> int:
        return st.park_counter(JACKPOT, self.cfg["jackpot"]["seed"])

    # ------------------------------------------------------------------ calls
    def state(self, token: str) -> dict[str, Any]:
        """The card still to reveal, the count toward the emote pity, whether the emote set is whole, and the pot."""
        cfg = self.cfg
        g = self.park.game
        pid = player_id_for(token)
        p = g.store.get_player(pid, g.now())
        owned = g.store.owned(pid)
        pending = g.store.pending_park_scratch(pid)
        return {"card": self._view(pending), "pity": p["scratch_pity"],
                "emotesWhole": all(i in owned for i in self._emotes(cfg["cards"]["basic"])),
                "jackpot": self._shown_pot(g.store, pending)}

    def _shown_pot(self, st: Store, pending: dict[str, Any] | None) -> int:
        """The pot as the save sees it: while its unrevealed card holds the pot, the pot as that card took it, so the
        restart at seed gives nothing away before the reveal."""
        return pending["shards"] if pending and pending["tier"] == "jackpot" else self._pot(st)

    def _answer(self, token: str, **extra: Any) -> dict[str, Any]:
        state = self.state(token)
        park = {**self.park.state(token), "jackpot": state["jackpot"]}
        return {**self.park.game.status(token), "park": park, **state, **extra}

    def buy(self, token: str, kind: str, version: str | None = None) -> dict[str, Any]:
        """Buys a card of [kind]: its prize is decided now and paid by reveal. A card still to reveal is handed back
        as it is, at no charge, so a save never holds two. Skins the client of [version] cannot show stay out."""
        card = self._card(kind)
        g = self.park.game
        pid = player_id_for(token)
        with g.store.transaction() as st:
            now = g.now()
            if st.pending_park_scratch(pid) is None:
                self._buy(st, pid, kind, card, version, now)
        return self._answer(token)

    def _buy(self, st: Store, pid: str, kind: str, card: dict[str, Any], version: str | None, now: float) -> None:
        cfg = self.cfg
        g = self.park.game
        coins = card["coins"]
        self.park.spend(st, pid, coins, "scratch", now)
        jackpot = cfg["jackpot"]
        pot = self._pot(st) + coins * jackpot["perCoin"]
        p = st.get_player(pid, now)
        owned = st.owned(pid)
        emotes = self._emotes(card)
        missing = [i for i in emotes if i not in owned]
        tier, shards = roll(card, p["scratch_pity"], g.rng, complete=not missing, odds=jackpot["odds"])
        item, back = "", 0
        if tier == "jackpot":
            shards, pot = pot, jackpot["seed"]
        elif tier == "again":
            back = coins
        elif tier == "emote":
            item = self._pick(missing)
        elif tier in ("skin", "big"):
            pool = self._items(tier, version)
            left = [i for i in pool if i not in owned]
            if left:
                item = self._pick(left)
            else:
                shards = card[tier]["shards"]
        st.set_park_counter(JACKPOT, pot)
        win = {"jackpot": POT, "again": AGAIN, "skin": SKIN, "big": BIG}.get(tier)
        if tier == "emote":
            win = item[len("emote:"):]
        elif tier == "shards":
            win = str(shards)
        cells = scratchlogic.layout(win, [x["shards"] for x in card["prizes"]], [i[6:] for i in emotes], g.rng,
                                    top=top_symbols(card, cfg["serverAt"][kind]), extra=symbols(card))
        st.add_park_scratch(pid, day_of(now), kind, json.dumps(cells), tier, shards, back, item, now)
        if card.get("emote") and missing:
            # Counted as on the old cards; a whole set leaves the count where the last emote left it.
            st.update_player(pid, scratch_pity=0 if tier == "emote" else p["scratch_pity"] + 1)

    def _pick(self, items: Sequence[str]) -> str:
        rng = self.park.game.rng
        return items[min(int(rng.random() * len(items)), len(items) - 1)]

    def _items(self, tier: str, version: str | None) -> list[str]:
        """Skins a client of [version] can show, or the big hidden cards."""
        m = self.park.game.manifest
        if tier == "skin":
            return [i["id"] for i in m.resonance_pool_for(version).get("skin", []) if i["kind"] == "char"]
        return [f"card:{c['id']}" for c in m.data["cards"] if c.get("tier") == "big"]

    def reveal(self, token: str, card_id: int) -> dict[str, Any]:
        """Pays a card's prize. Revealing it again answers the same prize and pays nothing. `announce` (popped by the
        route) is the shards to tell the rooms of the save, 0 when nothing."""
        cfg = self.cfg
        g = self.park.game
        pid = player_id_for(token)
        with g.store.transaction() as st:
            now = g.now()
            row = st.park_scratch_card(pid, card_id)
            if row is None:
                raise GameError("no_card", "没有这张刮刮乐")
            first = not row["revealed"]
            if first:
                row = self._pay(st, pid, row, now)
        prize = {"tier": row["tier"], "shards": row["shards"], "coins": row["coins"], "item": row["item"] or None}
        shards = row["shards"] if first and row["shards"] >= cfg["roomAt"][row["kind"]] else 0
        return self._answer(token, prize=prize, announce=shards)

    def _pay(self, st: Store, pid: str, row: dict[str, Any], now: float) -> dict[str, Any]:
        cfg = self.cfg
        g = self.park.game
        kind, tier, item = row["kind"], row["tier"], row["item"]
        card = self._card(kind)
        paid: dict[str, Any] = {}
        if item and item in st.owned(pid):
            # Found another way since the buy: a skin or big card pays its shards, an emote its coins back.
            item = ""
            if tier in ("skin", "big"):
                paid = {"item": "", "shards": card[tier]["shards"]}
            else:
                paid = {"item": "", "tier": "again", "coins": card["coins"]}
        row = {**row, **paid}
        st.reveal_park_scratch(row["id"], now, **paid)
        day = day_of(now)
        if row["shards"]:
            p = st.get_player(pid, now)
            st.update_player(pid, shards=p["shards"] + row["shards"])
            st.add_ledger(pid, day, POT_SOURCE if tier == "jackpot" else PRIZE, row["shards"])
        if row["coins"]:
            self.park.grant(st, pid, row["coins"], "scratch_again", now)
        if item:
            known = g.manifest.items.get(item)
            st.add_item(pid, item, now)
            st.log_drop(pid, item, known["rarity"] if known else "common", True, now)
        if tier == "jackpot":
            self.park.announce(st, "jackpot", pid, now, shards=row["shards"])
        elif item and tier in ("skin", "big"):
            self.park.announce(st, "scratch_item", pid, now, card=kind, item=item)
        elif row["shards"] >= cfg["serverAt"][kind]:
            self.park.announce(st, "scratch_big", pid, now, card=kind, shards=row["shards"])
        return row

    def prune(self) -> int:
        """Forgets revealed cards older than SCRATCH_DAYS. Returns rows removed."""
        g = self.park.game
        return g.store.prune_park_scratch(g.now() - SCRATCH_DAYS * 86400)
