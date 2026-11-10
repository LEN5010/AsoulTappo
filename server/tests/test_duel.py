"""Rock-paper-scissors in rooms: eligibility, invites, rounds, stakes, settling once and stickers."""
import asyncio
import copy
import threading

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.duel import MAX_DRAWS, RETRY_SEC, Duels
from app.game import DAY_OFFSET, Game, GameError, PlayerId, day_of, player_id_for
from app.manifest import Manifest
from app.rooms import RoomManager
from app.store import Store
from fixtures import Clock, SeqRng, tiny_manifest

M = Manifest.load()
CFG = M.duel
SHARDS = 100_000


def test_the_approved_numbers():
    assert CFG["stakes"] == [{"bet": 150, "prize": 250}, {"bet": 1500, "prize": 2500}, {"bet": 15000, "prize": 25000}]
    # a sixth of both bets is burnt
    for s in CFG["stakes"]:
        assert s["prize"] * 6 == s["bet"] * 2 * 5
    assert (CFG["inviteSec"], CFG["throwSec"], CFG["dailyWinCap"], CFG["minTaps"]) == (15, 10, 10000, 10000)
    assert CFG["sticker"] == {"set": "achao", "sec": 300}
    assert len(M.duel_stickers) == 20 and M.duel_stickers[0] == "achao.01"


# ------------------------------------------------------------------ helpers
class Sock:
    def __init__(self):
        self.got = []

    async def send_json(self, data):
        self.got.append(data)

    async def close(self, code=1000):
        pass

    def of(self, kind):
        return [m for m in self.got if m["type"] == kind]


class Handle:
    def __init__(self, delay, fn):
        self.delay, self.fn, self.cancelled = delay, fn, False

    def cancel(self):
        self.cancelled = True


class ManualTimers:
    """Timers that run only when a test fires them."""

    def __init__(self):
        self.pending = []

    def later(self, delay, fn):
        h = Handle(delay, fn)
        self.pending.append(h)
        return h

    def live(self):
        return [h for h in self.pending if not h.cancelled]

    async def fire(self):
        due, self.pending = self.live(), []
        for h in due:
            await h.fn()


async def settle():
    for _ in range(10):
        await asyncio.sleep(0)


def save(g, name, taps=10_000, shards=SHARDS):
    pid = PlayerId(player_id_for(f"{name}-duel-token-0001"))
    g.store.get_player(pid, g.now())
    g.store.update_player(pid, taps_total=taps, shards=shards)
    return pid


class World:
    def __init__(self, manifest=None):
        self.clock = Clock()
        self.g = Game(Store(":memory:"), manifest or Manifest.load(), rng=SeqRng(.5), now=self.clock)
        self.m = RoomManager()
        self.timers = ManualTimers()
        self.mono = 1000.0
        self.d = Duels(lambda: self.g, lambda: self.m, timers=self.timers, clock=lambda: self.mono, rng=SeqRng(0))
        self.m.on_depart = self.d.departed

    def join(self, nick, pid=None, room="r"):
        sock = Sock()
        return self.m.join(room, nick, "嘉然", sock, token=pid), sock

    def shards(self, pid):
        return self.g.store.get_player(pid, self.clock.t)["shards"]

    def pair(self, **kw):
        a_pid, b_pid = save(self.g, "a", **kw), save(self.g, "b", **kw)
        (a, sa), (b, sb) = self.join("a", a_pid), self.join("b", b_pid)
        return a, sa, a_pid, b, sb, b_pid

    async def started(self, bet=150, **kw):
        a, sa, a_pid, b, sb, b_pid = self.pair(**kw)
        await self.d.invite("r", a, b.id, bet)
        await settle()
        duel = sb.of("duel_invite")[-1]["duel"]
        await self.d.answer(b, duel, True)
        await settle()
        return a, sa, a_pid, b, sb, b_pid, duel


def run(coro):
    asyncio.run(coro)


