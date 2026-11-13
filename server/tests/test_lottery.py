import json
import random

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import Game, GameError
from app.lottery import (PRIZE, ROLL_SECOND, ROLL_TOP, Lottery, commitment, day_start, pools, settle, tier_of)
from app.manifest import Manifest
from app.park import Park
from app.store import Store, day_of
from fixtures import Clock

TOKENS = [f"lottery-player-token-{i:04d}" for i in range(6)]
M = Manifest.load()
CFG = M.park["lottery"]
PRICE = M.park["coin"]["price"]


class Picks:
    """Winning numbers handed out in order, one per new day."""

    def __init__(self, *numbers: str) -> None:
        self.numbers = list(numbers)

    def __call__(self) -> str:
        return self.numbers.pop(0) if self.numbers else "999"


def setup(*winning: str, players=2, coins=50):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    park = Park(lambda: g)
    lot = Lottery(lambda: g, park, pick=Picks(*winning))
    pids = []
    for token in TOKENS[:players]:
        pid = g.status(token)["player"]
        g.store.update_player(pid, coins=coins, taps_total=10_000)
        pids.append(pid)
    return g, park, lot, clock, pids


def at(clock, minute: float, days: int = 0) -> None:
    """Moves the clock to [minute] of the China day, [days] after the current one."""
    clock.t = day_start(clock.t) + days * 86400 + minute * 60


def shards(g, pid):
    return g.store.get_player(pid, g.now())["shards"]


# ------------------------------------------------------------------ the number and its hash
def test_the_number_is_fixed_before_the_first_ticket_and_only_its_hash_shows():
    g, _, lot, clock, pids = setup("042")
    state = lot.state(TOKENS[0])
    row = g.store.lottery_day(day_of(clock()))
    assert row["number"] == "042" and len(row["salt"]) >= 32  # 128 bits or more as hex
    assert state["hash"] == row["hash"] == commitment("042", row["salt"])
    assert "number" not in state and "salt" not in state and state["last"] is None
    lot.buy(TOKENS[0], ["042"])
    assert g.store.lottery_day(day_of(clock()))["hash"] == row["hash"]


def test_the_loop_makes_the_day_at_midnight():
    g, _, lot, clock, _ = setup("100", "200")
    at(clock, 0.5, days=1)
    lot.tick()
    assert g.store.lottery_day(day_of(clock()))["number"] == "100"


def test_the_draw_publishes_a_number_and_salt_matching_the_hash():
    g, _, lot, clock, _ = setup("731")
    lot.buy(TOKENS[0], ["731"])
    before = lot.state(TOKENS[0])["hash"]
    at(clock, CFG["drawAt"])
    assert lot.tick() == [day_of(clock())]
    last = lot.state(TOKENS[0])["last"]
    assert last["number"] == "731" and last["hash"] == before == commitment(last["number"], last["salt"])


# ------------------------------------------------------------------------------- tickets
def test_tickets_cost_a_coin_each_and_stop_at_the_daily_limit():
    g, park, lot, _, pids = setup()
    out = lot.buy(TOKENS[0], ["001", "001"], 3)
    assert out["park"]["coins"] == 50 - 5 and len(out["bought"]) == 5
    assert out["lottery"]["tickets"] == out["bought"] and out["lottery"]["left"] == CFG["daily"] - 5
    with pytest.raises(GameError) as e:
        lot.buy(TOKENS[0], [], CFG["daily"] - 4)
    assert e.value.code == "lottery_cap"
    assert park.state(TOKENS[0])["coins"] == 45  # all or nothing
    lot.buy(TOKENS[0], [], CFG["daily"] - 5)
    with pytest.raises(GameError) as e:
        lot.buy(TOKENS[0], ["123"])
    assert e.value.code == "lottery_cap"


def test_random_numbers_are_distinct_and_skip_the_saves_own():
    g, _, lot, _, _ = setup()
    lot.buy(TOKENS[0], ["005"])
    out = lot.buy(TOKENS[0], ["006"], 8)
    picked = out["bought"][1:]
    assert len(set(picked)) == 8 and not {"005", "006"} & set(picked)
    assert all(len(n) == 3 and n.isdigit() for n in picked)


