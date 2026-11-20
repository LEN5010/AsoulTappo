"""Holo versions (镭射款): resonance turns a draw of one of their cards into them at the economy's holoChance."""
import itertools
import json

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import economy
from app.game import BOARD_POINTS, Game, GameError, player_id_for
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock, SeqRng, real_pool_counts

TOKEN = "holo-player-token-0001"
NEW = "1.2.4"
M = Manifest.load()
CARD, HOLO = next(iter(M.holos.items()))
#: Every holo version but HOLO. A save holding every common card draws the cards whose holo version it lacks first:
#: with these held as well, that is CARD alone.
OTHER_HOLOS = [h for h in M.holos.values() if h != HOLO]
# A tier roll inside common, the pick (the only card left to find), then the holo roll.
COMMON = .5


def game(chance, *rolls, owned=()):
    """A save holding every common card but CARD (and [owned]); the economy's holo chance set to [chance]."""
    m = Manifest.load()
    if chance is None:
        m.resonance.pop("holoChance", None)
    else:
        m.resonance["holoChance"] = chance
    g = Game(Store(":memory:"), m, rng=SeqRng(*rolls), now=Clock())
    g.status(TOKEN)
    pid = player_id_for(TOKEN)
    for item in m.resonance_pool["common"]:
        if item["kind"] == "card" and item["id"] != CARD:
            g.store.add_item(pid, item["id"], 0)
    for iid in owned:
        g.store.add_item(pid, iid, 0)
    return g, pid


def test_the_21_holo_versions_are_items_outside_the_pool():
    assert len(M.holos) == 21
    for card, holo in M.holos.items():
        c = M.cards[card[5:]]
        assert holo == f"holo:{c['id']}" and M.items[holo]["kind"] == "holo"
        assert c["rarity"] == "common" and c["tier"] == "normal" and not c["video"]
        assert c["series"] in ("moon", "casket", "reverie") and c["holo"]["mask"] == f"pack:holo/{c['id']}.webp"
        assert set(c["holo"]["shine"]) == {"laserIntensity", "skinProtection", "clothBoost", "hueStart", "hueRange"}
    pooled = {i["id"] for tier in M.resonance_pool.values() for i in tier}
    assert not pooled & set(M.holos.values())
    assert len(pooled) == sum(real_pool_counts(M).values())


def test_the_chance_comes_from_the_economy():
    # just under the chance: holo; at it: the card alone
    g, _ = game(30, COMMON, 0, .2999)
    assert g.resonate(TOKEN, 1, NEW)["drops"][0].get("holo") is True
    g, _ = game(30, COMMON, 0, .30)
    drop = g.resonate(TOKEN, 1, NEW)["drops"][0]
    assert drop["item"] == CARD and "holo" not in drop


@pytest.mark.parametrize("chance", [None, 0])
def test_without_a_chance_there_are_no_holo_versions_and_no_roll_for_them(chance):
    # The next roll would be a holo one; with no chance it is the next draw's tier roll instead (legendary).
    g, pid = game(chance, COMMON, 0, 0, .5)
    drops = g.resonate(TOKEN, 2, NEW)["drops"]
    assert drops[0]["item"] == CARD and "holo" not in drops[0]
    assert drops[1]["rarity"] == "legendary"
    assert HOLO not in g.store.owned(pid)


def test_a_first_holo_version_comes_with_its_card():
    g, pid = game(100, COMMON, 0, 0)
    r = g.resonate(TOKEN, 1, NEW)
    assert r["drops"] == [{"item": CARD, "rarity": "common", "new": True, "count": 1, "shards": 0, "tier": "normal",
                           "holo": True, "cardNew": True}]
    owned = g.store.owned(pid)
    assert owned[CARD] == 1 and owned[HOLO] == 1
    assert r["shards"] == 1600 - 160
    # the drop log keeps the holo version
    assert g.store.recent_drops(pid)[0]["item"] == HOLO


def test_a_first_holo_version_of_a_held_card_pays_no_shards():
    g, pid = game(100, COMMON, 0, 0, owned=[CARD, *OTHER_HOLOS])
    r = g.resonate(TOKEN, 1, NEW)
    drop = r["drops"][0]
    assert drop["holo"] is True and drop["new"] is True and drop["cardNew"] is False and drop["shards"] == 0
    assert r["shards"] == 1600 - 160
    # the card is not kept twice
    owned = g.store.owned(pid)
    assert owned[CARD] == 1 and owned[HOLO] == 1


def test_a_repeat_holo_version_pays_the_holo_refund():
    g, pid = game(100, COMMON, 0, 0, owned=[CARD, HOLO, *OTHER_HOLOS])
    r = g.resonate(TOKEN, 1, NEW)
    drop = r["drops"][0]
    refund = M.resonance["duplicateRefund"]["holo"]
    assert refund == 180
    assert drop["holo"] is True and drop["new"] is False and drop["cardNew"] is False and drop["shards"] == refund
    assert r["shards"] == 1600 - 160 + refund
    owned = g.store.owned(pid)
    assert owned[CARD] == 1 and owned[HOLO] == 1


