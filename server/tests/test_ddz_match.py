"""The dou dizhu queue: waiting at a stake from any room, who may wait, tables the queue makes, and their games."""
import asyncio
import copy

import pytest

import app.main as main
from app.ddz import COUNTS_SEC, Bank, Tables
from app.game import Game
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock, SeqRng
from test_ddz import BASE, CFG, DEPOSIT, SHARDS, Stacked, World, api, joined, play_out, save, tok  # noqa: F401
from test_duel import ManualTimers, settle


class MatchWorld(World):
    """Members in their own rooms by default, on clients that queue."""

    def __init__(self, manifest=None, rng=None, require_account=False):
        super().__init__(manifest, rng or Stacked(first=0))
        self.counts = ManualTimers()
        self.t = Tables(lambda: self.g, lambda: self.m, timers=self.timers, clock=lambda: self.mono, rng=self.rng,
                        require_account=lambda: require_account, count_timers=self.counts)
        self.m.on_depart = self.t.departed
        self.who = {}

    def member(self, name, room=None, match=True, **kw):
        """A member with its own save named [name], in room r-[name] unless [room]."""
        pid = self.who.get(name) or save(self.g, name, **kw)
        self.who[name] = pid
        peer, sock = self.join(name, pid, room=room or f"r-{name}")
        peer.ddz_match = match
        return peer, sock

    async def queued(self, *names, base=BASE):
        out = [self.member(n) for n in names]
        for peer, _ in out:
            await self.t.queue(peer, base)
        await self.t.idle()
        return out


def run(coro):
    return asyncio.run(coro)


def queue_msgs(sock):
    return [{k: v for k, v in m.items() if k != "type"} for m in sock.of("ddz_queue")]


# ------------------------------------------------------------------ waiting
def test_waiting_moving_and_cancelling():
    async def go():
        w = MatchWorld()
        a, sa = w.member("a")
        await w.t.queue(a, BASE)
        assert queue_msgs(sa) == [{"base": BASE, "waited": 0.0}]
        assert w.t.lines == {BASE: [w.t.waiting[w.who["a"]]]}
        w.mono += 12.34
        await w.t.queue(a, BASE)  # the same stake again: told how long it waited
        assert queue_msgs(sa)[-1] == {"base": BASE, "waited": 12.3}
        b, _ = w.member("b")
        await w.t.queue(b, 50)
        await w.t.queue(a, 50)  # another stake: to the end of that line, waiting from now
        assert [x.peer for x in w.t.lines[50]] == [b, a] and BASE not in w.t.lines
        assert queue_msgs(sa)[-1] == {"base": 50, "waited": 0.0}
        w.t.unqueue(a)
        assert queue_msgs(sa)[-1] == {"base": None} and w.who["a"] not in w.t.waiting
        w.t.unqueue(a)  # not waiting: told so all the same
        assert queue_msgs(sa)[-2:] == [{"base": None}, {"base": None}]
        assert [x.peer for x in w.t.lines[50]] == [b]
    run(go())


@pytest.mark.parametrize("how, code", [
    ("guest", "ddz_locked"), ("taps", "ddz_locked"), ("poor", "no_shards"), ("cap", "ddz_cap"),
    ("account", "ddz_account"), ("dnd", "ddz_dnd"), ("stake", "bad_message"), ("old", "bad_message"),
    ("twin", "ddz_busy"), ("seated", "ddz_busy"),
])
def test_who_may_not_wait(how, code):
    async def go():
        w = MatchWorld(require_account=how == "account")
        if how == "guest":
            peer, _ = w.join("guest", None, room="r")
            peer.ddz_match = True
        else:
            peer, _ = w.member("a", match=how != "old", taps=9_999 if how == "taps" else 10_000,
                               shards=DEPOSIT - 1 if how == "poor" else SHARDS)
        peer.dnd = how == "dnd"
        if how == "cap":
            others = [save(w.g, n, shards=10_000_000) for n in "xy"]
            w.g.store.update_player(w.who["a"], shards=10_000_000)
            for _ in range(3):
                w.bank.settle(w.bank.start([w.who["a"], *others], 500), 0, True, 24)
        if how == "twin":
            twin, _ = w.member("a", room="elsewhere")
            await w.t.queue(twin, BASE)
        if how == "seated":
            w.three()
            await w.t.invite("r", w.peers[0], [w.peers[1].id, w.peers[2].id], BASE)
            peer = w.peers[1]
            peer.ddz_match = True
        with pytest.raises(Exception) as e:
            await w.t.queue(peer, 123 if how == "stake" else BASE)
        assert getattr(e.value, "code", None) == code
        assert all(x.peer is not peer for x in w.t.waiting.values())
    run(go())


