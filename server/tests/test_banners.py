"""Limited pools (app/banners.py): featured items leave the standing pool until their banner ends, and a draw from a
running banner finds them in a tier of their own or among the draws of their tier, at the banner's odds."""
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import banners, economy
from app.game import Game, GameError, player_id_for
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock, SeqRng

TOKEN = "banner-player-token-0001"
NEW = "9.9.9"
DAY = 86400.0
#: Two skins of the real catalog, featured from one day after the clock's start for a week.
SKINS = ["char:嘉然然龙", "char:乃琳法师"]


def manifest(**over):
    m = Manifest.load()
    t = Clock().t
    m.resonance["banners"] = [{"id": "forms", "name": "双形态", "start": t + DAY, "end": t + 8 * DAY,
                               "items": SKINS, "rate": 5, "pity": 4, **over}]
    return fresh(m)


def fresh(m):
    """Manifest.load read the banners already: read them again."""
    m.__dict__.pop("banners", None)
    return m


def game(*rolls, m=None, shards=100_000):
    clock = Clock()
    g = Game(Store(":memory:"), m or manifest(), rng=SeqRng(*rolls), now=clock)
    g.status(TOKEN)
    g.store.update_player(player_id_for(TOKEN), shards=shards)
    return g, clock


def pooled(m, now):
    return {i["id"] for tier in m.resonance_pool_for(NEW, now).values() for i in tier}


def test_featured_items_stay_out_of_the_standing_pool_until_the_banner_ends():
    m = manifest()
    t = Clock().t
    # before it starts, while it runs, after it ended
    assert not pooled(m, t) & set(SKINS)
    assert not pooled(m, t + 2 * DAY) & set(SKINS)
    assert set(SKINS) <= pooled(m, t + 8 * DAY)
    assert banners.held(m.banners, t + 8 * DAY) == frozenset()


def test_a_client_is_told_of_a_banner_from_an_hour_before_it_starts():
    m = manifest()
    t = Clock().t
    assert m.banners_for(NEW, t) == []
    assert [b.id for b in m.banners_for(NEW, t + DAY - 3000)] == ["forms"]
    assert m.banner("forms", NEW, t + DAY - 3000) is None
    assert m.banner("forms", NEW, t + DAY).id == "forms"
    assert m.banner("forms", NEW, t + 8 * DAY) is None
    # A client older than a featured skin is not offered the banner.
    assert m.banners_for("1.2.4", t + 2 * DAY) == []


def test_a_draw_at_the_top_of_the_roll_is_a_featured_item():
    # .95 is the first roll inside a 5% range; the second roll picks among the missing ones.
    g, clock = game(.95, 0, .5)
    clock.t += 2 * DAY
    out = g.resonate(TOKEN, 1, NEW, "forms")
    drop = out["drops"][0]
    assert drop == {"item": SKINS[0], "rarity": "skin", "new": True, "count": 1, "shards": 0, "featured": True}
    assert out["resonance"]["banners"] == {"forms": {"pity": 0, "drawn": 1}}
    # A skin: the skin pity starts over, the legendary one goes on.
    assert out["resonance"]["pity"] == {"legendary": 1, "skin": 0}


def test_just_under_the_range_is_a_common_draw_and_counts_toward_the_pity():
    g, clock = game(.9499)
    clock.t += 2 * DAY
    out = g.resonate(TOKEN, 3, NEW, "forms")
    assert [d["rarity"] for d in out["drops"]] == ["common"] * 3
    assert out["resonance"]["banners"] == {"forms": {"pity": 3, "drawn": 3}}
    # The fourth draw since the last featured item is one for certain.
    drop = g.resonate(TOKEN, 1, NEW, "forms")["drops"][0]
    assert drop["featured"] and drop["item"] in SKINS


def test_the_standing_pool_never_gives_a_featured_item_and_keeps_its_own_count():
    g, clock = game(.99)
    clock.t += 2 * DAY
    out = g.resonate(TOKEN, 5, NEW)
    assert all("featured" not in d and d["item"] not in SKINS for d in out["drops"])
    assert out["resonance"]["banners"] == {}


def test_a_whole_set_draws_as_the_standing_pool_does():
    g, clock = game(.99)
    pid = player_id_for(TOKEN)
    for iid in SKINS:
        g.store.add_item(pid, iid, 0)
    clock.t += 2 * DAY
    out = g.resonate(TOKEN, 6, NEW, "forms")
    assert all("featured" not in d for d in out["drops"])
    assert out["resonance"]["banners"] == {"forms": {"pity": 0, "drawn": 6}}


def test_the_legendary_pity_goes_before_the_banners():
    g, clock = game(.5)
    pid = player_id_for(TOKEN)
    hard = g.manifest.resonance["pity"]["legendary"]
    g.store.update_player(pid, draw_pity=hard - 1)
    g.store.save_banner_draws(pid, "forms", 3, 3)
    clock.t += 2 * DAY
    first, second = g.resonate(TOKEN, 2, NEW, "forms")["drops"]
    assert first["rarity"] == "legendary" and "featured" not in first
    assert second["featured"]


