"""Dou dizhu's card counter where it is sold: what it costs, when a game of it is used, and what each seat is told."""
import copy

import pytest

from app import economy
from app.game import GameError
from app.manifest import Manifest
from test_ddz import BASE, CFG, DEPOSIT, SHARDS, Stacked, World, api, joined, play_out, run, save, tok  # noqa: F401
from test_duel import settle

M = Manifest.load()
PRICE = M.park["coin"]["price"]
GAMES = CFG["counter"]["games"]


def held(w, pid):
    p = w.g.store.get_player(pid, w.clock.t)
    return p["shards"], p["coins"], p["ddz_counter"]


def coin_rows(w, pid):
    return {(r["source"], r["amount"]) for r in w.g.store.coin_ledger_of(pid, 14)}


def test_the_example_price():
    assert CFG["counter"] == {"coins": 1, "games": 10} and PRICE == 500


def test_it_is_off_until_bought_and_a_coin_short_is_bought_with_shards():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        a, b, _ = w.peers
        assert w.socks[0].of("ddz_deal")[0]["counter"] == {"on": False, "left": 0}
        assert w.socks[0].of("ddz_counter") == [] and w.t._state(w.t.by_id[tid], 0)["counter"] == {"on": False, "left": 0}
        await w.t.counter(a, tid)
        await w.t.idle()
        # Bought while the game is played: one of the games is this one.
        assert w.socks[0].of("ddz_counter") == [{"type": "ddz_counter", "table": tid, "on": True, "left": GAMES - 1}]
        assert held(w, w.pids[0]) == (SHARDS - DEPOSIT - PRICE, 0, GAMES - 1)
        assert coin_rows(w, w.pids[0]) == {("buy", 1), ("ddz_counter", -1)}
        assert w.g.store.ledger_sum(w.pids[0], w.g.store.coin_ledger_of(w.pids[0], 1)[0]["day"], ("coin_buy",)) == -PRICE
        assert w.g.store.get_player(w.pids[0], w.clock.t)["stamps_total"] == 1
        # Nobody else hears of it or pays; asking again while it is on buys nothing.
        assert w.socks[1].of("ddz_counter") == [] and held(w, w.pids[1]) == (SHARDS - DEPOSIT, 0, 0)
        await w.t.counter(a, tid)
        await w.t.idle()
        assert held(w, w.pids[0]) == (SHARDS - DEPOSIT - PRICE, 0, GAMES - 1)
        assert w.last("ddz_counter") == {"type": "ddz_counter", "table": tid, "on": True, "left": GAMES - 1}
        assert w.t._state(w.t.by_id[tid], 0)["counter"] == {"on": True, "left": GAMES - 1}
        assert w.t._state(w.t.by_id[tid], 1)["counter"] == {"on": False, "left": 0}
    run(go())


def test_a_coin_held_pays_for_it():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        w.g.store.update_player(w.pids[1], coins=3)
        await w.t.counter(w.peers[1], tid)
        await w.t.idle()
        assert held(w, w.pids[1]) == (SHARDS - DEPOSIT, 2, GAMES - 1)
        assert coin_rows(w, w.pids[1]) == {("ddz_counter", -1)}
        assert w.last("ddz_counter", 1) == {"type": "ddz_counter", "table": tid, "on": True, "left": GAMES - 1}
    run(go())


def test_a_save_that_cannot_pay_is_told_and_keeps_what_it_has():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing(shards=DEPOSIT + PRICE - 1)
        await w.t.counter(w.peers[2], tid)
        await w.t.idle()
        assert w.last("ddz_counter", 2) == {"type": "ddz_counter", "table": tid, "on": False, "left": 0,
                                            "error": "no_shards"}
        assert held(w, w.pids[2]) == (PRICE - 1, 0, 0) and coin_rows(w, w.pids[2]) == set()
    run(go())


def test_bought_while_the_seats_bid_it_is_used_when_the_landlord_is_known():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.dealt()
        a = w.peers[0]
        await w.t.counter(a, tid)
        await w.t.idle()
        assert w.last("ddz_counter") == {"type": "ddz_counter", "table": tid, "on": False, "left": GAMES}
        assert held(w, w.pids[0]) == (SHARDS - DEPOSIT - PRICE, 0, GAMES)
        # Asking again before the landlord is known buys nothing more.
        await w.t.counter(a, tid)
        await w.t.idle()
        assert held(w, w.pids[0]) == (SHARDS - DEPOSIT - PRICE, 0, GAMES)
        await w.t.bid(a, tid, 3)
        await w.t.idle()
        got = [m["type"] for m in w.socks[0].got if m["type"] in ("ddz_counter", "ddz_landlord")]
        # Told before the landlord, so the counter is on when the play shows.
        assert got[-2:] == ["ddz_counter", "ddz_landlord"]
        assert w.last("ddz_counter") == {"type": "ddz_counter", "table": tid, "on": True, "left": GAMES - 1}
        assert held(w, w.pids[0])[2] == GAMES - 1
    run(go())


