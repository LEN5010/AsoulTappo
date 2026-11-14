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
T0 = park_race.opened_at(CFG, 1_800_000_000)  # a boundary: a race opens its bets then


def seeds():
    n = iter(range(1, 10**6))
    return lambda: next(n).to_bytes(32, "big")


def manifest(popular=False):
    """The manifest; [popular]: draw each race's popularity as it says. Off, every race opens at the flat odds (4.2,
    2.1, 4.2), which the worked numbers in these tests start from."""
    m = Manifest.load()
    if not popular:
        m.park["race"].pop("popularity", None)
    return m


def make(path=":memory:", clock=None, coins=50, popular=False):
    clock = clock or Clock(T0 + 1)
    g = Game(Store(path), manifest(popular), now=clock)
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
    for secret in ("seed", "moves", "ranking", "start", "order", "rolls", "rest", "endsAt", "leadMs", "rollMs",
                   "stepMs", "slowFrom", "slowMs"):
        assert secret not in r
    su = r["setup"]
    assert set(su) == {"boost", "trip", "portal", "flip"}
    lo, hi = CFG["squares"]["range"]
    squares = [su["boost"], su["trip"], *su["portal"], su["flip"]]
    assert all(lo <= q <= hi for q in squares) and len(set(squares)) == 5
    g0, g1 = CFG["squares"]["portalGap"]
    assert g0 <= su["portal"][1] - su["portal"][0] <= g1
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