def test_leaving_the_room_turning_invites_down_or_the_stake_going_takes_a_save_out():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb) = await w.queued("a", "b")
        c, sc = w.member("c")
        await w.t.queue(c, 50)
        await w.m.depart("r-a", a.id)
        assert w.who["a"] not in w.t.waiting
        w.t.set_dnd(b, True)
        assert queue_msgs(sb)[-1] == {"base": None, "reason": "ddz_dnd"} and w.t.lines == {50: [w.t.waiting[w.who["c"]]]}
        data = copy.deepcopy(w.g.manifest.data)
        data["economy"]["doudizhu"]["stakes"] = [BASE, 500]
        w.g = Game(w.g.store, Manifest(data), rng=SeqRng(.5), now=w.clock)
        d, _ = w.member("d")
        await w.t.queue(d, BASE)
        assert queue_msgs(sc)[-1] == {"base": None} and w.t.waiting.keys() == {w.who["d"]}
    run(go())


# ------------------------------------------------------------------ counts
def test_members_that_queue_hear_how_many_wait_at_most_once_a_second():
    async def go():
        w = MatchWorld()
        _, s_watch = w.member("watch", room="r-a")
        old, s_old = w.member("old", room="r-a", match=False)
        a, sa = w.member("a")
        await w.t.queue(a, BASE)
        want = {"type": "ddz_waiting", "counts": [[BASE, 1]]}
        assert s_watch.of("ddz_waiting") == [want] and sa.of("ddz_waiting") == [want]
        assert s_old.of("ddz_waiting") == []
        # Within the second the next change waits for it; the counts go out as they are by then.
        b, _ = w.member("b")
        await w.t.queue(b, 50)
        c, _ = w.member("c")
        await w.t.queue(c, 50)
        assert [h.delay for h in w.counts.live()] == [COUNTS_SEC] and len(s_watch.of("ddz_waiting")) == 1
        w.mono += COUNTS_SEC
        await w.counts.fire()
        assert s_watch.of("ddz_waiting")[-1] == {"type": "ddz_waiting", "counts": [[50, 2], [BASE, 1]]}
        # A newcomer that queues hears them at once; an old client never does.
        late, s_late = w.member("late", room="r-new")
        await w.t.joined("r-new", late)
        assert s_late.of("ddz_waiting") == [{"type": "ddz_waiting", "counts": [[50, 2], [BASE, 1]]}]
        old2, s_old2 = w.member("old2", room="r-new", match=False)
        await w.t.joined("r-new", old2)
        assert s_old2.of("ddz_waiting") == [] and s_old.of("ddz_waiting") == []
        # Nothing changed: nothing goes out.
        w.mono += COUNTS_SEC
        w.t._counts_changed()
        assert len(s_watch.of("ddz_waiting")) == 2
    run(go())


