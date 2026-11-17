"""Holo versions (镭射款): resonance turns a draw of one of their cards into them at the economy's holoChance."""
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
    g, pid = game(100, COMMON, 0, 0, owned=[CARD])
    r = g.resonate(TOKEN, 1, NEW)
    drop = r["drops"][0]
    assert drop["holo"] is True and drop["new"] is True and drop["cardNew"] is False and drop["shards"] == 0
    assert r["shards"] == 1600 - 160
    # the card is not kept twice
    owned = g.store.owned(pid)
    assert owned[CARD] == 1 and owned[HOLO] == 1


def test_a_repeat_holo_version_pays_the_holo_refund():
    g, pid = game(100, COMMON, 0, 0, owned=[CARD, HOLO])
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
    g, _ = game(25, COMMON, 0, roll, owned=[CARD, HOLO])
    if not holo_configured:
        g.manifest.resonance["duplicateRefund"].pop("holo")
    drop = g.resonate(TOKEN, 1, NEW)["drops"][0]
    assert drop.get("holo", False) is holo
    assert drop["shards"] == M.resonance["duplicateRefund"]["normal"]


def test_the_second_holo_version_in_one_batch_is_a_repeat():
    g, pid = game(100, COMMON, 0, 0, COMMON, 0, 0)
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
