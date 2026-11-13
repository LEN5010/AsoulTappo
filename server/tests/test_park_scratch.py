import json
import random

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import scratch
from app.game import Game, GameError
from app.manifest import Manifest
from app.park import JACKPOT, Park
from app.park_scratch import BLANK, ParkScratch, mean_return, roll, symbols, top_symbols
from app.store import Store, day_of
from fixtures import Clock, SeqRng, tiny_manifest

TOKEN = "park-scratch-token-00001"
OTHER = "park-scratch-token-00002"
M = Manifest.load()
CFG = M.park["scratch"]
BASIC, PREMIUM = CFG["cards"]["basic"], CFG["cards"]["premium"]
POT = CFG["jackpot"]
EMOTES = [f"emote:{k}" for k in M.scratch_emotes]
SKINS = [i["id"] for i in M.resonance_pool["skin"]]
OLD_SKINS = [f"char:{s['name']}" for s in M.data["skins"] if not s.get("since")]
BIGS = [f"card:{c['id']}" for c in M.data["cards"] if c.get("tier") == "big"]

# rng values: the jackpot draw, then the table draw (x * 100 lands in the table's percent bands)
NO_POT = .5
MISS = .99


def setup(*rolls, coins=50):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), rng=SeqRng(*(rolls or (NO_POT, MISS))), now=clock)
    park = Park(lambda: g)
    ps = ParkScratch(park)
    pid = g.status(TOKEN)["player"]
    g.store.update_player(pid, coins=coins, shards=100_000)
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
    assert (PREMIUM["coins"], PREMIUM["again"]) == (5, 12)
    assert [(p["shards"], p["weight"]) for p in PREMIUM["prizes"]] == [(5000, 13), (12500, 3), (40000, .5),
                                                                       (250000, .02)]
    assert PREMIUM["skin"] == {"weight": .2, "shards": 30000} and PREMIUM["big"] == {"weight": .1, "shards": 60000}
    assert POT == {"perCoin": 20, "seed": 30000, "odds": 12000}
    assert BASIC["emote"]["set"] == M.scratch["emote"]["set"]


def test_mean_returns_against_the_design():
    # Design §3: 299 before the emote set is whole, 348 after, 340 for premium. The design's premium figure leaves
    # the pot's seed out (4% of the stake only); counted like the basic card's it is 342.5.
    assert mean_return(BASIC, POT, complete=False) == pytest.approx(299.28, abs=.01)
    assert mean_return(BASIC, POT, complete=True) == pytest.approx(347.47, abs=.01)
    assert mean_return(PREMIUM, POT, complete=False) == pytest.approx(342.46, abs=.01)


@pytest.mark.parametrize("card,pity,complete,rolls,want", [
    (BASIC, 0, False, (0, MISS), ("jackpot", 0)),
    (BASIC, 9, False, (0, MISS), ("jackpot", 0)),  # the pot comes before the pity
    (BASIC, 0, False, (NO_POT, 0), ("emote", 0)),
    (BASIC, 0, False, (NO_POT, .0499), ("emote", 0)),
    (BASIC, 9, False, (NO_POT, MISS), ("emote", 0)),
    (BASIC, 0, True, (NO_POT, 0), ("again", 0)),
    (BASIC, 9, True, (NO_POT, MISS), ("miss", 0)),
    (BASIC, 0, False, (NO_POT, .05), ("again", 0)),
    (BASIC, 0, False, (NO_POT, .1999), ("again", 0)),
    (BASIC, 0, False, (NO_POT, .2), ("shards", 1000)),
    (BASIC, 0, False, (NO_POT, .3), ("shards", 2500)),
    (BASIC, 0, False, (NO_POT, .333), ("shards", 8000)),
    (BASIC, 0, False, (NO_POT, .3362), ("shards", 50000)),
    (BASIC, 0, False, (NO_POT, .3366), ("miss", 0)),
    (PREMIUM, 0, False, (5 / 12000 - 1e-9, MISS), ("jackpot", 0)),
    (PREMIUM, 0, False, (5 / 12000, MISS), ("miss", 0)),
    (PREMIUM, 0, False, (NO_POT, .1199), ("again", 0)),
    (PREMIUM, 0, False, (NO_POT, .12), ("shards", 5000)),
    (PREMIUM, 0, False, (NO_POT, .25), ("shards", 12500)),
    (PREMIUM, 0, False, (NO_POT, .28), ("shards", 40000)),
    (PREMIUM, 0, False, (NO_POT, .2851), ("shards", 250000)),
    (PREMIUM, 0, False, (NO_POT, .2853), ("skin", 0)),
    (PREMIUM, 0, False, (NO_POT, .2873), ("big", 0)),
    (PREMIUM, 0, False, (NO_POT, .2882), ("miss", 0)),
])
def test_one_roll(card, pity, complete, rolls, want):
    assert roll(card, pity, SeqRng(*rolls), complete, POT["odds"]) == want


