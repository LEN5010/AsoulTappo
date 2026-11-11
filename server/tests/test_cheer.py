"""Cheer rounds: room members' paid taps fill a shared bar sized by how many saves cheer; a full bar pays each of them
more the more there are, also across members joining and leaving mid-round."""
import asyncio

from fastapi.testclient import TestClient

import app.main as main
from app.game import CHEER_DAILY_CAP, CHEER_MIN_TAPS, Game, player_id_for
from app.manifest import Manifest
from app.rooms import CHEER_GRACE, CHEER_MIN_SHARE, CHEER_PER_SAVE, CHEER_REWARD_PER_SAVE, RoomManager
from app.store import Store, day_of
from fixtures import Clock

M = Manifest.load()


class Sock:
    def __init__(self):
        self.got = []

    async def send_json(self, data):
        self.got.append(data)

    async def close(self, code=1000):
        pass


class Tick:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def manager_with(*saves, room="r", interval=1000.0):
    clock = Tick()
    m = RoomManager(cheer_interval=interval, clock=clock)
    peers = [m.join(room, f"n{i}", "c", Sock(), token=save) for i, save in enumerate(saves)]
    return m, peers, clock


def state(m, room="r"):
    return m.cheer_state(m.rooms[room])


def test_the_bar_grows_with_each_cheering_save_and_pays_more_the_more_there_are():
    async def go():
        m, (a, b, c, d), _ = manager_with("A", "B", "C", "D")
        assert state(m)["target"] == 2 * CHEER_PER_SAVE and state(m)["reward"] == 2 * CHEER_REWARD_PER_SAVE
        m.cheer("A", 250)
        m.cheer("B", 250)
        m.cheer("C", CHEER_MIN_SHARE - 1)  # held back: neither on the bar nor cheering yet
        assert state(m)["count"] == 2 and state(m)["total"] == 500
        assert m.cheer("C", 1) is None  # on the bar and cheering: the bar holds one more share
        assert state(m)["total"] == 500 + CHEER_MIN_SHARE
        assert state(m)["target"] == 3 * CHEER_PER_SAVE and state(m)["reward"] == 3 * CHEER_REWARD_PER_SAVE
        room, number, cheering, each = m.cheer("D", CHEER_PER_SAVE * 4 - 500 - CHEER_MIN_SHARE)
        assert (number, sorted(cheering), each) == (1, ["A", "B", "C", "D"], 4 * CHEER_REWARD_PER_SAVE)
        assert room.cheer == {} and room.cheer_rounds == 1
        await m.cheer_done(room, number, {"A": each, "B": each, "C": each, "D": 0})
        await asyncio.sleep(0)
        assert a.ws.got[0] == {"type": "cheer_done", "round": 1, "rewards": {a.id: each, b.id: each, c.id: each, d.id: 0}}
        assert d.ws.got[1] == {"type": "cheer", "target": 2 * CHEER_PER_SAVE, "minShare": CHEER_MIN_SHARE, "total": 0,
                               "shares": {}, "count": 0, "reward": 2 * CHEER_REWARD_PER_SAVE, "rounds": 1}
    asyncio.run(go())


def test_many_small_shares_do_not_fill_the_bar_before_the_saves_behind_them_cheer():
    async def go():
        saves = [f"S{i}" for i in range(20)]
        m, _, _ = manager_with(*saves)
        for save in saves:
            assert m.cheer(save, CHEER_MIN_SHARE - 1) is None
        assert m.cheer("S0", 1) is None and m.cheer("S1", 1) is None  # two cheer, the other 18 put in 49 each
        assert state(m)["total"] == 2 * CHEER_MIN_SHARE and state(m)["count"] == 2
        for save in saves[2:]:
            assert m.cheer(save, 1) is None  # each cheers in turn; the bar grows by 300 for each
        assert state(m)["count"] == 20 and state(m)["target"] == 20 * CHEER_PER_SAVE
        _, _, cheering, each = m.cheer("S0", 20 * (CHEER_PER_SAVE - CHEER_MIN_SHARE))
        assert len(cheering) == 20 and each == 20 * CHEER_REWARD_PER_SAVE
    asyncio.run(go())


