import json
import random

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import scratch
from app.game import Game, GameError
from app.manifest import Manifest
from app.park import POOL, Park
from app.park_scratch import BLANK, ParkScratch, mean_return, roll, symbols, top_symbols
from app.store import Store, day_of
from fixtures import Clock, SeqRng, tiny_manifest

TOKEN = "park-scratch-token-00001"
OTHER = "park-scratch-token-00002"
M = Manifest.load()
CFG = M.park["scratch"]
BASIC, PREMIUM = CFG["cards"]["basic"], CFG["cards"]["premium"]
PRICE = M.park["coin"]["price"]
POOL_CFG = M.park["lottery"]["pool"]
EMOTES = [f"emote:{k}" for k in M.scratch_emotes]
SKINS = [i["id"] for i in M.resonance_pool["skin"]]
OLD_SKINS = [f"char:{s['name']}" for s in M.data["skins"] if not s.get("since")]
BIGS = [f"card:{c['id']}" for c in M.data["cards"] if c.get("tier") == "big"]

# rng values: the table draw (x * 100 lands in the table's percent bands), then the layout's
MISS = .99


def use_first_cards(g, pid):
    """Records a revealed card of each kind, so the save's next cards are rolled, not first cards."""
    for kind in CFG["cards"]:
        g.store.reveal_park_scratch(g.store.add_park_scratch(pid, "2000-01-01", kind, "[]", "miss", 0, 0, "", 0), 1)


def setup(*rolls, coins=50, first=False):
    """A save with [coins] and 100,000 shards; unless [first], its first card of each kind is behind it."""
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), rng=SeqRng(*(rolls or (MISS,))), now=clock)
    park = Park(lambda: g)
    ps = ParkScratch(park)
    pid = g.status(TOKEN)["player"]
    g.store.update_player(pid, coins=coins, shards=100_000)
    if not first:
        use_first_cards(g, pid)
    g.status(OTHER)
    return g, ps, clock, pid


def play(ps, kind="basic", token=TOKEN):
    """Buys a card and reveals it; returns (bought, revealed)."""
    bought = ps.buy(token, kind)
    return bought, ps.reveal(token, bought["card"]["id"])


def coin_ledger(g, pid):
    rows = g.store._db.execute("SELECT source, amount FROM coin_ledger WHERE player_id = ?", (pid,)).fetchall()
    return {r["source"]: r["amount"] for r in rows}


def shard_ledger(g, pid):
    rows = g.store._db.execute("SELECT source, amount FROM shard_ledger WHERE player_id = ? AND source != 'starter'",
                               (pid,)).fetchall()
    return {r["source"]: r["amount"] for r in rows}


def news(g):
    return [{k: v for k, v in n.items() if k not in ("id", "ts")} for n in g.status(OTHER)["park"]["news"]]


# ----------------------------------------------------------------------- tables
def test_tables_are_the_approved_ones():
    assert (BASIC["coins"], BASIC["again"], BASIC["emote"]) == (1, 15, {"set": "achao", "weight": 5, "pity": 10})
    assert [(p["shards"], p["weight"]) for p in BASIC["prizes"]] == [(1000, 9.5), (2500, 3.5), (8000, .6), (50000, .05)]
    assert (PREMIUM["coins"], PREMIUM["again"]) == (5, 15)
    assert [(p["shards"], p["weight"]) for p in PREMIUM["prizes"]] == [(3000, 14), (5000, 10), (12500, 3),
                                                                       (40000, .5), (250000, .02)]
    assert PREMIUM["skin"] == {"weight": .5, "shards": 30000} and PREMIUM["big"] == {"weight": .5, "shards": 60000}
    assert (BASIC["first"], PREMIUM["first"]) == (1000, 5000)
    assert "jackpot" not in CFG
    assert BASIC["emote"]["set"] == M.scratch["emote"]["set"]


