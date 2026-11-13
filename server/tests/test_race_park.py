"""The dumpling race's schedule, bets and settlement (app/park_race.py)."""
import hashlib
import json
import random

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import park_race, race
from app.game import Game, GameError
from app.manifest import Manifest
from app.park import Park
from app.park_race import Races
from app.store import Store, day_of
from fixtures import Clock

TOKEN = "race-player-token-000001"
OTHER = "race-player-token-000002"
M = Manifest.load()
CFG = M.park["race"]
PRICE = M.park["coin"]["price"]
T0 = 1_800_000_000  # a multiple of the interval


def seeds():
    n = iter(range(1, 10**6))
    return lambda: next(n).to_bytes(32, "big")


def make(path=":memory:", clock=None, coins=50):
    clock = clock or Clock(T0 + 1)
    g = Game(Store(path), Manifest.load(), now=clock)
    park = Park(lambda: g)
    races = Races(lambda: g, park, sims=300, dealer=random.Random(3), seeds=seeds())
    pids = []
    for token in (TOKEN, OTHER):
        pid = g.status(token)["player"]
        g.store.update_player(pid, coins=coins)
        pids.append(pid)
    return g, races, clock, pids


def row(g, rid):
    return g.store.race_get(rid)


def test_bets_open_at_the_boundary_with_only_the_hash_public():
    g, races, clock, _ = make()
    races.tick()
    v = races.view(TOKEN)
    r = v["race"]
    assert r["id"] == T0 and r["phase"] == "betting" and r["startsAt"] == T0 + CFG["betting"]
    assert v["nextAt"] == T0 + CFG["interval"]
    seed = bytes.fromhex(row(g, T0)["seed"])
    assert len(seed) * 8 >= 128 and r["hash"] == hashlib.sha256(seed).hexdigest()
    for secret in ("seed", "moves", "ranking", "start", "endsAt", "stepMs"):
        assert secret not in r
    assert set(r["setup"]["moods"]) == set(CFG["skills"])
    assert sorted(r["setup"]["moods"].values()) == sorted(m["id"] for m in CFG["moods"])
    lo, hi = CFG["squares"]["range"]
    assert lo <= r["setup"]["boost"] <= hi and lo <= r["setup"]["trip"] <= hi
    assert r["setup"]["boost"] != r["setup"]["trip"]
    for kind in CFG["kinds"]:
        assert all(CFG["minOdds"] <= o <= race.MAX_ODDS_TENTHS / 10 for o in r["odds"][kind].values())
    # The next race is ready but hidden until its bets open.
    assert row(g, T0 + CFG["interval"]) is not None
    assert v["last"] is None and v["winners"] == []


def test_a_server_starting_late_in_the_window_waits_for_the_next_race():
    g, races, clock, _ = make(clock=Clock(T0 + CFG["betting"] - park_race.MIN_BETTING + 1))
    races.tick()
    assert row(g, T0) is None and row(g, T0 + CFG["interval"]) is not None
    assert races.view(TOKEN)["race"] is None


def test_bets_spend_coins_and_stay_within_the_cap():
    g, races, clock, (pid, other) = make()
    races.tick()
    out = races.bet(TOKEN, T0, "win", "jiaran", 3)
    assert out["park"]["coins"] == 47 and out["park"]["stampsTotal"] == 3
    races.bet(TOKEN, T0, "last", "nailin", 2)
    races.bet(TOKEN, T0, "win", "jiaran", 1)
    races.bet(OTHER, T0, "top2", "jiaran", 2)
    r = races.view(TOKEN)["race"]
    odds = r["odds"]
    assert r["mine"] == [{"kind": "win", "member": "jiaran", "coins": 4, "odds": odds["win"]["jiaran"]},
                         {"kind": "last", "member": "nailin", "coins": 2, "odds": odds["last"]["nailin"]}]
    assert r["pool"] == {"jiaran": {"coins": 6, "bettors": 2}, "nailin": {"coins": 2, "bettors": 1}}
    with pytest.raises(GameError) as e:
        races.bet(TOKEN, T0, "top2", "xinyi", CFG["maxCoins"] - 6 + 1)
    assert e.value.code == "race_cap"
    races.bet(TOKEN, T0, "top2", "xinyi", CFG["maxCoins"] - 6)
    assert g.store.get_player(pid, clock())["coins"] == 50 - CFG["maxCoins"]
    for args, code in [((T0, "show", "jiaran", 1), "bad_bet"), ((T0, "win", "nobody", 1), "bad_bet"),
                       ((T0, "win", "jiaran", 0), "bad_count"), ((T0 + 1, "win", "jiaran", 1), "no_race"),
                       ((T0 + CFG["interval"], "win", "jiaran", 1), "no_race")]:
        with pytest.raises(GameError) as e:
            races.bet(OTHER, *args)
        assert e.value.code == code
    g.store.update_player(other, coins=0)
    with pytest.raises(GameError) as e:
        races.bet(OTHER, T0, "win", "beila", 1)
    assert e.value.code == "no_coins"


