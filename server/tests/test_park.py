import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import DAY_OFFSET, Game, GameError
from app.manifest import Manifest
from app.park import COIN_BUY, Park
from app.store import Store, day_of
from fixtures import Clock

TOKEN = "park-player-token-000001"
OTHER = "park-player-token-000002"
M = Manifest.load()
COIN = M.park["coin"]


def setup(taps=COIN["minTaps"], shards=100_000):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    park = Park(lambda: g)
    pid = g.status(TOKEN)["player"]
    g.store.update_player(pid, shards=shards, taps_total=taps)
    return g, park, clock, pid


def next_midnight(t: float) -> float:
    return ((t + DAY_OFFSET) // 86400 + 1) * 86400 - DAY_OFFSET


def test_buying_costs_shards():
    g, park, _, pid = setup()
    out = park.buy(TOKEN, 3)
    assert out["park"]["coins"] == 3
    assert out["shards"] == 100_000 - 3 * COIN["price"]
    assert out["park"]["today"] == {"spent": 3 * COIN["price"], "won": 0}
    assert out["park"]["coins"] == g.status(TOKEN)["park"]["coins"]
    assert g.store.ledger_sum(pid, day_of(g.now()), (COIN_BUY,)) == -3 * COIN["price"]


def test_buying_has_no_daily_or_holding_limit():
    g, park, _, pid = setup(shards=10_000_000)
    g.store.update_player(pid, coins=5000)
    for _ in range(5):
        park.buy(TOKEN, 100)
    out = park.buy(TOKEN, 1)
    assert out["park"]["coins"] == 5501
    assert out["shards"] == 10_000_000 - 501 * COIN["price"]


def test_buying_needs_the_taps_and_the_shards():
    g, park, _, pid = setup(taps=COIN["minTaps"] - 1)
    with pytest.raises(GameError) as e:
        park.buy(TOKEN, 1)
    assert e.value.code == "park_locked"
    assert park.state(TOKEN)["unlocked"] is False
    g.store.update_player(pid, taps_total=COIN["minTaps"], shards=COIN["price"] - 1)
    with pytest.raises(GameError) as e:
        park.buy(TOKEN, 1)
    assert e.value.code == "no_shards"
    with pytest.raises(GameError) as e:
        park.buy(TOKEN, 0)
    assert e.value.code == "bad_count"


def test_the_free_coin_comes_once_a_day():
    g, park, clock, _ = setup()
    assert park.state(TOKEN)["gift"] is True
    out = park.gift(TOKEN)
    assert out["gift"] == COIN["gift"] and out["park"]["coins"] == COIN["gift"] and out["park"]["gift"] is False
    assert park.gift(TOKEN)["gift"] == 0
    clock.t = next_midnight(clock.t) + 1
    assert park.state(TOKEN)["gift"] is True
    assert park.gift(TOKEN)["park"]["coins"] == 2 * COIN["gift"]


def test_the_free_coin_needs_the_taps():
    _, park, _, _ = setup(taps=0)
    with pytest.raises(GameError) as e:
        park.gift(TOKEN)
    assert e.value.code == "park_locked"


def test_spending_stamps_each_coin_and_turns_stamps_into_coins():
    g, park, clock, pid = setup()
    per = COIN["stampsPerCoin"]
    g.store.update_player(pid, coins=per + 5)
    with g.store.transaction() as st:
        assert park.spend(st, pid, per - 1, "scratch", clock()) == 0
        assert park.spend(st, pid, 2, "race", clock()) == 1
    s = park.state(TOKEN)
    assert s["coins"] == per + 5 - (per + 1) + 1
    assert s["stamps"] == 1 and s["stampsTotal"] == per + 1
    with g.store.transaction() as st:
        with pytest.raises(GameError) as e:
            park.spend(st, pid, s["coins"] + 1, "scratch", clock())
    assert e.value.code == "no_coins"


def test_a_refund_undoes_the_spending_with_its_stamp_coin():
    g, park, clock, pid = setup()
    per = COIN["stampsPerCoin"]
    g.store.update_player(pid, coins=10, stamps_total=per - 1)
    with g.store.transaction() as st:
        assert park.spend(st, pid, 3, "race", clock()) == 1
    with g.store.transaction() as st:
        park.refund(st, pid, 3, "race_refund", clock())
    s = park.state(TOKEN)
    assert s["coins"] == 10 and s["stampsTotal"] == per - 1


def test_badges_follow_the_stamp_total():
    g, park, _, pid = setup()
    first, second, third = COIN["badges"]
    for total, badge in ((first - 1, 0), (first, 1), (second, 2), (third + 5, 3)):
        g.store.update_player(pid, stamps_total=total)
        assert park.state(TOKEN)["badge"] == badge


def test_grants_add_coins():
    g, park, clock, pid = setup()
    g.store.update_player(pid, coins=7)
    with g.store.transaction() as st:
        park.grant(st, pid, 5, "redeem", clock())
    assert park.state(TOKEN)["coins"] == 12


def test_news_reaches_every_status_for_a_while():
    g, park, clock, pid = setup()
    g.store.update_player(pid, loadout='{"nick": "小草"}')
    with g.store.transaction() as st:
        park.announce(st, "jackpot", pid, clock(), shards=123456)
    other = g.status(OTHER)["park"]["news"]
    assert [(n["kind"], n["nick"], n["shards"]) for n in other] == [("jackpot", "小草", 123456)]
    clock.t += 3600
    assert g.status(OTHER)["park"]["news"] == []


def test_news_nicks_are_masked():
    g, _, clock, pid = setup()
    park = Park(lambda: g, mask=lambda s: "*" * len(s))
    with g.store.transaction() as st:
        park.announce(st, "jackpot", pid, clock(), shards=1)
    assert g.status(OTHER)["park"]["news"][0]["nick"] == "*" * len("匿名小面包")


def test_the_jackpot_starts_at_its_seed():
    _, park, _, _ = setup()
    assert park.state(TOKEN)["jackpot"] == M.park["scratch"]["jackpot"]["seed"]


def test_http_buy_and_gift(monkeypatch):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    monkeypatch.setattr(main, "game", g)
    client = TestClient(main.app)
    headers = {"X-Player-Token": TOKEN}
    pid = client.get("/api/me", headers=headers).json()["player"]
    g.store.update_player(pid, taps_total=COIN["minTaps"], shards=10_000)
    assert client.get("/api/park", headers=headers).json()["coins"] == 0
    r = client.post("/api/park/gift", headers=headers)
    assert r.status_code == 200 and r.json()["gift"] == 1
    r = client.post("/api/park/coins", headers=headers, json={"count": 2})
    assert r.status_code == 200 and r.json()["park"]["coins"] == 3 and r.json()["park"]["coins"] == 3
    r = client.post("/api/park/coins", headers=headers, json={"count": 100})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_shards"