# ------------------------------------------------------------------ tables the queue makes
def test_three_waiting_get_a_table_all_three_accept_and_play_it_across_rooms_to_the_end():
    async def go():
        w = MatchWorld()
        _, s_watch1 = w.member("w1", room="r-a", match=False)
        _, s_watch2 = w.member("w2", room="r-c", match=False)
        (a, sa), (b, sb) = await w.queued("a", "b")
        assert w.t.by_id == {} and len(w.t.lines[BASE]) == 2
        (c, sc), = await w.queued("c")
        assert w.t.waiting == {} and w.t.lines == {}
        tid = sa.of("ddz_invite")[0]["table"]
        invite = {"type": "ddz_invite", "table": tid, "ids": [a.id, b.id, c.id], "base": BASE, "deposit": DEPOSIT,
                  "sec": CFG["inviteSec"], "match": True,
                  "seats": [{"id": p.id, "nick": p.nick, "character": "嘉然"} for p in (a, b, c)]}
        for s in (sa, sb, sc):
            assert s.of("ddz_invite") == [invite] and queue_msgs(s)[-1] == {"base": None}
        assert [h.delay for h in w.timers.live()] == [CFG["inviteSec"]]
        # Every seat answers, the one that waited longest too; nothing is taken until all three accept.
        await w.t.answer(a, tid, True)
        await w.t.answer(b, tid, True)
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3
        await w.t.answer(c, tid, True)
        await settle()
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS - DEPOSIT] * 3
        live = {"type": "ddz_live", "table": tid, "ids": [a.id, b.id, c.id], "on": True}
        # Each seat's room hears of the game, and only those.
        assert s_watch1.of("ddz_live") == [live] and s_watch2.of("ddz_live") == [live] and sb.of("ddz_live") == [live]
        assert w.t.by_id[tid].live_rooms == {"r-a", "r-b", "r-c"}
        deal = sb.of("ddz_deal")[0]
        assert deal["seats"][0] == {"id": a.id, "nick": "a", "character": "嘉然", "auto": False, "away": False}
        w.peers, w.socks = [a, b, c], [sa, sb, sc]
        await w.t.bid(a, tid, 3)
        await play_out(w, tid)
        assert sa.of("ddz_result")[0]["deltas"] == [2700, -1500, -1500]
        assert s_watch2.of("ddz_live")[-1] == {**live, "on": False, "gains": {a.id: 2700}}
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS + 2700, SHARDS - 1500, SHARDS - 1500]
        # Another game, as at an invited table.
        for p in (a, b, c):
            await w.t.again(p, tid)
        await settle()
        assert len(sa.of("ddz_deal")) == 2 and s_watch1.of("ddz_live")[-1] == live
    run(go())


def test_a_decline_puts_the_others_back_at_the_front_and_the_line_goes_on():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc), (d, sd) = await w.queued("a", "b", "c", "d")
        tid = sa.of("ddz_invite")[0]["table"]
        assert [x.peer for x in w.t.lines[BASE]] == [d]
        w.mono += 5
        await w.t.answer(a, tid, True)
        await w.t.answer(b, tid, False)
        await w.t.idle()
        over = {"type": "ddz_over", "table": tid, "reason": "declined", "by": b.id}
        assert sa.of("ddz_over") == [over] and sc.of("ddz_over") == [over]
        # The one who declined is out; the one who accepted and the one who had not answered yet go back ahead of d,
        # keeping how long they waited, and the three of them get the next table at once.
        assert queue_msgs(sb)[-1] == {"base": None, "reason": "ddz_match_cooldown", "retry": 60.0}
        assert queue_msgs(sa)[-2] == {"base": BASE, "waited": 5.0} and queue_msgs(sc)[-2] == {"base": BASE, "waited": 5.0}
        nxt = sd.of("ddz_invite")[0]
        assert nxt["ids"] == [a.id, c.id, d.id] and sa.of("ddz_invite")[-1] == nxt and sb.of("ddz_invite") == [sa.of("ddz_invite")[0]]
        assert w.t.waiting == {}
    run(go())