async def refused(code, fn):
    with pytest.raises(GameError) as e:
        await fn()
    assert e.value.code == code


# ------------------------------------------------------------------ eligibility
def test_eligibility():
    async def go():
        w = World()
        a_pid, b_pid = save(w.g, "a"), save(w.g, "b")
        few = save(w.g, "few", taps=9_999)
        (a, _), (b, _) = w.join("a", a_pid), w.join("b", b_pid)
        (guest, _), (low, _) = w.join("guest"), w.join("low", few)
        (a2, _) = w.join("a again", a_pid)
        (ghost, _) = w.join("ghost", PlayerId("0000000000000000"))  # a token whose save does not exist
        await refused("duel_target_locked", lambda: w.d.invite("r", a, guest.id, 150))
        await refused("duel_locked", lambda: w.d.invite("r", guest, a.id, 150))
        await refused("duel_target_locked", lambda: w.d.invite("r", a, low.id, 150))
        await refused("duel_locked", lambda: w.d.invite("r", low, a.id, 150))
        await refused("duel_target_locked", lambda: w.d.invite("r", a, ghost.id, 150))
        assert not w.g.store.has_player("0000000000000000")  # asking never creates a save
        await refused("duel_self", lambda: w.d.invite("r", a, a.id, 150))
        await refused("duel_self", lambda: w.d.invite("r", a, a2.id, 150))
        await refused("no_member", lambda: w.d.invite("r", a, "nobody", 150))
        await refused("bad_message", lambda: w.d.invite("r", a, b.id, 151))
        w.g.store.update_player(a_pid, shards=149)
        await refused("no_shards", lambda: w.d.invite("r", a, b.id, 150))
        w.g.store.update_player(a_pid, shards=SHARDS)
        # one invite or duel per save at a time, across connections
        await w.d.invite("r", a, b.id, 150)
        (c, _) = w.join("c", save(w.g, "c"))
        await refused("duel_busy", lambda: w.d.invite("r", a2, c.id, 150))
        await refused("duel_target_busy", lambda: w.d.invite("r", c, b.id, 150))
        # the target must be in the same room
        (far, _) = w.join("far", save(w.g, "far"), room="elsewhere")
        await refused("no_member", lambda: w.d.invite("r", c, far.id, 150))
    run(go())


def test_a_manifest_without_duels_turns_them_off():
    async def go():
        w = World(tiny_manifest())
        a, _, a_pid, b, _, _ = w.pair()
        await refused("no_duel", lambda: w.d.invite("r", a, b.id, 150))
        assert "duel" not in w.g.status(a_pid)
    run(go())


def test_status_carries_the_net_win_of_today():
    w = World()
    pid = save(w.g, "a")
    assert w.g.status(pid)["duel"] == {"net": 0}


# ------------------------------------------------------------------ invites
def test_unanswered_invite_times_out_and_the_inviter_waits_before_asking_again():
    async def go():
        w = World()
        a, sa, _, b, sb, _ = w.pair()
        await w.d.invite("r", a, b.id, 1500)
        await settle()
        invite = sb.of("duel_invite")[0]
        assert invite == {"type": "duel_invite", "duel": invite["duel"], "from": a.id, "to": b.id,
                          "bet": 1500, "prize": 2500, "sec": 15}
        assert sa.of("duel_invite") == [invite]
        assert [h.delay for h in w.timers.live()] == [15]
        await w.timers.fire()
        await settle()
        over = {"type": "duel_over", "duel": invite["duel"], "reason": "timeout"}
        assert sa.of("duel_over") == [over] and sb.of("duel_over") == [over]
        await refused("duel_cooldown", lambda: w.d.invite("r", a, b.id, 150))
        # the other way round is a different pair
        await w.d.invite("r", b, a.id, 150)
        await settle()
        await w.d.answer(a, sa.of("duel_invite")[-1]["duel"], False)
        w.mono += RETRY_SEC
        await w.d.invite("r", a, b.id, 150)
        await refused("duel_gone", lambda: w.d.answer(b, invite["duel"], True))  # the old invite is gone
    run(go())


