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
from app.park import POOL, Park
from app.park_race import OddsChanged, Races
from app.store import Store, day_of
from fixtures import Clock

TOKEN = "race-player-token-000001"
OTHER = "race-player-token-000002"
M = Manifest.load()
CFG = M.park["race"]
MEMBERS = tuple(c["id"] for c in M.data["characters"])
PRICE = M.park["coin"]["price"]
T0 = 1_800_000_000  # a multiple of the interval


def seeds():
    n = iter(range(1, 10**6))
    return lambda: next(n).to_bytes(32, "big")


def make(path=":memory:", clock=None, coins=50):
    clock = clock or Clock(T0 + 1)
    g = Game(Store(path), Manifest.load(), now=clock)
    park = Park(lambda: g)
    races = Races(lambda: g, park, dealer=random.Random(3), seeds=seeds())
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
    for secret in ("seed", "moves", "ranking", "start", "order", "rolls", "endsAt", "leadMs", "stepMs", "slowFrom",
                   "slowMs"):
        assert secret not in r
    assert set(r["setup"]) == {"boost", "trip"}
    lo, hi = CFG["squares"]["range"]
    assert lo <= r["setup"]["boost"] <= hi and lo <= r["setup"]["trip"] <= hi
    assert r["setup"]["boost"] != r["setup"]["trip"]
    assert r["odds"] == {"win": dict.fromkeys(MEMBERS, 4.2), "top2": dict.fromkeys(MEMBERS, 2.1),
                         "last": dict.fromkeys(MEMBERS, 4.2)}
    assert r["pool"] == {kind: dict.fromkeys(MEMBERS, 0) for kind in CFG["kinds"]}
    assert r["bettors"] == 0 and r["mine"] == []
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
    # Each bet is its own row at the odds before it: 4.2, then 0.85 × 5 × 103 / 115 = 3.8 with 3 on jiaran.
    assert r["mine"] == [{"kind": "win", "member": "jiaran", "coins": 3, "odds": 4.2},
                         {"kind": "last", "member": "nailin", "coins": 2, "odds": 4.2},
                         {"kind": "win", "member": "jiaran", "coins": 1, "odds": 3.8}]
    assert r["pool"]["win"] == {**dict.fromkeys(MEMBERS, 0), "jiaran": 4}
    assert r["pool"]["top2"] == {**dict.fromkeys(MEMBERS, 0), "jiaran": 2}
    assert r["pool"]["last"] == {**dict.fromkeys(MEMBERS, 0), "nailin": 2}
    assert r["bettors"] == 2
    assert r["odds"]["win"] == {m: race.odds_tenths(CFG, "win", MEMBERS, {"jiaran": 4})[m] / 10 for m in MEMBERS}
    assert r["odds"]["win"]["jiaran"] == 3.6 and r["odds"]["win"]["beila"] == 4.4
    assert races.view(OTHER)["race"]["mine"] == [{"kind": "top2", "member": "jiaran", "coins": 2, "odds": 2.1}]
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