def test_the_time_running_out_drops_who_did_not_answer():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        await w.t.answer(b, tid, True)
        await w.timers.fire()
        await w.t.idle()
        assert sa.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "timeout"}]
        assert w.t.by_id == {} and [x.peer for x in w.t.lines[BASE]] == [b]
        assert queue_msgs(sa)[-1] == {"base": None, "reason": "ddz_match_cooldown", "retry": 60.0} and queue_msgs(sb)[-1]["base"] == BASE
        (d, sd), (e, se) = await w.queued("d", "e")
        assert sd.of("ddz_invite")[0]["ids"] == [b.id, d.id, e.id]
    run(go())


@pytest.mark.parametrize("how", ["depart", "leave", "dnd"])
def test_leaving_or_turning_invites_down_during_the_invite(how):
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        if how == "depart":
            await w.m.depart("r-c", c.id)
        elif how == "leave":
            await w.t.leave(c, tid)
        else:
            w.t.set_dnd(c, True)
        await w.t.idle()
        reason = "gone" if how == "depart" else "declined"
        assert sa.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": reason, "by": c.id}]
        assert [x.peer for x in w.t.lines[BASE]] == [a, b] and w.who["c"] not in w.t.waiting
    run(go())


def test_a_save_that_cannot_sit_down_any_more_is_dropped_when_the_table_is_made():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb) = await w.queued("a", "b")
        w.g.store.update_player(w.who["a"], shards=10)
        (c, sc), = await w.queued("c")
        assert queue_msgs(sa)[-1] == {"base": None, "reason": "no_shards"}
        assert w.t.by_id == {} and [x.peer for x in w.t.lines[BASE]] == [b, c]
        assert sb.of("ddz_waiting")[0]["counts"] == [[BASE, 1]]
        (d, sd), = await w.queued("d")
        assert sd.of("ddz_invite")[0]["ids"] == [b.id, c.id, d.id]
    run(go())


def test_a_save_never_sits_with_itself_and_one_holding_an_invite_is_skipped():
    async def go():
        w = MatchWorld()
        (a, sa), = await w.queued("a")
        twin, s_twin = w.member("a", room="r-twin")
        with pytest.raises(Exception) as e:
            await w.t.queue(twin, BASE)
        assert e.value.code == "ddz_busy"
        # b waits; an invite from its own room holds it, so a, c and d sit down without it.
        b, sb = w.member("b", room="r")
        await w.t.queue(b, BASE)
        x, _ = w.member("x", room="r")
        y, _ = w.member("y", room="r")
        await w.t.invite("r", x, [b.id, y.id], BASE)
        (c, sc), = await w.queued("c")
        assert w.t.by_save[w.who["b"]].room == "r" and [q.peer for q in w.t.lines[BASE]] == [a, b, c]
        (d, sd), = await w.queued("d")
        assert sd.of("ddz_invite")[0]["ids"] == [a.id, c.id, d.id] and [q.peer for q in w.t.lines[BASE]] == [b]
        # Turned down, b's invite lets it be matched again; accepting one takes it out of the queue.
        invite = sb.of("ddz_invite")[0]["table"]
        await w.t.answer(b, invite, False)
        await w.t.idle()
        assert [q.peer for q in w.t.lines[BASE]] == [b]
        w.t.refused.clear()
        await w.t.invite("r", y, [b.id, x.id], BASE)
        await w.t.answer(b, sb.of("ddz_invite")[-1]["table"], True)
        assert queue_msgs(sb)[-1] == {"base": None} and w.t.lines == {}
    run(go())


def test_inviting_takes_the_inviter_out_of_the_queue():
    async def go():
        w = MatchWorld()
        a, sa = w.member("a", room="r")
        b, _ = w.member("b", room="r")
        c, _ = w.member("c", room="r")
        await w.t.queue(a, BASE)
        await w.t.invite("r", a, [b.id, c.id], BASE)
        assert queue_msgs(sa)[-1] == {"base": None} and w.t.waiting == {}
    run(go())


