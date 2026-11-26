"""Photocard boxes (app/photocards.py, app/photo_deal.py): the deal, buying, trading and what stays apart."""
import copy
import json
import random
from collections import Counter

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import economy, photo_deal, photocards
from app.game import DAY_OFFSET, Game, GameError, player_id_for
from app.manifest import Manifest
from app.photo_deal import Pull, deal
from app.photocards import BOX, BOX_DAYS, REPEAT, Photocards
from app.store import Store, day_of
from fixtures import Clock, SeqRng

TOKEN = "photocard-player-token-01"
OTHER = "photocard-player-token-02"
M = Manifest.load()
CFG = M.economy["photocards"][0]
SID = CFG["series"]
SERIES = M.photo_series[SID]
PRICE, SIZE, DAILY, SWAP = CFG["price"], CFG["size"], CFG["daily"], CFG["swap"]
SOLO, RARE = CFG["refund"]["solo"], CFG["refund"]["rare"]
SHARDS = 50_000
# The second series of two_series, with numbers of its own.
LATER = "later"
CFG2 = {**CFG, "series": LATER, "price": PRICE + 100, "size": SIZE + 2, "daily": DAILY + 1, "swap": SWAP + 1,
        "refund": {"solo": SOLO + 1, "rare": RARE + 1}}


def with_shelf(shelf, series=M.data["photocards"]):
    """The manifest with other boxes on the shelf (None: an economy without photocards) and other series."""
    data = {**M.data, "photocards": series, "economy": {k: v for k, v in M.economy.items() if k != "photocards"}}
    if shelf is not None:
        data["economy"]["photocards"] = shelf
    return Manifest(data)


def two_series(*shelf):
    """The manifest with a second series, which has the cards of the first; both are on the shelf unless it is given."""
    first = M.data["photocards"][0]
    return with_shelf(list(shelf) or [CFG, CFG2], [first, {**copy.deepcopy(first), "id": LATER}])


SERIES2 = two_series().photo_series[LATER]


def setup(shards=SHARDS, seed=7, manifest=None):
    clock = Clock()
    g = Game(Store(":memory:"), manifest or Manifest.load(), rng=random.Random(seed), now=clock)
    pid = g.status(TOKEN)["player"]
    g.store.update_player(pid, shards=shards)
    return g, Photocards(lambda: g), clock, pid


def shelve(g, *shelf):
    """Puts other boxes on the shelf of a running server."""
    g.manifest.__dict__["photo_shelf"] = {cfg["series"]: cfg for cfg in shelf}


def deals(monkeypatch, *boxes):
    """The next boxes hold these items, in this order; `new` is worked out as the deal does. Returns a list that fills
    with what each was dealt for: (series, dry)."""
    left, asked = list(boxes), []

    def fake(cfg, series, owned, dry, rng):
        assert cfg["series"] == series.id
        asked.append((series.id, dry))
        have, out = set(owned), []
        for item in left.pop(0):
            kind = next(k for k in ("solo", "duo", "group", "sign") if item in series.of(k))
            out.append(Pull(item, kind, item not in have))
            have.add(item)
        return out

    monkeypatch.setattr(photocards, "deal", fake)
    return asked


def shards(g, pid):
    return g.store.get_player(pid, 0)["shards"]


def ledger(g, pid):
    rows = g.store._db.execute("SELECT source, SUM(amount), SUM(count) FROM shard_ledger WHERE player_id = ? "
                               "AND source LIKE 'photo%' GROUP BY source", (pid,)).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def mine(pc, sid=SID):
    """The save's photocards of the series."""
    return pc.state(TOKEN)["photocards"]["series"][sid]


def got(answer, sid=SID):
    """The same in the answer to a call."""
    return answer["photocards"]["series"][sid]


def buy(pc, sid=SID):
    """A box of the series bought and opened; returns it."""
    box = got(pc.buy(TOKEN, sid), sid)["box"]
    pc.open(TOKEN, box["id"])
    return box


def code(fn, *args):
    with pytest.raises(GameError) as e:
        fn(*args)
    return e.value.code


# ----------------------------------------------------------------------- config
def test_the_series_holds_the_official_cards():
    assert [len(SERIES.of(k)) for k in ("solo", "duo", "group", "sign")] == [12, 6, 4, 12]
    assert [s.split("/")[1] for s in SERIES.sign] == [s.split("/")[1] for s in SERIES.solo]
    assert len(set(SERIES.items)) == 34
    # Ids carry the series, so another series may use the same card ids.
    assert SERIES.solo[0] == "photo:asoul2026/diana-1" and SERIES.sign[0] == "sign:asoul2026/diana-1"
    # The client's pages show what it is called.
    first = M.data["photocards"][0]
    assert (first["id"], first["name"], first["event"]) == (SID, "此间共鸣", "A-SOUL2026 线下演唱会")


