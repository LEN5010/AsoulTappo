"""脑洞波: twelve still portraits in the limited tier from 1.3.0, featured by a limited pool of their own, and a still
name plate a member, worn once her four cards are owned. Once their pool ends they stay in the limited tier with the
衣橱 cards, found wherever that tier has odds."""
import pytest

from app import banners
from app.game import Game, GameError, player_id_for
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock, SeqRng

TOKEN = "naodong-player-token-0001"
DAY = 86400.0
NEW, OLD = "1.3.0", "1.2.6"
M = Manifest.load()
CARDS = [c for c in M.data["cards"] if c["series"] == "naodong"]
IDS = [f"card:{c['id']}" for c in CARDS]
#: member -> the item_id of her 脑洞波 suit, which numbers her cards
SUITS = {"嘉然": "116741401", "乃琳": "123046201", "贝拉": "112644401"}
PLATES = {"naodong-jiaran": "嘉然", "naodong-nailin": "乃琳", "naodong-beila": "贝拉"}


def pool_manifest(**over):
    """The real catalog with one limited pool featuring the twelve, from a day after the clock's start for two weeks."""
    m = Manifest.load()
    t = Clock().t
    m.resonance["banners"] = [{"id": "naodong", "name": "脑洞共鸣", "start": t + DAY, "end": t + 15 * DAY,
                               "items": IDS, "rate": 1, "pity": 100, **over}]
    m.__dict__.pop("banners", None)
    return m


def game(*rolls, m=None, shards=0):
    clock = Clock()
    g = Game(Store(":memory:"), m or M, rng=SeqRng(*(rolls or (.5,))), now=clock)
    g.status(TOKEN)
    pid = player_id_for(TOKEN)
    if shards:
        g.store.update_player(pid, shards=shards)
    return g, pid, clock


def limited(m, version, now=None, rates=None):
    """The ids in the limited tier of the pool a client of [version] draws from."""
    return {i["id"] for i in m.resonance_pool_for(version, now, tiers=rates or ()).get("limited", [])}


def test_twelve_still_portraits_four_a_member_in_the_limited_tier_from_1_3_0():
    assert len(CARDS) == 12
    assert next(s for s in M.data["series"] if s["id"] == "naodong") == {"id": "naodong", "name": "脑洞波", "total": 12}
    for member, suit in SUITS.items():
        mine = [c for c in CARDS if c["characters"] == [member]]
        assert [c["id"] for c in mine] == [f"c{suit}{k:02d}" for k in range(1, 5)]
    for c in CARDS:
        assert c["rarity"] == "limited" and c["tier"] == "normal" and c["sub"] is None
        assert c["video"] is None and c["since"] == "1.3.0"
        assert c["thumb"] == f"bundle:cards/thumb/{c['id']}.webp" and c["full"] == f"pack:cards/naodong/{c['id']}.webp"
    others = {c["name"] for c in M.data["cards"] if c["series"] != "naodong"}
    assert len({c["name"] for c in CARDS}) == 12 and not {c["name"] for c in CARDS} & others


def test_older_clients_never_find_them():
    assert set(IDS) <= M.held_for(OLD)
    assert not limited(M, OLD) & set(IDS)
    assert set(IDS) <= limited(M, NEW)
    # never crafted: the limited tier has no price
    assert "limited" not in M.craft_cost


def test_each_member_has_a_still_plate_unlocked_by_her_four_cards():
    plates = {p["id"]: p for p in M.data["plates"]}
    for pid, member in PLATES.items():
        p = plates[pid]
        assert {k: v for k, v in p.items() if k != "aspect"} == {
            "id": pid, "name": f"脑洞波 · {member}", "series": "naodong", "member": member,
            "poster": f"bundle:plates/{pid}.webp", "still": f"pack:plates/{pid}.webp"}
        assert 0.8 < p["aspect"] < 0.9
        assert M.plates[pid] == [f"card:{c['id']}" for c in CARDS if c["characters"] == [member]]
        assert len(M.plates[pid]) == 4


def test_a_series_plate_without_a_member_still_asks_for_the_whole_series():
    data = {**M.data, "plates": [{"id": "x", "name": "x", "series": "naodong"}]}
    assert Manifest(data).plates["x"] == IDS


def test_a_plate_is_worn_once_its_members_four_cards_are_owned():
    g, pid, _ = game()
    for item in M.plates["naodong-nailin"][:-1] + M.plates["naodong-jiaran"] + M.plates["naodong-beila"]:
        g.store.add_item(pid, item, 0)
    with pytest.raises(GameError) as e:
        g.set_loadout(TOKEN, {"plate": "naodong-nailin"})
    assert e.value.code == "locked"
    assert g.room_plate(TOKEN, "naodong-nailin") is None
    # the other members' cards do not count for her, their own plates are whole
    assert g.set_loadout(TOKEN, {"plate": "naodong-jiaran"})["plate"] == "naodong-jiaran"
    g.store.add_item(pid, M.plates["naodong-nailin"][-1], 0)
    assert g.set_loadout(TOKEN, {"plate": "naodong-nailin"})["plate"] == "naodong-nailin"
    assert g.room_plate(TOKEN, "naodong-nailin") == "naodong-nailin"


def test_the_pool_is_offered_to_clients_that_can_show_its_cards():
    m = pool_manifest()
    t = Clock().t
    assert [b.id for b in m.banners_for(NEW, t + 2 * DAY)] == ["naodong"]
    assert m.banners_for(OLD, t + 2 * DAY) == []


def test_named_by_a_pool_they_are_held_until_it_ends_and_then_stay_in_the_limited_tier():
    m = pool_manifest()
    t = Clock().t
    # Another pool running meanwhile with odds for the limited tier deals the 衣橱 cards, never these.
    rates = {**m.resonance["rates"], "limited": 6}
    for now in (t, t + 2 * DAY):
        assert not limited(m, NEW, now, rates) & set(IDS)
        assert limited(m, NEW, now, rates)
    assert banners.held(m.banners, t + 15 * DAY) == frozenset()
    assert set(IDS) <= limited(m, NEW, t + 15 * DAY, rates)


def test_a_draw_at_the_top_of_the_roll_is_a_card_the_save_lacks():
    # .995 is inside the top 1%; the next roll picks the first of those the save lacks.
    g, pid, clock = game(.995, 0, m=pool_manifest(), shards=10_000)
    g.store.add_item(pid, IDS[0], 0)
    clock.t += 2 * DAY
    drop = g.resonate(TOKEN, 1, NEW, "naodong")["drops"][0]
    assert drop["item"] == IDS[1] and drop["rarity"] == "limited" and drop["featured"] and drop["new"]


def test_the_hundredth_draw_since_the_last_card_is_one_for_certain():
    g, _, clock = game(.5, m=pool_manifest(), shards=100 * 160)
    clock.t += 2 * DAY
    out = g.resonate(TOKEN, 99, NEW, "naodong")
    assert not any(d.get("featured") for d in out["drops"])
    assert out["resonance"]["banners"]["naodong"]["pity"] == 99
    drop = g.resonate(TOKEN, 1, NEW, "naodong")["drops"][0]
    assert drop["featured"] and drop["item"] in IDS