@pytest.mark.parametrize("card,pity,complete,x,want", [
    (BASIC, 0, False, 0, ("emote", 0)),
    (BASIC, 0, False, .0499, ("emote", 0)),
    (BASIC, 9, False, MISS, ("emote", 0)),
    (BASIC, 0, True, 0, ("again", 0)),
    (BASIC, 9, True, MISS, ("miss", 0)),
    (BASIC, 0, False, .05, ("again", 0)),
    (BASIC, 0, False, .1999, ("again", 0)),
    (BASIC, 0, False, .2, ("shards", 1000)),
    (BASIC, 0, False, .3, ("shards", 2500)),
    (BASIC, 0, False, .333, ("shards", 8000)),
    (BASIC, 0, False, .3362, ("shards", 50000)),
    (BASIC, 0, False, .3366, ("miss", 0)),
    (PREMIUM, 0, False, 0, ("again", 0)),
    (PREMIUM, 0, False, .1499, ("again", 0)),
    (PREMIUM, 0, False, .15, ("shards", 3000)),
    (PREMIUM, 0, False, .2899, ("shards", 3000)),
    (PREMIUM, 0, False, .2901, ("shards", 5000)),
    (PREMIUM, 0, False, .39, ("shards", 12500)),
    (PREMIUM, 0, False, .422, ("shards", 40000)),
    (PREMIUM, 0, False, .4251, ("shards", 250000)),
    (PREMIUM, 0, False, .4253, ("skin", 0)),
    (PREMIUM, 0, False, .4301, ("skin", 0)),
    (PREMIUM, 0, False, .4303, ("big", 0)),
    (PREMIUM, 0, False, .4351, ("big", 0)),
    (PREMIUM, 0, False, .4353, ("miss", 0)),
])
def test_one_roll(card, pity, complete, x, want):
    assert roll(card, pity, SeqRng(x), complete) == want


# ----------------------------------------------------------------------- money
def test_buying_takes_coins_and_the_prize_waits_for_the_reveal():
    g, ps, _, pid = setup(.3)
    bought = ps.buy(TOKEN, "basic")
    assert bought["park"]["coins"] == 49 and bought["shards"] == 100_000
    assert bought["park"]["stampsTotal"] == 1 and bought["park"]["today"] == {"spent": 0, "won": 0}
    assert bought["card"]["kind"] == "basic" and len(bought["card"]["cells"]) == 9
    assert scratch.prize_of(bought["card"]["cells"]) == "2500"
    # the card on the table comes back as it is, at no charge, whichever card is asked for
    for kind in ("basic", "premium"):
        again = ps.buy(TOKEN, kind)
        assert again["card"] == bought["card"] and again["park"]["coins"] == 49
    assert ps.state(TOKEN)["card"] == bought["card"]

    r = ps.reveal(TOKEN, bought["card"]["id"])
    assert r["prize"] == {"tier": "shards", "shards": 2500, "coins": 0, "item": None}
    assert r["shards"] == 102_500 and r["park"]["today"] == {"spent": 0, "won": 2500} and r["announce"] == 0
    assert r["card"] is None
    # revealing again answers the same prize and pays nothing
    r = ps.reveal(TOKEN, bought["card"]["id"])
    assert r["prize"]["shards"] == 2500 and r["shards"] == 102_500
    assert shard_ledger(g, pid) == {"park_scratch": 2500}
    assert coin_ledger(g, pid) == {"scratch": -1}
    assert ps.buy(TOKEN, "premium")["card"]["id"] != bought["card"]["id"]
    assert coin_ledger(g, pid) == {"scratch": -6}


def test_not_enough_coins():
    g, ps, _, pid = setup(coins=4)
    with pytest.raises(GameError) as e:
        ps.buy(TOKEN, "premium")
    assert e.value.code == "no_coins"
    assert ps.state(TOKEN)["card"] is None
    assert ps.buy(TOKEN, "basic")["park"]["coins"] == 3


def test_a_card_belongs_to_its_buyer():
    g, ps, _, _ = setup()
    card = ps.buy(TOKEN, "basic")["card"]
    for token, card_id in ((OTHER, card["id"]), (TOKEN, card["id"] + 1)):
        with pytest.raises(GameError) as e:
            ps.reveal(token, card_id)
        assert e.value.code == "no_card"


def test_again_gives_the_coins_back():
    g, ps, _, pid = setup(.1)
    bought, r = play(ps, "premium")
    assert scratch.prize_of(bought["card"]["cells"]) == "again" and bought["park"]["coins"] == 45
    assert r["prize"] == {"tier": "again", "shards": 0, "coins": 5, "item": None}
    assert r["park"]["coins"] == 50 and r["shards"] == 100_000 and r["park"]["today"]["won"] == 0
    assert coin_ledger(g, pid) == {"scratch": -5, "scratch_again": 5}
    # the stamps of the spent coins stay
    assert r["park"]["stampsTotal"] == 5


