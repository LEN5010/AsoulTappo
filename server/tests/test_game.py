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
    assert r["drops"] == [{"item": "card:c1", "rarity": "common", "new": True, "count": 1, "shards": 0}]
    assert r["boxes"] == 2
    col = g.collection(TOKEN)
    assert col["owned"] == {"card:c1": 1} and col["recent"][0]["item"] == "card:c1"
    assert g.status(TOKEN)["totals"]["opened"] == 1


def test_open_several_boxes_and_duplicates_give_shards():
    g, _ = make(DropConfig(taps_per_box=10, max_taps_per_sec=1000, max_open_batch=10), SeqRng(0.0))
    g.report_activity(TOKEN, 30)
    r = g.open_boxes(TOKEN, 5)   # only 3 boxes; rng 0.0 always picks card:c1
    assert [d["new"] for d in r["drops"]] == [True, False, False]
    assert [d["shards"] for d in r["drops"]] == [0, 1, 1] and [d["count"] for d in r["drops"]] == [1, 2, 3]
    assert r["boxes"] == 0 and r["shards"] == 2 and r["totals"]["opened"] == 3
    assert r["totals"] == {**r["totals"], "owned": 1, "items": 10}


def test_craft_spends_shards_on_missing_items():
    g, _ = make()
    g.store.update_player(player_id_for(TOKEN), shards=50)
    r = g.craft(TOKEN, "card:c3")                  # rare costs 30
    assert r["item"] == "card:c3" and r["shards"] == 20
    assert g.collection(TOKEN)["owned"] == {"card:c3": 1}
    for item, code in (("card:c3", "owned"), ("card:c4", "no_shards"), ("emote:e.01", "bad_item"),
                       ("nope", "bad_item")):
        with pytest.raises(GameError) as e:
            g.craft(TOKEN, item)
        assert e.value.code == code
    assert g.status(TOKEN)["shards"] == 20


def test_loadout_validates_ownership():
    g, _ = make()
    pid = player_id_for(TOKEN)
    assert g.get_loadout(TOKEN) == {"character": None, "head": None, "desk": None, "theme": None,
                                    "favorites": [], "frame": None, "badge": None}
    lo = g.set_loadout(TOKEN, {"character": "嘉然", "favorites": ["e.01", "thumbup", "e.01"], "theme": "x"})
    assert lo["character"] == "嘉然" and lo["favorites"] == ["e.01", "thumbup"] and lo["theme"] == "x"
    for patch, code in (({"favorites": ["e.02"]}, "locked"), ({"head": "hat"}, "locked"),
                        ({"theme": "y"}, "locked"), ({"desk": "hat"}, "bad_item"),
                        ({"character": "路人"}, "bad_item"), ({"favorites": ["e.01"] * 3 + list("abcdefgh")}, "bad_item")):
        with pytest.raises(GameError) as e:
            g.set_loadout(TOKEN, patch)
        assert e.value.code == code, patch
    g.store.add_item(pid, "acc:hat", 0)
    g.store.add_item(pid, "acc:cat", 0)
    lo = g.set_loadout(TOKEN, {"head": "hat", "desk": "cat"})
    assert (lo["head"], lo["desk"], lo["character"]) == ("hat", "cat", "嘉然")   # other keys are kept
    assert g.set_loadout(TOKEN, {"head": ""})["head"] is None


def test_presets_store_validated_snapshots():
    g, _ = make()
    g.store.add_item(player_id_for(TOKEN), "acc:hat", 0)
    out = g.save_preset(TOKEN, 0, {"character": "嘉然", "head": "hat"}, "上班")
    assert out["presets"][0] == {"name": "上班", "loadout": {"character": "嘉然", "head": "hat"}}
    assert out["presets"][1:] == [None] * 4
    assert g.save_preset(TOKEN, 3, {"favorites": ["e.01"]})["presets"][3]["name"] == "预设 4"
    with pytest.raises(GameError) as e:
        g.save_preset(TOKEN, 5, {})
    assert e.value.code == "bad_slot"
    with pytest.raises(GameError):
        g.save_preset(TOKEN, 1, {"desk": "cat"})          # not owned
    assert g.save_preset(TOKEN, 0, None)["presets"][0] is None


def test_room_profile_emotes_and_accessories():
    g, _ = make()
    a, b = g.profile_for(TOKEN, "r1"), g.profile_for(TOKEN, "r2")
    assert a["uid"] and a["uid"] == g.profile_for(TOKEN, "r1")["uid"] != b["uid"]
    assert TOKEN not in a["uid"] and player_id_for(TOKEN) not in a["uid"]
    assert g.profile_for(None, "r1") == g.profile_for("bad", "r1") == {
        "uid": None, "frame": None, "badge": None, "head": None, "desk": None}
    assert g.owns_emote(None, "e.01") and g.owns_emote(None, "thumbup") and not g.owns_emote(None, "e.02")
    assert not g.owns_emote(TOKEN, "e.02")
    g.store.add_item(player_id_for(TOKEN), "emote:e.02", 0)
    assert g.owns_emote(TOKEN, "e.02")
    with pytest.raises(GameError):
        g.check_accessories(None, "hat", None)
    assert g.check_accessories(None, "", None) == {"head": None}
    g.store.add_item(player_id_for(TOKEN), "acc:hat", 0)
    assert g.check_accessories(TOKEN, "hat", None) == {"head": "hat"}


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


def test_decor_unlock_select_and_validation():
    g, _ = make(DropConfig(taps_per_box=10, max_taps_per_sec=10**5), SeqRng(0.0))
    assert g.status(TOKEN)["unlocked"] == []
    with pytest.raises(GameError) as e:
        g.set_decor(TOKEN, None, "badge-s1")
    assert e.value.code == "locked"
    g.report_activity(TOKEN, 100)
    g.open_boxes(TOKEN)  # card:c1 of series s1 -> badge unlocked (min 1)
    assert "badge-s1" in g.status(TOKEN)["unlocked"] and "frame-s1" not in g.status(TOKEN)["unlocked"]
    assert g.set_decor(TOKEN, None, "badge-s1")["badge"] == "badge-s1"
    with pytest.raises(GameError):
        g.set_decor(TOKEN, "badge-s1", None)   # a badge cannot be used as a frame
    with pytest.raises(GameError) as e:
        g.set_decor(TOKEN, "nope", None)
    assert e.value.code == "bad_decor"
    assert (g.profile_for(TOKEN, "r")["frame"], g.profile_for(TOKEN, "r")["badge"]) == (None, "badge-s1")
    assert g.set_decor(TOKEN, None, "")["badge"] is None