def test_one_save_alone_does_not_move_the_bar_nor_finish_it_without_a_second_cheering_save():
    async def go():
        m, _, _ = manager_with("A")
        assert m.cheer("A", 5000) is None and m.rooms["r"].cheer == {}
        m.join("r", "guest", "c", Sock())  # a guest without a save is not a second save
        assert m.cheer("A", 5000) is None and m.rooms["r"].cheer == {}
        m.join("r", "b", "c", Sock(), token="B")
        assert m.cheer("A", 5000) is None  # full, but only one save cheers
        assert m.cheer("B", CHEER_MIN_SHARE)[2] == ["A", "B"]
    asyncio.run(go())


def test_a_member_joining_mid_round_cheers_once_its_share_is_in():
    async def go():
        m, _, _ = manager_with("A", "B")
        m.cheer("A", 300)
        m.cheer("B", 200)
        m.join("r", "late", "c", Sock(), token="C")
        assert state(m)["count"] == 2  # joining alone changes nothing
        assert m.cheer("C", CHEER_MIN_SHARE) is None  # one more share for the bar to hold
        assert state(m)["target"] == 3 * CHEER_PER_SAVE
        _, _, cheering, each = m.cheer("C", 3 * CHEER_PER_SAVE - 550)
        assert sorted(cheering) == ["A", "B", "C"] and each == 3 * CHEER_REWARD_PER_SAVE
    asyncio.run(go())


def test_a_save_that_left_counts_and_is_paid_within_the_grace_and_keeps_its_taps_after():
    async def go():
        m, (a, b, c), clock = manager_with("A", "B", "C")
        m.cheer("A", 400)
        m.cheer("B", 100)
        m.cheer("C", 100)
        await m.depart("r", a.id)
        await asyncio.sleep(0)
        assert state(m)["count"] == 3  # within the grace
        bars = [x for x in b.ws.got if x["type"] == "cheer"]
        assert bars and a.id not in bars[-1]["shares"] and bars[-1]["count"] == 3
        clock.t += CHEER_GRACE - 1
        _, _, cheering, each = m.cheer("B", 300)
        assert sorted(cheering) == ["A", "B", "C"] and each == 3 * CHEER_REWARD_PER_SAVE
        # Next round: A leaves again and stays away; its taps stay, it stops counting, and the bar it held goes.
        a = m.join("r", "a", "c", Sock(), token="A")
        m.cheer("A", 500)
        m.cheer("B", 60)
        m.leave("r", a.id)
        assert state(m)["count"] == 2 and state(m)["target"] == 2 * CHEER_PER_SAVE
        m.cheer("C", 10)
        clock.t += CHEER_GRACE
        assert state(m)["count"] == 1 and state(m)["target"] == 2 * CHEER_PER_SAVE
        _, _, cheering, each = m.cheer("C", CHEER_MIN_SHARE)  # 620 of 600: the round finishes without A
        assert sorted(cheering) == ["B", "C"] and each == 2 * CHEER_REWARD_PER_SAVE
    asyncio.run(go())


def test_a_dropped_connection_that_comes_back_keeps_its_share():
    async def go():
        m, (a, b), _ = manager_with("A", "B")
        m.cheer("A", 250)
        m.leave("r", a.id)
        m.join("r", "a", "c", Sock(), token="A")
        assert m.rooms["r"].cheer_gone == {} and m.rooms["r"].cheer["A"] == 250
        _, _, cheering, _ = m.cheer("B", 350)
        assert sorted(cheering) == ["A", "B"]
    asyncio.run(go())


def test_the_bar_counts_only_while_two_saves_are_in_the_room_or_within_their_grace():
    async def go():
        m, (a, b), clock = manager_with("A", "B")
        m.cheer("B", 100)
        m.leave("r", b.id)
        assert m.cheer("A", 100) is None and m.rooms["r"].cheer["A"] == 100
        clock.t += CHEER_GRACE
        assert m.cheer("A", 100) is None and m.rooms["r"].cheer["A"] == 100
    asyncio.run(go())


def test_a_save_in_two_rooms_cheers_in_the_one_it_joined_last():
    async def go():
        m = RoomManager(cheer_interval=1000.0)
        for room in ("one", "two"):
            m.join(room, "x", "c", Sock(), token="X")
        m.join("one", "y", "c", Sock(), token="Y")
        m.join("two", "z", "c", Sock(), token="Z")
        m.cheer("X", 300)
        assert m.rooms["one"].cheer == {} and m.rooms["two"].cheer == {"X": 300}
    asyncio.run(go())