def test_a_miss_pays_nothing():
    g, ps, _, pid = setup()
    bought, r = play(ps)
    assert scratch.prize_of(bought["card"]["cells"]) is None
    assert r["prize"] == {"tier": "miss", "shards": 0, "coins": 0, "item": None}
    assert r["park"]["coins"] == 49 and shard_ledger(g, pid) == {}


# ----------------------------------------------------------------------- emotes
def test_emote_pity_carries_over_from_the_old_cards():
    g, ps, _, pid = setup()
    g.store.update_player(pid, scratch_pity=8)
    assert play(ps)[1]["prize"]["tier"] == "miss"
    assert ps.state(TOKEN)["pity"] == 9 and g.scratch_state(TOKEN)["pity"] == 9
    bought, r = play(ps)
    assert r["prize"]["tier"] == "emote" and r["prize"]["item"] in EMOTES
    assert scratch.prize_of(bought["card"]["cells"]) == r["prize"]["item"][6:]
    assert ps.state(TOKEN)["pity"] == 0
    assert g.collection(TOKEN)["owned"] == {r["prize"]["item"]: 1}
    # premium cards leave the count alone
    play(ps, "premium")
    assert ps.state(TOKEN)["pity"] == 0


def test_a_whole_set_turns_the_emote_tier_into_again():
    g, ps, _, pid = setup(0)
    for item in EMOTES:
        g.store.add_item(pid, item, 0)
    g.store.update_player(pid, scratch_pity=9)
    assert ps.state(TOKEN)["emotesWhole"] is True
    bought, r = play(ps)
    assert r["prize"] == {"tier": "again", "shards": 0, "coins": 1, "item": None}
    assert scratch.prize_of(bought["card"]["cells"]) == "again"
    assert ps.state(TOKEN)["pity"] == 9


def test_an_emote_found_before_the_reveal_gives_the_coin_back():
    g, ps, _, pid = setup(0)
    card = ps.buy(TOKEN, "basic")["card"]
    item = g.store.pending_park_scratch(pid)["item"]
    # an old card bought and revealed in between (from an old client) gives the same emote
    g.rng = SeqRng(0)
    old = g.scratch_buy(TOKEN)["card"]
    assert g.scratch_reveal(TOKEN, old["id"])["prize"]["item"] == item
    r = ps.reveal(TOKEN, card["id"])
    assert r["prize"] == {"tier": "again", "shards": 0, "coins": 1, "item": None}
    assert r["park"]["coins"] == 50 and g.collection(TOKEN)["owned"] == {item: 1}
    assert ps.reveal(TOKEN, card["id"])["prize"]["tier"] == "again"


# ----------------------------------------------------------------------- skins and big cards
def test_a_premium_card_gives_a_missing_skin_and_tells_the_server():
    g, ps, _, pid = setup(.426)
    g.store.update_player(pid, loadout='{"nick": "小草"}')
    for item in SKINS[1:]:
        g.store.add_item(pid, item, 0)
    bought, r = play(ps, "premium")
    assert scratch.prize_of(bought["card"]["cells"]) == "skin"
    assert r["prize"] == {"tier": "skin", "shards": 0, "coins": 0, "item": SKINS[0]}
    assert g.collection(TOKEN)["owned"][SKINS[0]] == 1
    assert news(g) == [{"kind": "scratch_item", "nick": "小草", "card": "premium", "item": SKINS[0]}]
    # resonance pity is untouched
    assert r["resonance"]["pity"] == {"legendary": 0, "skin": 0}


def test_a_premium_card_gives_a_missing_big_card():
    g, ps, _, pid = setup(.431)
    r = play(ps, "premium")[1]
    assert r["prize"]["tier"] == "big" and r["prize"]["item"] in BIGS
    assert news(g)[0]["item"] == r["prize"]["item"]


@pytest.mark.parametrize("roll_at,tier,items,shards", [(.426, "skin", SKINS, 30000), (.431, "big", BIGS, 60000)])
def test_a_save_with_every_one_gets_shards(roll_at, tier, items, shards):
    g, ps, _, pid = setup(roll_at)
    for item in items:
        g.store.add_item(pid, item, 0)
    bought, r = play(ps, "premium")
    assert scratch.prize_of(bought["card"]["cells"]) == tier
    assert r["prize"] == {"tier": tier, "shards": shards, "coins": 0, "item": None}
    assert r["shards"] == 100_000 + shards and shard_ledger(g, pid) == {"park_scratch": shards}
    assert news(g) == []


