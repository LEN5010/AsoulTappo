import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import DAY_OFFSET, Game, GameError
from app.manifest import Manifest
from app.park import COIN_BUY, POOL, Park
from app.store import Store, day_of
from fixtures import Clock, tiny_manifest

TOKEN = "park-player-token-000001"
OTHER = "park-player-token-000002"
M = Manifest.load()
COIN = M.park["coin"]
POOL_CFG = M.park["lottery"]["pool"]


def setup(taps=COIN["minTaps"], shards=100_000, gifted=True):
    """A save with [taps]; with [gifted] today's free coin counts as given, so status gives none."""
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    park = Park(lambda: g)
    pid = g.status(TOKEN)["player"]
    g.store.update_player(pid, shards=shards, taps_total=taps, gift_day=day_of(clock()) if gifted else "")
    return g, park, clock, pid


def coin_ledger(g, pid):
    rows = g.store._db.execute("SELECT day, source, amount, count FROM coin_ledger WHERE player_id = ?",
                               (pid,)).fetchall()
    return [tuple(r) for r in rows]


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
    g, park, clock, _ = setup(gifted=False)
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
        park.announce(st, "scratch_big", pid, clock(), shards=123456)
    other = g.status(OTHER)["park"]["news"]
    assert [(n["kind"], n["nick"], n["shards"]) for n in other] == [("scratch_big", "小草", 123456)]
    clock.t += 3600
    assert g.status(OTHER)["park"]["news"] == []


def test_news_nicks_are_masked():
    g, _, clock, pid = setup()
    park = Park(lambda: g, mask=lambda s: "*" * len(s))
    with g.store.transaction() as st:
        park.announce(st, "scratch_big", pid, clock(), shards=1)
    assert g.status(OTHER)["park"]["news"][0]["nick"] == "*" * len("匿名小面包")


# ----------------------------------------------------------------------- the lottery pool
def test_the_pool_starts_at_its_seed():
    g, park, _, _ = setup()
    assert park.state(TOKEN)["jackpot"] == POOL_CFG["seed"] and g.store.park_counter(POOL, -1) == -1


@pytest.mark.parametrize("source", ["scratch", "race", "lottery"])
def test_every_coin_spent_feeds_the_pool(source):
    g, park, clock, pid = setup()
    g.store.update_player(pid, coins=10)
    with g.store.transaction() as st:
        park.spend(st, pid, 3, source, clock())
    assert park.state(TOKEN)["jackpot"] == POOL_CFG["seed"] + 3 * POOL_CFG["perCoin"]
    with g.store.transaction() as st:
        park.spend(st, pid, 1, source, clock())
    assert g.store.park_counter(POOL) == POOL_CFG["seed"] + 4 * POOL_CFG["perCoin"]


def test_a_failed_spend_feeds_nothing():
    g, park, clock, pid = setup()
    with pytest.raises(GameError):
        with g.store.transaction() as st:
            park.spend(st, pid, 1, "scratch", clock())
    assert park.state(TOKEN)["jackpot"] == POOL_CFG["seed"]


def test_a_refund_takes_its_share_back_out_of_the_pool():
    g, park, clock, pid = setup()
    g.store.update_player(pid, coins=10)
    with g.store.transaction() as st:
        park.spend(st, pid, 4, "race", clock())
        park.refund(st, pid, 4, "race_refund", clock())
    assert park.state(TOKEN)["jackpot"] == POOL_CFG["seed"]
    # never below 0, as after a draw paid the pool out since the coins were spent
    g.store.set_park_counter(POOL, POOL_CFG["perCoin"])
    with g.store.transaction() as st:
        park.spend(st, pid, 1, "race", clock())
        g.store.set_park_counter(POOL, 10)
        park.refund(st, pid, 1, "race_refund", clock())
    assert g.store.park_counter(POOL) == 0


# ----------------------------------------------------------------------- the free coin in status
def test_status_gives_the_free_coin_once_a_day_and_writes_only_then():
    g, park, clock, pid = setup(gifted=False)
    db = g.store._db
    before = db.total_changes
    out = g.status(TOKEN)
    assert out["park"]["coins"] == COIN["gift"] and out["park"]["gifted"] == COIN["gift"]
    assert db.total_changes > before
    assert coin_ledger(g, pid) == [(day_of(clock()), "gift", COIN["gift"], 1)]
    for _ in range(3):
        before = db.total_changes
        again = g.status(TOKEN)
        assert again["park"]["coins"] == COIN["gift"] and "gifted" not in again["park"]
        assert db.total_changes == before
    # the park's own call answers 0 once status gave the day's coin
    assert park.state(TOKEN)["gift"] is False and park.gift(TOKEN)["gift"] == 0
    clock.t = next_midnight(clock.t) + 1
    assert g.status(TOKEN)["park"]["coins"] == 2 * COIN["gift"]
    assert park.gift(TOKEN)["gift"] == 0
    assert sum(r[2] for r in coin_ledger(g, pid)) == 2 * COIN["gift"]


def test_status_gives_no_free_coin_before_the_taps():
    g, park, clock, pid = setup(taps=COIN["minTaps"] - 1, gifted=False)
    db = g.store._db
    before = db.total_changes
    out = g.status(TOKEN)
    assert out["park"]["coins"] == 0 and "gifted" not in out["park"] and db.total_changes == before
    g.store.update_player(pid, taps_total=COIN["minTaps"])
    assert g.status(TOKEN)["park"]["gifted"] == COIN["gift"]


def test_the_park_gift_call_still_gives_the_coin_first():
    g, park, clock, pid = setup(gifted=False)
    out = park.gift(TOKEN)
    assert out["gift"] == COIN["gift"] and out["park"]["coins"] == COIN["gift"]
    assert g.status(TOKEN)["park"]["coins"] == COIN["gift"]
    assert coin_ledger(g, pid) == [(day_of(clock()), "gift", COIN["gift"], 1)]


def test_status_inside_a_tap_report_transaction_gives_the_coin_once():
    g, park, clock, pid = setup(gifted=False)
    g.report_activity(TOKEN, 10, session="s", sequence=1)
    clock.t = next_midnight(clock.t) + 1
    # report_activity answers a replayed sequence from inside its transaction: the coin is given there
    out = g.report_activity(TOKEN, 10, session="s", sequence=1)
    assert out["credited"] == 0 and out["park"]["coins"] == 2 * COIN["gift"] and out["park"]["gifted"] == COIN["gift"]
    assert g.status(TOKEN)["park"]["coins"] == 2 * COIN["gift"]
    assert [r[1:] for r in coin_ledger(g, pid)] == [("gift", COIN["gift"], 1)] * 2


def test_a_server_without_the_park_gives_no_coin():
    g = Game(Store(":memory:"), tiny_manifest(), now=Clock())
    pid = g.status(TOKEN)["player"]
    g.store.update_player(pid, taps_total=10**6)
    assert "park" not in g.status(TOKEN) and g.store.get_player(pid, g.now())["coins"] == 0


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
    assert r.status_code == 200 and r.json()["gift"] == COIN["gift"]
    r = client.post("/api/park/coins", headers=headers, json={"count": 2})
    assert r.status_code == 200 and r.json()["park"]["coins"] == COIN["gift"] + 2
    r = client.post("/api/park/coins", headers=headers, json={"count": 100})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_shards"