def test_each_game_played_uses_one_and_a_deal_nobody_bids_on_uses_none():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        a, b, c = w.peers
        await w.t.counter(a, tid)
        await play_out(w, tid)
        for p in (a, b, c):
            await w.t.again(p, tid)
        await settle()
        await w.t.idle()
        assert w.last("ddz_deal")["counter"] == {"on": False, "left": GAMES - 1}
        assert w.last("ddz_deal", 1)["counter"] == {"on": False, "left": 0}
        t = w.t.by_id[tid]
        # Nobody bids: the cards are dealt again, and the game of the counter is still to use.
        for _ in range(3):
            await w.t.bid(w.peers[t.turn], tid, 0)
        assert t.deal == 2 and w.last("ddz_deal")["counter"] == {"on": False, "left": GAMES - 1}
        await w.t.bid(w.peers[t.turn], tid, 3)
        await w.t.idle()
        assert w.last("ddz_counter") == {"type": "ddz_counter", "table": tid, "on": True, "left": GAMES - 2}
        assert held(w, w.pids[0])[2] == GAMES - 2 and w.socks[1].of("ddz_counter") == []
    run(go())


def test_a_member_away_when_the_landlord_is_known_uses_its_game_on_coming_back():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.dealt()
        a, b, c = w.peers
        w.g.store.update_player(w.pids[1], coins=1)
        await w.t.counter(b, tid)
        await w.t.idle()
        await w.m.depart("r", b.id)
        await settle()
        await w.t.bid(a, tid, 3)
        await w.t.idle()
        assert held(w, w.pids[1])[2] == GAMES and w.t.by_id[tid].seats[1].counter is False
        b2, sock = w.join("b", w.pids[1])
        await w.t.joined("r", b2)
        await w.t.idle()
        assert sock.of("ddz_counter") == [{"type": "ddz_counter", "table": tid, "on": True, "left": GAMES - 1}]
        assert sock.of("ddz_state")[0]["counter"] == {"on": True, "left": GAMES - 1}
        assert held(w, w.pids[1])[2] == GAMES - 1
    run(go())


def test_only_a_seat_of_a_game_under_way_may_ask():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.invited()
        with pytest.raises(GameError) as e:
            await w.t.counter(w.peers[0], tid)
        assert e.value.code == "ddz_gone"
        stranger, _ = w.join("s", save(w.g, "s"))
        with pytest.raises(GameError):
            await w.t.counter(stranger, tid)
    run(go())


def test_where_it_is_not_sold_it_is_free_and_nothing_is_said_of_it():
    async def go():
        data = copy.deepcopy(M.data)
        del data["economy"]["doudizhu"]["counter"]
        w = World(manifest=Manifest(data), rng=Stacked(first=0))
        tid = await w.playing()
        assert "counter" not in w.socks[0].of("ddz_deal")[0] and "counter" not in w.t._state(w.t.by_id[tid], 0)
        with pytest.raises(GameError) as e:
            await w.t.counter(w.peers[0], tid)
        assert e.value.code == "bad_message"
        assert all(s.of("ddz_counter") == [] for s in w.socks) and held(w, w.pids[0]) == (SHARDS - DEPOSIT, 0, 0)
    run(go())


@pytest.mark.parametrize("counter", [{"coins": 0, "games": 10}, {"coins": 1}, {"coins": 1, "games": 1.5},
                                     {"coins": True, "games": 10}, 3])
def test_a_price_that_makes_no_sense_is_refused(counter):
    data = copy.deepcopy(M.data["economy"])
    data["doudizhu"]["counter"] = counter
    with pytest.raises(ValueError):
        economy.check(data)


def test_a_price_in_coins_needs_the_park():
    data = copy.deepcopy(M.data["economy"])
    economy.check(data)
    del data["park"]
    with pytest.raises(ValueError):
        economy.check(data)


def test_over_the_socket(api):  # noqa: F811
    c, g, _ = api
    for name in "abc":
        save(g, name)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as d:
        joined(a, "a")
        jb = joined(b, "b")
        a.receive_json()
        jd = joined(d, "c")
        a.receive_json(), b.receive_json()
        a.send_json({"type": "ddz_counter", "table": "nowhere"})
        assert a.receive_json() == {"type": "error", "code": "ddz_gone", "message": ""}
        a.send_json({"type": "ddz_invite", "ids": [jb["you"], jd["you"]], "base": BASE})
        tid = a.receive_json()["table"]
        b.receive_json(), d.receive_json()
        for ws in (b, d):
            ws.send_json({"type": "ddz_answer", "table": tid, "accept": True})
            for each in (a, b, d):
                assert each.receive_json()["type"] == "ddz_answer"
        for ws in (a, b, d):
            assert ws.receive_json()["type"] == "ddz_live"
            assert ws.receive_json()["counter"] == {"on": False, "left": 0}
        a.send_json({"type": "ddz_counter", "table": tid})
        assert a.receive_json() == {"type": "ddz_counter", "table": tid, "on": False, "left": GAMES}
        a.send_json({"type": "ddz_bid", "table": tid, "bid": 3})
        assert a.receive_json()["type"] == "ddz_bid"
        assert a.receive_json() == {"type": "ddz_counter", "table": tid, "on": True, "left": GAMES - 1}
        assert a.receive_json()["type"] == "ddz_landlord"
        for ws in (b, d):
            assert ws.receive_json()["type"] == "ddz_bid" and ws.receive_json()["type"] == "ddz_landlord"
        me = c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()
        assert me["shards"] == SHARDS - DEPOSIT - PRICE
        ledger = c.get("/api/park/ledger", headers={"X-Player-Token": tok("a")}).json()
        # The status just read gave the day's free coins as well.
        assert {(i["source"], i["amount"]) for i in ledger["days"][0]["items"]} >= {("buy", 1), ("ddz_counter", -1)}