def test_bad_numbers_counts_and_missing_coins():
    g, _, lot, _, pids = setup()
    for bad in (["1000"], ["7"], ["abc"], [""], [" 12"], [12], ["١٢٣"]):
        with pytest.raises(GameError) as e:
            lot.buy(TOKENS[0], bad)
        assert e.value.code == "bad_number"
    for numbers, count in (([], 0), ([], -1)):
        with pytest.raises(GameError) as e:
            lot.buy(TOKENS[0], numbers, count)
        assert e.value.code == "bad_count"
    g.store.update_player(pids[0], coins=1)
    with pytest.raises(GameError) as e:
        lot.buy(TOKENS[0], ["001", "002"])
    assert e.value.code == "no_coins"
    assert g.store.lottery_tickets(day_of(g.now())) == []


def test_sales_close_at_close_time_and_open_the_next_day():
    g, _, lot, clock, _ = setup()
    at(clock, CFG["closeAt"] - 1 / 60)
    lot.buy(TOKENS[0], ["001"])
    at(clock, CFG["closeAt"])
    assert lot.state(TOKENS[0])["open"] is False
    with pytest.raises(GameError) as e:
        lot.buy(TOKENS[0], ["002"])
    assert e.value.code == "lottery_closed"
    at(clock, 1, days=1)
    assert lot.buy(TOKENS[0], ["002"])["lottery"]["tickets"] == ["002"]


def test_coins_spent_on_tickets_get_stamps_and_ledger_rows():
    g, park, lot, clock, pids = setup()
    lot.buy(TOKENS[0], [], 4)
    assert park.state(TOKENS[0])["stampsTotal"] == 4
    rows = g.store.coin_ledger_by_day(day_of(clock()))
    assert [(r["source"], r["amount"]) for r in rows] == [("lottery", -4)]


# ---------------------------------------------------------------------------- prize math
def test_tiers_count_only_the_best_one():
    assert tier_of("123", "123") == 1
    assert tier_of("923", "123") == 2
    assert tier_of("993", "123") == 3
    assert tier_of("124", "123") == 0
    assert tier_of("321", "123") == 0


def test_pools_take_shares_of_sales_plus_rollovers():
    sales = 100
    top, second, overflow = pools(CFG, PRICE, sales, 1000, 77)
    assert top == int(CFG["top"] * sales * PRICE) + 1000
    assert second == int(CFG["second"] * sales * PRICE) + 77 and overflow == 0


def test_the_top_above_its_cap_joins_that_days_second():
    roll = CFG["topCap"] - 1000
    top, second, overflow = pools(CFG, PRICE, 100, roll, 50)
    raw = int(CFG["top"] * 100 * PRICE) + roll
    assert top == CFG["topCap"] and overflow == raw - CFG["topCap"]
    assert second == int(CFG["second"] * 100 * PRICE) + 50 + overflow


