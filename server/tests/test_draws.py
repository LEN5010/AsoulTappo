import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from app import economy
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
    assert r["income"] == {"day": day_of(clock.t), "today": 0, "cap": 18000, "taps": 0, "perTap": 1.603, "multiplier": 1, "perMinute": 96.2}
    # the pool, the holo versions and the scratch emotes
    assert r["totals"]["items"] == sum(map(len, g.manifest.resonance_pool.values())) + len(g.manifest.holos) + 20


def test_taps_pay_along_the_log_curve():
    g, clock = game()
    clock.t += 20
    r = g.report_activity(TOKEN, 100)
    # 18000 * (1 - e^-x) at 100 taps = 159.1
    assert r["shards"] == 1759
    assert r["income"] == {"day": day_of(clock.t), "today": 159, "cap": 18000, "taps": 100, "perTap": 1.579, "multiplier": 1, "perMinute": 94.7}


def test_the_curve_meets_its_marks_and_nears_the_cap():
    g, _ = game()
    assert [round(g._tap_shards(n)) for n in (10000, 20000, 30000)] == [9000, 13000, 16000]
    rates = [g._tap_rate(n) for n in range(0, 60000, 100)]
    assert all(a >= b for a, b in zip(rates, rates[1:])) and rates[0] < 1.61
    assert g._tap_shards(10**7) <= 18000 and g.tap_full_shards == 17971


def test_a_minute_pays_for_its_first_taps_only():
    g, clock = game()
    clock.t += 20
    r = g.report_activity(TOKEN, 200)
    # Only 120 of the 200 pay: 190.6.
    assert r["totals"]["taps"] == 200 and r["income"]["taps"] == 120 and r["shards"] == 1790
    r = g.report_activity(TOKEN, 0)
    clock.t += 60
    r = g.report_activity(TOKEN, 100)
    # A new minute: 220 paid taps, 346.9, the fraction carried between reports.
    assert r["income"]["taps"] == 220 and r["shards"] == 1946


def test_the_day_stops_at_the_cap_and_starts_over_the_next_day():
    g, clock = game()
    pid = player_id_for(TOKEN)
    g.store.update_player(pid, tap_day=day_of(clock.t), day_taps=60000)
    clock.t += 20
    r = g.report_activity(TOKEN, 100)
    assert r["shards"] == 1600
    # Past about 49 200 taps a tap pays under 0.01: the day counts as full, shards stay just under the cap.
    assert r["income"]["today"] == 17999 and r["income"]["perTap"] == 0 and r["income"]["perMinute"] == 0
    clock.t += 86400
    r = g.report_activity(TOKEN, 100)
    assert r["shards"] == 1759 and r["income"]["taps"] == 100


def test_fractional_shards_do_not_depend_on_batch_size():
    split, split_clock = game()
    whole, whole_clock = game()
    whole_clock.t += 20
    expected = whole.report_activity(TOKEN, 100)["shards"]
    for _ in range(100):
        split_clock.t += 0.5
        r = split.report_activity(TOKEN, 1)
    assert r["shards"] == expected == 1759


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


def test_skins_of_a_later_release_stay_out_of_older_clients_pools():
    M = Manifest.load()
    later = set(M.skin_since)
    winter = {"char:嘉然冬日奇迹", "char:乃琳冬日奇迹", "char:贝拉冬日奇迹"}
    birthday = {"char:心宜2025生日", "char:思诺2025生日"}
    forms = {"char:嘉然然龙", "char:乃琳法师", "char:贝拉炎头队长"}
    heart = {"char:心宜2026生日"}
    assert later == winter | birthday | forms | heart
    skins = lambda version: {i["id"] for i in M.resonance_pool_for(version)["skin"]}
    every = {i["id"] for i in M.resonance_pool["skin"]}
    for version in (None, "1.3.0", "v1.3.0", "1.3.0-rc.1"):
        assert skins(version) == every
    for version in ("1.2.5", "v1.2.5", "1.2.5-rc.1", "1.2.6"):
        assert skins(version) == every - heart
    for version in ("1.2.2", "v1.2.4", "1.2.4-rc.1"):
        assert skins(version) == every - forms - heart
    for version in ("1.2.0", "v1.2.1", "1.2.0-rc.3"):
        assert skins(version) == every - birthday - forms - heart
    for version in ("1.1.4", "1.2.0" + "x", ""):
        assert skins(version) == every - later
    # Besides skins only the wardrobe cards (the limited tier) and the 45 live-room emotes (uncommon) are held back.
    every = {r: len(v) for r, v in M.resonance_pool.items() if r not in ("skin", "limited")}
    assert {r: len(v) for r, v in M.resonance_pool_for("1.1.4").items() if r not in ("skin", "limited")} == \
        {**every, "uncommon": every["uncommon"] - 45}