# ----------------------------------------------------------------------- money
def test_buying_takes_coins_and_the_prize_waits_for_the_reveal():
    g, ps, _, pid = setup(NO_POT, .3)
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
    assert ps.state(TOKEN)["card"] is None and ps.state(TOKEN)["jackpot"] == POT["seed"]
    assert ps.buy(TOKEN, "basic")["park"]["coins"] == 3


def test_a_card_belongs_to_its_buyer():
    g, ps, _, _ = setup()
    card = ps.buy(TOKEN, "basic")["card"]
    for token, card_id in ((OTHER, card["id"]), (TOKEN, card["id"] + 1)):
        with pytest.raises(GameError) as e:
            ps.reveal(token, card_id)
        assert e.value.code == "no_card"


def test_again_gives_the_coins_back():
    g, ps, _, pid = setup(NO_POT, .1)
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


def test_a_jackpot_card_counts_toward_the_pity():
    g, ps, _, pid = setup(0, MISS)
    assert play(ps)[1]["prize"]["tier"] == "jackpot"
    assert ps.state(TOKEN)["pity"] == 1


def test_a_whole_set_turns_the_emote_tier_into_again():
    g, ps, _, pid = setup(NO_POT, 0)
    for item in EMOTES:
        g.store.add_item(pid, item, 0)
    g.store.update_player(pid, scratch_pity=9)
    assert ps.state(TOKEN)["emotesWhole"] is True
    bought, r = play(ps)
    assert r["prize"] == {"tier": "again", "shards": 0, "coins": 1, "item": None}
    assert scratch.prize_of(bought["card"]["cells"]) == "again"
    assert ps.state(TOKEN)["pity"] == 9


def test_the_emote_on_an_unrevealed_old_card_counts_as_owned():
    g, ps, _, pid = setup(NO_POT, 0)
    for item in EMOTES[:-1]:
        g.store.add_item(pid, item, 0)
    g.rng = SeqRng(0)
    old = g.scratch_buy(TOKEN)["card"]
    assert g.store.scratch_card(pid, old["id"])["item"] == EMOTES[-1]
    g.rng = SeqRng(NO_POT, 0)
    # the last emote is on its way, so the set counts as whole and the tier pays the coin back
    assert play(ps)[1]["prize"]["tier"] == "again"


def test_an_emote_found_before_the_reveal_gives_the_coin_back():
    g, ps, _, pid = setup(NO_POT, 0)
    card = ps.buy(TOKEN, "basic")["card"]
    item = g.store.pending_park_scratch(pid)["item"]
    g.store.add_item(pid, item, 0)
    r = ps.reveal(TOKEN, card["id"])
    assert r["prize"] == {"tier": "again", "shards": 0, "coins": 1, "item": None}
    assert r["park"]["coins"] == 50 and g.collection(TOKEN)["owned"] == {item: 1}
    assert ps.reveal(TOKEN, card["id"])["prize"]["tier"] == "again"


# ----------------------------------------------------------------------- skins and big cards
def test_a_premium_card_gives_a_missing_skin_and_tells_the_server():
    g, ps, _, pid = setup(NO_POT, .286)
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
    g, ps, _, pid = setup(NO_POT, .2875)
    r = play(ps, "premium")[1]
    assert r["prize"]["tier"] == "big" and r["prize"]["item"] in BIGS
    assert news(g)[0]["item"] == r["prize"]["item"]