@pytest.mark.parametrize("roll_at,tier,shards", [(.426, "skin", 30000), (.431, "big", 60000)])
def test_an_item_found_before_the_reveal_pays_its_shards(roll_at, tier, shards):
    g, ps, _, pid = setup(roll_at)
    card = ps.buy(TOKEN, "premium")["card"]
    item = g.store.pending_park_scratch(pid)["item"]
    assert item
    g.store.add_item(pid, item, 0)
    r = ps.reveal(TOKEN, card["id"])
    assert r["prize"] == {"tier": tier, "shards": shards, "coins": 0, "item": None}
    assert g.collection(TOKEN)["owned"][item] == 1 and news(g) == []


def test_skins_a_client_cannot_show_stay_out():
    later = [i for i in SKINS if i not in OLD_SKINS]
    assert later
    g, ps, _, pid = setup(.426)
    for item in OLD_SKINS:
        g.store.add_item(pid, item, 0)
    card = ps.buy(TOKEN, "premium", "1.1.0")["card"]
    assert ps.reveal(TOKEN, card["id"])["prize"]["shards"] == 30000
    card = ps.buy(TOKEN, "premium", "1.2.1")["card"]
    assert ps.reveal(TOKEN, card["id"])["prize"]["item"] in later


# ----------------------------------------------------------------------- the lottery pool
def test_every_coin_spent_on_cards_feeds_the_lottery_pool():
    g, ps, _, _ = setup()
    play(ps)
    bought = ps.buy(TOKEN, "premium")
    want = POOL_CFG["seed"] + 6 * POOL_CFG["perCoin"]
    assert g.store.park_counter(POOL) == want and bought["park"]["jackpot"] == want
    assert "jackpot" not in bought and "jackpot" not in ps.state(TOKEN)


# ----------------------------------------------------------------------- the first card
def test_the_first_card_of_each_kind_wins_its_first_prize_once():
    g, ps, _, pid = setup(first=True)
    for kind, card in CFG["cards"].items():
        bought, r = play(ps, kind)
        cells = bought["card"]["cells"]
        assert scratch.prize_of(cells) == str(card["first"]) and cells.count(str(card["first"])) == 3
        assert r["prize"] == {"tier": "shards", "shards": card["first"], "coins": 0, "item": None}
        assert r["announce"] == 0
        # the next card of that kind is rolled (MISS)
        bought, r = play(ps, kind)
        assert scratch.prize_of(bought["card"]["cells"]) is None and r["prize"]["tier"] == "miss"
    assert shard_ledger(g, pid) == {"park_scratch": BASIC["first"] + PREMIUM["first"]}
    assert r["shards"] == 100_000 + BASIC["first"] + PREMIUM["first"]
    assert r["park"]["today"]["won"] == BASIC["first"] + PREMIUM["first"] and news(g) == []
    # another save gets its own first cards
    g.store.update_player(g.status(OTHER)["player"], coins=5)
    assert play(ps, "premium", OTHER)[1]["prize"]["shards"] == PREMIUM["first"]


def test_the_first_card_counts_toward_the_emote_pity_like_a_shard_win():
    g, ps, _, pid = setup(first=True)
    g.store.update_player(pid, scratch_pity=8)
    assert play(ps)[1]["prize"]["shards"] == BASIC["first"]
    assert ps.state(TOKEN)["pity"] == 9


def test_the_first_card_is_never_given_again_after_old_cards_are_pruned():
    g, ps, clock, _ = setup(first=True)
    play(ps)
    play(ps)
    clock.t += 31 * 86400
    assert ps.prune() == 1
    assert play(ps)[1]["prize"]["tier"] == "miss"
    clock.t += 31 * 86400
    assert ps.prune() == 1
    assert play(ps)[1]["prize"]["tier"] == "miss"


def test_a_big_first_prize_is_told_like_any_shard_win():
    g, ps, _, _ = setup(first=True)
    g.manifest.park["scratch"]["cards"]["basic"]["first"] = 50000
    r = play(ps)[1]
    assert r["prize"]["shards"] == 50000 and r["announce"] == 50000
    assert news(g) == [{"kind": "scratch_big", "nick": "匿名小面包", "card": "basic", "shards": 50000}]