def test_bets_close_at_the_start():
    g, races, clock, _ = make()
    races.tick()
    clock.t = T0 + CFG["betting"]
    with pytest.raises(GameError) as e:
        races.bet(TOKEN, T0, "win", "jiaran", 1)
    assert e.value.code == "race_closed"
    assert races.view(TOKEN)["race"]["phase"] == "starting"


def test_the_start_publishes_the_seed_and_the_moves_it_decides():
    g, races, clock, _ = make()
    races.tick()
    committed = races.view(TOKEN)["race"]["hash"]
    clock.t = T0 + CFG["betting"] + 1
    races.tick()
    r = races.view(TOKEN)["race"]
    assert r["phase"] == "running"
    seed = bytes.fromhex(r["seed"])
    assert hashlib.sha256(seed).hexdigest() == committed
    outcome = race.run_seed(race.Rules.of(CFG), r["setup"], seed)
    assert (r["start"], r["moves"], r["ranking"]) == (outcome["start"], outcome["moves"], outcome["ranking"])
    steps = len(r["moves"])
    assert r["endsAt"] == r["startsAt"] + (r["leadMs"] + steps * r["stepMs"] + park_race.TAIL_MS) / 1000
    assert r["endsAt"] <= T0 + CFG["interval"] - park_race.RUN_MARGIN


def settle_with_bets(roomAt=None):
    g, races, clock, (pid, other) = make()
    if roomAt is not None:
        g.manifest.park["race"]["roomAt"] = roomAt
    races.tick()
    ranking = json.loads(row(g, T0)["ranking"])
    races.bet(TOKEN, T0, "win", ranking[0], 2)
    races.bet(TOKEN, T0, "top2", ranking[1], 1)
    races.bet(TOKEN, T0, "last", ranking[0], 3)
    races.bet(OTHER, T0, "win", ranking[-1], 1)
    before = g.store.get_player(pid, clock())["shards"]
    clock.t = T0 + CFG["betting"]
    races.tick()
    clock.t = row(g, T0)["ends_at"]
    wins = races.tick()
    return g, races, clock, pid, other, ranking, before, wins