#: A banner with odds of its own for two tiers, whose skins are found among the skins it gives.
SHARED = {"rate": 0, "pity": None, "rates": {"skin": 3, "limited": 5}, "share": 40}


def test_a_banner_rolls_its_own_odds_for_the_tiers_it_names():
    # .02 is an epic at the standing pool's odds, and a skin where skins have 3%.
    for pool, tier in ((None, "epic"), ("forms", "skin")):
        g, clock = game(.02, .99, 0, m=manifest(**SHARED))
        clock.t += 2 * DAY
        assert g.resonate(TOKEN, 1, NEW, pool)["drops"][0]["rarity"] == tier


def test_a_share_of_the_tiers_draws_are_its_featured_items():
    # A skin, the share's roll inside 40%, the first of the missing ones.
    g, clock = game(.002, .39, 0, m=manifest(**SHARED))
    clock.t += 2 * DAY
    out = g.resonate(TOKEN, 1, NEW, "forms")
    assert out["drops"][0] == {"item": SKINS[0], "rarity": "skin", "new": True, "count": 1, "shards": 0, "featured": True}
    assert out["resonance"]["banners"] == {"forms": {"pity": 0, "drawn": 1}}
    assert out["resonance"]["pity"]["skin"] == 0


def test_the_rest_of_the_tiers_draws_are_its_standing_items():
    g, clock = game(.002, .4, 0, m=manifest(**SHARED))
    clock.t += 2 * DAY
    drop = g.resonate(TOKEN, 1, NEW, "forms")["drops"][0]
    assert drop["rarity"] == "skin" and "featured" not in drop and drop["item"] not in SKINS


@pytest.mark.parametrize("share_roll, featured", [(.39, True), (.4, False)])
def test_a_skin_from_the_saves_pity_is_a_featured_one_the_same_share_of_the_time(share_roll, featured):
    # .9 is a common draw, but the save's skin pity is due: the skin it gives goes through the share's roll as well.
    g, clock = game(.9, share_roll, 0, m=manifest(**SHARED))
    pid = player_id_for(TOKEN)
    g.store.update_player(pid, skin_pity=g.manifest.resonance["pity"]["skin"] - 1)
    clock.t += 2 * DAY
    out = g.resonate(TOKEN, 1, NEW, "forms")
    drop = out["drops"][0]
    assert drop["rarity"] == "skin" and (drop["item"] in SKINS) is featured and drop.get("featured", False) is featured
    assert out["resonance"]["pity"]["skin"] == 0


def test_a_shared_tier_with_every_featured_item_found_gives_its_standing_items():
    g, clock = game(.002, 0, 0, m=manifest(**SHARED))
    pid = player_id_for(TOKEN)
    for iid in SKINS:
        g.store.add_item(pid, iid, 0)
    clock.t += 2 * DAY
    drop = g.resonate(TOKEN, 1, NEW, "forms")["drops"][0]
    assert drop["rarity"] == "skin" and "featured" not in drop


def test_the_client_is_told_a_banners_own_odds_and_share():
    view = manifest(**SHARED).banners[0].view()
    assert view["rates"] == {"skin": 3, "limited": 5} and view["share"] == 40
    assert "rate" not in view and "pity" not in view


@pytest.mark.parametrize("when", [0, 9 * DAY])
def test_a_banner_that_is_not_running_refuses_the_draw_and_takes_nothing(when):
    g, clock = game(.5)
    clock.t += when
    with pytest.raises(GameError) as e:
        g.resonate(TOKEN, 1, NEW, "forms")
    assert e.value.code == "no_banner"
    assert g.status(TOKEN)["shards"] == 100_000


def test_an_older_client_cannot_draw_from_a_banner_it_cannot_show():
    g, clock = game(.5)
    clock.t += 2 * DAY
    with pytest.raises(GameError):
        g.resonate(TOKEN, 1, "1.2.4", "forms")


def test_a_featured_card_cannot_be_crafted_while_its_banner_holds_it():
    m = Manifest.load()
    card = next(i["id"] for i in m.resonance_pool["common"] if i["kind"] == "card")
    t = Clock().t
    m.resonance["banners"] = [{"id": "b", "start": t - DAY, "end": t + DAY, "items": [card], "rate": 5}]
    g, clock = game(.5, m=fresh(m))
    with pytest.raises(GameError):
        g.craft(TOKEN, card)
    clock.t += 2 * DAY
    assert g.craft(TOKEN, card)["item"] == card


@pytest.mark.parametrize("bad", [
    {"items": ["char:nobody"]},
    {"items": []},
    {"rate": 0},
    {"rate": 0, "share": 0},
    {"share": 120},
    {"rates": {"common": 5}},
    {"rates": {"skin": 99}},
    {"rates": ["skin"]},
    {"pity": 0},
    {"end": "2020-01-01T00:00:00+08:00"},
    {"start": "2026-11-21T12:00:00"},
])
def test_a_banner_the_server_could_not_run_stops_the_start(bad):
    m = manifest(**bad)
    with pytest.raises(ValueError):
        m.banners