def test_progress_goes_out_once_per_interval_with_each_present_members_share():
    async def go():
        m, (a, b), _ = manager_with("A", "B", interval=0.01)
        m.cheer("A", 300)
        m.cheer("B", 200)
        m.cheer("A", 50)
        await asyncio.sleep(0.05)
        assert a.ws.got == [{"type": "cheer", "target": 2 * CHEER_PER_SAVE, "minShare": CHEER_MIN_SHARE, "total": 550,
                             "shares": {a.id: 350, b.id: 200}, "count": 2, "reward": 2 * CHEER_REWARD_PER_SAVE,
                             "rounds": 0}]
        m.leave("r", b.id)
        m.leave("r", a.id)
        assert "r" not in m.rooms
    asyncio.run(go())


def game():
    return Game(Store(":memory:"), M, now=Clock())


def test_rewards_stop_at_the_daily_cap_and_go_into_the_ledger():
    g = game()
    a, b = player_id_for("cheer-token-aaaa01"), player_id_for("cheer-token-bbbb02")
    g.status("cheer-token-aaaa01")
    g.status("cheer-token-bbbb02")
    start = g.store.get_player(a, g.now())["shards"]
    for _ in range(CHEER_DAILY_CAP // 300):
        assert g.cheer_reward([a, b], 300) == {a: 300, b: 300}
    left = CHEER_DAILY_CAP % 300
    assert g.cheer_reward([a, "no-such-save"], 300) == {a: left}
    assert g.cheer_reward([a], 300) == {a: 0}
    assert g.store.get_player(a, g.now())["shards"] == start + CHEER_DAILY_CAP
    assert g.store.ledger_amount(a, day_of(g.now()), "cheer") == CHEER_DAILY_CAP
    assert g.status("cheer-token-aaaa01")["cheer"]["got"] == CHEER_DAILY_CAP
    g.now.t += 86400
    assert g.cheer_reward([a], 20) == {a: 20}


def test_only_saves_with_enough_taps_in_all_cheer_and_only_with_taps_that_paid():
    g = game()
    token = "cheer-token-cccc03"
    pid = player_id_for(token)
    g.status(token)
    g.now.t += 60
    assert g.report_activity(token, 50, "s" * 16, 1)["cheerTaps"] == 0
    g.store.update_player(pid, taps_total=CHEER_MIN_TAPS)
    g.now.t += 60
    assert g.report_activity(token, 50, "s" * 16, 2)["cheerTaps"] == 50
    # Beyond the taps a minute pays, nothing more cheers.
    per_minute = M.income["tapsPerMinute"]
    assert g.report_activity(token, per_minute, "s" * 16, 3)["cheerTaps"] == per_minute - 50


def test_rooms_fill_the_bar_from_reported_taps_and_pay_over_the_socket(monkeypatch):
    g = game()
    tokens = ["cheer-token-dddd04", "cheer-token-eeee05"]
    for token in tokens:
        g.status(token)
        g.store.update_player(player_id_for(token), taps_total=CHEER_MIN_TAPS)
    monkeypatch.setattr(main, "game", g)
    main.manager.rooms.clear()
    monkeypatch.setattr(main.manager, "cheer_interval", 1000.0)
    per_minute = M.income["tapsPerMinute"]
    target, each = 2 * CHEER_PER_SAVE, 2 * CHEER_REWARD_PER_SAVE
    with TestClient(main.app) as c, c.websocket_connect("/ws") as wa, c.websocket_connect("/ws") as wb:
        wa.send_json({"type": "join", "room": "cheer", "nick": "a", "token": tokens[0], "motionVersion": 3})
        ja = wa.receive_json()
        assert ja["cheer"] == {"target": target, "minShare": CHEER_MIN_SHARE, "total": 0, "shares": {}, "count": 0,
                               "reward": each, "rounds": 0}
        wb.send_json({"type": "join", "room": "cheer", "nick": "b", "token": tokens[1], "motionVersion": 3})
        jb = wb.receive_json()
        wa.receive_json()  # b joined
        sequence, last = 0, None
        while sequence * per_minute * 2 < target:
            g.now.t += 60
            sequence += 1
            for token in tokens:
                last = c.post("/api/activity", headers={"X-Player-Token": token},
                              json={"taps": per_minute, "session": "s" * 16, "sequence": sequence}).json()
                assert "cheerTaps" not in last
        done = {"type": "cheer_done", "round": 1, "rewards": {ja["you"]: each, jb["you"]: each}}
        assert wa.receive_json() == done and wb.receive_json() == done
        assert wa.receive_json()["total"] == 0
        assert last["cheer"]["got"] == each