@pytest.mark.parametrize("change,match", [
    (lambda c: c.update(series=""), "series"),
    (lambda c: c.update(price=0), "price"),
    (lambda c: c.update(size=1.5), "size"),
    (lambda c: c.update(size=economy.PHOTO_SIZE_MAX + 1), "size"),
    (lambda c: c.update(daily=True), "daily"),
    (lambda c: c.update(daily=-1), "daily"),
    (lambda c: c.update(signPity=0), "signPity"),
    (lambda c: c.update(swap="4"), "swap"),
    (lambda c: c.update(rare=101), "rare"),
    (lambda c: c.update(rare=True), "rare"),
    (lambda c: c.update(rare=float("nan")), "rare"),
    (lambda c: c.pop("sure"), "sure"),
    (lambda c: c.update(sure=1), "sure"),
    (lambda c: c.update(weight=[1]), "weight"),
    (lambda c: c.update(weight={"diana-1": 0}), "weight"),
    (lambda c: c.update(weight={"diana-1": True}), "weight"),
    (lambda c: c.update(weight={"diana-1": float("inf")}), "weight"),
    (lambda c: c["split"].pop("duo"), "split"),
    (lambda c: c["split"].update(solo=1), "split"),
    (lambda c: c["split"].update(sign=-1), "split"),
    (lambda c: c.update(split={"duo": 0, "group": 0, "sign": 0}), "split must not be all zero"),
    (lambda c: c.update(split={"duo": 1e308, "group": 1e308, "sign": 1}), "split must not"),
    (lambda c: c["refund"].update(rare=-1), "refund.rare"),
    (lambda c: c.pop("refund"), "refund.solo"),
    # Repeats that pay a box back, by the solo cards alone or by the rare ones.
    (lambda c: c["refund"].update(solo=c["price"] // (c["size"] - 2)), "refund pays"),
    (lambda c: c["refund"].update(rare=c["price"]), "refund pays"),
    (lambda c: (c.update(rare=100), c["refund"].update(rare=c["price"] // c["size"] + 1)), "refund pays"),
    (lambda c: (c.update(sure=False, rare=0), c["refund"].update(solo=c["price"] // c["size"] + 1)), "refund pays"),
])
def test_boxes_that_could_not_be_dealt_are_refused(change, match):
    cfg = copy.deepcopy(CFG2)
    economy.check_photocards([CFG, cfg])
    change(cfg)
    with pytest.raises(ValueError, match=rf"photocards\[1\]\.{match}"):
        economy.check_photocards([CFG, cfg])


@pytest.mark.parametrize("shelf,match", [
    (CFG, "must be a list"),
    ({}, "must be a list"),
    ([CFG, SID], r"photocards\[1\] must be an object"),
    ([CFG, CFG2, {**CFG2, "series": SID}], rf"photocards\[2\].*{SID}.*twice"),
])
def test_a_shelf_is_a_list_of_boxes_with_each_series_once(shelf, match):
    with pytest.raises(ValueError, match=match):
        economy.check_photocards(shelf)


def test_a_shelf_may_be_empty_and_a_series_on_it_may_sell_none():
    economy.check_photocards([])
    economy.check_photocards([{**CFG, "daily": 0}, CFG2])


def test_a_box_without_a_certain_rare_card_pays_back_by_its_own_chance():
    # Rare repeats that would pay the price back with a certain rare card in every box.
    lavish = {**CFG2, "rare": 0, "refund": {"solo": 1, "rare": CFG2["price"]}}
    economy.check_photocards([{**lavish, "sure": False, "weight": {"diana-1": 0.5}}])
    with pytest.raises(ValueError, match="refund pays"):
        economy.check_photocards([lavish])


def economy_file(tmp_path, photocards):
    path = tmp_path / "economy.json"
    data = json.loads(economy.EXAMPLE.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "photocards": photocards}), encoding="utf-8")
    return path


def test_an_unknown_series_stops_the_start(tmp_path):
    with pytest.raises(ValueError, match=r"photocards\[1\].*nope"):
        Manifest.load(economy=economy_file(tmp_path, [CFG, {**CFG, "series": "nope"}]))


def test_a_weight_names_cards_of_its_series(tmp_path):
    with pytest.raises(ValueError, match=r"photocards\[0\]\.weight.*'nope'"):
        Manifest.load(economy=economy_file(tmp_path, [{**CFG, "weight": {"nope": 2}}]))
    # Signed cards go by the ids of their solo cards, which are weighed as solo cards only.
    with pytest.raises(ValueError, match="weight"):
        Manifest.load(economy=economy_file(tmp_path, [{**CFG, "weight": {"sign:asoul2026/diana-1": 2}}]))
    weighed = {**CFG, "weight": {"bella-eileen-1": 0.5, "group-2": 3, "diana-1": 2}}
    assert Manifest.load(economy=economy_file(tmp_path, [weighed])).photo_shelf == {SID: weighed}


def test_boxes_are_checked_at_the_start_and_keep_their_order(tmp_path):
    with pytest.raises(ValueError, match="must be a list"):
        Manifest.load(economy=economy_file(tmp_path, CFG))
    assert Manifest.load(economy=economy_file(tmp_path, [])).photo_shelf == {}
    assert Manifest.load(economy=economy_file(tmp_path, [CFG])).photo_shelf == {SID: CFG}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(two_series().data), encoding="utf-8")
    m = Manifest.load(path, economy_file(tmp_path, [CFG2, CFG]))
    assert list(m.photo_shelf) == [LATER, SID] and list(m.photo_series) == [SID, LATER]


@pytest.mark.parametrize("cards,match", [
    ([{"id": "a", "kind": "solo"}, {"id": "a", "kind": "duo"}], "repeats"),
    ([{"id": "a", "kind": "trio"}], "trio"),
    ([{"id": "a", "kind": "solo"}, {"id": "b", "kind": "duo"}], "group"),
    ([{"id": "a/b", "kind": "solo"}], "a/b"),
    ([{"id": "A", "kind": "solo"}], "'A'"),
    ([{"id": "a" * 29, "kind": "solo"}], "aaa"),
    ([{"id": 1, "kind": "solo"}], "1"),
])
def test_a_series_no_box_can_be_dealt_from_is_refused(cards, match):
    with pytest.raises(ValueError, match=match):
        photo_deal.load([{"id": "s", "cards": cards}])


@pytest.mark.parametrize("sid", ["", "A", "a:b", "-a", "a" * 29])
def test_a_series_is_named_in_small_letters(sid):
    cards = [{"id": kind, "kind": kind} for kind in photo_deal.KINDS]
    assert photo_deal.load([{"id": "a-1_b", "cards": cards}])["a-1_b"].solo == ("photo:a-1_b/solo",)
    with pytest.raises(ValueError, match="photocards"):
        photo_deal.load([{"id": sid, "cards": cards}])


@pytest.mark.parametrize("shelf", [None, []])
def test_an_economy_without_photocards_has_none(shelf):
    g = Game(Store(":memory:"), with_shelf(shelf), now=Clock())
    pc = Photocards(lambda: g)
    for call in (lambda: pc.state(TOKEN), lambda: pc.buy(TOKEN, SID), lambda: pc.buy(TOKEN, "nope"),
                 lambda: pc.open(TOKEN, 1), lambda: pc.swap(TOKEN, SERIES.sign[0])):
        assert code(call) == "no_photocards"
    assert not g.store.has_player(player_id_for(TOKEN))
    assert Manifest({k: v for k, v in M.data.items() if k != "photocards"}).photo_series == {}


# ------------------------------------------------------------------------- deal
def cfg(**change):
    return {**CFG, **change}


def test_a_box_has_one_rare_card_for_certain_at_any_place():
    rng = random.Random(3)
    places = Counter()
    for _ in range(2000):
        pulls = deal(cfg(rare=0), SERIES, (), 0, rng)
        assert len(pulls) == SIZE
        rare = [i for i, p in enumerate(pulls) if p.kind != "solo"]
        assert len(rare) == 1
        places[rare[0]] += 1
    assert len(places) == SIZE and max(places.values()) < 2 * min(places.values())


def test_the_other_cards_are_rare_at_their_own_chance():
    rng = random.Random(4)
    pulls = [p for _ in range(3000) for p in deal(cfg(rare=20, signPity=99), SERIES, SERIES.items, 0, rng)]
    share = sum(p.kind != "solo" for p in pulls) / len(pulls)
    assert share == pytest.approx((1 + (SIZE - 1) * 0.2) / SIZE, abs=0.01)
    assert all(p.kind != "solo" for p in deal(cfg(rare=100), SERIES, (), 0, rng))


def test_rare_kinds_follow_the_split_and_solo_cards_are_even():
    rng = random.Random(5)
    pulls = [p for _ in range(6000) for p in deal(cfg(rare=30, signPity=99), SERIES, SERIES.items, 0, rng)]
    kinds = Counter(p.kind for p in pulls)
    rare = sum(kinds[k] for k in photo_deal.RARE_KINDS)
    total = sum(CFG["split"].values())
    for k in photo_deal.RARE_KINDS:
        assert kinds[k] / rare == pytest.approx(CFG["split"][k] / total, abs=0.02)
    solo = Counter(p.item for p in pulls if p.kind == "solo")
    assert set(solo) == set(SERIES.solo) and max(solo.values()) < 1.2 * min(solo.values())


@pytest.mark.parametrize("kind", ["duo", "group"])
def test_a_duo_or_group_card_repeats_only_once_its_kind_is_whole(kind):
    split = {k: int(k == kind) for k in photo_deal.RARE_KINDS}
    cards = SERIES.of(kind)
    rng = random.Random(6)
    for held in range(len(cards) + 1):
        owned = set(cards[:held])
        pulls = deal(cfg(rare=100, split=split, size=len(cards) + 3), SERIES, owned, 0, rng)
        fresh = len(cards) - held
        assert [p.new for p in pulls] == [True] * fresh + [False] * 3 + [False] * held
        assert {p.item for p in pulls[:fresh]} == set(cards) - owned


def test_a_repeat_after_the_kind_is_whole_is_any_of_it():
    rng = random.Random(8)
    got = Counter(p.item for _ in range(2000)
                  for p in deal(cfg(rare=0, split={"duo": 1, "group": 0, "sign": 0}), SERIES, SERIES.items, 0, rng)
                  if p.kind == "duo")
    assert set(got) == set(SERIES.duo) and max(got.values()) < 1.4 * min(got.values())


@pytest.mark.parametrize("held", [0, 1, 11, 12])
def test_a_signed_card_is_any_of_them_whatever_the_save_holds(held):
    only_sign = {"duo": 0, "group": 0, "sign": 1}
    owned = set(SERIES.sign[:held])
    rng = random.Random(6)
    pulls = [p for _ in range(6000) for p in deal(cfg(rare=0, split=only_sign), SERIES, owned, 0, rng)
             if p.kind == "sign"]
    got = Counter(p.item for p in pulls)
    assert len(pulls) == 6000 and all(p.new == (p.item not in owned) for p in pulls)
    assert set(got) == set(SERIES.sign) and max(got.values()) < 1.4 * min(got.values())
    # A box may hold the same one twice.
    box = deal(cfg(rare=100, split=only_sign, size=40), SERIES, owned, 0, rng)
    assert [p.new for p in box] == [p.item not in owned and p.item not in {q.item for q in box[:i]}
                                    for i, p in enumerate(box)]
    assert len({p.item for p in box}) < len(box)


def test_the_pity_turns_the_certain_card_into_a_signed_one():
    no_sign = {"duo": 1, "group": 0, "sign": 0}
    owned = set(SERIES.sign[1:])
    seen = set()
    for seed in range(300):
        for dry in range(CFG["signPity"] + 3):
            pulls = deal(cfg(rare=0, split=no_sign), SERIES, owned, dry, random.Random(seed))
            signs = [p for p in pulls if p.kind == "sign"]
            assert len(signs) == (1 if dry + 1 >= CFG["signPity"] else 0)
            # The box still has exactly one rare card: the pity changes its kind only.
            assert sum(p.kind != "solo" for p in pulls) == 1
            seen.update(signs)
    # Any of them, those the save holds among them.
    assert seen == {Pull(item, "sign", item not in owned) for item in SERIES.sign}


def test_the_pity_adds_none_to_a_box_that_has_one_and_stops_with_the_set():
    only_sign = {"duo": 0, "group": 0, "sign": 1}
    pulls = deal(cfg(rare=0, split=only_sign), SERIES, (), 99, random.Random(1))
    assert sum(p.kind == "sign" for p in pulls) == 1
    no_sign = {"duo": 1, "group": 0, "sign": 0}
    assert all(p.kind != "sign" for p in deal(cfg(rare=0, split=no_sign), SERIES, SERIES.sign, 99, random.Random(1)))


def test_the_pity_leaves_a_box_with_a_signed_card_of_its_own_alone():
    half = cfg(rare=30, split={"duo": 1, "group": 0, "sign": 1})
    seen = 0
    for seed in range(60):
        plain = deal(half, SERIES, (), 0, random.Random(seed))
        if any(p.kind == "sign" for p in plain):
            seen += 1
            assert deal(half, SERIES, (), 99, random.Random(seed)) == plain
    assert seen > 20


def test_the_pity_spares_the_bags_that_rolled_rare_by_themselves():
    # Bag 0 is the certain one; every bag is rare and a duo, and the pity turns only bag 0.
    pulls = deal(cfg(rare=100, split={"duo": 1, "group": 0, "sign": 0}), SERIES, (), 99, SeqRng(0.0))
    assert [p.kind for p in pulls] == ["sign"] + ["duo"] * (SIZE - 1)


def test_without_a_certain_rare_card_each_bag_is_rare_at_its_own_chance():
    rng = random.Random(9)
    pulls = [p for _ in range(3000) for p in deal(cfg(sure=False, rare=20, signPity=99), SERIES, SERIES.items, 0, rng)]
    assert sum(p.kind != "solo" for p in pulls) / len(pulls) == pytest.approx(0.2, abs=0.01)
    assert all(p.kind == "solo" for p in deal(cfg(sure=False, rare=0), SERIES, (), 0, rng))
    assert all(p.kind != "solo" for p in deal(cfg(sure=False, rare=100), SERIES, (), 0, rng))


def test_without_a_certain_rare_card_the_pity_takes_any_plain_bag():
    no_sign = {"duo": 1, "group": 0, "sign": 0}
    places = Counter()
    for seed in range(1500):
        pulls = deal(cfg(sure=False, rare=0, split=no_sign), SERIES, (), CFG["signPity"] - 1, random.Random(seed))
        assert [p.kind for p in pulls].count("sign") == 1 and {p.kind for p in pulls} == {"solo", "sign"}
        places[next(i for i, p in enumerate(pulls) if p.kind == "sign")] += 1
    assert len(places) == SIZE and max(places.values()) < 2 * min(places.values())
    # It spares a bag that rolled rare by itself, and takes one anyway when none is plain.
    for seed in range(200):
        half = deal(cfg(sure=False, rare=50, split=no_sign), SERIES, (), 99, random.Random(seed))
        alone = [p.kind for p in deal(cfg(sure=False, rare=50, split=no_sign), SERIES, (), 0, random.Random(seed))]
        if "solo" in alone:
            assert [p.kind for p in half].count("duo") == alone.count("duo")
    full = deal(cfg(sure=False, rare=100, split=no_sign), SERIES, (), 99, random.Random(1))
    assert sorted(p.kind for p in full) == ["duo"] * (SIZE - 1) + ["sign"]


def test_a_card_is_weighed_against_the_others_of_its_kind():
    only_duo = {"duo": 1, "group": 0, "sign": 0}
    pair = {f"bella-eileen-{n}": 0.5 for n in (1, 2)}
    rng = random.Random(10)
    got = Counter(p.item for _ in range(3000)
                  for p in deal(cfg(rare=100, split=only_duo, weight=pair), SERIES, SERIES.items, 0, rng))
    light = sum(got[f"photo:{SID}/{card}"] for card in pair)
    assert light / sum(got.values()) == pytest.approx(1 / 5, abs=0.01)
    # A card the save lacks still comes before any repeat, lightly weighed or not.
    owned = set(SERIES.duo) - {f"photo:{SID}/bella-eileen-1"}
    assert deal(cfg(rare=100, split=only_duo, weight=pair), SERIES, owned, 0, rng)[0].item == f"photo:{SID}/bella-eileen-1"


def test_a_signed_card_stays_even_when_its_solo_card_is_weighed():
    heavy = cfg(rare=30, split={"duo": 0, "group": 0, "sign": 1}, signPity=99, weight={"diana-1": 5})
    rng = random.Random(11)
    pulls = [p for _ in range(4000) for p in deal(heavy, SERIES, SERIES.items, 0, rng)]
    solo = Counter(p.item for p in pulls if p.kind == "solo")
    sign = Counter(p.item for p in pulls if p.kind == "sign")
    assert solo[SERIES.solo[0]] / sum(solo.values()) == pytest.approx(5 / 16, abs=0.02)
    assert max(sign.values()) < 1.4 * min(sign.values())


def test_a_deal_without_weights_is_the_one_it_always_was():
    rng = random.Random(12)
    for _ in range(50):
        state = rng.getstate()
        plain = deal(cfg(rare=30), SERIES, (), 3, rng)
        rng.setstate(state)
        assert deal(cfg(rare=30, weight={}), SERIES, (), 3, rng) == plain


# ------------------------------------------------------------------------ buying
def test_a_box_takes_its_price_and_credits_all_it_holds_at_once(monkeypatch):
    g, pc, _, pid = setup()
    s, d = SERIES.solo, SERIES.duo
    deals(monkeypatch, [s[0], s[0], d[0], s[1], s[0]])
    out = pc.buy(TOKEN, SID)
    save = got(out)
    assert save["box"]["cards"] == [{"item": s[0], "new": True}, {"item": s[0], "shards": SOLO},
                                    {"item": d[0], "new": True}, {"item": s[1], "new": True},
                                    {"item": s[0], "shards": SOLO}]
    assert save["box"]["price"] == PRICE and "settled" not in save["box"]
    assert save["owned"] == [s[0], s[1], d[0]]
    assert (save["left"], save["boxes"], save["dry"], save["spare"]) == (DAILY - 1, 1, 1, 0)
    assert out["shards"] == shards(g, pid) == SHARDS - PRICE + 2 * SOLO
    assert ledger(g, pid) == {BOX: (-PRICE, 1), REPEAT: (2 * SOLO, 2)}
    assert g.store.owned(pid) == {s[0]: 1, s[1]: 1, d[0]: 1}


def test_a_box_not_opened_yet_is_handed_back_at_no_charge():
    g, pc, _, pid = setup()
    first = pc.buy(TOKEN, SID)
    again = pc.buy(TOKEN, SID)
    assert again["photocards"] == first["photocards"] and again["shards"] == first["shards"]
    assert mine(pc)["box"] == got(first)["box"]
    assert ledger(g, pid)[BOX] == (-PRICE, 1)
    box = got(first)["box"]["id"]
    assert got(pc.open(TOKEN, box))["box"] is None
    assert got(pc.open(TOKEN, box))["box"] is None
    assert got(pc.buy(TOKEN, SID))["box"]["id"] != box
    assert ledger(g, pid)[BOX] == (-2 * PRICE, 2)


def test_boxes_are_sold_daily_a_china_day():
    g, pc, clock, pid = setup()
    clock.t = (clock.t + DAY_OFFSET) // 86400 * 86400 - DAY_OFFSET + 86399
    for left in reversed(range(DAILY)):
        assert got(pc.buy(TOKEN, SID))["left"] == left
        pc.open(TOKEN, mine(pc)["box"]["id"])
    before = shards(g, pid)
    assert code(pc.buy, TOKEN, SID) == "photo_sold_out" and shards(g, pid) == before
    clock.t += 2
    assert mine(pc)["left"] == DAILY
    pc.buy(TOKEN, SID)
    # The box still shut when the day turned takes none of the new day's.
    clock.t += 86400
    assert got(pc.buy(TOKEN, SID))["left"] == DAILY


def test_a_save_without_the_price_buys_nothing():
    g, pc, _, pid = setup(shards=PRICE - 1)
    assert code(pc.buy, TOKEN, SID) == "no_shards"
    assert shards(g, pid) == PRICE - 1 and ledger(g, pid) == {} and g.store.owned(pid) == {}
    assert mine(pc)["left"] == DAILY


def test_nothing_is_bought_at_another_price_than_the_one_shown():
    g, pc, _, pid = setup()
    for price in (PRICE - 1, PRICE + 1):
        assert code(pc.buy, TOKEN, SID, price) == "price_changed"
    assert shards(g, pid) == SHARDS and mine(pc)["boxes"] == 0
    box = got(pc.buy(TOKEN, SID, PRICE))["box"]["id"]
    # One that waits was paid for, whatever the series costs by now.
    shelve(g, {**CFG, "price": PRICE + 1})
    assert got(pc.buy(TOKEN, SID, PRICE))["box"]["id"] == box
    pc.open(TOKEN, box)
    assert code(pc.buy, TOKEN, SID, PRICE) == "price_changed"
    # A client that shows none takes what it costs.
    assert got(pc.buy(TOKEN, SID))["box"]["price"] == PRICE + 1


def test_the_pity_counts_boxes_and_starts_over_with_a_signed_card(monkeypatch):
    _, pc, clock, _ = setup()
    d, sign = SERIES.duo, SERIES.sign
    deals(monkeypatch, [d[0]], [d[1]], [sign[0]], [d[2]])
    seen = []
    for _ in range(4):
        buy(pc)
        seen.append(mine(pc)["dry"])
        clock.t += 86400
    assert seen == [1, 2, 0, 1]


def test_the_pity_holds_through_buy():
    g, pc, clock, _ = setup(shards=10_000_000)
    # An rng that never rolls a rare bag and always the first kind (duo): only the pity gives signed cards.
    g.rng = SeqRng(0.5)
    shelve(g, dict(CFG, rare=0, split={"duo": 1, "group": 0, "sign": 0}))
    for n in range(1, 2 * CFG["signPity"] + 1):
        box = buy(pc)
        signed = [c for c in box["cards"] if c["item"].startswith("sign:")]
        assert len(signed) == (1 if n % CFG["signPity"] == 0 else 0)
        clock.t += 86400


def test_opening_needs_a_box_of_ones_own():
    _, pc, _, _ = setup()
    box = got(pc.buy(TOKEN, SID))["box"]["id"]
    assert code(pc.open, TOKEN, box + 1) == "no_box"
    assert code(pc.open, OTHER, box) == "no_box"
    assert mine(pc)["box"]["id"] == box


def test_a_series_the_manifest_lacks_sells_nothing():
    g, pc, _, pid = setup()
    for sid in ("nope", "", SID.upper()):
        assert code(pc.buy, TOKEN, sid) == "no_series"
    assert shards(g, pid) == SHARDS and ledger(g, pid) == {}


def test_a_series_with_daily_0_sells_nothing():
    g, pc, _, pid = setup()
    shelve(g, {**CFG, "daily": 0})
    assert mine(pc)["left"] == 0
    assert code(pc.buy, TOKEN, SID) == "photo_off_sale"
    # Whatever the save has to pay with.
    g.store.update_player(pid, shards=0)
    assert code(pc.buy, TOKEN, SID) == "photo_off_sale"
    assert ledger(g, pid) == {} and g.store.owned(pid) == {}


@pytest.mark.parametrize("shelf", [[{**CFG, "daily": 0}], [CFG2], [{**CFG, "daily": 1}]],
                         ids=["daily 0", "off the shelf", "sold out"])
def test_a_box_is_handed_back_and_opened_after_its_series_stopped_selling(shelf):
    g, pc, _, pid = setup(manifest=two_series())
    box = got(pc.buy(TOKEN, SID))["box"]
    before = shards(g, pid)
    shelve(g, *shelf)
    assert mine(pc)["box"] == box and mine(pc)["left"] == 0
    assert got(pc.buy(TOKEN, SID))["box"] == box
    assert shards(g, pid) == before and ledger(g, pid)[BOX] == (-PRICE, 1)
    out = got(pc.open(TOKEN, box["id"]))
    assert out["box"] is None and out["owned"] == mine(pc)["owned"] != [] and out["boxes"] == 1
    assert code(pc.buy, TOKEN, SID) == ("photo_sold_out" if shelf[0]["daily"] == 1 else "photo_off_sale")
    assert mine(pc)["box"] is None and shards(g, pid) == before


def test_a_limit_lowered_below_what_was_bought_today_leaves_none():
    g, pc, _, _ = setup()
    buy(pc)
    buy(pc)
    shelve(g, {**CFG, "daily": 1})
    assert mine(pc)["left"] == 0 and code(pc.buy, TOKEN, SID) == "photo_sold_out"


# ------------------------------------------------------------------------ trading
def test_a_repeat_duo_or_group_card_turns_into_shards(monkeypatch):
    g, pc, _, pid = setup()
    d, group = SERIES.duo[0], SERIES.group[0]
    deals(monkeypatch, [d, d, group, group, group])
    assert buy(pc)["cards"] == [{"item": d, "new": True}, {"item": d, "shards": RARE}, {"item": group, "new": True},
                                {"item": group, "shards": RARE}, {"item": group, "shards": RARE}]
    assert shards(g, pid) == SHARDS - PRICE + 3 * RARE and ledger(g, pid)[REPEAT] == (3 * RARE, 3)
    assert (mine(pc)["spare"], mine(pc)["dry"]) == (0, 1)


def test_signed_repeats_are_put_by_and_traded_for_a_signed_card(monkeypatch):
    g, pc, _, pid = setup()
    d, sign = SERIES.duo, SERIES.sign
    deals(monkeypatch, [sign[0]] * (SWAP + 2), [d[0]], [sign[0], sign[1], sign[1]])
    box = buy(pc)
    assert box["cards"] == [{"item": sign[0], "new": True}] + [{"item": sign[0], "spare": True}] * (SWAP + 1)
    assert mine(pc)["spare"] == SWAP + 1 and REPEAT not in ledger(g, pid)
    buy(pc)

    assert code(pc.swap, TOKEN, d[1]) == "bad_item"
    assert code(pc.swap, TOKEN, "sign:asoul2026/nobody") == "bad_item"
    before = shards(g, pid)
    out = pc.swap(TOKEN, sign[3])
    assert out["swapped"] == sign[3] and "settled" not in out
    assert got(out)["spare"] == 1 and sign[3] in got(out)["owned"]
    assert got(out)["dry"] == 1  # a trade is not a signed card drawn
    assert shards(g, pid) == before
    assert code(pc.swap, TOKEN, sign[3]) == "owned"
    assert code(pc.swap, TOKEN, sign[4]) == "no_spare"
    # The first copies are never put by.
    assert [c.get("spare") for c in buy(pc)["cards"]] == [True, None, True]
    assert mine(pc)["spare"] == 3


def test_a_trade_takes_exactly_its_price_in_repeats():
    g, pc, _, pid = setup()
    g.store.set_photo_save(pid, SERIES.id, 1, 3, SWAP - 1)
    assert code(pc.swap, TOKEN, SERIES.sign[0]) == "no_spare"
    assert g.store.owned(pid) == {} and g.store.photo_save(pid, SERIES.id) == {"boxes": 1, "dry": 3, "spare": SWAP - 1}
    g.store.set_photo_save(pid, SERIES.id, 1, 3, SWAP)
    assert got(pc.swap(TOKEN, SERIES.sign[0]))["spare"] == 0
    assert g.store.photo_save(pid, SERIES.id) == {"boxes": 1, "dry": 3, "spare": 0}


def test_the_last_signed_card_traded_for_pays_out_the_repeats_left(monkeypatch):
    g, pc, _, pid = setup()
    sign = SERIES.sign
    for item in sign[:-1]:
        g.store.add_item(pid, item, 0)
    g.store.set_photo_save(pid, SID, 1, 3, SWAP + 2)
    deals(monkeypatch, [sign[0], sign[-1]], [SERIES.duo[0]])
    before = shards(g, pid)
    out = pc.swap(TOKEN, sign[-1])
    assert out["settled"] == {"cards": 2, "shards": 2 * RARE}
    assert got(out)["spare"] == 0 and got(out)["dry"] == 0
    assert out["shards"] == shards(g, pid) == before + 2 * RARE
    assert ledger(g, pid)[REPEAT] == (2 * RARE, 2)
    # From here on a signed repeat pays at once, no box counts toward the pity and nothing is left to trade for.
    assert buy(pc)["cards"] == [{"item": sign[0], "shards": RARE}, {"item": sign[-1], "shards": RARE}]
    buy(pc)
    assert (mine(pc)["spare"], mine(pc)["dry"]) == (0, 0)
    assert code(pc.swap, TOKEN, sign[0]) == "owned"


def test_a_box_that_completes_the_signed_cards_pays_out_the_repeats_put_by(monkeypatch):
    g, pc, _, pid = setup()
    s, sign = SERIES.solo, SERIES.sign
    for item in sign[:-1]:
        g.store.add_item(pid, item, 0)
    deals(monkeypatch, [sign[0], sign[1]], [sign[0], sign[-1], s[0], s[0], sign[-1]])
    buy(pc)
    assert mine(pc)["spare"] == 2
    before = shards(g, pid)
    box = buy(pc)
    # The repeats of the same box pay too, wherever the last signed card was among them.
    assert box["cards"] == [{"item": sign[0], "shards": RARE}, {"item": sign[-1], "new": True},
                            {"item": s[0], "new": True}, {"item": s[0], "shards": SOLO},
                            {"item": sign[-1], "shards": RARE}]
    assert box["settled"] == {"cards": 2, "shards": 2 * RARE}
    assert shards(g, pid) == before - PRICE + 4 * RARE + SOLO
    assert ledger(g, pid)[REPEAT] == (4 * RARE + SOLO, 5)
    assert (mine(pc)["spare"], mine(pc)["dry"]) == (0, 0)


def test_a_trade_needs_its_series_on_the_shelf_but_not_on_sale():
    g, pc, _, pid = setup(manifest=two_series())
    sign = SERIES.sign
    g.store.set_photo_save(pid, SID, 3, 2, 2 * SWAP)
    g.store.add_item(pid, sign[1], 0)
    shelve(g, CFG2)
    for item in sign[:2]:
        assert code(pc.swap, TOKEN, item) == "photo_off_sale"
    # What is not a signed card of any series is no item to trade for, whatever is on the shelf.
    for item in (SERIES.solo[0], SERIES.duo[0], "sign:nope/diana-1", "sign:" + SID):
        assert code(pc.swap, TOKEN, item) == "bad_item"
    assert g.store.owned(pid) == {sign[1]: 1}
    assert g.store.photo_save(pid, SID) == {"boxes": 3, "dry": 2, "spare": 2 * SWAP}
    shelve(g, CFG2, {**CFG, "daily": 0})
    out = pc.swap(TOKEN, sign[0])
    assert out["swapped"] == sign[0] and got(out)["spare"] == SWAP and got(out)["owned"] == list(sign[:2])


def test_the_shards_a_box_names_are_the_shards_it_pays():
    g, pc, clock, pid = setup(shards=10_000_000, seed=11)
    paid = 0
    for _ in range(150):
        before = shards(g, pid)
        box = buy(pc)
        gained = sum(c.get("shards", 0) for c in box["cards"]) + box.get("settled", {}).get("shards", 0)
        assert shards(g, pid) == before - PRICE + gained
        paid += gained
        clock.t += 86400
        while mine(pc)["spare"] >= SWAP:
            missing = [i for i in SERIES.sign if i not in mine(pc)["owned"]]
            before = shards(g, pid)
            out = pc.swap(TOKEN, missing[0])
            assert shards(g, pid) == before + out.get("settled", {}).get("shards", 0)
            paid += out.get("settled", {}).get("shards", 0)
    assert mine(pc)["owned"] == list(SERIES.items)
    assert ledger(g, pid)[BOX] == (-150 * PRICE, 150) and ledger(g, pid)[REPEAT][0] == paid
    assert all(n == 1 for n in g.store.owned(pid).values())


# ------------------------------------------------------------------ several series
def test_every_series_is_told_on_the_shelf_or_not():
    g, pc, _, pid = setup(manifest=two_series(CFG2))
    held = [SERIES.sign[2], SERIES.solo[3]]
    for item in held:
        g.store.add_item(pid, item, 0)
    g.store.set_photo_save(pid, SID, 4, 2, 1)
    out = pc.state(TOKEN)["photocards"]
    assert set(out) == {"day", "series"} and out["day"] == day_of(g.now())
    assert list(out["series"]) == [SID, LATER]
    assert out["series"][SID] == {"owned": held[::-1], "left": 0, "boxes": 4, "dry": 2, "spare": 1, "box": None}
    assert out["series"][LATER] == {"owned": [], "left": CFG2["daily"], "boxes": 0, "dry": 0, "spare": 0, "box": None}
    # Every call answers with all of them.
    bought = pc.buy(TOKEN, LATER)["photocards"]
    assert bought["series"][SID] == out["series"][SID] and bought["series"][LATER]["boxes"] == 1
    opened = pc.open(TOKEN, bought["series"][LATER]["box"]["id"])["photocards"]
    assert opened["series"] == {**bought["series"], LATER: {**bought["series"][LATER], "box": None}}


def test_each_series_has_its_own_price_and_daily_limit():
    g, pc, clock, pid = setup(manifest=two_series())
    for _ in range(DAILY):
        assert len(buy(pc)["cards"]) == SIZE
    assert code(pc.buy, TOKEN, SID) == "photo_sold_out"
    assert (mine(pc)["left"], mine(pc, LATER)["left"]) == (0, CFG2["daily"])
    for n in range(CFG2["daily"]):
        box = buy(pc, LATER)
        assert len(box["cards"]) == CFG2["size"] and box["price"] == CFG2["price"]
        assert mine(pc, LATER)["left"] == CFG2["daily"] - n - 1
    assert code(pc.buy, TOKEN, LATER) == "photo_sold_out"
    assert ledger(g, pid)[BOX] == (-DAILY * PRICE - CFG2["daily"] * CFG2["price"], DAILY + CFG2["daily"])
    assert (mine(pc)["boxes"], mine(pc, LATER)["boxes"]) == (DAILY, CFG2["daily"])
    clock.t += 86400
    assert (mine(pc)["left"], mine(pc, LATER)["left"]) == (DAILY, CFG2["daily"])
    # The price of one is not enough for the other.
    g.store.update_player(pid, shards=PRICE)
    assert code(pc.buy, TOKEN, LATER) == "no_shards"
    assert got(pc.buy(TOKEN, SID))["box"]["price"] == PRICE


def test_a_series_is_bought_while_a_box_of_another_is_half_open():
    g, pc, _, pid = setup(manifest=two_series())
    a = got(pc.buy(TOKEN, SID))["box"]
    out = pc.buy(TOKEN, LATER)
    b = got(out, LATER)["box"]
    assert got(out)["box"] == a and b["id"] != a["id"]
    assert all(c["item"] in SERIES.items for c in a["cards"]) and all(c["item"] in SERIES2.items for c in b["cards"])
    # Each is handed back by its own series.
    assert got(pc.buy(TOKEN, SID))["box"] == a and got(pc.buy(TOKEN, LATER), LATER)["box"] == b
    assert ledger(g, pid)[BOX] == (-PRICE - CFG2["price"], 2)
    out = pc.open(TOKEN, b["id"])
    assert got(out)["box"] == a and got(out, LATER)["box"] is None
    assert got(pc.buy(TOKEN, LATER), LATER)["box"]["id"] not in (a["id"], b["id"])
    assert mine(pc)["box"] == a
    out = pc.open(TOKEN, a["id"])
    assert got(out)["box"] is None and got(out, LATER)["box"] is not None


def test_each_series_has_its_own_cards_and_pity(monkeypatch):
    _, pc, clock, _ = setup(manifest=two_series())
    asked = deals(monkeypatch, [SERIES.duo[0]], [SERIES2.duo[0]], [SERIES2.sign[0]], [SERIES.duo[0]],
                  [SERIES2.duo[0]], [SERIES.sign[0]], [SERIES.duo[1]])
    boxes = []
    for sid in (SID, LATER, LATER, SID, LATER, SID, SID):
        boxes.append(buy(pc, sid))
        clock.t += 86400
    # How many boxes without a signed card each deal was told of.
    assert asked == [(SID, 0), (LATER, 0), (LATER, 1), (SID, 1), (LATER, 0), (SID, 2), (SID, 0)]
    # The same card of another series is another card: new there, and a repeat only of its own.
    assert [b["cards"][0].get("new", False) for b in boxes] == [True, True, True, False, False, True, True]
    assert (mine(pc)["dry"], mine(pc, LATER)["dry"]) == (1, 1)
    assert mine(pc)["owned"] == [SERIES.duo[0], SERIES.duo[1], SERIES.sign[0]]
    assert mine(pc, LATER)["owned"] == [SERIES2.duo[0], SERIES2.sign[0]]


def test_each_series_trades_its_own_repeats(monkeypatch):
    g, pc, _, pid = setup(manifest=two_series())
    deals(monkeypatch, [SERIES.sign[0]] * (SWAP + 2), [SERIES2.sign[0]] * CFG2["swap"])
    buy(pc)
    buy(pc, LATER)
    assert (mine(pc)["spare"], mine(pc, LATER)["spare"]) == (SWAP + 1, CFG2["swap"] - 1)
    # A trade of the second takes more: what is enough in the first is not there, and the two are not added up.
    assert SWAP <= mine(pc, LATER)["spare"] and code(pc.swap, TOKEN, SERIES2.sign[1]) == "no_spare"
    out = pc.swap(TOKEN, SERIES.sign[1])
    assert got(out)["spare"] == 1 and SERIES.sign[1] in got(out)["owned"]
    assert got(out, LATER)["spare"] == CFG2["swap"] - 1 and got(out, LATER)["owned"] == [SERIES2.sign[0]]
    g.store.set_photo_save(pid, LATER, 1, 1, CFG2["swap"])
    out = pc.swap(TOKEN, SERIES2.sign[1])
    assert got(out, LATER)["spare"] == 0 and got(out)["spare"] == 1
    assert REPEAT not in ledger(g, pid)


def test_the_signed_cards_of_one_series_settle_nothing_of_another(monkeypatch):
    g, pc, _, pid = setup(manifest=two_series())
    for item in SERIES.sign:
        g.store.add_item(pid, item, 0)
    for item in SERIES2.sign[:-1]:
        g.store.add_item(pid, item, 0)
    deals(monkeypatch, [SERIES.sign[0]], [SERIES2.sign[0]] * 2, [SERIES2.sign[-1], SERIES2.solo[0], SERIES2.solo[0]])
    assert buy(pc)["cards"] == [{"item": SERIES.sign[0], "shards": RARE}]
    assert buy(pc, LATER)["cards"] == [{"item": SERIES2.sign[0], "spare": True}] * 2
    g.store.set_photo_save(pid, SID, 1, 0, 3)
    before = shards(g, pid)
    box = buy(pc, LATER)
    rare, solo = CFG2["refund"]["rare"], CFG2["refund"]["solo"]
    assert box["settled"] == {"cards": 2, "shards": 2 * rare} and box["cards"][2]["shards"] == solo
    assert shards(g, pid) == before - CFG2["price"] + 2 * rare + solo
    assert (mine(pc)["spare"], mine(pc, LATER)["spare"]) == (3, 0)


def test_the_last_signed_card_traded_for_pays_by_its_own_series():
    g, pc, _, pid = setup(manifest=two_series())
    for item in SERIES2.sign[:-1]:
        g.store.add_item(pid, item, 0)
    g.store.set_photo_save(pid, SID, 1, 2, 5)
    g.store.set_photo_save(pid, LATER, 1, 2, CFG2["swap"] + 3)
    out = pc.swap(TOKEN, SERIES2.sign[-1])
    assert out["settled"] == {"cards": 3, "shards": 3 * CFG2["refund"]["rare"]}
    assert (got(out)["spare"], got(out)["dry"]) == (5, 2)
    assert (got(out, LATER)["spare"], got(out, LATER)["dry"]) == (0, 0)


# ---------------------------------------------------------------- what stays apart
def test_photocards_count_nowhere_else():
    g, pc, _, pid = setup()
    before = g.status(TOKEN)["totals"]
    progress = g.member_profile(TOKEN)["progress"]
    pc.buy(TOKEN, SID)
    assert g.store.owned(pid)
    assert g.status(TOKEN)["totals"] == before and g.member_profile(TOKEN)["progress"] == progress
    assert g.collection(TOKEN) == {"owned": {}, "recent": []}
    assert g.drop_history(TOKEN) == {"drops": [], "next": None}
    assert g.board(TOKEN, False, "score")["cards"] == []
    assert not set(SERIES.items) & set(g.manifest.items)
    assert code(g.craft, TOKEN, SERIES.solo[0]) == "bad_item"
    g.store.add_item(pid, "card:" + next(iter(g.manifest.cards)), 0)
    assert list(g.collection(TOKEN, "1.0.0")["owned"]) == ["card:" + next(iter(g.manifest.cards))]


def test_a_reset_save_starts_its_photocards_over(monkeypatch):
    g, pc, _, pid = setup()
    deals(monkeypatch, [SERIES.sign[0]] * 3, [SERIES.duo[0]])
    buy(pc)
    pc.buy(TOKEN, SID)
    assert (mine(pc)["boxes"], mine(pc)["dry"], mine(pc)["spare"]) == (2, 1, 2)
    g.admin_reset_save(pid, "op", "why")
    # The boxes were bought today all the same.
    assert mine(pc) == {"owned": [], "left": DAILY - 2, "boxes": 0, "dry": 0, "spare": 0, "box": None}


def test_opened_boxes_are_forgotten_after_a_while():
    g, pc, clock, _ = setup()
    buy(pc)
    shut = got(pc.buy(TOKEN, SID))["box"]["id"]
    clock.t += BOX_DAYS * 86400 + 1
    assert pc.prune() == 1 and pc.prune() == 0
    assert mine(pc)["box"]["id"] == shut and mine(pc)["boxes"] == 2


def test_the_database_keeps_a_box_through_a_restart(tmp_path):
    path = str(tmp_path / "t.db")
    clock = Clock()
    g = Game(Store(path), Manifest.load(), rng=random.Random(1), now=clock)
    g.store.update_player(g.status(TOKEN)["player"], shards=SHARDS)
    bought = Photocards(lambda: g).buy(TOKEN, SID)["photocards"]
    g.store.close()
    again = Game(Store(path), Manifest.load(), now=clock)
    assert Photocards(lambda: again).state(TOKEN)["photocards"] == bought
    again.store.close()


# ------------------------------------------------------------------------- HTTP
def test_the_api(monkeypatch):
    g, _, _, pid = setup(manifest=two_series({**CFG2, "daily": 0}, CFG))
    monkeypatch.setattr(main, "game", g)
    client = TestClient(main.app)
    h = {"X-Player-Token": TOKEN, "X-Client-Version": "9.9.9"}
    get = lambda: client.get("/api/photocards", headers=h).json()
    post = lambda path, body=None: client.post(f"/api/photocards/{path}", headers=h, json=body)

    def refused(r):
        return r.status_code, r.json()["detail"]["code"]

    state = get()
    assert state["player"] == pid and state["photocards"]["day"] == day_of(g.now())
    assert list(state["photocards"]["series"]) == [SID, LATER] and got(state)["box"] is None
    bought = post("buy", {"series": SID}).json()
    box = got(bought)["box"]
    assert len(box["cards"]) == SIZE and bought["shards"] == shards(g, pid)
    for body in (None, {}, {"series": ""}, {"series": "x" * 65}, {"series": 1}, {"series": SID, "price": 0},
                 {"series": SID, "price": "x"}, {"series": SID, "price": 2**70}):
        assert post("buy", body).status_code == 422
    assert refused(post("buy", {"series": "nope"})) == (404, "no_series")
    assert refused(post("buy", {"series": LATER})) == (409, "photo_off_sale")
    assert refused(post("open", {"box": 10**9})) == (404, "no_box")
    assert post("open", {"box": 2**70}).status_code == 422
    assert got(post("open", {"box": box["id"]}).json())["box"] is None
    assert refused(post("swap", {"item": SERIES.solo[0]})) == (400, "bad_item")
    missing = next(i for i in SERIES.sign if i not in got(bought)["owned"])
    assert refused(post("swap", {"item": missing})) == (409, "no_spare")
    g.store.set_photo_save(pid, LATER, 1, 1, CFG2["swap"])
    swapped = post("swap", {"item": SERIES2.sign[4]}).json()
    assert swapped["swapped"] == SERIES2.sign[4] and got(swapped, LATER)["owned"] == [SERIES2.sign[4]]
    assert refused(post("swap", {"item": SERIES2.sign[4]})) == (409, "owned")
    assert refused(post("buy", {"series": SID, "price": PRICE + 1})) == (409, "price_changed")
    for _ in range(DAILY - 1):
        post("buy", {"series": SID, "price": PRICE})
        post("open", {"box": got(get())["box"]["id"]})
    assert refused(post("buy", {"series": SID})) == (409, "photo_sold_out")
    g.store.update_player(pid, shards=0)
    g.store._db.execute("DELETE FROM photo_boxes")
    assert refused(post("buy", {"series": SID})) == (409, "no_shards")
    shelve(g, {**CFG2, "daily": 0})
    assert refused(post("swap", {"item": missing})) == (409, "photo_off_sale")
    assert not any(i.startswith(photo_deal.PREFIXES) for i in client.get("/api/collection", headers=h).json()["owned"])


def test_the_client_gets_the_shelf_as_it_is(monkeypatch):
    shelf = [CFG2, {**CFG, "daily": 0}]
    monkeypatch.setattr(main, "manifest", two_series(*shelf))
    assert TestClient(main.app).get("/api/economy").json()["photocards"] == shelf


@pytest.mark.parametrize("shelf", [None, []])
def test_the_api_without_photocards(monkeypatch, shelf):
    monkeypatch.setattr(main, "game", Game(Store(":memory:"), with_shelf(shelf), now=Clock()))
    client = TestClient(main.app)
    h = {"X-Player-Token": TOKEN, "X-Client-Version": "9.9.9"}
    for method, path, body in (("GET", "", None), ("POST", "/buy", {"series": SID}), ("POST", "/open", {"box": 1}),
                               ("POST", "/swap", {"item": SERIES.sign[0]})):
        r = client.request(method, f"/api/photocards{path}", headers=h, json=body)
        assert (r.status_code, r.json()["detail"]["code"]) == (404, "no_photocards")