def test_splits_round_down_and_the_remainder_rolls_over():
    tickets = [(1, "123"), (2, "123"), (3, "123"), (4, "023"), (5, "923"), (6, "003"), (7, "555")]
    s = settle(CFG, PRICE, "123", tickets, roll_top=1, roll_second=2)
    top, second, _ = pools(CFG, PRICE, 7, 1, 2)
    assert s.winners == {"top": 3, "second": 2, "third": 1}
    assert s.each == {"top": top // 3, "second": second // 2, "third": CFG["third"]}
    assert s.roll == {"top": top % 3, "second": second % 2}
    assert sorted(s.prizes) == [(1, 1, top // 3), (2, 1, top // 3), (3, 1, top // 3), (4, 2, second // 2),
                                (5, 2, second // 2), (6, 3, CFG["third"])]


def test_pools_without_winners_roll_over_whole():
    s = settle(CFG, PRICE, "123", [(1, "456"), (2, "003")], roll_top=500, roll_second=9)
    top, second, _ = pools(CFG, PRICE, 2, 500, 9)
    assert s.roll == {"top": top, "second": second} and s.prizes == [(2, 3, CFG["third"])]


def test_top_and_second_shares_are_conserved_over_many_days():
    rng = random.Random(7)
    roll_top = roll_second = paid = 0
    sold = 0
    for _ in range(400):
        n = rng.randint(0, 60)
        sold += n
        tickets = [(i, f"{rng.randrange(1000):03d}") for i in range(n)]
        s = settle(CFG, PRICE, f"{rng.randrange(1000):03d}", tickets, roll_top, roll_second)
        paid += sum(p for _, t, p in s.prizes if t in (1, 2))
        roll_top, roll_second = s.roll["top"], s.roll["second"]
    assert paid + roll_top + roll_second == int((CFG["top"] + CFG["second"]) * sold * PRICE)


# ---------------------------------------------------------------------------------- draw
def test_the_draw_pays_winners_through_the_ledger_and_rolls_over():
    g, _, lot, clock, (a, b, c) = setup("123", players=3)
    lot.buy(TOKENS[0], ["123", "923", "456"])  # top, second, nothing
    lot.buy(TOKENS[1], ["123", "003"])  # top, third
    lot.buy(TOKENS[2], ["777"])
    before = {p: shards(g, p) for p in (a, b, c)}
    top, second, _ = pools(CFG, PRICE, 6, 0, 0)
    assert lot.state(TOKENS[0])["prize"] == {"top": top, "second": second, "third": CFG["third"]}
    at(clock, CFG["drawAt"])
    lot.tick()
    day = day_of(clock())
    gains = {p: shards(g, p) - before[p] for p in (a, b, c)}
    assert gains == {a: top // 2 + second, b: top // 2 + CFG["third"], c: 0}
    for p in (a, b, c):
        assert g.store.ledger_amount(p, day, PRIZE) == gains[p]
    assert g.store.park_counter(ROLL_TOP) == top % 2 and g.store.park_counter(ROLL_SECOND) == 0
    last = lot.state(TOKENS[0])["last"]
    assert last["mine"] == [{"number": "123", "tier": "top", "prize": top // 2},
                            {"number": "923", "tier": "second", "prize": second},
                            {"number": "456", "tier": None, "prize": 0}]
    assert last["won"] == gains[a] and last["winners"] == {"top": 2, "second": 1, "third": 1}
    assert g.status(TOKENS[0])["park"]["coins"] == 47


def test_an_unwon_top_prize_grows_the_next_day():
    g, _, lot, clock, _ = setup("123", "555")
    lot.buy(TOKENS[0], ["456"] * 5)
    at(clock, CFG["drawAt"])
    lot.tick()
    top, second, _ = pools(CFG, PRICE, 5, 0, 0)
    state = lot.state(TOKENS[0])
    # After the draw the page shows what has rolled into tomorrow.
    assert state["drawn"] and not state["open"] and state["prize"]["top"] == top
    at(clock, 60, days=1)
    lot.buy(TOKENS[1], ["000"] * 2)
    t2, s2, _ = pools(CFG, PRICE, 2, top, second)
    assert lot.state(TOKENS[1])["prize"]["top"] == t2 and t2 == top + int(CFG["top"] * 2 * PRICE)


def test_the_draw_waits_for_draw_time():
    g, _, lot, clock, _ = setup("123")
    lot.buy(TOKENS[0], ["123"])
    at(clock, CFG["drawAt"] - 1 / 60)
    assert lot.tick() == []
    at(clock, CFG["drawAt"])
    assert lot.tick() == [day_of(clock())]


def test_missed_draws_are_caught_up_on_start_once_and_in_order():
    g, park, lot, clock, (a, b) = setup("111", "222")
    lot.buy(TOKENS[0], ["000"] * 3)  # day 1: nobody wins the top
    day1 = day_of(clock())
    at(clock, 60, days=1)
    lot.buy(TOKENS[1], ["222"])  # day 2: wins its top with day 1's rollover
    day2 = day_of(clock())
    before = shards(g, b)
    at(clock, 30, days=2)  # the server was down over both draws
    restarted = Lottery(lambda: g, park, pick=Picks("333"))
    assert restarted.tick() == [day1, day2]
    roll1, roll2, _ = pools(CFG, PRICE, 3, 0, 0)
    t2, _, _ = pools(CFG, PRICE, 1, roll1, roll2)
    assert shards(g, b) - before == t2
    assert restarted.tick() == [] and restarted.draw(day1) is None and lot.draw(day2) is None
    assert shards(g, b) - before == t2
    assert g.store.lottery_undrawn() == [day_of(clock())]


def test_the_draw_is_told_server_wide_with_every_top_winner():
    g, park, lot, clock, (a, b, c) = setup("123", players=3)
    g.store.update_player(a, loadout='{"nick": "阿草"}')
    g.store.update_player(b, loadout='{"nick": "小草"}')
    lot.buy(TOKENS[1], ["123"])
    lot.buy(TOKENS[0], ["123", "123", "023"])
    at(clock, CFG["drawAt"])
    lot.tick()
    news = g.status(TOKENS[2])["park"]["news"]
    assert len(news) == 1
    item = news[0]
    assert item["kind"] == "lottery_draw" and item["number"] == "123" and item["nick"] == "小草"
    assert item["nicks"] == ["小草", "阿草"]
    assert item["winners"] == {"top": 3, "second": 1, "third": 0}


def test_a_draw_without_a_top_winner_is_told_without_a_nick_and_an_empty_day_is_not_told():
    g, _, lot, clock, _ = setup("123", "456")
    lot.buy(TOKENS[0], ["023"])
    at(clock, CFG["drawAt"])
    lot.tick()
    news = g.status(TOKENS[1])["park"]["news"]
    assert [(n["nick"], n["nicks"], n["winners"]["second"]) for n in news] == [("", [], 1)]
    at(clock, CFG["drawAt"], days=1)
    lot.tick()
    assert g.store.lottery_last_drawn()["day"] == day_of(clock())
    assert len(g.store.park_news_since(0, 10)) == 1


def test_history_lists_the_saves_last_seven_drawn_days_with_tickets():
    g, _, lot, clock, _ = setup(*[f"{i:03d}" for i in range(10)])
    for i in range(10):
        if i != 4:  # no tickets that day
            lot.buy(TOKENS[0], [f"{i:03d}" if i % 2 else "999"])  # odd days win the top
        if i == 9:
            break  # the last day is not drawn yet
        at(clock, CFG["drawAt"])
        lot.tick()
        at(clock, 60, days=1)
    history = lot.state(TOKENS[0])["history"]
    days = [h["day"] for h in history]
    assert len(history) == 7 and days == sorted(days, reverse=True)
    assert [h["number"] for h in history] == ["008", "007", "006", "005", "003", "002", "001"]
    assert all((h["won"] > 0) == (int(h["number"]) % 2 == 1) for h in history)
    assert lot.state(TOKENS[1])["history"] == []


def test_the_park_result_counts_lottery_prizes():
    g, park, lot, clock, _ = setup("123")
    lot.buy(TOKENS[0], ["003"])
    at(clock, CFG["drawAt"])
    lot.tick()
    assert park.state(TOKENS[0])["today"]["won"] == CFG["third"]


def test_sleep_wakes_for_draw_time_and_midnight():
    _, _, lot, clock, _ = setup()
    at(clock, CFG["drawAt"] - 0.5)
    assert lot.sleep_for() == pytest.approx(30.5)
    at(clock, 24 * 60 - 1 / 60)
    assert lot.sleep_for() == pytest.approx(1.5)
    at(clock, 600)
    assert lot.sleep_for() == 60


def test_http_lottery(monkeypatch):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    monkeypatch.setattr(main, "game", g)
    client = TestClient(main.app)
    headers = {"X-Player-Token": TOKENS[0]}
    pid = client.get("/api/me", headers=headers).json()["player"]
    g.store.update_player(pid, coins=5, taps_total=10_000)
    r = client.get("/api/park/lottery", headers=headers)
    assert r.status_code == 200 and r.json()["tickets"] == [] and len(r.json()["hash"]) == 64
    r = client.post("/api/park/lottery", headers=headers, json={"numbers": ["007"], "random": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["park"]["coins"] == 2 and body["lottery"]["tickets"][0] == "007" and len(body["bought"]) == 3
    r = client.post("/api/park/lottery", headers=headers, json={"numbers": ["7"]})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_number"
    r = client.post("/api/park/lottery", headers=headers, json={"random": 3})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_coins"


# ---------------------------------------------------------------------------- simulation
def simulate(daily: int, days: int, seed: int = 1) -> dict:
    """Steady [daily] tickets on uniform random numbers for [days] days: the share of sales paid back, the share
    still in the rollovers at the end, and the mean days between top prizes."""
    rng = random.Random(seed)
    roll_top = roll_second = paid = 0
    tops = 0
    for _ in range(days):
        tickets = [(i, f"{rng.randrange(1000):03d}") for i in range(daily)]
        s = settle(CFG, PRICE, f"{rng.randrange(1000):03d}", tickets, roll_top, roll_second)
        paid += sum(p for _, _, p in s.prizes)
        roll_top, roll_second = s.roll["top"], s.roll["second"]
        tops += s.winners["top"] > 0
    sold = daily * days * PRICE
    return {"paid": paid / sold, "left": (roll_top + roll_second) / sold, "topEvery": days / max(1, tops)}


def test_the_average_return_is_about_the_design_value():
    expected = CFG["top"] + CFG["second"] + 0.09 * CFG["third"] / PRICE  # 70.8% with the default numbers
    out = simulate(300, 1500)
    assert out["paid"] + out["left"] == pytest.approx(expected, abs=0.005)
    assert out["paid"] == pytest.approx(expected, abs=0.01)
