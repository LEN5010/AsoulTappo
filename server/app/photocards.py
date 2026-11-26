"""Photocards (官周小卡; economy photocards): boxes of a series' cards, each card in a bag of its own, sold for shards.

What a box holds is decided by photo_deal.py when it is bought, and the save gets all of it then: the cards, and the
shards its repeats turn into. The client plays the opening from the answer and says when it is done (open); until then
buying a box of the series hands the same one back at no charge, so a request sent again never pays twice and an opening
broken off goes on later. A save buys `daily` boxes of a series a China day.

A repeat solo card turns into `refund.solo` shards, a repeat duo or group card into `refund.rare`. A repeat signed card
is put by (`spare`), and `swap` of them are traded for a signed card of the save's choice it lacks (swap). Once the save
holds every signed card there is nothing left to trade for: those put by and every later one turn into `refund.rare`
shards each.

Each series has its own box, daily limit, pity and repeats put by. The economy lists those on the shelf. One with
`daily` 0 sells no box and still trades; one that is not listed does neither. The cards a save has of either stay, and
so does a box not opened yet."""
from __future__ import annotations

import json
from typing import Any, Callable

from .game import Game, GameError, player_id_for
from .photo_deal import Series, deal
from .store import Store, day_of

# Shard ledger sources: what boxes cost and what repeats paid back.
BOX = "photo_box"
REPEAT = "photo_repeat"
# Opened boxes are kept this long to look up what one held; only the current day's are ever counted.
BOX_DAYS = 14