@pytest.mark.parametrize("roll_at,tier,items,shards", [(.286, "skin", SKINS, 30000), (.2875, "big", BIGS, 60000)])
def test_a_save_with_every_one_gets_shards(roll_at, tier, items, shards):
    g, ps, _, pid = setup(NO_POT, roll_at)
    for item in items:
        g.store.add_item(pid, item, 0)
    bought, r = play(ps, "premium")
    assert scratch.prize_of(bought["card"]["cells"]) == tier
    assert r["prize"] == {"tier": tier, "shards": shards, "coins": 0, "item": None}
    assert r["shards"] == 100_000 + shards and shard_ledger(g, pid) == {"park_scratch": shards}
    assert news(g) == []


@pytest.mark.parametrize("roll_at,tier,shards", [(.286, "skin", 30000), (.2875, "big", 60000)])
def test_an_item_found_before_the_reveal_pays_its_shards(roll_at, tier, shards):
    g, ps, _, pid = setup(NO_POT, roll_at)
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
    g, ps, _, pid = setup(NO_POT, .286)
    for item in OLD_SKINS:
        g.store.add_item(pid, item, 0)
    card = ps.buy(TOKEN, "premium", "1.1.0")["card"]
    assert ps.reveal(TOKEN, card["id"])["prize"]["shards"] == 30000
    card = ps.buy(TOKEN, "premium", "1.2.1")["card"]
    assert ps.reveal(TOKEN, card["id"])["prize"]["item"] in later


# ----------------------------------------------------------------------- jackpot
def test_every_coin_feeds_the_pot():
    g, ps, _, _ = setup()
    play(ps)
    play(ps, "premium")
    want = POT["seed"] + 6 * POT["perCoin"]
    assert ps.state(TOKEN)["jackpot"] == want and g.store.park_counter(JACKPOT) == want


def test_the_jackpot_takes_the_whole_pot_and_starts_again():
    g, ps, _, pid = setup(0, MISS)
    g.store.set_park_counter(JACKPOT, 200_000)
    bought = ps.buy(TOKEN, "premium")
    assert scratch.prize_of(bought["card"]["cells"]) == "jackpot"
    # taken when bought, paid when revealed
    assert bought["shards"] == 100_000 and bought["jackpot"] == POT["seed"]
    r = ps.reveal(TOKEN, bought["card"]["id"])
    won = 200_000 + 5 * POT["perCoin"]
    assert r["prize"] == {"tier": "jackpot", "shards": won, "coins": 0, "item": None}
    assert r["shards"] == 100_000 + won and r["announce"] == won
    assert r["park"]["today"]["won"] == won and shard_ledger(g, pid) == {"jackpot": won}
    assert news(g) == [{"kind": "jackpot", "nick": "匿名小面包", "shards": won}]
    assert ps.reveal(TOKEN, bought["card"]["id"])["shards"] == 100_000 + won and len(news(g)) == 1


def test_a_second_winner_gets_the_new_pot():
    g, ps, _, _ = setup(0, MISS)
    pid2 = g.status(OTHER)["player"]
    g.store.update_player(pid2, coins=5)
    first = ps.buy(TOKEN, "basic")["card"]
    g.rng = SeqRng(0, MISS)
    second = ps.buy(OTHER, "basic")["card"]
    assert ps.reveal(OTHER, second["id"])["prize"]["shards"] == POT["seed"] + POT["perCoin"]
    assert ps.reveal(TOKEN, first["id"])["prize"]["shards"] == POT["seed"] + POT["perCoin"]