def test_two_banners_running_together_cannot_share_an_item():
    m = manifest()
    m.resonance["banners"].append({**m.resonance["banners"][0], "id": "again"})
    with pytest.raises(ValueError):
        fresh(m).banners


def test_times_are_read_with_their_offset():
    m = manifest(start="2026-11-21T12:00:00+08:00", end="2026-11-28T12:00:00+08:00")
    b = m.banners[0]
    assert b.end - b.start == 7 * DAY and b.start == 1795233600.0


def test_the_client_gets_running_banners_and_held_items_never_the_whole_schedule():
    m = manifest()
    t = Clock().t
    view = economy.client_view(m.economy, Game(Store(":memory:"), m).cfg, m.resonance_pool_for(NEW, t),
                               banners=[b.view() for b in m.banners_for(NEW, t)], held=sorted(banners.held(m.banners, t)))
    assert "banners" not in view["resonance"] and view["resonance"]["held"] == sorted(SKINS)
    now = t + 2 * DAY
    view = economy.client_view(m.economy, Game(Store(":memory:"), m).cfg, m.resonance_pool_for(NEW, now),
                               banners=[b.view() for b in m.banners_for(NEW, now)], held=sorted(banners.held(m.banners, now)))
    assert view["resonance"]["banners"] == [{"id": "forms", "name": "双形态", "start": t + DAY, "end": t + 8 * DAY,
                                             "items": SKINS, "rate": 5, "pity": 4}]


def test_the_draw_route_takes_the_banner(monkeypatch):
    m = manifest()
    clock = Clock()
    clock.t += 2 * DAY
    g = Game(Store(":memory:"), m, rng=SeqRng(.99, 0), now=clock)
    monkeypatch.setattr(main, "game", g)
    monkeypatch.setattr(main, "manifest", m)
    client = TestClient(main.app)
    headers = {"X-Player-Token": TOKEN, "X-Client-Version": NEW}
    g.status(TOKEN)
    out = client.post("/api/resonance/draw", json={"count": 1, "banner": "forms"}, headers=headers).json()
    assert out["drops"][0]["featured"] is True
    assert client.post("/api/resonance/draw", json={"count": 1, "banner": "nope"}, headers=headers).status_code == 409
    eco = client.get("/api/economy", headers=headers).json()
    assert [b["id"] for b in eco["resonance"]["banners"]] == ["forms"] and eco["resonance"]["held"] == sorted(SKINS)


def test_a_tier_at_zero_in_the_standing_pool_is_found_in_a_banner_that_rates_it():
    # The standing pool keeps the limited tier at 0: its cards are found only where a banner gives the tier odds.
    def closet(**over):
        m = manifest(**over)
        rates = m.resonance["rates"]
        rates["common"] += rates["limited"]
        rates["limited"] = 0
        return m
    # .17 is past every standing tier; with skins at 3% and the limited tier at 5% it is inside the limited range.
    g, clock = game(.17, 0, 0, m=closet(**SHARED))
    clock.t += 2 * DAY
    assert g.resonate(TOKEN, 1, NEW)["drops"][0]["rarity"] == "common"
    g, clock = game(.17, .99, 0, m=closet(**SHARED))
    clock.t += 2 * DAY
    drop = g.resonate(TOKEN, 1, NEW, "forms")["drops"][0]
    assert drop["rarity"] == "limited" and drop["new"] and "featured" not in drop
    # The client is told the standing pool's 0 and the banner's own odds.
    view = economy.client_view(g.manifest.economy, g.cfg, g.manifest.resonance_pool_for(NEW, clock.t))
    assert view["resonance"]["rates"]["limited"] == 0


def test_a_banner_can_add_a_tier_missing_from_the_standing_pool():
    featured = Manifest.load().resonance_pool["limited"][0]["id"]
    m = manifest(items=[featured], **SHARED)
    rates = m.resonance["rates"]
    rates["common"] += rates.pop("limited")
    g, clock = game(.17, 0, 0, m=m)
    clock.t += 2 * DAY
    assert "limited" not in m.resonance_pool_for(NEW, clock.t)
    drop = g.resonate(TOKEN, 1, NEW, "forms")["drops"][0]
    assert drop["item"] == featured and drop["rarity"] == "limited" and drop["featured"]


def test_a_banners_common_cards_come_as_holo_versions_too():
    m = manifest()
    m.resonance["holoChance"] = 100
    # A common card, as in the standing pool (tests/test_holo.py): tier, kind, item, then the holo roll.
    g, clock = game(.5, 0, 0, 0, m=m)
    clock.t += 2 * DAY
    drop = g.resonate(TOKEN, 1, NEW, "forms")["drops"][0]
    assert drop["rarity"] == "common" and drop["holo"] is True