@pytest.mark.parametrize("roll, holo_configured, holo", [(0, False, True), (.99, True, False)])
def test_a_repeat_without_a_holo_refund_uses_the_card_refund(roll, holo_configured, holo):
    g, _ = game(25, COMMON, 0, roll, owned=[CARD, HOLO, *OTHER_HOLOS])
    if not holo_configured:
        g.manifest.resonance["duplicateRefund"].pop("holo")
    drop = g.resonate(TOKEN, 1, NEW)["drops"][0]
    assert drop.get("holo", False) is holo
    assert drop["shards"] == M.resonance["duplicateRefund"]["normal"]


def test_the_second_holo_version_in_one_batch_is_a_repeat():
    g, pid = game(100, COMMON, 0, 0, COMMON, 0, 0, owned=OTHER_HOLOS)
    drops = g.resonate(TOKEN, 2, NEW)["drops"]
    assert [(d["item"], d.get("holo"), d["new"], d["shards"]) for d in drops] == [
        (CARD, True, True, 0), (CARD, True, False, M.resonance["duplicateRefund"]["holo"])]
    assert g.store.owned(pid)[HOLO] == 1


@pytest.mark.parametrize("version,holo", [("1.2.3", False), ("1.2.2", False), ("", False), ("1.2.4-rc.1", True),
                                          (NEW, True), ("1.3.0", True)])
def test_clients_older_than_the_holo_versions_never_get_one(version, holo):
    g, pid = game(100, COMMON, 0, 0)
    drop = g.resonate(TOKEN, 1, version)["drops"][0]
    assert drop["item"] == CARD and drop.get("holo", False) is holo and (HOLO in g.store.owned(pid)) is holo


def test_a_holo_version_is_never_crafted():
    g, _ = game(100, COMMON)
    g.store.update_player(player_id_for(TOKEN), shards=10**6)
    with pytest.raises(GameError, match="unknown item"):
        g.craft(TOKEN, HOLO)


def test_holo_versions_score_on_the_board_but_are_not_cards():
    assert BOARD_POINTS["holo"] == 20
    assert all(p == BOARD_POINTS["holo"] for iid, p in Game(Store(":memory:"), M).board_points.items()
               if iid in M.holos.values())
    g = Game(Store(":memory:"), M, now=Clock())
    g.status(TOKEN)
    pid = player_id_for(TOKEN)
    g.store.add_item(pid, CARD, 0)
    before = g.board(TOKEN, False, "score")["me"]
    g.store.add_item(pid, HOLO, 0)
    g._board = None
    after = g.board(TOKEN, False, "score")
    assert after["me"]["score"] == before["score"] + 20
    assert after["me"]["cards"] == before["cards"] == 1
    assert after["total"] == len(M.cards) and after["points"]["holo"] == 20


def test_progress_and_totals_count_the_holo_versions():
    g = Game(Store(":memory:"), M, now=Clock())
    status = g.status(TOKEN)
    assert status["totals"]["items"] == sum(real_pool_counts(M).values()) + 21 + 20
    pid = player_id_for(TOKEN)
    g.store.add_item(pid, HOLO, 0)
    assert g.collection_progress(g.store.owned(pid))["cards"] == [1, len(M.cards) + 21]


def test_older_clients_are_sent_no_holo_versions_nor_their_chance():
    g = Game(Store(":memory:"), M, now=Clock())
    g.status(TOKEN)
    g.store.add_item(player_id_for(TOKEN), HOLO, 0)
    g.store.add_item(player_id_for(TOKEN), CARD, 0)
    assert HOLO in g.collection(TOKEN, NEW)["owned"]
    old = g.collection(TOKEN, "1.2.3")["owned"]
    assert HOLO not in old and CARD in old
    data, _ = economy.load(economy.EXAMPLE)
    client = TestClient(main.app)
    got = client.get("/api/economy", headers={"X-Client-Version": NEW}).json()["resonance"]
    assert got["holoChance"] == data["resonance"]["holoChance"]
    for version in ("1.2.3", ""):
        headers = {"X-Client-Version": version} if version else {}
        assert "holoChance" not in client.get("/api/economy", headers=headers).json()["resonance"]


@pytest.mark.parametrize("chance", [-1, 101, "10", True])
def test_a_holo_chance_outside_0_to_100_is_refused(tmp_path, chance):
    raw = json.loads(economy.EXAMPLE.read_text(encoding="utf-8"))
    raw["resonance"]["holoChance"] = chance
    path = tmp_path / "economy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="holoChance"):
        economy.load(path)