def test_refusal_starts_the_wait_and_takes_nothing():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid = w.pair()
        await w.d.invite("r", a, b.id, 150)
        await settle()
        duel = sb.of("duel_invite")[0]["duel"]
        await refused("duel_gone", lambda: w.d.answer(a, duel, True))  # only the invited member answers
        await w.d.answer(b, duel, False)
        await settle()
        assert sa.of("duel_over") == [{"type": "duel_over", "duel": duel, "reason": "declined"}]
        await refused("duel_cooldown", lambda: w.d.invite("r", a, b.id, 150))
        assert w.shards(a_pid) == w.shards(b_pid) == SHARDS
        assert w.timers.live() == []
    run(go())


def test_do_not_disturb_turns_invites_down_unseen():
    async def go():
        w = World()
        a, sa, _, b, sb, _ = w.pair()
        b.dnd = True
        await w.d.invite("r", a, b.id, 150)
        await settle()
        assert [m["type"] for m in sa.got] == ["duel_invite", "duel_over"]
        assert sa.of("duel_over")[0]["reason"] == "declined"  # the same as a refusal
        assert sb.got == []
        await refused("duel_cooldown", lambda: w.d.invite("r", a, b.id, 150))
        # turning it on while an invite waits refuses that invite too
        (c, sc) = w.join("c", save(w.g, "c"))
        await w.d.invite("r", c, a.id, 150)
        w.d.set_dnd(a, True)
        await settle()
        assert sc.of("duel_over")[0]["reason"] == "declined" and a.dnd
    run(go())


def test_an_invite_is_dropped_when_either_side_leaves():
    async def go():
        w = World()
        a, sa, _, b, sb, _ = w.pair()
        await w.d.invite("r", a, b.id, 150)
        await w.m.depart("r", b.id)
        await settle()
        assert sa.of("duel_over")[0]["reason"] == "gone"
        assert w.d.by_save == {} and w.timers.live() == []
        # the invited member leaving is no refusal: no wait before the next invite
        (b2, sb2) = w.join("b", b.token)
        await w.d.invite("r", a, b2.id, 150)
        await settle()
        # the inviter leaving and coming back waits as after a refusal
        await w.m.depart("r", a.id)
        await settle()
        assert sb2.of("duel_over")[0]["reason"] == "gone"
        (a2, _) = w.join("a", a.token)
        await refused("duel_cooldown", lambda: w.d.invite("r", a2, b2.id, 150))
    run(go())


# ------------------------------------------------------------------ stakes and rounds
def test_accepting_takes_both_bets_at_once():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid, duel = await w.started(bet=1500)
        assert w.shards(a_pid) == w.shards(b_pid) == SHARDS - 1500
        start = {"type": "duel_start", "duel": duel, "round": 1, "sec": 10}
        assert sa.of("duel_start") == [start] and sb.of("duel_start") == [start]
        assert [h.delay for h in w.timers.live()] == [10]
    run(go())


def test_one_side_short_of_shards_takes_nothing_from_either():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid = w.pair()
        await w.d.invite("r", a, b.id, 15000)
        await settle()
        duel = sb.of("duel_invite")[0]["duel"]
        w.g.store.update_player(b_pid, shards=14_999)
        await w.d.answer(b, duel, True)
        await settle()
        over = {"type": "duel_over", "duel": duel, "reason": "no_shards"}
        assert sa.of("duel_over") == [over] and sb.of("duel_over") == [over]
        assert (w.shards(a_pid), w.shards(b_pid)) == (SHARDS, 14_999)
        assert w.g.store.open_duels() == [] and w.d.by_save == {}
    run(go())