def test_a_member_comes_back_to_its_seat_from_another_room():
    async def go():
        w = MatchWorld()
        _, s_left = w.member("stays", room="r-b", match=False)
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        for p in (a, b, c):
            await w.t.answer(p, tid, True)
        await settle()
        t = w.t.by_id[tid]
        await w.m.depart("r-b", b.id)
        assert t.seats[1].peer is None and sa.of("ddz_seat")[-1]["away"] is True
        # An old client of the save does not take the seat; one that queues does, in whatever room.
        old, s_old = w.member("b", room="r-x", match=False)
        await w.t.joined("r-x", old)
        assert t.seats[1].peer is None and s_old.of("ddz_state") == []
        _, s_watch = w.member("w", room="r-y", match=False)
        b2, sb2 = w.member("b", room="r-y")
        await w.t.joined("r-y", b2)
        assert t.seats[1].peer is b2 and sb2.of("ddz_state")[0]["you"] == 1
        live = {"type": "ddz_live", "table": tid, "ids": [a.id, b2.id, c.id], "on": True}
        assert s_watch.of("ddz_live") == [live] and sa.of("ddz_live")[-1] == live
        assert t.live_rooms == {"r-a", "r-b", "r-c", "r-y"}
        # The game is called off: the room b left hears it ended as well.
        for p, room in ((a, "r-a"), (b2, "r-y"), (c, "r-c")):
            await w.m.depart(room, p.id)
        await settle()
        assert w.t.by_id == {} and [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3
        assert t.live_rooms == set() and s_left.of("ddz_live")[-1] == {**live, "on": False}
    run(go())


def test_an_invited_table_still_takes_its_seat_back_only_in_its_own_room():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        t = w.t.by_id[tid]
        await w.m.depart("r", w.peers[1].id)
        other, sock = w.join("b", w.pids[1], room="elsewhere")
        other.ddz_match = True
        await w.t.joined("elsewhere", other)
        assert t.seats[1].peer is None and sock.of("ddz_state") == [] and sock.of("ddz_live") == []
    run(go())


def test_open_games_of_tables_the_queue_made_are_refunded_at_startup(tmp_path):
    path = str(tmp_path / "match.db")

    async def go():
        w = MatchWorld()
        w.g = Game(Store(path), Manifest.load(), rng=SeqRng(.5), now=w.clock)
        (a, sa), (b, _), (c, _) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        for p in (a, b, c):
            await w.t.answer(p, tid, True)
        await settle()
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS - DEPOSIT] * 3
        w.g.store.close()
        return [w.who[n] for n in "abc"]

    pids = asyncio.run(go())
    g = Game(Store(path), Manifest.load(), now=Clock())
    assert Bank(g).refund_open() == 1
    assert [g.store.get_player(p, g.now())["shards"] for p in pids] == [SHARDS] * 3


# ------------------------------------------------------------------ over the socket
def matched(ws, nick, room, match=True):
    extra = {"motionVersion": 3, **({"ddzMatch": True} if match else {})}
    return joined(ws, nick, room, **extra)


def receive(ws, kind):
    """The next message of [kind], skipping the counts and anything else before it."""
    while True:
        m = ws.receive_json()
        if m["type"] == kind:
            return m