def test_first_cards_show_their_amount_three_times_and_nothing_else_as_often():
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), rng=random.Random(11), now=clock)
    ps = ParkScratch(Park(lambda: g))
    for i in range(300):
        token = f"park-first-token-{i:07d}"
        g.store.update_player(g.status(token)["player"], coins=5)
        kind = ("basic", "premium")[i % 2]
        card = CFG["cards"][kind]
        cells = ps.buy(token, kind)["card"]["cells"]
        win = str(card["first"])
        assert len(cells) == 9 and cells.count(win) == 3 and scratch.prize_of(cells) == win
        assert all(cells.count(c) <= 2 for c in cells if c != win)
        top = top_symbols(card, CFG["serverAt"][kind])
        assert sum(1 for c in cells if c in top) <= 1


# ----------------------------------------------------------------------- news
def test_big_wins_are_told_and_small_ones_are_not():
    g, ps, _, _ = setup(.3)
    assert play(ps)[1]["announce"] == 0
    g.rng = SeqRng(.333)
    assert play(ps)[1]["announce"] == 8000 and news(g) == []
    g.rng = SeqRng(.3362)
    assert play(ps)[1]["announce"] == 50000
    assert news(g) == [{"kind": "scratch_big", "nick": "匿名小面包", "card": "basic", "shards": 50000}]
    g.rng = SeqRng(.422)
    assert play(ps, "premium")[1]["announce"] == 40000
    g.rng = SeqRng(.4251)
    assert play(ps, "premium")[1]["announce"] == 250000
    assert [n["shards"] for n in news(g)] == [50000, 250000]


# ----------------------------------------------------------------------- layout
def test_a_card_shows_one_prize_and_one_top_symbol_at_most():
    g, ps, _, pid = setup(coins=100_000)
    g.rng = random.Random(20261113)
    seen = {"basic": set(), "premium": set()}
    for n in range(3000):
        kind = ("basic", "premium")[n % 2]
        card = CFG["cards"][kind]
        cells = ps.buy(TOKEN, kind)["card"]["cells"]
        row = g.store.pending_park_scratch(pid)
        ps.reveal(TOKEN, row["id"])
        win = scratch.prize_of(cells)
        want = {"again": "again", "skin": "skin", "big": "big", "miss": None,
                "shards": str(row["shards"]), "emote": row["item"][6:]}[row["tier"]]
        assert len(cells) == 9 and win == want
        counts = {s: cells.count(s) for s in cells}
        assert all(c <= 2 for s, c in counts.items() if s != win) and counts.get(win, 3) == 3
        top = top_symbols(card, CFG["serverAt"][kind])
        assert sum(c for s, c in counts.items() if s in top and s != win) <= 1
        allowed = {str(p["shards"]) for p in card["prizes"]} | set(symbols(card))
        allowed |= set(M.scratch_emotes) if kind == "basic" else set()
        assert set(cells) <= allowed
        seen[kind] |= set(cells)
    assert BLANK in seen["premium"] and BLANK not in seen["basic"]
    assert "50000" in seen["basic"] and {"3000", "250000", "skin", "big"} <= seen["premium"]
    assert "jackpot" not in seen["basic"] | seen["premium"]


def test_old_cards_show_the_largest_amount_once_at_most():
    rng = random.Random(5)
    amounts = [p["shards"] for p in M.scratch["prizes"]]
    seen = 0
    for _ in range(5000):
        cells = scratch.layout(None, amounts, M.scratch_emotes, rng)
        assert cells.count("30000") <= 1 and scratch.prize_of(cells) is None
        seen += "30000" in cells
    assert seen > 1000


