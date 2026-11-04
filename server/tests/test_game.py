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


def test_rate_limit_clips_credit():
    g, clock = make(DropConfig(max_taps_per_sec=10), elapsed=0)
    clock.t += 2
    st = g.report_activity(TOKEN, 5000)
    assert st["credited"] == st["totals"]["taps"] == 20


def test_active_minutes_count_once_per_minute():
    g, clock = make(clock=Clock(59990))
    clock.t = 60000
    g.report_activity(TOKEN, 4)
    clock.t += 5
    assert g.report_activity(TOKEN, 8)["totals"]["activeMinutes"] == 1
    clock.t += 5
    assert g.report_activity(TOKEN, 8)["totals"]["activeMinutes"] == 1
    clock.t = 60060
    assert g.report_activity(TOKEN, 12)["totals"]["activeMinutes"] == 2


@pytest.mark.parametrize("item,cost", [("card:c1", 480), ("emote:e.02", 480), ("emote:rare.01", 1600)])
def test_craft_prices_and_owned(item, cost):
    manifest = tiny_manifest()
    manifest.data["emoteSets"].append({"id": "rare", "name": "rare", "character": "嘉然", "rarity": "rare",
                                        "emotes": [{"key": "rare.01", "name": "r", "img": "bundle:x"}]})
    g = Game(Store(), manifest)
    assert g.status(TOKEN)["shards"] == 1600
    assert g.craft(TOKEN, item)["shards"] == 1600 - cost
    with pytest.raises(GameError, match="owned"):
        g.craft(TOKEN, item)


@pytest.mark.parametrize("item", ["card:c4", "card:c5", "char:嘉然山海经", "emote:e.01", "acc:hat", "nope"])
def test_uncraftable_items(item):
    g, _ = make()
    with pytest.raises(GameError, match="unknown item"):
        g.craft(TOKEN, item)


def test_craft_insufficient_shards():
    g, _ = make()
    g.store.update_player(player_id_for(TOKEN), shards=479)
    with pytest.raises(GameError) as e:
        g.craft(TOKEN, "card:c1")
    assert e.value.code == "no_shards"


def test_loadout_validates_favorites_and_ignores_retired_equipment():
    g, _ = make()
    assert g.get_loadout(TOKEN) == {"character": None, "favorites": []}
    lo = g.set_loadout(TOKEN, {"character": "嘉然", "favorites": ["e.01", "thumbup", "e.01"], "head": "hat"})
    assert lo == {"character": "嘉然", "favorites": ["e.01", "thumbup"]}
    for patch, code in (({"favorites": ["e.02"]}, "locked"), ({"character": "路人"}, "bad_item")):
        with pytest.raises(GameError) as e:
            g.set_loadout(TOKEN, patch)
        assert e.value.code == code


def test_loadout_requires_owned_skin_and_accepts_original():
    g, _ = make()
    with pytest.raises(GameError) as e:
        g.set_loadout(TOKEN, {"character": "嘉然山海经"})
    assert e.value.code == "locked"
    g.store.add_item(player_id_for(TOKEN), "char:嘉然山海经", 0)
    assert g.set_loadout(TOKEN, {"character": "嘉然山海经"})["character"] == "嘉然山海经"
    assert g.set_loadout(TOKEN, {"character": "嘉然"})["character"] == "嘉然"
    with pytest.raises(GameError) as e:
        g.set_loadout(TOKEN, {"character": "嘉然不存在"})
    assert e.value.code == "bad_item"


def test_room_profile_and_emote_ownership():
    g, _ = make()
    a = g.profile_for(TOKEN, "r1")
    assert a["uid"] == g.profile_for(TOKEN, "r1")["uid"] != g.profile_for(TOKEN, "r2")["uid"]
    assert g.profile_for(None, "r1") == g.profile_for("bad", "r1") == {"uid": None}
    assert g.owns_emote(None, "e.01") and g.owns_emote(None, "thumbup")
    assert not g.owns_emote(TOKEN, "heart") and not g.owns_emote(TOKEN, "e.02")
    g.store.add_item(player_id_for(TOKEN), "emote:e.02", 0)
    assert g.owns_emote(TOKEN, "e.02")


def test_players_are_isolated():
    g, _ = make()
    g.resonate(TOKEN)
    other = "o" * 32
    assert g.status(other)["shards"] == 1600 and g.collection(other)["owned"] == {}