def test_a_game_the_queue_made_over_the_socket(api):
    c, g, timers = api
    for name in ("a", "b", "c", "old"):
        save(g, name)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as d, \
            c.websocket_connect("/ws") as o:
        ja, jb, jd = matched(a, "a", "r1"), matched(b, "b", "r2"), matched(d, "c", "r3")
        jo = matched(o, "old", "r1", match=False)
        assert "ddz_match" in ja["features"] and "ddz_match" not in jo["features"]
        o.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(o, "error")["code"] == "bad_message"
        a.send_json({"type": "ddz_queue", "base": 123})
        assert receive(a, "error")["code"] == "bad_message"
        a.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(a, "ddz_queue") == {"type": "ddz_queue", "base": BASE, "waited": 0.0}
        assert receive(a, "ddz_waiting") == {"type": "ddz_waiting", "counts": [[BASE, 1]]}
        b.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(b, "ddz_queue")["base"] == BASE
        d.send_json({"type": "ddz_queue", "base": BASE})
        invite = receive(d, "ddz_invite")
        assert invite["match"] is True and invite["ids"] == [ja["you"], jb["you"], jd["you"]] and "from" not in invite
        assert receive(a, "ddz_invite") == invite and receive(b, "ddz_invite") == invite
        tid = invite["table"]
        for ws in (a, b, d):
            ws.send_json({"type": "ddz_answer", "table": tid, "accept": True})
        deals = [receive(ws, "ddz_deal") for ws in (a, b, d)]
        assert [x["you"] for x in deals] == [0, 1, 2] and deals[0]["turn"] == 0
        # The old client in r1 sees the game of its room's member, and nothing of the queue.
        assert receive(o, "ddz_live")["ids"] == invite["ids"]
        a.send_json({"type": "ddz_bid", "table": tid, "bid": 3})
        receive(a, "ddz_landlord")
        hand = list(main.tables.by_id[tid].seats[0].hand)
        socks = {0: a, 1: b, 2: d}
        turn, left = 0, 20
        while left:
            if turn == 0:
                a.send_json({"type": "ddz_play", "table": tid, "cards": [hand.pop(0)]})
                left -= 1
            else:
                socks[turn].send_json({"type": "ddz_play", "table": tid, "cards": []})
            for ws in (a, b, d):
                assert receive(ws, "ddz_play")["seat"] == turn
            turn = (turn + 1) % 3
        result = receive(b, "ddz_result")
        assert result["deltas"] == [2700, -1500, -1500]
        assert receive(o, "ddz_live")["gains"] == {ja["you"]: 2700}
        assert receive(d, "ddz_live")["on"] is False
    me = c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()
    assert me["shards"] == SHARDS + 2700