class Photocards:
    def __init__(self, game: Callable[[], Game]) -> None:
        # The game may be replaced (tests), so it is looked up on every call, as in Park.
        self._game = game

    @property
    def game(self) -> Game:
        return self._game()

    @property
    def shelf(self) -> dict[str, dict[str, Any]]:
        """The boxes on the shelf by series."""
        shelf = self.game.manifest.photo_shelf
        if not shelf:
            raise GameError("no_photocards", "这个服务器没有小卡")
        return shelf

    @property
    def series(self) -> dict[str, Series]:
        """Every series of the manifest, on the shelf or not."""
        return self.game.manifest.photo_series

    # ------------------------------------------------------------------ views
    def _view(self, st: Store, pid: str, now: float) -> dict[str, Any]:
        owned = st.held_of(pid, (item for series in self.series.values() for item in series.items))
        day = day_of(now)
        return {"day": day,
                "series": {sid: self._series_view(st, pid, series, owned, day) for sid, series in self.series.items()}}

    def _series_view(self, st: Store, pid: str, series: Series, owned: set[str], day: str) -> dict[str, Any]:
        cfg = self.shelf.get(series.id)
        box = st.photo_unopened(pid, series.id)
        return {
            "owned": [i for i in series.items if i in owned],
            "left": max(0, cfg["daily"] - st.photo_bought(pid, series.id, day)) if cfg else 0,
            **st.photo_save(pid, series.id),
            "box": {"id": box["id"], "ts": box["ts"], "price": box["price"], **json.loads(box["contents"])}
                   if box else None,
        }

    def _answer(self, token: str, **extra: Any) -> dict[str, Any]:
        """The status and the photocards as they are at one moment, whatever another device does meanwhile."""
        g = self.game
        with g.store.lock:
            return {**g.status(token), "photocards": self._view(g.store, player_id_for(token), g.now()), **extra}

    # ------------------------------------------------------------------ calls
    def state(self, token: str) -> dict[str, Any]:
        self.shelf
        return self._answer(token)

    def buy(self, token: str, sid: str, price: int | None = None) -> dict[str, Any]:
        """Buys a box of the series [sid], or hands back its one not opened to the end yet at no charge, whether the
        series still sells or not. Nothing is bought at another price than the one shown ([price])."""
        cfg = self.shelf.get(sid)
        series = self.series.get(sid)
        if series is None:
            raise GameError("no_series", "没有这一期小卡")
        g = self.game
        pid = player_id_for(token)
        with g.store.transaction() as st:
            now = g.now()
            day = day_of(now)
            p = st.get_player(pid, now)
            if st.photo_unopened(pid, sid) is None:
                if cfg is None or not cfg["daily"]:
                    raise GameError("photo_off_sale", "这一期小卡没有在售")
                if price is not None and price != cfg["price"]:
                    raise GameError("price_changed", "价格已更新")
                if st.photo_bought(pid, sid, day) >= cfg["daily"]:
                    raise GameError("photo_sold_out", "这一期小卡今天买完了")
                if p["shards"] < cfg["price"]:
                    raise GameError("no_shards", "碎片不足")
                self._deal(st, p, cfg, series, day, now)
        return self._answer(token)

    def _deal(self, st: Store, p: dict[str, Any], cfg: dict[str, Any], series: Series, day: str, now: float) -> None:
        """In buy's transaction: deals the save [p] a box, takes the price and credits what it holds."""
        pid = p["id"]
        mine = st.photo_save(pid, series.id)
        owned = st.owned(pid)
        pulls = deal(cfg, series, owned, mine["dry"], self.game.rng)
        have = owned.keys() | {pull.item for pull in pulls}
        whole = have.issuperset(series.sign)
        cards: list[dict[str, Any]] = []
        spare, refund, repeats = mine["spare"], 0, 0
        for pull in pulls:
            card: dict[str, Any] = {"item": pull.item}
            if pull.new:
                card["new"] = True
            elif pull.kind == "sign" and not whole:
                card["spare"] = True
                spare += 1
            else:
                card["shards"] = cfg["refund"]["solo" if pull.kind == "solo" else "rare"]
                refund += card["shards"]
                repeats += 1
            cards.append(card)
        contents: dict[str, Any] = {"cards": cards}
        settled = self._settle(cfg, spare) if whole else None
        if settled:
            contents["settled"] = settled
            refund, repeats, spare = refund + settled["shards"], repeats + settled["cards"], 0
        st.add_items(pid, {pull.item: 1 for pull in pulls if pull.new}, now)
        st.update_player(pid, shards=p["shards"] - cfg["price"] + refund)
        st.add_ledger(pid, day, BOX, -cfg["price"])
        if repeats:
            st.add_ledger(pid, day, REPEAT, refund, repeats)
        signed = any(pull.kind == "sign" for pull in pulls)
        st.set_photo_save(pid, series.id, mine["boxes"] + 1, 0 if signed or whole else mine["dry"] + 1, spare)
        st.add_photo_box(pid, series.id, day, cfg["price"], json.dumps(contents, separators=(",", ":")), now)

    @staticmethod
    def _settle(cfg: dict[str, Any], spare: int) -> dict[str, int] | None:
        """What the repeat signed cards put by turn into once every signed card is held; None without any."""
        return {"cards": spare, "shards": spare * cfg["refund"]["rare"]} if spare else None

    def open(self, token: str, box_id: int) -> dict[str, Any]:
        """The client opened the last bag of the box (or skipped to the end). Saying it again changes nothing."""
        self.shelf
        g = self.game
        pid = player_id_for(token)
        with g.store.transaction() as st:
            if st.photo_box(pid, box_id) is None:
                raise GameError("no_box", "没有这一盒小卡")
            st.open_photo_box(box_id, g.now())
        return self._answer(token)

    def swap(self, token: str, item: str) -> dict[str, Any]:
        """Trades `swap` repeat signed cards put by for the signed card [item] of their series. With the last signed
        card, the repeats left over turn into shards (`settled`). The signed-card pity is not touched."""
        shelf = self.shelf
        series = next((s for s in self.series.values() if item in s.sign), None)
        if series is None:
            raise GameError("bad_item", "只能换签名卡")
        cfg = shelf.get(series.id)
        if cfg is None:
            raise GameError("photo_off_sale", "这一期小卡已经下架，不能换签名卡")
        g = self.game
        pid = player_id_for(token)
        with g.store.transaction() as st:
            now = g.now()
            p = st.get_player(pid, now)
            owned = st.owned(pid)
            if item in owned:
                raise GameError("owned", "已经有这张签名卡了")
            mine = st.photo_save(pid, series.id)
            spare = mine["spare"] - cfg["swap"]
            if spare < 0:
                raise GameError("no_spare", "重复的签名不够")
            st.add_item(pid, item, now)
            whole = (owned.keys() | {item}).issuperset(series.sign)
            settled = self._settle(cfg, spare) if whole else None
            if settled:
                spare = 0
                st.update_player(pid, shards=p["shards"] + settled["shards"])
                st.add_ledger(pid, day_of(now), REPEAT, settled["shards"], settled["cards"])
            st.set_photo_save(pid, series.id, mine["boxes"], 0 if whole else mine["dry"], spare)
        return self._answer(token, swapped=item, **({"settled": settled} if settled else {}))

    def prune(self) -> int:
        """Forgets opened boxes older than BOX_DAYS. Returns rows removed."""
        return self.game.store.prune_photo_boxes(self.game.now() - BOX_DAYS * 86400)
