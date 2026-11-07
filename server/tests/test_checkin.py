import pytest
from app.game import DAY_OFFSET, Game, GameError
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock, SeqRng

TOKEN = "checkin-player-token-0001"


def game(*rolls):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), rng=SeqRng(*(rolls or (.5,))), now=clock)
    g.status(TOKEN)
    return g, clock


def next_midnight(t: float) -> float:
    """The next 00:00 China Standard Time after `t`."""
    return ((t + DAY_OFFSET) // 86400 + 1) * 86400 - DAY_OFFSET


def test_prize_table_is_the_approved_one():
    table = Manifest.load().checkin
    prizes = table["prizes"]
    assert [p["shards"] for p in prizes] == [80, 160, 320, 480, 800, 1600]
    assert sum(p["weight"] for p in prizes) == 100
    assert sum(p["shards"] * p["weight"] for p in prizes) / 100 == pytest.approx(273.6)
    assert table["spread"] == 0.1


@pytest.mark.parametrize("rolls,index,shards", [((0, 0), 0, 72), ((0, .5), 0, 80), ((.5, .9999), 1, 176),
                                                 ((.99, 0), 5, 1440), ((.99, .9999), 5, 1760)])
def test_prizes_pay_give_or_take_the_spread(rolls, index, shards):
    g, _ = game(*rolls)
    assert g.checkin(TOKEN)["prize"]["index"] == index
    assert g.checkin_month(TOKEN)["days"][0]["shards"] == shards


def test_one_checkin_per_china_day():
    g, clock = game(.99)
    assert g.status(TOKEN)["checkin"] == {"available": True}
    r = g.checkin(TOKEN)
    today = r["prize"]["day"]
    assert r["prize"] == {"index": 5, "shards": 1757, "day": today}
    assert r["shards"] == 1600 + 1757 and r["checkin"] == {"available": False}
    with pytest.raises(GameError) as e:
        g.checkin(TOKEN)
    assert e.value.code == "checked_in"
    assert g.status(TOKEN)["shards"] == 3357

    midnight = next_midnight(clock.t)
    clock.t = midnight - 1
    assert g.status(TOKEN)["checkin"] == {"available": False}
    clock.t = midnight
    assert g.status(TOKEN)["checkin"] == {"available": True}
    assert g.checkin(TOKEN)["prize"]["index"] == 5


def test_month_lists_this_months_checkins_only():
    g, clock = game(0)
    # Start on the last day of a month, so the next check-in falls in a new one.
    while True:
        month = g.checkin_month(TOKEN)
        clock.t = next_midnight(clock.t)
        if g.checkin_month(TOKEN)["today"][:7] != month["today"][:7]:
            clock.t -= 1
            break
    last = g.checkin_month(TOKEN)
    assert last["available"] and last["days"] == []
    g.checkin(TOKEN)
    month = g.checkin_month(TOKEN)
    assert month["available"] is False and month["days"] == [{"day": last["today"], "prize": 0, "shards": 72}]

    clock.t += 1
    fresh = g.checkin_month(TOKEN)
    assert fresh["today"].endswith("-01") and fresh["available"] and fresh["days"] == []
    g.checkin(TOKEN)
    clock.t = next_midnight(clock.t)
    g.checkin(TOKEN)
    assert [d["day"][-2:] for d in g.checkin_month(TOKEN)["days"]] == ["01", "02"]