@pytest.mark.parametrize("match", [True, False])
def test_a_member_back_while_the_deposits_are_taken_gets_the_deal(monkeypatch, match):
    async def go():
        import threading

        gate = threading.Event()
        real = Bank.start

        def slow(self, pids, base):
            gate.wait(5)
            return real(self, pids, base)

        monkeypatch.setattr(Bank, "start", slow)
        if match:
            w = MatchWorld()
            (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
            tid = sa.of("ddz_invite")[0]["table"]
            await w.t.answer(a, tid, True)
            await w.t.answer(b, tid, True)
            back_room, room = "r-y", "r-b"
        else:
            w = MatchWorld()
            w.three()
            a, b, c = w.peers
            sa = w.socks[0]
            await w.t.invite("r", a, [b.id, c.id], BASE)
            tid = sa.of("ddz_invite")[0]["table"]
            await w.t.answer(b, tid, True)
            back_room, room = "r", "r"
        t = w.t.by_id[tid]
        task = asyncio.create_task(w.t.answer(c, tid, True))
        for _ in range(200):
            await asyncio.sleep(0.005)
            if t.phase == "starting":
                break
        assert t.phase == "starting"
        await w.m.depart(room, b.id)
        b2, sb2 = w.join("b2", w.who["b"] if match else w.pids[1], room=back_room)
        b2.ddz_match = True
        await w.t.joined(back_room, b2)
        gate.set()
        await task
        await settle()
        assert t.seats[1].peer is b2 and not t.seats[1].auto
        deal = sb2.of("ddz_deal")
        assert len(deal) == 1 and deal[0]["you"] == 1 and len(deal[0]["hand"]) == 17
        assert deal[0]["seats"][1] == {"id": b2.id, "nick": "b2", "character": "嘉然", "auto": False, "away": False}
    run(go())


def test_an_answer_for_a_table_that_fell_through_does_not_touch_the_next_one():
    async def go():
        w = MatchWorld()
        (a, sa), (b, _), (c, _), (d, _) = await w.queued("a", "b", "c", "d")
        first = sa.of("ddz_invite")[0]["table"]
        await w.t.answer(b, first, False)
        await w.t.idle()
        second = sa.of("ddz_invite")[-1]["table"]
        assert second != first
        with pytest.raises(Exception) as e:
            await w.t.answer(a, first, True)
        assert e.value.code == "ddz_gone"
        assert not w.t.by_id[second].seats[0].accepted and [w.shards(w.who[n]) for n in "acd"] == [SHARDS] * 3
    run(go())


def test_a_save_that_declines_or_lets_the_time_run_out_waits_before_queueing_again():
    async def go():
        from app.ddz import MATCH_RETRY_SEC

        assert MATCH_RETRY_SEC == 60
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        await w.t.answer(a, tid, True)
        await w.t.answer(b, tid, False)
        await w.t.idle()
        # The one who declined hears how long it waits; the others are back in line as before.
        assert queue_msgs(sb)[-1] == {"base": None, "reason": "ddz_match_cooldown", "retry": MATCH_RETRY_SEC}
        assert [x.peer for x in w.t.lines[BASE]] == [a, c]
        with pytest.raises(Exception) as e:
            await w.t.queue(b, BASE)
        assert e.value.code == "ddz_match_cooldown"
        # Inviting is not held up, and the wait ends.
        w.mono += MATCH_RETRY_SEC
        await w.t.queue(b, BASE)
        tid = sb.of("ddz_invite")[-1]["table"]
        assert sb.of("ddz_invite")[-1]["ids"] == [a.id, c.id, b.id]
        # Letting the time run out counts the same, for every seat that did not accept.
        await w.t.answer(a, tid, True)
        await w.timers.fire()
        await w.t.idle()
        for s in (sb, sc):
            assert queue_msgs(s)[-1] == {"base": None, "reason": "ddz_match_cooldown", "retry": MATCH_RETRY_SEC}
        assert queue_msgs(sa)[-1]["base"] == BASE
        for p in (b, c):
            with pytest.raises(Exception) as e:
                await w.t.queue(p, BASE)
            assert e.value.code == "ddz_match_cooldown"
    run(go())


def test_leaving_the_room_during_a_table_of_the_queue_holds_nobody_up():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        await w.m.depart("r-c", c.id)
        c2, sc2 = w.member("c", room="r-c2")
        await w.t.queue(c2, BASE)
        assert queue_msgs(sc2)[0] == {"base": BASE, "waited": 0.0} and sc2.of("ddz_invite")[0]["ids"] == [a.id, b.id, c2.id]
    run(go())


def test_joining_or_moving_in_the_queue_reads_the_save_at_most_once_a_second_per_connection(monkeypatch):
    async def go():
        from app.ddz import QUEUE_INTERVAL

        assert QUEUE_INTERVAL == 1
        checks = []
        real = Bank.check
        monkeypatch.setattr(Bank, "check", lambda self, pids, base: checks.append(base) or real(self, pids, base))
        w = MatchWorld()
        a, sa = w.member("a")
        await w.t.queue(a, BASE)
        with pytest.raises(Exception) as e:
            await w.t.queue(a, 50)
        assert e.value.code == "rate_limited"
        await w.t.queue(a, BASE)  # the stake it waits at: answered without reading the save
        w.t.unqueue(a)  # stopping is never held up
        assert queue_msgs(sa)[-1] == {"base": None}
        with pytest.raises(Exception) as e:
            await w.t.queue(a, BASE)
        assert e.value.code == "rate_limited"
        b, _ = w.member("b")
        await w.t.queue(b, 50)  # another connection is not held up
        w.mono += QUEUE_INTERVAL
        await w.t.queue(a, 50)
        assert checks == [BASE, 50, 50] and queue_msgs(sa)[-1] == {"base": 50, "waited": 0.0}
    run(go())