def test_a_bet_is_refused_when_its_odds_dropped():
    g, races, clock, (pid, other) = make()
    races.tick()
    shown = races.view(OTHER)["race"]["odds"]["win"]["jiaran"]
    races.bet(TOKEN, T0, "win", "jiaran", 5)
    before = (g.store.get_player(other, clock()), g.store.park_counter(POOL), g.store.race_bets(T0))
    view = races.view(OTHER)["race"]
    with pytest.raises(OddsChanged) as e:
        races.bet(OTHER, T0, "win", "jiaran", 2, shown)
    assert e.value.code == "odds_changed" and e.value.odds == view["odds"]["win"]["jiaran"] < shown
    p = g.store.get_player(other, clock())
    assert (p["coins"], p["stamps_total"]) == (before[0]["coins"], before[0]["stamps_total"])
    assert (g.store.park_counter(POOL), g.store.race_bets(T0)) == before[1:]
    after = races.view(OTHER)["race"]
    assert (after["pool"], after["bettors"], after["mine"]) == (view["pool"], view["bettors"], [])
    # The odds shown now, or lower ones, are taken; the bet gets the current odds.
    races.bet(OTHER, T0, "win", "jiaran", 1, e.value.odds)
    up = races.view(OTHER)["race"]["odds"]["win"]["beila"]
    races.bet(OTHER, T0, "win", "beila", 1, 1.1)
    assert [b["odds"] for b in races.view(OTHER)["race"]["mine"]] == [e.value.odds, up]
    # Float noise in the shown number does not refuse the bet.
    g.store.update_player(other, coins=50)
    races.bet(OTHER, T0, "last", "sinuo", 1, 4.2)


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
    outcome = race.run_seed(race.Rules.of(CFG, MEMBERS), r["setup"], seed)
    for k in ("start", "order", "rolls", "moves", "ranking"):
        assert r[k] == outcome[k], k
    assert sorted(r["start"]) == sorted(MEMBERS) and sorted(r["order"]) == sorted(MEMBERS)
    assert r["rolls"][0] == [{"m": m, "face": r["rolls"][0][i]["face"]} for i, m in enumerate(MEMBERS)]
    steps = len(r["moves"])
    slow = 5 * ((steps - 1) // 5)
    lead = 4000 + 1500 * (len(r["rolls"]) - 1)
    assert (r["leadMs"], r["stepMs"], r["slowMs"], r["slowFrom"]) == (lead, 3000, 4000, slow)
    # The last round plays slowly: its first step starts after slowFrom normal steps.
    last_start = r["startsAt"] * 1000 + r["leadMs"] + slow * r["stepMs"] + (steps - 1 - slow) * r["slowMs"]
    assert r["endsAt"] * 1000 == last_start + r["slowMs"] + park_race.TAIL_MS
    assert r["endsAt"] <= T0 + CFG["interval"] - park_race.RUN_MARGIN


def test_playback_timing():
    assert park_race.slow_from(30) == 25 and park_race.slow_from(31) == 30 and park_race.slow_from(5) == 0
    # One round of order dice, then each round rolled again adds REROLL_MS.
    assert park_race.lead_ms(1) == 4000 and park_race.lead_ms(3) == 4000 + 2 * 1500
    # 22 steps: 20 at 3000, the last round's two at 4000.
    assert park_race.playback_ms(4000, 22, 3000, 4000) == 4000 + 20 * 3000 + 2 * 4000 + 4000


def test_the_longest_races_play_unhurried():
    window = (CFG["interval"] - CFG["betting"] - park_race.RUN_MARGIN) * 1000
    # Past the longest of 20000 races (77 steps with the finish bounce) after six rounds of order dice.
    assert park_race.playback_ms(park_race.lead_ms(7), 80, park_race.STEP_MS, park_race.SLOW_MS) <= window
    rules = race.Rules.of(CFG, MEMBERS)
    deal = random.Random(7)
    longest = 0
    for k in range(3000):
        out = race.run_seed(rules, race.deal(rules, deal), k.to_bytes(32, "big"))
        n = len(out["moves"])
        longest = max(longest, n)
        assert park_race.playback_ms(park_race.lead_ms(len(out["rolls"])), n, park_race.STEP_MS,
                                     park_race.SLOW_MS) <= window
    assert longest <= 80
    g, races, clock, _ = make()
    for rid in range(T0, T0 + 200 * CFG["interval"], CFG["interval"]):
        r = races.prepare(rid)
        assert (r["step_ms"], r["slow_ms"]) == (park_race.STEP_MS, park_race.SLOW_MS)


def test_a_short_run_window_slows_nothing_past_the_next_race():
    g, races, clock, _ = make()
    cfg = g.manifest.park["race"]
    cfg["betting"] = cfg["interval"] - 50
    clock.t = T0 + 1
    races.tick()
    clock.t = T0 + cfg["betting"]
    races.tick()
    r = races.view(TOKEN)["race"]
    assert r["phase"] == "running"
    # 40 s less RUN_MARGIN for lead, steps and tail: both step lengths shrink together.
    assert r["stepMs"] < 3000 and r["slowMs"] < 4000
    assert abs(r["slowMs"] / r["stepMs"] - 4 / 3) < 0.01
    assert r["endsAt"] <= T0 + cfg["interval"] - park_race.RUN_MARGIN
    n = len(r["moves"])
    assert r["endsAt"] == r["startsAt"] + park_race.playback_ms(r["leadMs"], n, r["stepMs"], r["slowMs"]) / 1000


def settle_with_bets(roomAt=None):
    g, races, clock, (pid, other) = make()
    if roomAt is not None:
        g.manifest.park["race"]["roomAt"] = roomAt
    races.tick()
    ranking = json.loads(row(g, T0)["ranking"])
    races.bet(TOKEN, T0, "win", ranking[0], 2)
    races.bet(TOKEN, T0, "top2", ranking[1], 1)
    races.bet(TOKEN, T0, "last", ranking[0], 3)
    races.bet(OTHER, T0, "win", ranking[0], 4)
    races.bet(OTHER, T0, "win", ranking[-1], 1)
    # Same selection again, at lower odds now.
    races.bet(TOKEN, T0, "win", ranking[0], 1)
    before = g.store.get_player(pid, clock())["shards"]
    clock.t = T0 + CFG["betting"]
    races.tick()
    clock.t = row(g, T0)["ends_at"]
    wins = races.tick()
    return g, races, clock, pid, other, ranking, before, wins


def test_settlement_pays_each_winning_bet_at_its_own_odds():
    g, races, clock, pid, other, ranking, before, wins = settle_with_bets()
    w0 = ranking[0]
    # Locked odds: 4.2 with nothing on it; 2.1 for top two; then 0.85 × 5 × 102 / 110 = 3.9 with 2 on the winner;
    # 0.85 × 5 × 107 / 130 = 3.4 with 6 on it.
    assert [b["odds"] for b in g.store.race_bets(T0, pid)] == [42, 21, 42, 34]
    assert [b["odds"] for b in g.store.race_bets(T0, other)] == [39, 45]
    prizes = [2 * PRICE * 42 // 10, PRICE * 21 // 10, 0, PRICE * 34 // 10]
    p = g.store.get_player(pid, clock())
    assert p["shards"] == before + sum(prizes)
    assert g.store.ledger_sum(pid, day_of(clock()), ("race_prize",)) == sum(prizes)
    v = races.view(TOKEN)
    r = v["race"]
    assert r["phase"] == "done" and [b["prize"] for b in r["mine"]] == prizes
    assert [(b["kind"], b["member"], b["odds"]) for b in r["mine"]] == [
        ("win", w0, 4.2), ("top2", ranking[1], 2.1), ("last", w0, 4.2), ("win", w0, 3.4)]
    assert r["result"] == {"staked": 7 * PRICE, "won": sum(prizes), "net": sum(prizes) - 7 * PRICE}
    assert v["winners"] == [{"id": T0, "member": w0}]
    won = 4 * PRICE * 39 // 10
    assert races.view(OTHER)["race"]["result"] == {"staked": 5 * PRICE, "won": won, "net": won - 5 * PRICE}
    assert g.store.ledger_sum(other, day_of(clock()), ("race_prize",)) == won
    # Settling again pays nothing more.
    assert races.settle(T0) == [] and races.tick() == []
    assert g.store.get_player(pid, clock())["shards"] == p["shards"]


def test_big_wins_are_told_to_rooms():
    g, races, clock, pid, other, ranking, before, wins = settle_with_bets(roomAt=1)
    won = g.store.get_player(pid, clock())["shards"] - before
    assert wins == [{"pid": pid, "shards": won}, {"pid": other, "shards": 4 * PRICE * 39 // 10}]
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
    pool = M.park["lottery"]["pool"]
    assert g.store.park_counter(POOL) == pool["seed"] + 5 * pool["perCoin"]
    shards = g.store.get_player(pid, clock())["shards"]
    clock.t = T0 + CFG["betting"] + park_race.START_GRACE + 1
    assert races.tick() == []
    p = g.store.get_player(pid, clock())
    assert (p["coins"], p["stamps_total"], p["shards"]) == (10, 28, shards)
    assert g.store.park_counter(POOL) == pool["seed"]
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


def test_a_row_from_before_the_order_dice_plays_without_them():
    g, races, clock, pid, other, ranking, before, wins = settle_with_bets()
    old = json.loads(row(g, T0)["result"])
    del old["order"], old["rolls"]
    with g.store.transaction() as st:
        st._db.execute("UPDATE park_races SET result = ? WHERE id = ?", (json.dumps(old), T0))
    r = races.view(TOKEN)["race"]
    assert "order" not in r and "rolls" not in r
    assert r["leadMs"] == park_race.LEAD_MS and r["moves"] == old["moves"]


def test_http_race_and_bet(monkeypatch):
    clock = Clock(T0 + 1)
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    monkeypatch.setattr(main, "game", g)
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
    assert out.json()["race"]["mine"][0]["odds"] == 4.2 and out.json()["race"]["odds"]["win"]["beila"] == 3.9
    out = client.post("/api/park/race/bet", headers=headers,
                      json={"race": T0, "kind": "win", "member": "beila", "coins": 1, "odds": 4.2})
    assert out.status_code == 409 and out.json()["detail"] == {"code": "odds_changed", "message": "赔率变成了 3.9",
                                                                "odds": 3.9}
    assert g.store.get_player(pid, clock())["coins"] == 3
    out = client.post("/api/park/race/bet", headers=headers,
                      json={"race": T0, "kind": "win", "member": "beila", "coins": 1, "odds": 3.9})
    assert out.status_code == 200 and [b["odds"] for b in out.json()["race"]["mine"]] == [4.2, 3.9]
    out = client.post("/api/park/race/bet", headers=headers,
                      json={"race": T0, "kind": "win", "member": "beila", "coins": 9})
    assert out.status_code == 409 and out.json()["detail"]["code"] == "race_cap"
    clock.t = T0 + CFG["betting"]
    out = client.post("/api/park/race/bet", headers=headers,
                      json={"race": T0, "kind": "win", "member": "beila", "coins": 1})
    assert out.status_code == 409 and out.json()["detail"]["code"] == "race_closed"


OLD_RACE_TABLES = """
CREATE TABLE park_races (id INTEGER PRIMARY KEY, starts_at REAL NOT NULL, ends_at REAL NOT NULL,
  step_ms INTEGER NOT NULL, seed TEXT NOT NULL, hash TEXT NOT NULL, setup TEXT NOT NULL, odds TEXT NOT NULL,
  ranking TEXT NOT NULL, result TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open');
CREATE INDEX park_races_status ON park_races (status, id);
CREATE TABLE park_race_bets (race_id INTEGER NOT NULL, player_id TEXT NOT NULL, kind TEXT NOT NULL,
  member TEXT NOT NULL, coins INTEGER NOT NULL, odds INTEGER NOT NULL, prize INTEGER NOT NULL DEFAULT 0,
  ts REAL NOT NULL, PRIMARY KEY (race_id, player_id, kind, member));
INSERT INTO park_races VALUES (1800000000, 1800003300, 1800003400, 1300, '00', 'h',
  '{"moods": {}, "boost": 6, "trip": 9}', '{}', '[]', '', 'open');
INSERT INTO park_race_bets VALUES (1800000000, 'p', 'win', 'jiaran', 2, 42, 0, 1800000001);
"""


def test_a_database_from_the_test_builds_still_opens(tmp_path):
    import sqlite3
    path = str(tmp_path / "old.db")
    db = sqlite3.connect(path)
    db.executescript(OLD_RACE_TABLES)
    db.close()
    g, races, clock, _ = make(path)
    # The old race tables are made anew; the first race comes back with the new rules.
    races.tick()
    r = races.view(TOKEN)["race"]
    assert r["id"] == T0 and set(r["setup"]) == {"boost", "trip"} and r["mine"] == []
    races.bet(TOKEN, T0, "win", "jiaran", 1)
    races.bet(TOKEN, T0, "win", "jiaran", 1)
    assert len(races.view(TOKEN)["race"]["mine"]) == 2
    g.store.close()
    g, races, clock, _ = make(path)
    assert len(races.view(TOKEN)["race"]["mine"]) == 2
    g.store.close()
