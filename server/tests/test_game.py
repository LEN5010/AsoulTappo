import pytest

from app.cards import DropConfig
from app.game import Game, GameError, player_id_for
from app.store import Store

from fixtures import Clock, SeqRng, tiny_manifest

TOKEN = "t" * 32


def make(cfg=None, rng=None, clock=None):
    clock = clock or Clock()
    g = Game(Store(":memory:"), tiny_manifest(), cfg, rng or SeqRng(0.0), clock)
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
    g, clock = make(DropConfig(max_taps_per_sec=10, taps_per_box=100))
    g.report_activity(TOKEN, 0)
    clock.t += 2
    st = g.report_activity(TOKEN, 5000)  # only ~20 taps are plausible in 2s
    assert st["credited"] == 20 and st["totals"]["taps"] == 20


def test_active_minute_counts_once_per_minute_and_awards_box():
    g, clock = make(DropConfig(taps_per_box=10**6, minutes_per_box=2, min_taps_active_minute=10))
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
    g.open_box(TOKEN)
    st = g.report_activity(TOKEN, 1000)
    assert st["boxesToday"] == 3 and st["boxes"] == 2          # daily cap 3 (only one more granted)
    clock.t += 86400
    st = g.report_activity(TOKEN, 0)
    assert st["boxesToday"] == 0                               # new UTC day


def test_open_box_requires_box_and_stores_collection():
    g, _ = make(DropConfig(taps_per_box=10, max_taps_per_sec=1000), SeqRng(0.0))
    with pytest.raises(GameError) as e:
        g.open_box(TOKEN)
    assert e.value.code == "no_box"
    g.report_activity(TOKEN, 30)
    r = g.open_box(TOKEN)
    assert r["card"] == "c1" and r["new"] and r["count"] == 1 and r["boxes"] == 2
    r = g.open_box(TOKEN)
    assert not r["new"] or r["card"] != "c1"
    col = g.collection(TOKEN)
    assert sum(col["owned"].values()) == 2 and len(col["recent"]) == 2
    assert g.status(TOKEN)["totals"]["opened"] == 2


def test_pity_counters_persist_and_reset():
    g, _ = make(DropConfig(taps_per_box=10, max_taps_per_sec=10**5), SeqRng(0.0))
    g.report_activity(TOKEN, 100)
    for _ in range(3):
        g.open_box(TOKEN)
    assert g.status(TOKEN)["pity"] == {"epic": 3, "legendary": 3}


def test_players_are_isolated():
    g, _ = make(DropConfig(taps_per_box=10, max_taps_per_sec=1000))
    g.report_activity(TOKEN, 50)
    other = "o" * 32
    assert g.status(other)["boxes"] == 0 and g.collection(other)["owned"] == {}


def test_decor_unlock_select_and_validation():
    g, _ = make(DropConfig(taps_per_box=10, max_taps_per_sec=10**5), SeqRng(0.0, 0.99))
    assert g.status(TOKEN)["unlocked"] == []
    with pytest.raises(GameError) as e:
        g.set_decor(TOKEN, None, "badge-s1")
    assert e.value.code == "locked"
    g.report_activity(TOKEN, 100)
    g.open_box(TOKEN)  # a card of series s1 -> badge unlocked (min 1)
    assert "badge-s1" in g.status(TOKEN)["unlocked"] and "frame-s1" not in g.status(TOKEN)["unlocked"]
    assert g.set_decor(TOKEN, None, "badge-s1")["badge"] == "badge-s1"
    with pytest.raises(GameError):
        g.set_decor(TOKEN, "badge-s1", None)   # a badge cannot be used as a frame
    with pytest.raises(GameError) as e:
        g.set_decor(TOKEN, "nope", None)
    assert e.value.code == "bad_decor"
    assert g.decor_for(TOKEN) == (None, "badge-s1")
    assert g.set_decor(TOKEN, None, "")["badge"] is None
    assert g.decor_for("bad") == (None, None)
