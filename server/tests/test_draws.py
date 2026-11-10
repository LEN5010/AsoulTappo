from concurrent.futures import ThreadPoolExecutor

import pytest
from app.game import Game, GameError, day_of, player_id_for
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


def test_new_player_and_online_time_pays_nothing():
    g, clock = game()
    assert g.status(TOKEN)["shards"] == 1600
    for _ in range(4):
        r = g.presence(TOKEN, SESSION)
        clock.t += 20
    assert r["shards"] == 1600
    assert r["income"] == {"day": day_of(clock.t), "today": 0, "cap": 10400, "taps": 0, "perTap": 2.8, "multiplier": 1, "perMinute": 168.0}
    # 549 from resonance and the 20 scratch emotes
    assert r["totals"]["items"] == 569


def test_taps_pay_along_the_log_curve():
    g, clock = game()
    clock.t += 20
    r = g.report_activity(TOKEN, 100)
    # 2800 * ln(1 + 100 / 1000) = 266.9
    assert r["shards"] == 1866
    assert r["income"] == {"day": day_of(clock.t), "today": 266, "cap": 10400, "taps": 100, "perTap": 2.545, "multiplier": 1, "perMinute": 152.7}


def test_a_minute_pays_for_its_first_taps_only():
    g, clock = game()
    clock.t += 20
    r = g.report_activity(TOKEN, 200)
    # Only 120 of the 200 pay: 2800 * ln(1.12) = 317.3.
    assert r["totals"]["taps"] == 200 and r["income"]["taps"] == 120 and r["shards"] == 1917
    r = g.report_activity(TOKEN, 0)
    clock.t += 60
    r = g.report_activity(TOKEN, 100)
    # A new minute: 220 paid taps, 2800 * ln(1.22) = 556.8, the fraction carried between reports.
    assert r["income"]["taps"] == 220 and r["shards"] == 2156


def test_the_day_stops_at_the_cap_and_starts_over_the_next_day():
    g, clock = game()
    pid = player_id_for(TOKEN)
    g.store.update_player(pid, tap_day=day_of(clock.t), day_taps=42200)
    clock.t += 20
    r = g.report_activity(TOKEN, 100)
    assert r["shards"] == 1600
    assert r["income"]["today"] == 10400 and r["income"]["perTap"] == 0 and r["income"]["perMinute"] == 0
    clock.t += 86400
    r = g.report_activity(TOKEN, 100)
    assert r["shards"] == 1866 and r["income"]["taps"] == 100


def test_fractional_shards_do_not_depend_on_batch_size():
    split, split_clock = game()
    whole, whole_clock = game()
    whole_clock.t += 20
    expected = whole.report_activity(TOKEN, 100)["shards"]
    for _ in range(100):
        split_clock.t += 0.5
        r = split.report_activity(TOKEN, 1)
    assert r["shards"] == expected == 1866


def test_simultaneous_pities_then_independent_resets():
    g, _ = game()
    g.store.update_player(player_id_for(TOKEN), draw_pity=399, skin_pity=199)
    r = g.resonate(TOKEN)
    assert r["drops"][0]["rarity"] == "legendary"
    assert r["resonance"]["pity"] == {"legendary": 0, "skin": 200}
    r = g.resonate(TOKEN)
    assert r["drops"][0]["rarity"] == "skin"
    assert r["resonance"]["pity"] == {"legendary": 1, "skin": 0}


@pytest.mark.parametrize("roll,tier,counters", [(0, "legendary", {"legendary": 0, "skin": 88}), (.002, "skin", {"legendary": 213, "skin": 0})])
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


@pytest.mark.parametrize("rarity,roll", [("legendary", 0), ("skin", .002), ("rare", .055), ("uncommon", .085)])
def test_completed_high_tier_rolls_into_common(rarity, roll):
    g, _ = game(SeqRng(roll, .5))
    for item in g.manifest.resonance_pool[rarity]:
        g.store.add_item(player_id_for(TOKEN), item["id"], 0)
    assert g.resonate(TOKEN)["drops"][0]["rarity"] == "common"


@pytest.mark.parametrize("kind,roll", [("card", 0), ("emote", .9999)])
def test_common_prefers_unowned_within_kind_then_refunds_duplicates(kind, roll):
    g, _ = game(SeqRng(.5, roll, .5, roll))
    pid = player_id_for(TOKEN)
    pool = [item for item in g.manifest.resonance_pool["common"] if item["kind"] == kind]
    for item in pool[:-1]:
        g.store.add_item(pid, item["id"], 0)
    r = g.resonate(TOKEN, 2)
    assert r["drops"][0]["item"] == pool[-1]["id"]
    assert [d["new"] for d in r["drops"]] == [True, False]
    refund = 5 if kind == "emote" else 20
    assert [d["shards"] for d in r["drops"]] == [0, refund]
    assert r["shards"] == 1280 + refund
    assert all(d["item"].startswith(f"{kind}:") for d in r["drops"])
    # The repeat turned into shards and was not kept.
    assert r["drops"][1]["count"] == 1 and g.store.owned(pid)[pool[-1]["id"]] == 1


@pytest.mark.parametrize("tier,shards", [("small", 360), ("normal", 20)])
def test_the_hidden_tier_keeps_rolling_once_complete_and_repeats_pay_by_tier(tier, shards):
    g, _ = game(SeqRng(.01, .0))
    pid = player_id_for(TOKEN)
    epic = g.manifest.resonance_pool["epic"]
    for item in epic:
        g.store.add_item(pid, item["id"], 0)
    # Every repeat pick in the tier lands on its first item; put a card of the wanted tier there.
    first = next(i for i in epic if i["kind"] == "card" and g.manifest.cards[i["id"][5:]]["tier"] == tier)
    g.manifest.resonance_pool["epic"].remove(first)
    g.manifest.resonance_pool["epic"].insert(0, first)
    r = g.resonate(TOKEN)
    assert r["drops"][0]["rarity"] == "epic" and r["drops"][0]["item"] == first["id"]
    assert r["drops"][0]["shards"] == shards and r["shards"] == 1600 - 160 + shards
    assert g.store.owned(pid)[first["id"]] == 1


def test_repeats_kept_before_1_1_pay_out_once():
    g, _ = game()
    pid = player_id_for(TOKEN)
    cards = {g.manifest.cards[c]["tier"]: f"card:{c}" for c in g.manifest.cards}
    g.store.add_items(pid, {cards["normal"]: 4, cards["small"]: 2, cards["big"]: 2, "emote:" + "x": 3}, 0)
    assert g.refund_duplicate_cards() == (1, 3 * 20 + 1 * 360)
    owned = g.store.owned(pid)
    assert owned[cards["normal"]] == owned[cards["small"]] == 1 and owned["emote:x"] == 3
    # A big hidden card has no exchange value, so its copies stay.
    assert owned[cards["big"]] == 2
    assert g.status(TOKEN)["shards"] == 1600 + 420
    assert g.refund_duplicate_cards() == (0, 0)
    assert g.status(TOKEN)["shards"] == 1600 + 420


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
    original = g.store.log_drops
    def fail(*args):
        original(*args)
        raise RuntimeError("interrupted")
    monkeypatch.setattr(g.store, "log_drops", fail)
    with pytest.raises(RuntimeError):
        g.resonate(TOKEN)
    assert g.status(TOKEN)["shards"] == 1600
    assert g.collection(TOKEN) == {"owned": {}, "recent": []}