def test_settlement_pays_each_winning_selection_and_reports_the_net():
    g, races, clock, pid, other, ranking, before, wins = settle_with_bets()
    odds = json.loads(row(g, T0)["odds"])
    prizes = [2 * PRICE * odds["win"][ranking[0]] // 10, PRICE * odds["top2"][ranking[1]] // 10]
    p = g.store.get_player(pid, clock())
    assert p["shards"] == before + sum(prizes)
    assert g.store.ledger_sum(pid, day_of(clock()), ("race_prize",)) == sum(prizes)
    v = races.view(TOKEN)
    r = v["race"]
    assert r["phase"] == "done" and [b["prize"] for b in r["mine"]] == [*prizes, 0]
    assert r["result"] == {"staked": 6 * PRICE, "won": sum(prizes), "net": sum(prizes) - 6 * PRICE}
    assert v["winners"] == [{"id": T0, "member": ranking[0]}]
    assert races.view(OTHER)["race"]["result"] == {"staked": PRICE, "won": 0, "net": -PRICE}
    assert g.store.ledger_sum(other, day_of(clock()), ("race_prize",)) == 0
    # Settling again pays nothing more.
    assert races.settle(T0) == [] and races.tick() == []
    assert g.store.get_player(pid, clock())["shards"] == p["shards"]


def test_big_wins_are_told_to_rooms():
    g, races, clock, pid, other, ranking, before, wins = settle_with_bets(roomAt=1)
    won = g.store.get_player(pid, clock())["shards"] - before
    assert wins == [{"pid": pid, "shards": won}]
    _, _, _, _, _, _, _, wins = settle_with_bets(roomAt=10**9)
    assert wins == []


def test_the_next_race_follows_and_the_last_one_stays_shown():
    g, races, clock, pid, other, ranking, before, wins = settle_with_bets()
    clock.t = T0 + CFG["interval"] + 1
    races.tick()
    v = races.view(TOKEN)
    assert v["race"]["id"] == T0 + CFG["interval"] and v["race"]["phase"] == "betting"
    assert v["last"]["id"] == T0 and v["last"]["ranking"] == ranking and "moves" in v["last"]
    assert v["last"]["result"]["won"] > 0
    assert row(g, T0 + 2 * CFG["interval"]) is not None


def test_a_race_missed_while_down_is_called_off_and_refunded():
    g, races, clock, (pid, other) = make()
    g.store.update_player(pid, coins=10, stamps_total=28)
    races.tick()
    races.bet(TOKEN, T0, "win", "jiaran", 3)
    races.bet(TOKEN, T0, "last", "sinuo", 2)
    # Five stamps passed 30, which turned into a coin: 10 - 5 + 1.
    assert g.store.get_player(pid, clock())["coins"] == 6
    shards = g.store.get_player(pid, clock())["shards"]
    clock.t = T0 + CFG["betting"] + park_race.START_GRACE + 1
    assert races.tick() == []
    p = g.store.get_player(pid, clock())
    assert (p["coins"], p["stamps_total"], p["shards"]) == (10, 28, shards)
    r = races.view(TOKEN)["race"]
    assert r["phase"] == "void" and "seed" not in r and "moves" not in r
    assert races.view(TOKEN)["winners"] == []
    with g.store.transaction() as st:
        ledger = st._db.execute("SELECT source, amount FROM coin_ledger WHERE player_id = ? ORDER BY source",
                                (pid,)).fetchall()
    assert {r["source"]: r["amount"] for r in ledger} == {"race": -5, "race_refund": 5, "stamp": 0}


def test_a_start_a_few_seconds_late_still_runs():
    g, races, clock, _ = make()
    races.tick()
    clock.t = T0 + CFG["betting"] + park_race.START_GRACE
    races.tick()
    assert row(g, T0)["status"] == "running"


def test_a_restart_resumes_the_race(tmp_path):
    path = str(tmp_path / "race.db")
    clock = Clock(T0 + 1)
    g, races, _, (pid, _) = make(path, clock)
    races.tick()
    committed = row(g, T0)["hash"]
    races.bet(TOKEN, T0, "win", "jiaran", 2)
    g.store.close()
    clock.t = T0 + 100
    g, races, _, _ = make(path, clock, coins=48)
    races.tick()
    v = races.view(TOKEN)["race"]
    assert v["hash"] == committed and v["phase"] == "betting" and len(v["mine"]) == 1
    races.bet(TOKEN, T0, "top2", "nailin", 1)
    clock.t = T0 + CFG["betting"]
    races.tick()
    # Down again while it runs: it is settled after the restart, even late.
    g.store.close()
    clock.t = row_ends = T0 + CFG["interval"] - 1
    g, races, _, _ = make(path, clock, coins=47)
    assert row(g, T0)["status"] == "running" and row(g, T0)["ends_at"] <= row_ends
    races.tick()
    assert row(g, T0)["status"] == "settled"
    g.store.close()


def test_old_results_are_dropped_but_still_shown():
    g, races, clock, pid, other, ranking, before, wins = settle_with_bets()
    moves = races.view(TOKEN)["race"]["moves"]
    clock.t = T0 + park_race.RESULT_KEEP_DAYS * 86400 + CFG["interval"] + 1
    races.tick()
    assert row(g, T0)["result"] == ""
    assert races.settle(T0) == []
    # Nothing ran since (the clock jumped), so it is still the last race, rebuilt from its seed.
    last = races.view(TOKEN)["last"]
    assert last["id"] == T0 and last["moves"] == moves


def test_http_race_and_bet(monkeypatch):
    clock = Clock(T0 + 1)
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    monkeypatch.setattr(main, "game", g)
    monkeypatch.setattr(main.races, "sims", 200)
    client = TestClient(main.app)
    headers = {"X-Player-Token": TOKEN}
    pid = client.get("/api/me", headers=headers).json()["player"]
    g.store.update_player(pid, coins=5)
    assert client.get("/api/park/race", headers=headers).json()["race"] is None
    main.races.tick()
    r = client.get("/api/park/race", headers=headers).json()
    assert r["race"]["id"] == T0 and r["now"] == T0 + 1
    out = client.post("/api/park/race/bet", headers=headers,
                      json={"race": T0, "kind": "win", "member": "beila", "coins": 2})
    assert out.status_code == 200 and out.json()["park"]["coins"] == 3
    assert out.json()["race"]["mine"][0]["coins"] == 2
    out = client.post("/api/park/race/bet", headers=headers,
                      json={"race": T0, "kind": "win", "member": "beila", "coins": 9})
    assert out.status_code == 409 and out.json()["detail"]["code"] == "race_cap"
    clock.t = T0 + CFG["betting"]
    out = client.post("/api/park/race/bet", headers=headers,
                      json={"race": T0, "kind": "win", "member": "beila", "coins": 1})
    assert out.status_code == 409 and out.json()["detail"]["code"] == "race_closed"