def test_wardrobe_cards_stay_out_of_clients_older_than_1_2_4():
    M = Manifest.load()
    wardrobe = {f"card:{c['id']}" for c in M.data["cards"] if c["rarity"] == "limited"}
    assert {i["id"] for i in M.resonance_pool["limited"]} == wardrobe and len(wardrobe) == 36
    for version in (None, "1.2.4", "1.2.4-rc.2", "v1.3.0"):
        assert {i["id"] for i in M.resonance_pool_for(version)["limited"]} == wardrobe
    for version in ("1.2.3", "1.2.3-rc.1", "1.2.2", ""):
        assert M.resonance_pool_for(version)["limited"] == []


def test_live_room_emotes_stay_out_of_clients_older_than_1_3_0():
    M = Manifest.load()
    live = {f"emote:{e['key']}" for s in M.data["emoteSets"] if s.get("since") for e in s["emotes"]}
    every = {i["id"] for i in M.resonance_pool["uncommon"]}
    assert len(live) == 45 and live <= every
    uncommon = lambda version: {i["id"] for i in M.resonance_pool_for(version)["uncommon"]}
    for version in (None, "1.3.0", "1.3.0-rc.1", "v1.3.1"):
        assert uncommon(version) == every and not live & M.held_for(version)
    for version in ("1.2.6", "1.2.6-rc.4", "1.2.4", ""):
        assert uncommon(version) == every - live and live <= M.held_for(version)


def test_an_older_client_never_draws_a_live_room_emote():
    def draw(version):
        # The uncommon range, with every uncommon emote a 1.2.6 client can show owned.
        g, _ = game(SeqRng(.137, .5))
        pid = player_id_for(TOKEN)
        for item in g.manifest.resonance_pool_for("1.2.6")["uncommon"]:
            g.store.add_item(pid, item["id"], 0)
        return g.resonate(TOKEN, 1, version)["drops"][0]

    # Nothing is left to find there for 1.2.6: the range lands on common.
    assert draw("1.2.6")["rarity"] == "common"
    drop = draw("1.3.0")
    assert drop["rarity"] == "uncommon" and drop["new"]
    assert drop["item"].split(":")[1].split(".")[0] in ("jiaran-live", "nailin-live", "beila-live")


def test_the_limited_tier_sits_just_above_common():
    # Example rates: the five tiers above take 13.8 of 100, the limited tier the next 2.
    g, _ = game(SeqRng(.139, .5))
    drop = g.resonate(TOKEN, 1, "1.2.4")["drops"][0]
    assert drop["rarity"] == "limited" and drop["new"] and drop["item"].startswith("card:c")
    g, _ = game(SeqRng(.137, .5))
    assert g.resonate(TOKEN, 1, "1.2.4")["drops"][0]["rarity"] == "uncommon"
    g, _ = game(SeqRng(.159, .5))
    assert g.resonate(TOKEN, 1, "1.2.4")["drops"][0]["rarity"] == "common"


def test_an_older_client_rolling_the_limited_range_gets_common():
    g, _ = game(SeqRng(.139, .5))
    assert g.resonate(TOKEN, 1, "1.2.3")["drops"][0]["rarity"] == "common"