# ---- a save that owns the whole pool but not every holo version
DAY = 86400.0
BANNER_VERSION = "9.9.9"
BANNER = {"id": "forms", "name": "双形态", "items": ["char:嘉然然龙", "char:乃琳法师"], "rate": 5, "pity": 4}


def whole_save(*rolls, lacking=(HOLO,), chance=25, banner=None, featured=True, holos=None):
    """A save holding every item of the pool it draws from and every holo version but [lacking]. With [banner] (fields
    over BANNER's) the pool is a running limited pool and the client is BANNER_VERSION; the save holds the banner's
    featured items too unless [featured] is false. [holos] replaces the manifest's card -> holo version table."""
    m = Manifest.load()
    if chance is None:
        m.resonance.pop("holoChance", None)
    else:
        m.resonance["holoChance"] = chance
    clock = Clock()
    version = NEW
    if banner is not None:
        m.resonance["banners"] = [{**BANNER, "start": clock.t + DAY, "end": clock.t + 8 * DAY, **banner}]
        m.__dict__.pop("banners", None)
        clock.t += 2 * DAY
        version = BANNER_VERSION
    if holos is not None:
        m.__dict__["holos"] = holos
    g = Game(Store(":memory:"), m, rng=SeqRng(*rolls), now=clock)
    g.status(TOKEN)
    pid = player_id_for(TOKEN)
    running = m.banner("forms", version, clock.t) if banner is not None else None
    pool = m.resonance_pool_for(version, clock.t, tiers=running.tier_rates(m.resonance["rates"]) if running else ())
    held = list(running.items) if running and featured else []
    for iid in [i["id"] for items in pool.values() for i in items] + held:
        g.store.add_item(pid, iid, 0)
    for holo in m.holos_for(version).values():
        if holo not in lacking:
            g.store.add_item(pid, holo, 0)
    return g, pid, version, pool


def card_roll(at):
    """A roll for the common pick that lands [at] (0 to 1) of the way into its card group."""
    weights = M.resonance["commonKindWeights"]
    before = sum(w for kind, w in itertools.takewhile(lambda kw: kw[0] != "card", weights.items()))
    return (before + at * weights["card"]) / sum(weights.values())


#: Past the middle of the card group: with every common card a candidate, a card other than CARD.
MIDDLE = .55
PICK = card_roll(MIDDLE)


def picked_from_all(pool):
    """The card PICK gives when every common card is a candidate (as before the holo versions kept cards apart)."""
    cards = [i["id"] for i in pool["common"] if i["kind"] == "card"]
    return cards[int(MIDDLE * len(cards))]


def test_a_save_owning_every_item_still_draws_and_finds_its_missing_holo_version():
    g, pid, version, pool = whole_save(COMMON, PICK, 0)
    assert picked_from_all(pool) != CARD
    r = g.resonate(TOKEN, 1, version)
    drop = r["drops"][0]
    assert drop["item"] == CARD and drop["holo"] is True and drop["new"] is True and drop["cardNew"] is False
    assert drop["shards"] == 0 and r["shards"] == 1600 - 160
    assert g.store.owned(pid)[HOLO] == 1


def test_without_the_holo_the_preferred_card_is_a_repeat_and_stays_preferred():
    g, pid, version, _ = whole_save(COMMON, PICK, .99, COMMON, PICK, 0)
    drops = g.resonate(TOKEN, 2, version)["drops"]
    assert drops[0]["item"] == CARD and "holo" not in drops[0]
    assert drops[0]["new"] is False and drops[0]["shards"] == M.resonance["duplicateRefund"]["normal"]
    assert drops[1]["item"] == CARD and drops[1]["holo"] is True and drops[1]["new"] is True
    assert g.store.owned(pid)[HOLO] == 1


def test_a_batch_moves_on_to_the_next_missing_holo_version():
    other = next(card for card in M.holos if card != CARD)
    lacking = (HOLO, M.holos[other])
    # A quarter into the card group: the first of the two cards, then the only one left.
    pick = card_roll(.25)
    g, pid, version, pool = whole_save(COMMON, pick, 0, COMMON, pick, 0, lacking=lacking)
    order = [i["id"] for i in pool["common"] if i["id"] in (CARD, other)]
    drops = g.resonate(TOKEN, 2, version)["drops"]
    assert [(d["item"], d.get("holo"), d["new"]) for d in drops] == [(order[0], True, True), (order[1], True, True)]
    owned = g.store.owned(pid)
    assert all(owned[h] == 1 for h in lacking)


def test_a_save_owning_every_holo_version_draws_as_before():
    g, _, version, pool = whole_save(COMMON, PICK, .99, lacking=())
    drop = g.resonate(TOKEN, 1, version)["drops"][0]
    assert drop["item"] == picked_from_all(pool) and drop["new"] is False


