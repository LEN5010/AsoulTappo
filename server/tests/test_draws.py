from concurrent.futures import ThreadPoolExecutor

import pytest
from app.game import Game, GameError, player_id_for
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock, SeqRng

TOKEN = "draw-player-token-0001"
SESSION = "running-session-0001"


def game(rng=None, path=":memory:"):
    clock = Clock()
    g = Game(Store(str(path)), Manifest.load(), rng=rng or SeqRng(.5), now=clock)
    g.status(TOKEN)
    return g, clock


def test_new_player_and_idle_income():
    g, clock = game()
    assert g.status(TOKEN)["shards"] == 1600
    g.presence(TOKEN, SESSION)
    for _ in range(3):
        clock.t += 20
        r = g.presence(TOKEN, SESSION)
    assert r["shards"] == 1616 and r["income"] == {"multiplier": 1, "perMinute": 16}
    assert r["totals"]["items"] == 428


@pytest.mark.parametrize("taps,multiplier,rate", [(0, 1, 16), (30, 3, 48), (60, 5, 80), (120, 5, 80)])
def test_previous_minute_income(taps, multiplier, rate):
    g, clock = game()
    clock.t += 20
    g.report_activity(TOKEN, taps)
    clock.t += 40
    assert g.status(TOKEN)["income"] == {"multiplier": multiplier, "perMinute": rate}
    g.presence(TOKEN, SESSION)
    clock.t += 20
    # Repeated reports keep the previous-minute sample available.
    g.report_activity(TOKEN, taps)
    for _ in range(2):
        g.presence(TOKEN, SESSION)
        clock.t += 20
    assert g.presence(TOKEN, SESSION)["shards"] == 1600 + rate
    clock.t += 120
    assert g.status(TOKEN)["income"] == {"multiplier": 1, "perMinute": 16}


def test_fractional_shards_accumulate():
    g, clock = game()
    g.presence(TOKEN, SESSION)
    for _ in range(60):
        clock.t += 1
        g.presence(TOKEN, SESSION)
    assert g.status(TOKEN)["shards"] == 1616
    assert g.store.get_player(player_id_for(TOKEN), clock.t)["shard_remainder"] == pytest.approx(0)


def test_heartbeats_overlap_once_and_pause_resumes_from_new_baseline():
    g, clock = game()
    g.presence(TOKEN, SESSION)
    clock.t += 10
    g.presence(TOKEN, "second-session-0001")
    clock.t += 10
    g.presence(TOKEN, SESSION)
    g.presence(TOKEN, "second-session-0001")
    assert g.status(TOKEN)["shards"] == 1605
    clock.t += 3600
    assert g.presence(TOKEN, SESSION)["shards"] == 1605
    clock.t += 40
    assert g.presence(TOKEN, SESSION)["shards"] == 1616


def test_simultaneous_pities_then_independent_resets():
    g, _ = game()
    g.store.update_player(player_id_for(TOKEN), draw_pity=399, skin_pity=199)
    r = g.resonate(TOKEN)
    assert r["drops"][0]["rarity"] == "legendary"
    assert r["resonance"]["pity"] == {"legendary": 0, "skin": 200}
    r = g.resonate(TOKEN)
    assert r["drops"][0]["rarity"] == "skin"
    assert r["resonance"]["pity"] == {"legendary": 1, "skin": 0}


@pytest.mark.parametrize("roll,tier,counters", [(0, "legendary", {"legendary": 0, "skin": 88}), (.005, "skin", {"legendary": 213, "skin": 0})])
def test_natural_roll_resets_only_its_own_counter(roll, tier, counters):
    g, _ = game(SeqRng(roll, .5))
    g.store.update_player(player_id_for(TOKEN), draw_pity=212, skin_pity=87)
    r = g.resonate(TOKEN)
    assert r["drops"][0]["rarity"] == tier and r["resonance"]["pity"] == counters