@pytest.mark.parametrize("ha,hb,a_wins", [
    ("rock", "scissors", True), ("scissors", "paper", True), ("paper", "rock", True),
    ("scissors", "rock", False), ("paper", "scissors", False), ("rock", "paper", False),
])
def test_rock_scissors_paper(ha, hb, a_wins):
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid, duel = await w.started()
        (c, sc) = w.join("c")
        before = len(sb.got)
        await w.d.throw(a, duel, ha)
        await settle()
        # nothing tells b what a threw, or even that a threw
        assert len(sb.got) == before
        await w.d.throw(b, duel, hb)
        await settle()
        winner, loser = (a, b) if a_wins else (b, a)
        result = {"type": "duel_result", "duel": duel, "winner": winner.id, "loser": loser.id, "prize": 250,
                  "hands": {a.id: ha, b.id: hb}}
        for s in (sa, sb, sc):
            assert s.of("duel_result") == [result]
            assert s.of("sticker") == [{"type": "sticker", "id": loser.id, "key": "achao.01", "sec": 300}]
        assert w.shards(a_pid) == SHARDS - 150 + (250 if a_wins else 0)
        assert w.shards(b_pid) == SHARDS - 150 + (0 if a_wins else 250)
        assert w.g.duel_net(a_pid) == (100 if a_wins else -150)
        assert w.timers.live() == [] and w.d.by_save == {}
    run(go())


def test_a_draw_plays_again_and_shows_the_draw():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid, duel = await w.started()
        await w.d.throw(a, duel, "rock")
        await w.d.throw(a, duel, "paper")  # one hand a round: ignored
        await w.d.throw(b, duel, "rock")
        await settle()
        again = {"type": "duel_round", "duel": duel, "round": 2, "sec": 10, "hands": {a.id: "rock", b.id: "rock"}}
        assert sa.of("duel_round") == [again] and sb.of("duel_round") == [again]
        assert len(w.timers.live()) == 1  # the first round's timer is gone
        await w.d.throw(b, duel, "paper")
        await w.d.throw(a, duel, "scissors")
        await settle()
        assert sa.of("duel_result")[0]["winner"] == a.id
    run(go())


def test_ten_draws_in_a_row_give_both_bets_back():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid, duel = await w.started()
        for _ in range(MAX_DRAWS):
            await w.d.throw(a, duel, "paper")
            await w.d.throw(b, duel, "paper")
        await settle()
        assert len(sa.of("duel_round")) == MAX_DRAWS - 1
        assert sa.of("duel_over") == [{"type": "duel_over", "duel": duel, "reason": "draws"}]
        assert w.shards(a_pid) == w.shards(b_pid) == SHARDS
        assert w.g.duel_net(a_pid) == 0 and sa.of("sticker") == []
    run(go())


def test_the_side_that_does_not_throw_in_time_loses():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid, duel = await w.started()
        await w.d.throw(b, duel, "rock")
        await w.timers.fire()
        await settle()
        assert sa.of("duel_result") == [{"type": "duel_result", "duel": duel, "winner": b.id, "loser": a.id,
                                         "prize": 250, "hands": {a.id: None, b.id: "rock"}}]
        assert w.shards(b_pid) == SHARDS + 100
    run(go())


def test_both_sides_idle_get_their_bets_back():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid, duel = await w.started(bet=15000)
        await w.timers.fire()
        await settle()
        assert sb.of("duel_over") == [{"type": "duel_over", "duel": duel, "reason": "idle"}]
        assert w.shards(a_pid) == w.shards(b_pid) == SHARDS
        await refused("duel_gone", lambda: w.d.throw(a, duel, "rock"))
    run(go())


@pytest.mark.parametrize("how", ["leave", "failed"])
def test_leaving_or_losing_the_connection_loses(how):
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid, duel = await w.started()
        await w.d.throw(a, duel, "rock")
        if how == "leave":
            await w.m.depart("r", a.id)
        else:
            await w.m._failed("r", a)
        await settle()
        assert sb.of("duel_result")[0] == {"type": "duel_result", "duel": duel, "winner": b.id, "loser": a.id,
                                           "prize": 250, "hands": {a.id: "rock", b.id: None}}
        assert w.shards(a_pid) == SHARDS - 150 and w.shards(b_pid) == SHARDS + 100
    run(go())