@pytest.mark.parametrize("chance", [0, None])
def test_without_a_holo_chance_a_missing_holo_version_changes_nothing(chance):
    g, pid, version, pool = whole_save(COMMON, PICK, chance=chance)
    drop = g.resonate(TOKEN, 1, version)["drops"][0]
    assert drop["item"] == picked_from_all(pool) and "holo" not in drop
    assert HOLO not in g.store.owned(pid)


def test_a_client_that_cannot_show_the_holo_version_draws_as_before():
    g, _, _, _ = whole_save(COMMON, PICK, .99)
    drop = g.resonate(TOKEN, 1, "1.2.3")["drops"][0]
    assert drop["item"] == picked_from_all(g.manifest.resonance_pool_for("1.2.3", g.now())) and "holo" not in drop


def test_a_tier_with_a_missing_holo_version_stays_in_the_roll():
    # A limited-tier card (a tier that rolls no repeats) given a holo version: once the whole pool is owned, its tier
    # keeps its odds while the holo is missing, and its draws go to that card first.
    c = next(c for c in M.data["cards"] if c["rarity"] == "limited")
    card, holo = f"card:{c['id']}", f"holo:{c['id']}"
    rates = M.resonance["rates"]
    assert "limited" not in M.resonance.get("repeatTiers", ())
    edge = sum(rates[r] for r in ("legendary", "skin", "epic", "rare", "uncommon"))
    in_tier = (edge + rates["limited"] / 2) / 100
    g, pid, version, _ = whole_save(in_tier, .99, 0, lacking=(holo,), holos={card: holo})
    drop = g.resonate(TOKEN, 1, version)["drops"][0]
    assert drop["rarity"] == "limited" and drop["item"] == card and drop["holo"] is True and drop["new"] is True
    assert g.store.owned(pid)[holo] == 1
    # with that holo version owned the tier drops out and its odds go to common
    g, _, version, _ = whole_save(in_tier, .99, 0, lacking=(), holos={card: holo})
    assert g.resonate(TOKEN, 1, version)["drops"][0]["rarity"] == "common"


def test_a_limited_pool_draw_finds_the_missing_holo_version_too():
    # The tier roll stays under the featured range at the top of the roll.
    g, pid, version, pool = whole_save(COMMON, PICK, 0, banner={})
    assert picked_from_all(pool) != CARD
    r = g.resonate(TOKEN, 1, version, "forms")
    drop = r["drops"][0]
    assert drop["item"] == CARD and drop["holo"] is True and drop["new"] is True and "featured" not in drop
    assert g.store.owned(pid)[HOLO] == 1


def test_a_limited_pool_without_common_odds_still_deals_the_missing_holo_version():
    # Every tier but the limited one at 0, so common has no odds of its own: once the limited cards are all owned,
    # their odds go to common, which still holds CARD's missing holo version.
    limited = [i["id"] for i in M.resonance_pool["limited"]][:2]
    rates = {**{tier: 0 for tier in ("legendary", "skin", "epic", "rare", "uncommon")}, "limited": 100}
    over = {"items": limited, "rate": 0, "pity": None, "share": 50, "rates": rates}
    g, pid, version, _ = whole_save(COMMON, PICK, 0, banner=over)
    assert g.manifest.banner("forms", version, g.now()).tier_rates(M.resonance["rates"])["common"] == 0
    drop = g.resonate(TOKEN, 1, version, "forms")["drops"][0]
    assert drop["rarity"] == "common" and drop["item"] == CARD and drop["holo"] is True and drop["new"] is True
    assert g.store.owned(pid)[HOLO] == 1


def test_a_shared_tier_with_a_missing_holo_version_keeps_the_banner_share():
    # A banner sharing the common tier with a featured card the save lacks. Its standing common cards are all owned
    # but CARD's holo version is missing, so a common draw is featured at `share` percent, not for certain.
    plain = next(f"card:{c['id']}" for c in M.data["cards"] if c["rarity"] == "common" and not c.get("holo")
                 and f"card:{c['id']}" not in M.starter)
    over = {"items": [plain], "rate": 0, "pity": None, "share": 50}
    # common, the share roll (over 50: a standing card), the pick, the holo roll; then common, now featured for
    # certain (the last common draw here gave a standing card), and the pick among the featured.
    g, pid, version, _ = whole_save(COMMON, .99, PICK, 0, COMMON, 0, banner=over, featured=False)
    first = g.resonate(TOKEN, 1, version, "forms")
    drop = first["drops"][0]
    assert drop["item"] == CARD and drop["holo"] is True and "featured" not in drop
    assert first["resonance"]["banners"]["forms"]["guaranteed"] == ["common"]
    drop = g.resonate(TOKEN, 1, version, "forms")["drops"][0]
    assert drop["item"] == plain and drop["featured"] is True