def test_full_pity_is_preserved_when_tier_is_complete_until_new_content():
    g, _ = game()
    pid = player_id_for(TOKEN)
    for rarity in ("legendary", "skin"):
        for item in g.manifest.resonance_pool[rarity]:
            g.store.add_item(pid, item["id"], 0)
    g.store.update_player(pid, draw_pity=400, skin_pity=200)
    r = g.resonate(TOKEN)
    assert r["drops"][0]["rarity"] == "common"
    assert r["resonance"]["pity"] == {"legendary": 401, "skin": 201}
    # A newly released skin makes the stored counter eligible again.
    g.manifest.data["skins"].append({"name": "心宜新皮肤", "member": "心宜"})
    g.manifest = Manifest(g.manifest.data)
    assert g.resonate(TOKEN)["drops"][0]["item"] == "char:心宜新皮肤"


@pytest.mark.parametrize("rarity,roll", [("legendary", 0), ("skin", .005), ("epic", .01), ("rare", .055)])
def test_completed_high_tier_rolls_into_common(rarity, roll):
    g, _ = game(SeqRng(roll, .5))
    for item in g.manifest.resonance_pool[rarity]:
        g.store.add_item(player_id_for(TOKEN), item["id"], 0)
    assert g.resonate(TOKEN)["drops"][0]["rarity"] == "common"


def test_common_prefers_unowned_then_refunds_duplicates():
    g, _ = game()
    pid = player_id_for(TOKEN)
    pool = g.manifest.resonance_pool["common"]
    for item in pool[:-1]:
        g.store.add_item(pid, item["id"], 0)
    r = g.resonate(TOKEN, 2)
    assert r["drops"][0]["item"] == pool[-1]["id"]
    assert [d["new"] for d in r["drops"]] == [True, False]
    assert [d["shards"] for d in r["drops"]] == [0, 40]
    assert r["shards"] == 1320


def test_shared_card_has_one_pool_entry_and_one_ownership_record():
    g, _ = game(SeqRng(.01, .9999))
    pid = player_id_for(TOKEN)
    shared = next(c for c in g.manifest.cards.values() if c["name"] == "魔女契约")
    iid = f"card:{shared['id']}"
    assert sum(item["id"] == iid for item in g.manifest.resonance_pool["epic"]) == 1
    for item in g.manifest.resonance_pool["epic"]:
        if item["id"] != iid:
            g.store.add_item(pid, item["id"], 0)
    assert g.resonate(TOKEN)["drops"][0]["item"] == iid
    assert g.resonate(TOKEN)["drops"][0]["rarity"] == "common"
    assert g.collection(TOKEN)["owned"][iid] == 1


def test_count_is_capped_by_balance_and_batch_size():
    g, _ = game()
    assert len(g.resonate(TOKEN, 999)["drops"]) == 10
    with pytest.raises(GameError) as e:
        g.resonate(TOKEN)
    assert e.value.code == "no_shards"
    g.store.update_player(player_id_for(TOKEN), shards=100000)
    assert len(g.resonate(TOKEN, 999)["drops"]) == 100


def test_concurrent_draws_spend_balance_once():
    g, _ = game()
    def draw(_):
        try:
            return len(g.resonate(TOKEN, 100)["drops"])
        except GameError as e:
            assert e.code == "no_shards"
            return 0
    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(draw, range(4))) == 10
    assert g.status(TOKEN)["shards"] == 0


def test_resonance_transaction_rolls_back(monkeypatch):
    g, _ = game()
    original = g.store.log_drop
    def fail(*args):
        original(*args)
        raise RuntimeError("interrupted")
    monkeypatch.setattr(g.store, "log_drop", fail)
    with pytest.raises(RuntimeError):
        g.resonate(TOKEN)
    assert g.status(TOKEN)["shards"] == 1600
    assert g.collection(TOKEN) == {"owned": {}, "recent": []}