# ----------------------------------------------------------------------- the tables in the long run
def simulate(card, complete, n, seed):
    """Plays n cards on one save. Returns the shards per coin bought, its standard error, the count of each tier
    (shard prizes as "shards:<amount>"), and the shards the cards paid at face value (skin and big at their shards).

    A card pays s shards and costs c coins net (its coins, less those `again` gives back); the estimate is
    sum(s) / sum(c), and its standard error is that of a ratio, sqrt(sum((s - R c)^2)) / sum(c), with the cards taken
    as independent (the pity ties neighbours together a little)."""
    rng = random.Random(seed)
    pity = 0
    coins, tiers = card["coins"], {}
    ss = cc = s2 = c2 = sc = 0
    for _ in range(n):
        tier, s = roll(card, pity, rng, complete)
        c = coins
        if tier == "again":
            c = 0
        elif tier in ("skin", "big"):
            s = card[tier]["shards"]
        key = f"shards:{s}" if tier == "shards" else tier
        tiers[key] = tiers.get(key, 0) + 1
        if card.get("emote") and not complete:
            pity = 0 if tier == "emote" else pity + 1
        ss += s
        cc += c
        s2 += s * s
        c2 += c * c
        sc += s * c
    r = ss / cc
    return r, (s2 - 2 * r * sc + r * r * c2) ** .5 / cc, tiers, ss


def face_return(card):
    """One card's return per shard of its price on the table's weights: shard prizes, skin and big at their shards,
    and `again` at the card's price; the emote tier counts as nothing."""
    shards = sum(p["shards"] * p["weight"] for p in card["prizes"])
    shards += sum(card[t]["shards"] * card[t]["weight"] for t in ("skin", "big") if t in card)
    return shards / 100 / (card["coins"] * PRICE) + card["again"] / 100


def miss_rate(card):
    weights = [card["again"], *(p["weight"] for p in card["prizes"])]
    weights += [card[t]["weight"] for t in ("skin", "big") if t in card]
    weights += [card["emote"]["weight"]] if card.get("emote") else []
    return 1 - sum(weights) / 100


def test_the_returns_are_the_designed_ones():
    # Per card at face value: premium 1995 shards of 2500 plus 15% again, basic 255.5 of 500 plus 15% again.
    assert face_return(PREMIUM) == pytest.approx(.948, abs=1e-9)
    assert face_return(BASIC) == pytest.approx(.661, abs=1e-9)
    assert miss_rate(PREMIUM) == pytest.approx(.5648, abs=1e-9)
    # Per coin with the coins from `again` played on until they turn into shards (the emote tier is worth nothing).
    assert (round(mean_return(BASIC, False), 2), round(mean_return(BASIC, True), 2)) == (273.2, 319.38)
    assert round(mean_return(PREMIUM, False), 2) == 469.41


@pytest.mark.parametrize("kind,seed", [("basic", 4), ("premium", 5)])
def test_a_seeded_run_returns_the_face_value_and_misses_as_often_as_designed(kind, seed):
    # the basic card without its emote tier, which the face value counts as nothing
    card = {k: v for k, v in CFG["cards"][kind].items() if k != "emote"}
    n = 1_000_000
    _, _, tiers, shards = simulate(card, False, n, seed)
    ret = (shards + tiers["again"] * card["coins"] * PRICE) / (n * card["coins"] * PRICE)
    assert ret == pytest.approx(face_return(card), abs=.01)
    if kind == "premium":
        assert ret == pytest.approx(.948, abs=.01)
        assert tiers["miss"] / n == pytest.approx(.565, abs=.002)
    else:
        assert ret == pytest.approx(.66, abs=.01)


# A million cards a table, each within 4 standard errors of what the table should return (the error is about 0.6% of
# it on the basic card, from the 100x tier, and 0.3% on the premium one); every tier within 4 standard deviations of
# its count.
@pytest.mark.parametrize("kind,complete,seed", [("basic", False, 1), ("basic", True, 2), ("premium", False, 3)])
def test_a_table_returns_what_it_should(kind, complete, seed):
    card = CFG["cards"][kind]
    n = 1_000_000
    per_coin, se, tiers, _ = simulate(card, complete, n, seed)
    assert se < .01 * per_coin
    assert abs(per_coin - mean_return(card, complete)) <= 4 * se

    def near(count, p):
        sd = (n * p * (1 - p)) ** .5
        return abs(count - n * p) <= 4 * sd + 1

    rolled = 1.0
    again = card["again"]
    if card.get("emote") and complete:
        again += card["emote"]["weight"]
    elif card.get("emote"):
        # the 10-card pity: one emote every 8.03 cards, and the forced ones take the table's place
        p = card["emote"]["weight"] / 100
        cycle = sum((1 - p) ** k for k in range(card["emote"]["pity"]))
        assert near(tiers["emote"], 1 / cycle)
        rolled *= 1 - (1 - p) ** (card["emote"]["pity"] - 1) / cycle
    assert near(tiers["again"], again / 100 * rolled)
    for prize in card["prizes"]:
        assert near(tiers.get(f"shards:{prize['shards']}", 0), prize["weight"] / 100 * rolled)
    for tier in ("skin", "big"):
        if tier in card:
            assert near(tiers[tier], card[tier]["weight"] / 100 * rolled)