def test_leaving_while_the_bets_are_taken_loses_too():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid = w.pair()
        await w.d.invite("r", a, b.id, 150)
        await settle()
        duel = sb.of("duel_invite")[0]["duel"]
        entered, release = threading.Event(), threading.Event()
        start = w.g.duel_start

        def slow(*args):
            entered.set()
            release.wait(2)
            return start(*args)

        w.g.duel_start = slow
        task = asyncio.create_task(w.d.answer(b, duel, True))
        while not entered.is_set():
            await asyncio.sleep(.001)
        assert w.d.in_duel(a)
        await w.m.depart("r", a.id)
        release.set()
        await task
        await settle()
        assert sb.of("duel_start") == [] and sb.of("duel_result")[0]["winner"] == b.id
        assert w.shards(a_pid) == SHARDS - 150 and w.shards(b_pid) == SHARDS + 100
    run(go())


def test_a_database_error_while_taking_the_bets_ends_the_duel_and_frees_both_saves():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid = w.pair()
        (c, _) = w.join("c", save(w.g, "c"))
        await w.d.invite("r", a, b.id, 150)
        await settle()
        duel = sb.of("duel_invite")[0]["duel"]
        start = w.g.duel_start

        def broken(*args):
            raise RuntimeError("database is locked")

        w.g.duel_start = broken
        with pytest.raises(RuntimeError):
            await w.d.answer(b, duel, True)
        await settle()
        over = {"type": "duel_over", "duel": duel, "reason": "error"}
        assert sa.of("duel_over") == [over] and sb.of("duel_over") == [over]
        assert w.d.by_save == {} and w.d.by_id == {} and w.timers.live() == []
        assert w.shards(a_pid) == w.shards(b_pid) == SHARDS
        # both saves can be invited again, by each other and by others, with no wait
        w.g.duel_start = start
        await w.d.invite("r", c, b.id, 150)
        await w.d.invite("r", a, w.join("d", save(w.g, "d"))[0].id, 150)
    run(go())


def test_a_database_error_while_settling_leaves_the_duel_for_the_startup_refund():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid, duel = await w.started(bet=1500)

        def broken(*args):
            raise RuntimeError("disk I/O error")

        w.g.duel_settle, settle_ok = broken, w.g.duel_settle
        await w.d.throw(a, duel, "rock")
        with pytest.raises(RuntimeError):
            await w.d.throw(b, duel, "scissors")
        await settle()
        assert w.d.by_save == {} and w.timers.live() == []  # over in memory
        assert sa.of("duel_result") == []
        assert len(w.g.store.open_duels()) == 1  # still open in the database, bets held
        w.g.duel_settle = settle_ok
        assert w.g.refund_open_duels() == 1
        assert w.shards(a_pid) == w.shards(b_pid) == SHARDS
    run(go())