def test_the_limited_tier_gives_missing_cards_and_closes_once_all_are_owned():
    g, _ = game(SeqRng(.139, .5))
    pid = player_id_for(TOKEN)
    cards = [i["id"] for i in g.manifest.resonance_pool["limited"]]
    for item in cards[:-1]:
        g.store.add_item(pid, item, 0)
    g.store.update_player(pid, shards=160 * 2)
    drop = g.resonate(TOKEN, 1, "1.2.4")["drops"][0]
    assert drop == {**drop, "item": cards[-1], "rarity": "limited", "new": True, "shards": 0}
    # All 36 owned: the limited range lands on common, never a repeat.
    assert g.resonate(TOKEN, 1, "1.2.4")["drops"][0]["rarity"] == "common"


def test_wardrobe_cards_cannot_be_crafted():
    g, _ = game()
    item = next(i["id"] for i in g.manifest.resonance_pool["limited"])
    g.store.update_player(player_id_for(TOKEN), shards=100_000)
    with pytest.raises(GameError) as e:
        g.craft(TOKEN, item)
    assert e.value.code == "bad_item"


def test_a_tier_the_economy_has_no_rate_for_stays_out_of_the_pool(tmp_path):
    raw = json.loads(economy.EXAMPLE.read_text(encoding="utf-8"))
    rates = raw["resonance"]["rates"]
    rates["common"] += rates.pop("limited")
    path = tmp_path / "economy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    m = Manifest.load(economy=path)
    assert "limited" not in m.resonance_pool
    g = Game(Store(":memory:"), m, rng=SeqRng(.139, .5), now=Clock())
    g.status(TOKEN)
    assert g.resonate(TOKEN, 1, "1.2.4")["drops"][0]["rarity"] == "common"


def test_an_older_client_on_skin_pity_gets_a_skin_it_can_show():
    g, _ = game(SeqRng(.5, .99))
    pid = player_id_for(TOKEN)
    g.store.update_player(pid, skin_pity=199)
    drop = g.resonate(TOKEN, 1, "1.1.4")["drops"][0]
    assert drop["rarity"] == "skin" and drop["item"] not in g.manifest.skin_since
    # Once the older skins are all owned the skin tier is closed to that client and its odds go to common.
    for item in g.manifest.resonance_pool["skin"]:
        if item["id"] not in g.manifest.skin_since:
            g.store.add_item(pid, item["id"], 0)
    g.store.update_player(pid, skin_pity=199)
    assert g.resonate(TOKEN, 1, "1.1.4")["drops"][0]["rarity"] == "common"
    g.store.update_player(pid, skin_pity=199)
    assert g.resonate(TOKEN, 1, "1.2.0-rc.3")["drops"][0]["item"] in g.manifest.skin_since


@pytest.mark.parametrize("rarity,roll", [("legendary", 0), ("skin", .002), ("rare", .055), ("uncommon", .085)])
def test_completed_high_tier_rolls_into_common(rarity, roll):
    g, _ = game(SeqRng(roll, .5))
    for item in g.manifest.resonance_pool[rarity]:
        g.store.add_item(player_id_for(TOKEN), item["id"], 0)
    assert g.resonate(TOKEN)["drops"][0]["rarity"] == "common"


@pytest.mark.parametrize("kind,roll", [("card", 0), ("emote", .9999)])
def test_common_prefers_unowned_within_kind_then_refunds_duplicates(kind, roll):
    # The repeat of a card lands on the first card, which has a holo version: the last roll keeps it plain.
    g, _ = game(SeqRng(.5, roll, .5, roll, .99))
    pid = player_id_for(TOKEN)
    pool = [item for item in g.manifest.resonance_pool["common"] if item["kind"] == kind]
    # The one left to find has no holo version, which would take a roll of its own.
    last = [item for item in pool if item["id"] not in g.manifest.holos][-1]
    pool = [item for item in pool if item is not last] + [last]
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


@pytest.mark.parametrize("tier,has_dance_refund,shards", [("small", True, 360), ("normal", True, 360),
                                                         ("normal", False, 20)])
def test_the_epic_tier_keeps_rolling_once_complete_and_repeats_pay_by_kind(tier, has_dance_refund, shards):
    g, _ = game(SeqRng(.01, .0))
    if not has_dance_refund:
        g.manifest.resonance["duplicateRefund"].pop("dance")
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