def test_each_race_opens_at_odds_leaning_on_its_popularity():
    g, races, clock, _ = make(popular=True)
    races.tick()
    r = races.view(TOKEN)["race"]
    pop = r["setup"]["popularity"]
    lo, hi = CFG["popularity"]
    assert set(pop) == set(MEMBERS) and all(lo <= w <= hi for w in pop.values()) and len(set(pop.values())) > 1
    # The squares are dealt before the popularity, from the same dealer: the same as a dealer drawing no popularity.
    assert {k: v for k, v in r["setup"].items() if k != "popularity"} == race.deal(race.Rules.of(CFG, MEMBERS),
                                                                                    random.Random(3))
    opening = race.odds(CFG, MEMBERS, {}, pop)
    assert r["odds"] == {k: {m: t / 10 for m, t in per.items()} for k, per in opening.items()}
    assert len(set(r["odds"]["win"].values())) > 1
    # A bet locks the odds shown, and the stakes move them from there.
    fav = min(MEMBERS, key=lambda m: r["odds"]["win"][m])
    races.bet(TOKEN, T0, "win", fav, 2, r["odds"]["win"][fav])
    r = races.view(TOKEN)["race"]
    assert r["mine"] == [{"kind": "win", "member": fav, "coins": 2, "odds": opening["win"][fav] / 10}]
    assert r["odds"]["win"] == {m: t / 10 for m, t in race.odds_tenths(CFG, "win", MEMBERS, {fav: 2}, pop).items()}
    # A race prepared before popularity (its setup has none) keeps the flat odds.
    setup = json.loads(row(g, T0)["setup"])
    del setup["popularity"]
    with g.store.transaction() as st:
        st._db.execute("UPDATE park_races SET setup = ? WHERE id = ?", (json.dumps(setup), T0))
    races.bet(TOKEN, T0, "last", fav, 1, 4.2)
    assert races.view(TOKEN)["race"]["odds"]["top2"] == dict.fromkeys(MEMBERS, 2.1)


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
    for k in ("start", "order", "rolls", "moves", "rest", "ranking"):
        assert r[k] == outcome[k], k
    assert sorted(r["start"]) == sorted(MEMBERS) and sorted(r["order"]) == sorted(MEMBERS)
    assert r["rolls"][0] == [{"m": m, "face": r["rolls"][0][i]["face"]} for i, m in enumerate(MEMBERS)]
    steps = len(r["moves"])
    slow = 5 * ((steps - 1) // 5)
    lead = 4000 + 1500 * (len(r["rolls"]) - 1)
    assert (r["leadMs"], r["rollMs"], r["stepMs"], r["slowMs"], r["slowFrom"]) == (lead, 2400, 2500, 3300, slow)
    # The last round fills up with dice for those who never got to move.
    assert [d["m"] for d in r["rest"]] == r["order"][(steps - 1) % 5 + 1:]
    # Each round opens with its dice; the last round plays slowly: its last step starts after slowFrom normal steps,
    # every round's dice and the slow steps before it.
    rounds = slow // 5 + 1
    last_start = (r["startsAt"] * 1000 + r["leadMs"] + rounds * r["rollMs"] + slow * r["stepMs"]
                  + (steps - 1 - slow) * r["slowMs"])
    assert r["endsAt"] * 1000 == last_start + r["slowMs"] + park_race.TAIL_MS
    assert r["endsAt"] <= T0 + CFG["interval"] - park_race.RUN_MARGIN


def test_playback_timing():
    assert park_race.slow_from(30) == 25 and park_race.slow_from(31) == 30 and park_race.slow_from(5) == 0
    # One round of order dice, then each round rolled again adds REROLL_MS.
    assert park_race.lead_ms(1) == 4000 and park_race.lead_ms(3) == 4000 + 2 * 1500
    # 22 steps: five rounds of dice, 20 steps at 2500, the last round's two at 3300.
    assert park_race.playback_ms(4000, 22, 2500, 3300) == 4000 + 5 * 2400 + 20 * 2500 + 2 * 3300 + 4000
    assert park_race.playback_ms(4000, 20, 2500, 3300) == 4000 + 4 * 2400 + 15 * 2500 + 5 * 3300 + 4000
    # The dice scale with the steps; without them (rows from before them) a round costs nothing.
    assert park_race.roll_ms(1250) == 1200 and park_race.playback_ms(0, 5, 1000, 1000, 0) == 5000 + 4000


def test_the_longest_races_play_unhurried():
    window = (CFG["interval"] - CFG["betting"] - park_race.RUN_MARGIN) * 1000
    # Past the longest of most 20000 races (portal and flip squares included: about 85 steps) after six rounds of
    # order dice; about 3 in 100000 run longer and play a little faster (see the next test).
    assert park_race.playback_ms(park_race.lead_ms(7), 86, park_race.STEP_MS, park_race.SLOW_MS) <= window
    rules = race.Rules.of(CFG, MEMBERS)
    deal = random.Random(7)
    longest = 0
    for k in range(3000):
        out = race.run_seed(rules, race.deal(rules, deal), k.to_bytes(32, "big"))
        n = len(out["moves"])
        longest = max(longest, n)
        assert park_race.playback_ms(park_race.lead_ms(len(out["rolls"])), n, park_race.STEP_MS,
                                     park_race.SLOW_MS) <= window
    assert longest <= 86
    g, races, clock, _ = make()
    for rid in range(T0, T0 + 200 * CFG["interval"], CFG["interval"]):
        r = races.prepare(rid)
        assert (r["step_ms"], r["slow_ms"]) == (park_race.STEP_MS, park_race.SLOW_MS)


def test_a_short_run_window_slows_nothing_past_the_next_race():
    g, races, clock, _ = make()
    cfg = g.manifest.park["race"]
    cfg["betting"] = cfg["interval"] - 50
    # The boundaries move with the bets' length (startAt places the start); t0 is the one before T0.
    t0 = park_race.opened_at(cfg, T0)
    clock.t = t0 + 1
    races.tick()
    clock.t = t0 + cfg["betting"]
    races.tick()
    r = races.view(TOKEN)["race"]
    assert r["phase"] == "running"
    # 40 s less RUN_MARGIN for lead, steps and tail: both step lengths shrink together.
    assert r["stepMs"] < 2500 and r["slowMs"] < 3300 and r["rollMs"] < 2400
    assert abs(r["slowMs"] / r["stepMs"] - 3300 / 2500) < 0.01 and r["rollMs"] == r["stepMs"] * 2400 // 2500
    assert r["endsAt"] <= t0 + cfg["interval"] - park_race.RUN_MARGIN
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
    before = g.store.get_player(pid, clock())["coins"]
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
    # Prizes in tenths of a coin: 2 × 4.2, 1 × 2.1, a loss, 1 × 3.4; 13.9 in all, paid as 14 coins.
    prizes = [84, 21, 0, 34]
    assert [b["prize"] for b in g.store.race_bets(T0, pid)] == prizes
    p = g.store.get_player(pid, clock())
    assert p["coins"] == before + 14
    shards = p["shards"]
    assert coin_ledger(g, pid, "race_prize") == (14, 1)
    # The race pays coins, not shards: the park's shard result for the day leaves it out.
    assert g.store.ledger_sum(pid, day_of(clock()), ("race_prize",)) == 0
    assert races.park.state(TOKEN)["today"]["won"] == 0
    v = races.view(TOKEN)
    r = v["race"]
    assert r["phase"] == "done" and [b["prize"] for b in r["mine"]] == [8.4, 2.1, 0, 3.4]
    assert [(b["kind"], b["member"], b["odds"]) for b in r["mine"]] == [
        ("win", w0, 4.2), ("top2", ranking[1], 2.1), ("last", w0, 4.2), ("win", w0, 3.4)]
    assert r["result"] == {"staked": 7, "won": 14, "net": 7}
    assert v["winners"] == [{"id": T0, "member": w0}]
    # 4 × 3.9 = 15.6, paid as 16; the bet on the last one lost.
    assert races.view(OTHER)["race"]["result"] == {"staked": 5, "won": 16, "net": 11}
    assert coin_ledger(g, other, "race_prize") == (16, 1)
    # Settling again pays nothing more.
    assert races.settle(T0) == [] and races.tick() == []
    assert g.store.get_player(pid, clock())["coins"] == p["coins"]
    assert g.store.get_player(pid, clock())["shards"] == shards


def coin_ledger(g, pid, source):
    """The save's coin ledger [source] rows, summed: (coins, rows)."""
    got = g.store._db.execute("SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM coin_ledger WHERE player_id = ? AND "
                              "source = ?", (pid, source)).fetchone()
    return tuple(got)


def test_a_save_s_prizes_on_a_race_are_summed_then_rounded_half_up():
    assert park_race.payout([]) == 0 and park_race.payout([0, 0]) == 0
    assert park_race.payout([4]) == 0 and park_race.payout([5]) == 1
    # Exactly halves go up, unlike round() (2 and 2).
    assert park_race.payout([15]) == 2 and park_race.payout([25]) == 3
    # Summed first, rounded once: 4.4 + 4.4 = 8.8 is 9 coins, not 4 + 4.
    assert park_race.payout([44, 44]) == 9
    assert park_race.payout(b for b in (11, 11, 11)) == 3


def test_big_wins_are_told_to_rooms():
    g, races, clock, pid, other, ranking, before, wins = settle_with_bets(roomAt=1)
    won = g.store.get_player(pid, clock())["coins"] - before
    assert won == 14
    assert wins == [{"pid": pid, "coins": 14}, {"pid": other, "coins": 16}]
    assert park_race.room_message("peer", 14) == {"type": "race_win", "id": "peer", "coins": 14}
    _, _, _, _, _, _, _, wins = settle_with_bets(roomAt=16)
    assert wins == [{"pid": other, "coins": 16}]
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
        # The bets and the refund may fall on different days (a day of bets): summed over the days.
        ledger = st._db.execute("SELECT source, SUM(amount) AS amount FROM coin_ledger WHERE player_id = ? "
                                "GROUP BY source", (pid,)).fetchall()
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


def test_a_row_from_before_the_rounds_dice_plays_without_them():
    g, races, clock, pid, other, ranking, before, wins = settle_with_bets()
    old = json.loads(row(g, T0)["result"])
    del old["rest"]
    with g.store.transaction() as st:
        st._db.execute("UPDATE park_races SET result = ? WHERE id = ?", (json.dumps(old), T0))
    r = races.view(TOKEN)["race"]
    assert r["rollMs"] == 0 and r["rest"] == [] and r["moves"] == old["moves"]


def test_http_race_and_bet(monkeypatch):
    clock = Clock(T0 + 1)
    g = Game(Store(":memory:"), manifest(), now=clock)
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
    assert r["id"] == T0 and set(r["setup"]) == {"boost", "trip", "portal", "flip"} and r["mine"] == []
    races.bet(TOKEN, T0, "win", "jiaran", 1)
    races.bet(TOKEN, T0, "win", "jiaran", 1)
    assert len(races.view(TOKEN)["race"]["mine"]) == 2
    g.store.close()
    g, races, clock, _ = make(path)
    assert len(races.view(TOKEN)["race"]["mine"]) == 2
    g.store.close()


def test_one_race_a_day_starts_at_seven_in_the_evening_china_time():
    # The manifest's schedule: bets open ten minutes after a start and run until the next day's 19:00.
    china = lambda t: (t + 8 * 3600) % 86400
    for now in (1_800_000_000, 1_800_030_000, 1_800_060_000):
        opened = park_race.opened_at(CFG, now)
        assert opened <= now < opened + CFG["interval"]
        assert china(opened + CFG["betting"]) == 19 * 3600
        assert china(opened) == 19 * 3600 + 600
    # Without startAt the boundaries are plain multiples of the interval.
    plain = {k: v for k, v in CFG.items() if k != "startAt"}
    assert park_race.opened_at(plain, 1_800_000_000) % CFG["interval"] == 0