# ------------------------------------------------------------------ paid once
def test_settling_twice_pays_once_across_threads():
    w = World()
    a, b = save(w.g, "a"), save(w.g, "b")
    row = w.g.duel_start(a, b, 1500)
    results, barrier = [], threading.Barrier(8)

    def settle_one(i):
        barrier.wait()
        results.append(w.g.duel_settle(row, (a, b, None)[i % 3]))

    threads = [threading.Thread(target=settle_one, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1
    d = w.g.store.duel(row)
    total = w.shards(a) + w.shards(b)
    assert total == 2 * SHARDS - 3000 + (2500 if d["state"] == "won" else 3000)
    assert w.g.duel_settle(row, a) is False


def test_a_throw_a_timeout_and_a_departure_at_once_settle_once():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid, duel = await w.started()
        (c, sc) = w.join("c")
        await w.d.throw(b, duel, "rock")
        await asyncio.gather(w.d.throw(a, duel, "scissors"), w.timers.fire(), w.m.depart("r", b.id))
        await settle()
        assert len(sc.of("duel_result")) == 1
        winner = sc.of("duel_result")[0]["winner"]
        assert w.shards(a_pid) + w.shards(b_pid) == 2 * SHARDS - 300 + 250
        assert (w.shards(b_pid) > w.shards(a_pid)) == (winner == b.id)
        assert w.g.store.open_duels() == []
    run(go())


# ------------------------------------------------------------------ daily cap
def won(g, winner, loser, bet, day_ts):
    """Records a duel [winner] won on the China day of [day_ts]."""
    stake = next(s for s in CFG["stakes"] if s["bet"] == bet)
    row = g.store.add_duel(winner, loser, bet, stake["prize"], day_of(day_ts), day_ts)
    g.store.close_duel(row, "won", winner, day_ts)


def next_midnight(t):
    return ((t + DAY_OFFSET) // 86400 + 1) * 86400 - DAY_OFFSET


def test_the_daily_net_win_cap_follows_the_china_day():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid = w.pair()
        other = save(w.g, "other")
        midnight = next_midnight(w.clock.t)
        w.clock.t = midnight - 60
        for _ in range(9):
            won(w.g, a_pid, other, 1500, w.clock.t)  # +9000 today
        assert w.g.duel_net(a_pid) == 9000
        await refused("duel_cap", lambda: w.d.invite("r", a, b.id, 15000))
        await refused("duel_cap", lambda: w.d.invite("r", b, a.id, 15000))  # either side's cap counts
        await w.d.invite("r", a, b.id, 1500)  # exactly the cap is allowed
        await settle()
        await w.d.answer(b, sb.of("duel_invite")[0]["duel"], False)
        won(w.g, a_pid, other, 1500, w.clock.t)
        await refused("duel_cap", lambda: w.d.invite("r", b, a.id, 150))
        # losses count against the net win
        won(w.g, other, a_pid, 150, w.clock.t)
        assert w.g.duel_net(a_pid) == 10000 - 150
        await w.d.invite("r", b, a.id, 150)
        await settle()
        await w.d.answer(a, sa.of("duel_invite")[-1]["duel"], False)
        w.clock.t = midnight
        assert w.g.duel_net(a_pid) == 0
        w.mono += RETRY_SEC
        await w.d.invite("r", b, a.id, 15000)
    run(go())


def test_the_cap_is_checked_again_when_the_bets_are_taken():
    w = World()
    a, b, other = save(w.g, "a"), save(w.g, "b"), save(w.g, "other")
    for _ in range(10):
        won(w.g, b, other, 1500, w.clock.t)
    with pytest.raises(GameError) as e:
        w.g.duel_start(a, b, 150)
    assert e.value.code == "duel_cap"
    assert w.shards(a) == w.shards(b) == SHARDS


# ------------------------------------------------------------------ database
def test_open_duels_are_refunded_at_startup(tmp_path):
    path = str(tmp_path / "duels.db")
    g = Game(Store(path), Manifest.load(), now=Clock())
    a, b = save(g, "a"), save(g, "b")
    g.duel_start(a, b, 15000)
    done = g.duel_start(a, b, 150)
    g.duel_settle(done, a)
    g.store.close()
    g = Game(Store(path), Manifest.load(), now=Clock())
    assert g.refund_open_duels() == 1
    assert g.refund_open_duels() == 0
    assert g.store.get_player(a, 0)["shards"] == SHARDS + 100
    assert g.store.get_player(b, 0)["shards"] == SHARDS - 150


def test_a_database_from_before_duels_is_migrated(tmp_path):
    path = str(tmp_path / "old.db")
    store = Store(path)
    store._db.executescript("DROP TABLE duels;")
    store.close()
    g = Game(Store(path), Manifest.load(), now=Clock())
    a, b = save(g, "a"), save(g, "b")
    assert g.duel_settle(g.duel_start(a, b, 150), b)


# ------------------------------------------------------------------ stickers
def test_the_losers_sticker_is_seen_by_later_members_and_after_reconnecting():
    async def go():
        w = World()
        a, sa, a_pid, b, sb, b_pid, duel = await w.started()
        await w.d.throw(a, duel, "rock")
        await w.d.throw(b, duel, "paper")
        await settle()
        w.mono += 100
        assert w.d.stickers("r") == [{"type": "sticker", "id": a.id, "key": "achao.01", "sec": 200}]
        await w.m.depart("r", a.id)
        (a2, _) = w.join("a", a_pid)
        assert w.d.sticker_of("r", a2) == {"type": "sticker", "id": a2.id, "key": "achao.01", "sec": 200}
        w.mono += 200
        assert w.d.stickers("r") == [] and w.m.rooms["r"].stickers == {}
    run(go())


# ------------------------------------------------------------------ over the socket
@pytest.fixture()
def api(monkeypatch):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), rng=SeqRng(.5), now=clock)
    monkeypatch.setattr(main, "game", g)
    timers = ManualTimers()
    monkeypatch.setattr(main.duels, "timers", timers)
    monkeypatch.setattr(main.duels, "rng", SeqRng(.99))
    main.manager.rooms.clear()
    main.duels.clear()
    with TestClient(main.app) as c:
        yield c, g, timers
    main.manager.rooms.clear()
    main.duels.clear()


def tok(name):
    return f"{name}-duel-token-0001"


def joined(ws, nick, room="r1", **extra):
    ws.send_json({"type": "join", "room": room, "nick": nick, "token": tok(nick), **extra})
    return ws.receive_json()


def test_a_duel_over_the_socket(api):
    c, g, timers = api
    for name in ("a", "b"):
        save(g, name)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = joined(a, "a")
        jb = joined(b, "b")
        a.receive_json()  # member_joined
        assert c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()["duel"] == {"net": 0}
        a.send_json({"type": "duel_invite", "id": jb["you"], "bet": 1500})
        invite = a.receive_json()
        assert invite["type"] == "duel_invite" and invite["from"] == ja["you"] and invite["to"] == jb["you"]
        assert b.receive_json() == invite
        b.send_json({"type": "duel_answer", "duel": invite["duel"], "accept": True})
        assert a.receive_json()["type"] == b.receive_json()["type"] == "duel_start"
        assert c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()["shards"] == SHARDS - 1500
        # the host cannot remove a member mid-duel
        a.send_json({"type": "kick", "id": jb["you"]})
        assert a.receive_json() == {"type": "error", "code": "in_duel", "message": "member is in a duel"}
        a.send_json({"type": "duel_throw", "duel": invite["duel"], "hand": "lizard"})
        assert a.receive_json()["code"] == "bad_message"
        a.send_json({"type": "duel_throw", "duel": invite["duel"], "hand": "paper"})
        b.send_json({"type": "duel_throw", "duel": invite["duel"], "hand": "rock"})
        result = a.receive_json()
        assert result == {"type": "duel_result", "duel": invite["duel"], "winner": ja["you"], "loser": jb["you"],
                          "prize": 2500, "hands": {ja["you"]: "paper", jb["you"]: "rock"}}
        assert b.receive_json() == result
        sticker = {"type": "sticker", "id": jb["you"], "key": "achao.20", "sec": 300}
        assert a.receive_json() == sticker and b.receive_json() == sticker
        me = c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()
        assert me["shards"] == SHARDS + 1000 and me["duel"] == {"net": 1000}
        # someone joining later sees the sticker right after joined, and so does the loser coming back
        with c.websocket_connect("/ws") as d:
            d.send_json({"type": "join", "room": "r1", "nick": "d"})
            assert d.receive_json()["type"] == "joined"
            assert d.receive_json() == sticker
            a.receive_json()
            b.receive_json()  # member_joined d
        assert a.receive_json()["type"] == b.receive_json()["type"] == "member_left"
        b.send_json({"type": "leave"})
        a.receive_json()
        jb2 = joined(b, "b")
        assert b.receive_json() == {**sticker, "id": jb2["you"]}
        assert a.receive_json()["type"] == "member_joined"
        assert a.receive_json() == {**sticker, "id": jb2["you"]}
        # and now the host may remove that member
        a.send_json({"type": "kick", "id": jb2["you"]})
        assert b.receive_json()["reason"] == "kicked"


def test_do_not_disturb_from_the_join_and_its_own_message(api):
    c, g, timers = api
    for name in ("a", "b"):
        save(g, name)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        joined(a, "a")
        jb = joined(b, "b", dnd=True)
        a.receive_json()
        a.send_json({"type": "duel_invite", "id": jb["you"], "bet": 150})
        assert a.receive_json()["type"] == "duel_invite"
        assert a.receive_json()["reason"] == "declined"
        b.send_json({"type": "dnd", "dnd": False})
        main.duels.refused.clear()
        a.send_json({"type": "duel_invite", "id": jb["you"], "bet": 150})
        assert a.receive_json()["type"] == "duel_invite"
        assert b.receive_json()["type"] == "duel_invite"
        c.portal.call(timers.fire)
        assert a.receive_json()["reason"] == "timeout" and b.receive_json()["reason"] == "timeout"
        a.send_json({"type": "duel_invite", "id": jb["you"], "bet": 150})
        assert a.receive_json() == {"type": "error", "code": "duel_cooldown", "message": ""}


def test_a_server_without_duels_answers_no_duel_and_keeps_the_old_messages(api, monkeypatch):
    c, g, timers = api
    data = copy.deepcopy(Manifest.load().data)
    del data["economy"]["duel"]
    monkeypatch.setattr(main, "game", Game(Store(":memory:"), Manifest(data), now=Clock()))
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        # the 1.1 join, without dnd
        ja = joined(a, "a")
        assert set(ja) == {"type", "room", "you", "members", "info"}
        assert set(ja["members"][0]) == {"id", "uid", "nick", "character", "taps", "motion", "plate"}
        jb = joined(b, "b")
        a.receive_json()
        a.send_json({"type": "duel_invite", "id": jb["you"], "bet": 150})
        assert a.receive_json() == {"type": "error", "code": "no_duel", "message": "这个服务器没有猜拳"}
        assert "duel" not in c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()
        a.send_json({"type": "tap", "count": 1})
        assert a.receive_json()["type"] == "tap" and b.receive_json()["type"] == "tap"


def test_closing_the_connection_mid_duel_loses_it(api):
    c, g, timers = api
    for name in ("a", "b"):
        save(g, name)
    with c.websocket_connect("/ws") as b:
        jb = joined(b, "b")
        with c.websocket_connect("/ws") as a:
            ja = joined(a, "a")
            b.receive_json()  # member_joined a
            a.send_json({"type": "duel_invite", "id": jb["you"], "bet": 150})
            invite = b.receive_json()
            b.send_json({"type": "duel_answer", "duel": invite["duel"], "accept": True})
            assert b.receive_json()["type"] == "duel_start"
            a.send_json({"type": "duel_throw", "duel": invite["duel"], "hand": "rock"})
        # a's connection is gone: it left the room, and the duel with it
        assert b.receive_json() == {"type": "member_left", "id": ja["you"]}
        assert b.receive_json() == {"type": "duel_result", "duel": invite["duel"], "winner": jb["you"],
                                    "loser": ja["you"], "prize": 250, "hands": {ja["you"]: "rock", jb["you"]: None}}
        assert c.get("/api/me", headers={"X-Player-Token": tok("b")}).json()["shards"] == SHARDS + 100
        assert c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()["shards"] == SHARDS - 150
        assert g.store.open_duels() == []