# ----------------------------------------------------------------------- housekeeping
def test_old_revealed_cards_are_pruned_but_the_first_of_each_kind():
    g, ps, clock, pid = setup()
    play(ps)
    kept = ps.buy(TOKEN, "basic")["card"]
    clock.t += 31 * 86400
    assert ps.prune() == 1
    assert ps.state(TOKEN)["card"] == kept
    assert g.store.has_park_scratch(pid, "basic") and g.store.has_park_scratch(pid, "premium")


def test_a_manifest_without_the_park():
    g = Game(Store(":memory:"), tiny_manifest(), rng=SeqRng(0), now=Clock())
    ps = ParkScratch(Park(lambda: g))
    for call in (lambda: ps.state(TOKEN), lambda: ps.buy(TOKEN, "basic"), lambda: ps.reveal(TOKEN, 1)):
        with pytest.raises(GameError) as e:
            call()
        assert e.value.code == "no_park"


def test_cards_are_stored_as_the_client_gets_them():
    g, ps, clock, pid = setup(.3)
    card = ps.buy(TOKEN, "basic")["card"]
    row = g.store.park_scratch_card(pid, card["id"])
    assert json.loads(row["cells"]) == card["cells"] and row["kind"] == "basic" and row["day"] == day_of(clock())
    assert (row["tier"], row["shards"], row["coins"], row["item"], row["revealed"]) == ("shards", 2500, 0, "", 0)


# ----------------------------------------------------------------------- HTTP and rooms
H = {"X-Player-Token": TOKEN, "X-Client-Version": "1.2.1"}


@pytest.fixture()
def api(monkeypatch):
    g, ps, clock, pid = setup(.333)
    monkeypatch.setattr(main, "game", g)
    main.manager.rooms.clear()
    with TestClient(main.app) as c:
        yield c, g, pid


def test_http_flow(api):
    c, g, pid = api
    assert c.get("/api/park/scratch").status_code == 401
    state = c.get("/api/park/scratch", headers=H).json()
    assert state == {"card": None, "pity": 0, "emotesWhole": False}
    assert c.post("/api/park/scratch", json={"kind": "gold"}, headers=H).status_code == 422
    bought = c.post("/api/park/scratch", json={"kind": "basic"}, headers=H).json()
    assert bought["park"]["coins"] == 49 and bought["card"]["kind"] == "basic"
    assert c.get("/api/park/scratch", headers=H).json()["card"] == bought["card"]
    r = c.post("/api/park/scratch/reveal", json={"card": bought["card"]["id"]}, headers=H)
    assert r.status_code == 200 and r.json()["prize"] == {"tier": "shards", "shards": 8000, "coins": 0, "item": None}
    assert "announce" not in r.json() and r.json()["shards"] == 108_000
    missing = c.post("/api/park/scratch/reveal", json={"card": 999}, headers=H)
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "no_card"
    g.store.update_player(pid, coins=0)
    r = c.post("/api/park/scratch", json={"kind": "premium"}, headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_coins"
    # the old cards are a separate game
    assert c.get("/api/scratch", headers=H).json()["card"] is None


def test_the_room_sees_a_big_win_once(api):
    c, g, _ = api
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        a.send_json({"type": "join", "room": "r1", "nick": "a", "token": TOKEN})
        you = a.receive_json()["you"]
        b.send_json({"type": "join", "room": "r1", "nick": "b", "token": OTHER})
        b.receive_json()
        a.receive_json()  # member_joined(b)
        card = c.post("/api/park/scratch", json={"kind": "basic"}, headers=H).json()["card"]
        for _ in range(2):  # the second reveal pays nothing and says nothing
            c.post("/api/park/scratch/reveal", json={"card": card["id"]}, headers=H)
        expected = {"type": "scratch", "id": you, "shards": 8000}
        assert a.receive_json() == expected and b.receive_json() == expected
        for ws in (a, b):
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