# ----------------------------------------------------------------------- news
def test_big_wins_are_told_and_small_ones_are_not():
    g, ps, _, _ = setup(NO_POT, .3)
    assert play(ps)[1]["announce"] == 0
    g.rng = SeqRng(NO_POT, .333)
    assert play(ps)[1]["announce"] == 8000 and news(g) == []
    g.rng = SeqRng(NO_POT, .3362)
    assert play(ps)[1]["announce"] == 50000
    assert news(g) == [{"kind": "scratch_big", "nick": "匿名小面包", "card": "basic", "shards": 50000}]
    g.rng = SeqRng(NO_POT, .28)
    assert play(ps, "premium")[1]["announce"] == 40000
    g.rng = SeqRng(NO_POT, .2851)
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
        want = {"jackpot": "jackpot", "again": "again", "skin": "skin", "big": "big", "miss": None,
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
    assert {"50000", "jackpot"} <= seen["basic"] and {"250000", "skin", "big", "jackpot"} <= seen["premium"]


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
    """Plays n cards on one save with the pot as it grows; returns (shards per coin bought, tier counts)."""
    rng = random.Random(seed)
    pity, pot, shards, spent, back = 0, POT["seed"], 0, 0, 0
    coins, tiers = card["coins"], {}
    for _ in range(n):
        spent += coins
        pot += coins * POT["perCoin"]
        tier, s = roll(card, pity, rng, complete, POT["odds"])
        tiers[tier] = tiers.get(tier, 0) + 1
        if tier == "jackpot":
            s, pot = pot, POT["seed"]
        elif tier == "again":
            back += coins
        elif tier in ("skin", "big"):
            s = card[tier]["shards"]
        if card.get("emote") and not complete:
            pity = 0 if tier == "emote" else pity + 1
        shards += s
    return shards / (spent - back), tiers


# One million cards leave a standard error of about 0.6% on the basic card (the 100x tier and the pot) and 0.4% on the
# premium one, about the ±0.5% asked for; ten and five million bring both to about 0.18%.
@pytest.mark.parametrize("kind,complete,n,seed", [("basic", False, 10_000_000, 1), ("basic", True, 10_000_000, 2),
                                                  ("premium", False, 5_000_000, 3)])
def test_a_table_returns_what_it_should(kind, complete, n, seed):
    card = CFG["cards"][kind]
    per_coin, tiers = simulate(card, complete, n, seed)
    assert per_coin == pytest.approx(mean_return(card, POT, complete), rel=.005)

    def near(count, p):
        sd = (n * p * (1 - p)) ** .5
        return abs(count - n * p) <= 4 * sd + 1

    q = card["coins"] / POT["odds"]
    assert near(tiers.get("jackpot", 0), q)
    rolled = 1 - q
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
    for tier in ("skin", "big"):
        if tier in card:
            assert near(tiers[tier], card[tier]["weight"] / 100 * rolled)


def test_shard_tiers_come_at_their_rates():
    rng = random.Random(9)
    n = 1_000_000
    for card in (BASIC, PREMIUM):
        seen = {}
        for _ in range(n):
            tier, s = roll(card, 0, rng, True, POT["odds"])
            if tier == "shards":
                seen[s] = seen.get(s, 0) + 1
        for prize in card["prizes"]:
            p = prize["weight"] / 100 * (1 - card["coins"] / POT["odds"])
            assert abs(seen.get(prize["shards"], 0) - n * p) <= 4 * (n * p * (1 - p)) ** .5 + 1


# ----------------------------------------------------------------------- housekeeping
def test_old_revealed_cards_are_pruned():
    g, ps, clock, _ = setup()
    play(ps)
    kept = ps.buy(TOKEN, "basic")["card"]
    clock.t += 31 * 86400
    assert ps.prune() == 1
    assert ps.state(TOKEN)["card"] == kept


def test_a_manifest_without_the_park():
    g = Game(Store(":memory:"), tiny_manifest(), rng=SeqRng(0), now=Clock())
    ps = ParkScratch(Park(lambda: g))
    for call in (lambda: ps.state(TOKEN), lambda: ps.buy(TOKEN, "basic"), lambda: ps.reveal(TOKEN, 1)):
        with pytest.raises(GameError) as e:
            call()
        assert e.value.code == "no_park"


def test_cards_are_stored_as_the_client_gets_them():
    g, ps, clock, pid = setup(NO_POT, .3)
    card = ps.buy(TOKEN, "basic")["card"]
    row = g.store.park_scratch_card(pid, card["id"])
    assert json.loads(row["cells"]) == card["cells"] and row["kind"] == "basic" and row["day"] == day_of(clock())
    assert (row["tier"], row["shards"], row["coins"], row["item"], row["revealed"]) == ("shards", 2500, 0, "", 0)


# ----------------------------------------------------------------------- HTTP and rooms
H = {"X-Player-Token": TOKEN, "X-Client-Version": "1.2.1"}


@pytest.fixture()
def api(monkeypatch):
    g, ps, clock, pid = setup(NO_POT, .333)
    monkeypatch.setattr(main, "game", g)
    main.manager.rooms.clear()
    with TestClient(main.app) as c:
        yield c, g, pid


def test_http_flow(api):
    c, g, pid = api
    assert c.get("/api/park/scratch").status_code == 401
    state = c.get("/api/park/scratch", headers=H).json()
    assert state == {"card": None, "pity": 0, "emotesWhole": False, "jackpot": POT["seed"]}
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
