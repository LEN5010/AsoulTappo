import pytest

from app.cards import DropConfig
from app.game import Game, GameError, player_id_for
from app.store import Store

from fixtures import Clock, SeqRng, tiny_manifest

TOKEN = "t" * 32


def make(cfg=None, rng=None, clock=None, elapsed=10):
    clock = clock or Clock()
    g = Game(Store(":memory:"), tiny_manifest(), cfg, rng or SeqRng(0.0), clock)
    g.status(TOKEN)
    clock.t += elapsed
    return g, clock


def test_token_validation_and_player_id():
    with pytest.raises(GameError):
        player_id_for("short")
    assert player_id_for(TOKEN) == player_id_for(TOKEN) != player_id_for("u" * 32)
    assert TOKEN not in player_id_for(TOKEN)


def test_taps_progress_and_box_award():
    g, clock = make(DropConfig(taps_per_box=100, minutes_per_box=1000))
    st = g.report_activity(TOKEN, 60)
    assert st["boxes"] == 0 and st["progress"]["taps"] == 60
    clock.t += 10
    st = g.report_activity(TOKEN, 60)
    assert st["boxes"] == 1 and st["newBoxes"] == 1 and st["progress"]["taps"] == 20


def test_rate_limit_clips_credit():
    g, clock = make(DropConfig(max_taps_per_sec=10, taps_per_box=100), elapsed=0)
    g.report_activity(TOKEN, 0)
    clock.t += 2
    st = g.report_activity(TOKEN, 5000)  # only ~20 taps are plausible in 2s
    assert st["credited"] == 20 and st["totals"]["taps"] == 20


def test_active_minute_counts_once_per_minute_and_awards_box():
    g, clock = make(DropConfig(taps_per_box=10**6, minutes_per_box=2, min_taps_active_minute=10), clock=Clock(59990))
    clock.t = 60 * 1000.0
    g.report_activity(TOKEN, 4)         # below threshold: not active yet
    clock.t += 5
    st = g.report_activity(TOKEN, 8)    # 12 taps this minute -> active
    assert st["totals"]["activeMinutes"] == 1
    clock.t += 5
    st = g.report_activity(TOKEN, 8)    # same minute: no double count
    assert st["totals"]["activeMinutes"] == 1 and st["boxes"] == 0
    clock.t = 60 * 1001.0
    st = g.report_activity(TOKEN, 12)   # next minute: 2nd active minute -> box
    assert st["totals"]["activeMinutes"] == 2 and st["boxes"] == 1


def test_daily_and_inventory_caps():
    g, clock = make(DropConfig(taps_per_box=10, daily_box_cap=3, inventory_cap=2, max_taps_per_sec=1000))
    st = g.report_activity(TOKEN, 1000)
    assert st["boxes"] == 2 and st["boxesToday"] == 2          # inventory cap 2
    g.open_boxes(TOKEN)
    st = g.report_activity(TOKEN, 1000)
    assert st["boxesToday"] == 3 and st["boxes"] == 2          # daily cap 3 (only one more granted)
    clock.t += 86400
    st = g.report_activity(TOKEN, 0)
    assert st["boxesToday"] == 0                               # new UTC day


def test_open_box_requires_box_and_stores_collection():
    g, _ = make(DropConfig(taps_per_box=10, max_taps_per_sec=1000), SeqRng(0.0))
    with pytest.raises(GameError) as e:
        g.open_boxes(TOKEN)
    assert e.value.code == "no_box"
    g.report_activity(TOKEN, 30)
    r = g.open_boxes(TOKEN)
    assert r["drops"] == [{"item": "emote:e.02", "rarity": "common", "new": True, "count": 1, "shards": 0}]
    assert r["boxes"] == 2
    col = g.collection(TOKEN)
    assert col["owned"] == {"emote:e.02": 1} and col["recent"][0]["item"] == "emote:e.02"
    assert g.status(TOKEN)["totals"]["opened"] == 1


def test_open_several_boxes_and_duplicates_give_shards():
    g, _ = make(DropConfig(taps_per_box=10, max_taps_per_sec=1000, max_open_batch=10), SeqRng(0.0))
    g.report_activity(TOKEN, 30)
    r = g.open_boxes(TOKEN, 5)   # only 3 boxes; rng 0.0 always picks card:c1
    assert [d["new"] for d in r["drops"]] == [True, False, False]
    assert [d["shards"] for d in r["drops"]] == [0, 1, 1] and [d["count"] for d in r["drops"]] == [1, 2, 3]
    assert r["boxes"] == 0 and r["shards"] == 2 and r["totals"]["opened"] == 3
    assert r["totals"] == {**r["totals"], "owned": 1, "items": 8}


def test_craft_spends_shards_on_missing_emotes_only():
    g, _ = make()
    g.store.update_player(player_id_for(TOKEN), shards=15)
    r = g.craft(TOKEN, "emote:e.02")
    assert r["item"] == "emote:e.02" and r["shards"] == 5
    for item, code in (("emote:e.02", "owned"), ("emote:e.03", "no_shards"),
                       ("emote:e.01", "bad_item"), ("card:c1", "bad_item"), ("acc:hat", "bad_item")):
        with pytest.raises(GameError) as e:
            g.craft(TOKEN, item)
        assert e.value.code == code


def test_loadout_validates_favorites_and_ignores_retired_equipment():
    g, _ = make()
    assert g.get_loadout(TOKEN) == {"character": None, "favorites": []}
    lo = g.set_loadout(TOKEN, {"character": "嘉然", "favorites": ["e.01", "thumbup", "e.01"], "head": "hat"})
    assert lo == {"character": "嘉然", "favorites": ["e.01", "thumbup"]}
    for patch, code in (({"favorites": ["e.02"]}, "locked"), ({"character": "路人"}, "bad_item")):
        with pytest.raises(GameError) as e:
            g.set_loadout(TOKEN, patch)
        assert e.value.code == code


def test_room_profile_and_emote_ownership():
    g, _ = make()
    a = g.profile_for(TOKEN, "r1")
    assert a["uid"] == g.profile_for(TOKEN, "r1")["uid"] != g.profile_for(TOKEN, "r2")["uid"]
    assert g.profile_for(None, "r1") == g.profile_for("bad", "r1") == {"uid": None}
    assert g.owns_emote(None, "e.01") and g.owns_emote(None, "thumbup")
    assert not g.owns_emote(TOKEN, "heart") and not g.owns_emote(TOKEN, "e.02")
    g.store.add_item(player_id_for(TOKEN), "emote:e.02", 0)
    assert g.owns_emote(TOKEN, "e.02")


def test_pity_counters_persist_and_reset():
    g, _ = make(DropConfig(taps_per_box=10, max_taps_per_sec=10**5), SeqRng(0.0))
    g.report_activity(TOKEN, 100)
    for _ in range(3):
        g.open_boxes(TOKEN)
    assert g.status(TOKEN)["pity"] == {"epic": 3, "legendary": 3}


def test_players_are_isolated():
    g, _ = make(DropConfig(taps_per_box=10, max_taps_per_sec=1000))
    g.report_activity(TOKEN, 50)
    other = "o" * 32
    assert g.status(other)["boxes"] == 0 and g.collection(other)["owned"] == {}
