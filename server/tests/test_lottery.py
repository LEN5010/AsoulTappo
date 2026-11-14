import json
import random

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import BOARD_DEFAULT_NICK, Game, GameError, board_id
from app.lottery import PRIZE, ROLL_SECOND, Lottery, commitment, day_start, second_pool, settle, tier_of
from app.manifest import Manifest
from app.park import POOL, Park
from app.store import Store, day_of
from fixtures import Clock

TOKENS = [f"lottery-player-token-{i:04d}" for i in range(6)]
M = Manifest.load()
CFG = M.park["lottery"]
PRICE = M.park["coin"]["price"]
SEED, PER_COIN = CFG["pool"]["seed"], CFG["pool"]["perCoin"]


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
        # today's free coin counts as given, so status leaves the coin counts alone
        g.store.update_player(pid, coins=coins, taps_total=10_000, gift_day=day_of(clock()))
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


def test_the_second_prize_is_a_share_of_sales_plus_its_rollover():
    assert second_pool(CFG, PRICE, 100, 77) == int(CFG["second"] * 100 * PRICE) + 77
    assert second_pool(CFG, PRICE, 0, 77) == 77


def test_the_pool_is_split_rounding_down_and_starts_again_at_the_seed_plus_the_remainder():
    tickets = [(1, "123"), (2, "123"), (3, "123"), (4, "023"), (5, "923"), (6, "003"), (7, "555")]
    pool = 100_001
    s = settle(CFG, PRICE, "123", tickets, pool=pool, roll_second=2)
    second = second_pool(CFG, PRICE, 7, 2)
    assert s.winners == {"top": 3, "second": 2, "third": 1}
    assert s.pools == {"top": pool, "second": second}
    assert s.each == {"top": pool // 3, "second": second // 2, "third": CFG["third"]}
    assert s.pool == SEED + pool % 3 and s.roll == {"second": second % 2}
    assert sorted(s.prizes) == [(1, 1, pool // 3), (2, 1, pool // 3), (3, 1, pool // 3), (4, 2, second // 2),
                                (5, 2, second // 2), (6, 3, CFG["third"])]


def test_without_winners_the_pool_and_the_second_carry_over_whole():
    s = settle(CFG, PRICE, "123", [(1, "456"), (2, "003")], pool=54_321, roll_second=9)
    second = second_pool(CFG, PRICE, 2, 9)
    assert s.pool == 54_321 and s.roll == {"second": second} and s.prizes == [(2, 3, CFG["third"])]
    assert s.each == {"top": 0, "second": 0, "third": CFG["third"]}


def test_the_pool_and_the_second_are_conserved_over_many_days():
    rng = random.Random(7)
    pool, roll_second, top_paid, second_paid, sold, fed, wins = SEED, 0, 0, 0, 0, 0, 0
    for _ in range(3000):
        n = rng.randint(0, 60)
        sold += n
        # coins spent on other games feed the pool too
        spent = n + rng.randint(0, 200)
        fed += spent * PER_COIN
        pool += spent * PER_COIN
        tickets = [(i, f"{rng.randrange(1000):03d}") for i in range(n)]
        s = settle(CFG, PRICE, f"{rng.randrange(1000):03d}", tickets, pool, roll_second)
        top_paid += sum(p for _, t, p in s.prizes if t == 1)
        second_paid += sum(p for _, t, p in s.prizes if t == 2)
        wins += s.winners["top"] > 0
        pool, roll_second = s.pool, s.roll["second"]
    assert wins > 10
    assert top_paid + pool == SEED * (wins + 1) + fed
    assert second_paid + roll_second == int(CFG["second"] * sold * PRICE)


# ---------------------------------------------------------------------------------- draw
def test_the_draw_pays_winners_through_the_ledger_and_rolls_over():
    g, _, lot, clock, (a, b, c) = setup("123", players=3)
    lot.buy(TOKENS[0], ["123", "923", "456"])  # top, second, nothing
    lot.buy(TOKENS[1], ["123", "003"])  # top, third
    lot.buy(TOKENS[2], ["777"])
    before = {p: shards(g, p) for p in (a, b, c)}
    top, second = SEED + 6 * PER_COIN, second_pool(CFG, PRICE, 6, 0)
    assert lot.state(TOKENS[0])["prize"] == {"top": top, "second": second, "third": CFG["third"]}
    at(clock, CFG["drawAt"])
    lot.tick()
    day = day_of(clock())
    gains = {p: shards(g, p) - before[p] for p in (a, b, c)}
    assert gains == {a: top // 2 + second, b: top // 2 + CFG["third"], c: 0}
    for p in (a, b, c):
        assert g.store.ledger_amount(p, day, PRIZE) == gains[p]
    assert g.store.park_counter(POOL) == SEED + top % 2 and g.store.park_counter(ROLL_SECOND) == 0
    assert lot.state(TOKENS[0])["prize"]["top"] == SEED + top % 2
    last = lot.state(TOKENS[0])["last"]
    assert last["mine"] == [{"number": "123", "tier": "top", "prize": top // 2},
                            {"number": "923", "tier": "second", "prize": second},
                            {"number": "456", "tier": None, "prize": 0}]
    assert last["won"] == gains[a] and last["winners"] == {"top": 2, "second": 1, "third": 1}
    assert last["each"] == {"top": top // 2, "second": second, "third": CFG["third"]}
    assert g.status(TOKENS[0])["park"]["coins"] == 47


def test_an_unwon_pool_carries_over_and_keeps_growing():
    g, _, lot, clock, _ = setup("123", "555")
    lot.buy(TOKENS[0], ["456"] * 5)
    at(clock, CFG["drawAt"])
    lot.tick()
    top, second = SEED + 5 * PER_COIN, second_pool(CFG, PRICE, 5, 0)
    state = lot.state(TOKENS[0])
    # The draw starts tomorrow's day at once: on sale, with the pool and what has rolled into its second.
    assert state["day"] == day_of(clock() + 86400) and not state["drawn"] and state["open"]
    assert state["prize"]["top"] == top and state["prize"]["second"] == second
    assert g.store.park_counter(POOL) == top
    assert lot.draw(day_of(clock())) is None
    at(clock, 60, days=1)
    lot.buy(TOKENS[1], ["000"] * 2)
    assert lot.state(TOKENS[1])["prize"] == {"top": top + 2 * PER_COIN, "second": second_pool(CFG, PRICE, 2, second),
                                             "third": CFG["third"]}


def test_the_draw_pays_the_pool_fed_by_every_game_and_records_it():
    g, park, lot, clock, (a, b) = setup("123")
    g.store.set_park_counter(POOL, 777_777)
    with g.store.transaction() as st:  # a scratch card and a race bet of the other save
        park.spend(st, b, 5, "scratch", clock())
        park.spend(st, b, 3, "race", clock())
    lot.buy(TOKENS[0], ["123"])
    pool = 777_777 + 9 * PER_COIN
    assert park.state(TOKENS[1])["jackpot"] == lot.state(TOKENS[1])["prize"]["top"] == pool
    before = shards(g, a)
    at(clock, CFG["drawAt"])
    lot.tick()
    assert shards(g, a) - before == pool and g.store.park_counter(POOL) == SEED
    result = json.loads(g.store.lottery_last_drawn()["result"])
    assert result["pools"]["top"] == pool and result["each"]["top"] == pool and result["pool"] == SEED
    news = g.status(TOKENS[1])["park"]["news"]
    assert [(n["kind"], n["each"]["top"]) for n in news] == [("lottery_draw", pool)]


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
    # day 1's pool carried over; day 2's draw pays it all, with its own ticket's share
    t2 = SEED + 4 * PER_COIN
    assert shards(g, b) - before == t2 and g.store.park_counter(POOL) == SEED
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


def test_draws_list_each_days_top_winners_once_newest_first():
    g, park, lot, clock, (a, b) = setup("123", "123", "123", "123")
    park.mask = lambda s: s.replace("坏", "*")
    g.store.update_player(a, loadout='{"nick": "坏阿草"}')
    plays = [
        [(0, ["000"])],  # nobody wins the top
        [(0, ["123"])],  # one save, one ticket
        [(0, ["123", "023", "123"])],  # one save, two top tickets
        [(1, ["123"]), (0, ["123"])],  # two saves split it, the earlier ticket first
    ]
    days = []
    for i, buys in enumerate(plays):
        for who, numbers in buys:
            lot.buy(TOKENS[who], numbers)
        days.append(day_of(clock()))
        at(clock, CFG["drawAt"])
        lot.tick()
        at(clock, 60, days=1)
    pools = {d: json.loads(g.store.lottery_day(d)["result"])["pools"]["top"] for d in days}
    draws = lot.state(TOKENS[1])["draws"]
    assert [d["day"] for d in draws] == days[::-1] and all(d["number"] == "123" for d in draws)
    ra, rb = {"id": board_id(a), "nick": "*阿草"}, {"id": board_id(b), "nick": BOARD_DEFAULT_NICK}
    assert [d["top"] for d in draws] == [[rb, ra], [ra], [ra], []]
    assert [d["each"] for d in draws] == [pools[days[3]] // 2, pools[days[2]] // 2, pools[days[1]], 0]
    assert len(board_id(a)) == 12 and a not in json.dumps(draws)


def test_draws_keep_the_latest_seven_days():
    g, _, lot, clock, _ = setup()
    for _ in range(9):
        at(clock, CFG["drawAt"])
        lot.tick()
        at(clock, 60, days=1)
    draws = lot.state(TOKENS[0])["draws"]
    assert len(draws) == 7 and draws[0]["day"] == g.store.lottery_last_drawn()["day"]


def test_the_park_result_counts_lottery_prizes():
    g, park, lot, clock, _ = setup("123")
    lot.buy(TOKENS[0], ["003"])
    at(clock, CFG["drawAt"])
    lot.tick()
    assert park.state(TOKENS[0])["today"]["won"] == CFG["third"]


def test_sleep_wakes_for_draw_time():
    _, _, lot, clock, _ = setup()
    at(clock, CFG["drawAt"] - 0.5)
    assert lot.sleep_for() == pytest.approx(30.5)
    at(clock, CFG["drawAt"] - 1 / 60)
    assert lot.sleep_for() == pytest.approx(1.5)
    # Midnight is nothing to the lottery: its days turn over at the draw.
    at(clock, 24 * 60 - 1 / 60)
    assert lot.sleep_for() == 60
    at(clock, CFG["drawAt"])
    assert lot.sleep_for() == 60


def test_a_day_runs_from_one_draw_to_the_next():
    g, _, lot, clock, _ = setup("123", "456")
    at(clock, CFG["closeAt"] - 1 / 60)
    today = day_of(clock())
    assert lot.state(TOKENS[0])["day"] == today and lot.state(TOKENS[0])["open"]
    at(clock, CFG["closeAt"])
    state = lot.state(TOKENS[0])
    assert state["day"] == today and not state["open"]
    with pytest.raises(GameError):
        lot.buy(TOKENS[0], ["111"])
    at(clock, CFG["drawAt"])
    state = lot.state(TOKENS[0])
    # The draw of today is made, and tomorrow's tickets are on sale until tomorrow's close.
    assert g.store.lottery_day(today)["drawn"] is not None
    assert state["day"] == day_of(clock() + 86400) and state["open"]
    assert state["drawAt"] == clock() + 86400 and state["closeAt"] == state["drawAt"] - (CFG["drawAt"] - CFG["closeAt"]) * 60
    assert lot.buy(TOKENS[0], ["111"])["lottery"]["tickets"] == ["111"]


def test_http_lottery(monkeypatch):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    monkeypatch.setattr(main, "game", g)
    client = TestClient(main.app)
    headers = {"X-Player-Token": TOKENS[0]}
    pid = client.get("/api/me", headers=headers).json()["player"]
    g.store.update_player(pid, coins=5, taps_total=10_000, gift_day=day_of(clock()))
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
    """Steady [daily] tickets on uniform random numbers for [days] days, with nothing else feeding the pool: the
    share of sales paid back as second and third prizes, and what the second still holds at the end."""
    rng = random.Random(seed)
    pool, roll_second, paid = SEED, 0, 0
    for _ in range(days):
        pool += daily * PER_COIN
        tickets = [(i, f"{rng.randrange(1000):03d}") for i in range(daily)]
        s = settle(CFG, PRICE, f"{rng.randrange(1000):03d}", tickets, pool, roll_second)
        paid += sum(p for _, t, p in s.prizes if t != 1)
        pool, roll_second = s.pool, s.roll["second"]
    sold = daily * days * PRICE
    return {"paid": paid / sold, "left": roll_second / sold}


def test_second_and_third_return_their_design_share():
    expected = CFG["second"] + 0.09 * CFG["third"] / PRICE  # 30.8% with the default numbers
    out = simulate(300, 1500)
    assert out["paid"] + out["left"] == pytest.approx(expected, abs=0.005)
    assert out["paid"] == pytest.approx(expected, abs=0.01)
