"""The dou dizhu queue: waiting at a stake from any room, who may wait, tables the queue makes, and their games."""
import asyncio
import copy
import secrets
import time

import pytest
from starlette.websockets import WebSocketDisconnect

import app.main as main
from app.ddz import COUNTS_SEC, QUEUE_INTERVAL, Bank, Tables
from app.game import FREE_EMOTES, Game, player_id_for
from app.manifest import Manifest
from app.rooms import Peer
from app.store import Store
from fixtures import Clock, SeqRng
from test_ddz import BASE, CFG, DEPOSIT, SHARDS, Stacked, World, api, joined, play_out, save, tok  # noqa: F401
from test_duel import ManualTimers, Sock, settle


class MatchWorld(World):
    """Saves on dou dizhu connections (in no room) by default; members of rooms on clients that queue when asked."""

    def __init__(self, manifest=None, rng=None, require_account=False):
        super().__init__(manifest, rng or Stacked(first=0))
        self.counts = ManualTimers()
        self.t = Tables(lambda: self.g, lambda: self.m, timers=self.timers, clock=lambda: self.mono, rng=self.rng,
                        require_account=lambda: require_account, count_timers=self.counts)
        self.m.on_depart = self.t.departed
        self.who = {}

    def member(self, name, room=None, match=True, **kw):
        """A connection of the save named [name] (made on first use): a dou dizhu connection, or with [room] a member
        of that room."""
        pid = self.who.get(name) or save(self.g, name, **kw)
        self.who[name] = pid
        if room is None:
            return self.lobby(name, pid)
        peer, sock = self.join(name, pid, room=room)
        peer.ddz_match = match
        return peer, sock

    def lobby(self, nick, pid):
        """A dou dizhu connection of save [pid], known to the tables (as after hello, without its messages)."""
        sock = Sock()
        peer = Peer(id=secrets.token_hex(4), nick=nick, character="嘉然", ws=sock, token=pid, lobby=True, ddz=True,
                    ddz_match=True)
        peer.join_seq = self.m.next_seq()
        peer.enqueue = lambda data, done=None: sock.got.append(data) if peer.active else None
        self.t.lobby[peer.id] = peer
        return peer, sock

    async def bye(self, peer):
        """The dou dizhu connection [peer] closes."""
        peer.active = False
        await self.t.bye(peer)

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
    ("account", "ddz_account"), ("dnd", "ddz_dnd"), ("stake", "bad_message"), ("room", "bad_message"),
    ("twin", "ddz_queued"), ("seated", "ddz_busy"),
])
def test_who_may_not_wait(how, code):
    async def go():
        w = MatchWorld(require_account=how == "account")
        if how == "guest":
            peer, _ = w.lobby("guest", None)
        else:
            # A room connection, its client queueing or not, does not queue: the dou dizhu connection does.
            peer, _ = w.member("a", room="r-a" if how == "room" else None, taps=9_999 if how == "taps" else 10_000,
                               shards=DEPOSIT - 1 if how == "poor" else SHARDS)
        peer.dnd = how == "dnd"
        if how == "cap":
            others = [save(w.g, n, shards=10_000_000) for n in "xy"]
            w.g.store.update_player(w.who["a"], shards=10_000_000)
            for _ in range(3):
                w.bank.settle(w.bank.start([w.who["a"], *others], 500), 0, True, 24)
        if how == "twin":
            twin, _ = w.member("a")
            await w.t.queue(twin, BASE)
        if how == "seated":
            w.three()
            await w.t.invite("r", w.peers[0], [w.peers[1].id, w.peers[2].id], BASE)
            peer, _ = w.lobby("b", w.pids[1])
        with pytest.raises(Exception) as e:
            await w.t.queue(peer, 123 if how == "stake" else BASE)
        assert getattr(e.value, "code", None) == code
        assert all(x.peer is not peer for x in w.t.waiting.values())
    run(go())


def test_closing_the_connection_turning_invites_down_or_the_stake_going_takes_a_save_out():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb) = await w.queued("a", "b")
        c, sc = w.member("c")
        await w.t.queue(c, 50)
        await w.bye(a)
        assert w.who["a"] not in w.t.waiting
        # A room connection of the save coming and going, or turning invites down, changes nothing; turning them down
        # on the connection that waits does.
        c_room, _ = w.member("c", room="r-c")
        await w.m.depart("r-c", c_room.id)
        b_room, _ = w.member("b", room="r-b")
        b_room.dnd = True
        w.t.set_dnd(b_room, True)
        assert queue_msgs(sb)[-1] == {"base": BASE, "waited": 0.0} and [x.peer for x in w.t.lines[BASE]] == [b]
        b.dnd = True
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
        _, s_none = w.member("w3", room="r-none", match=False)
        # a and c are in rooms on their room connections too; b is in none.
        a_room, sa_room = w.member("a", room="r-a")
        c_room, _ = w.member("c", room="r-c")
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
        assert sa_room.of("ddz_invite") == []
        assert [h.delay for h in w.timers.live()] == [CFG["inviteSec"]]
        # Every seat answers, the one that waited longest too; nothing is taken until all three accept.
        await w.t.answer(a, tid, True)
        await w.t.answer(b, tid, True)
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3
        await w.t.answer(c, tid, True)
        await settle()
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS - DEPOSIT] * 3
        # The rooms the seats' saves are in hear of the game, by the member ids they know them by, and only those.
        live_a = {"type": "ddz_live", "table": tid, "ids": [a_room.id, b.id, c.id], "on": True, "base": BASE}
        live_c = {"type": "ddz_live", "table": tid, "ids": [a.id, b.id, c_room.id], "on": True, "base": BASE}
        assert s_watch1.of("ddz_live") == [live_a] and sa_room.of("ddz_live") == [live_a]
        assert s_watch2.of("ddz_live") == [live_c] and s_none.of("ddz_live") == [] and sb.of("ddz_live") == []
        assert w.t.by_id[tid].live_rooms == {"r-a", "r-c"}
        deal = sb.of("ddz_deal")[0]
        assert deal["seats"][0] == {"id": a.id, "nick": "a", "character": "嘉然", "auto": False, "away": False}
        w.peers, w.socks = [a, b, c], [sa, sb, sc]
        await w.t.bid(a, tid, 3)
        await play_out(w, tid)
        assert sa.of("ddz_result")[0]["deltas"] == [2700, -1500, -1500]
        # The winner's pet in its room shows the shards.
        assert s_watch1.of("ddz_live")[-1] == {"type": "ddz_live", "table": tid, "ids": live_a["ids"], "on": False,
                                                "gains": {a_room.id: 2700}}
        assert s_watch2.of("ddz_live")[-1] == {"type": "ddz_live", "table": tid, "ids": live_c["ids"], "on": False,
                                                "gains": {a.id: 2700}}
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS + 2700, SHARDS - 1500, SHARDS - 1500]
        # Another game, as at an invited table.
        for p in (a, b, c):
            await w.t.again(p, tid)
        await settle()
        assert len(sa.of("ddz_deal")) == 2 and s_watch1.of("ddz_live")[-1] == live_a
    run(go())


def test_a_decline_puts_the_others_back_ahead_of_later_saves_and_the_line_goes_on():
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


@pytest.mark.parametrize("how", ["poor", "error"])
def test_a_start_that_falls_short_puts_the_three_back_in_the_line(how, monkeypatch):
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        w.mono += 4
        await w.t.answer(a, tid, True)
        await w.t.answer(b, tid, True)
        if how == "poor":
            w.g.store.update_player(w.who["b"], shards=DEPOSIT - 1)
        else:
            # The database fails once the deposits are taken, and is there again.
            monkeypatch.setattr(Bank, "start", lambda *x: 1 / 0)
        await w.t.answer(c, tid, True)
        await w.t.idle()
        reason = {"poor": "no_shards", "error": "error"}[how]
        for s in (sa, sb, sc):
            assert s.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": reason}]
        assert w.g.store.open_ddz_games() == [] and tid not in w.t.by_id
        if how == "poor":
            # Read again in the line: the one that may no longer play leaves it, told why; the others wait on.
            assert queue_msgs(sb)[-1] == {"base": None, "reason": "no_shards"} and w.who["b"] not in w.t.waiting
            assert [x.peer for x in w.t.lines[BASE]] == [a, c] and w.t.by_id == {}
            assert queue_msgs(sa)[-1] == queue_msgs(sc)[-1] == {"base": BASE, "waited": 4.0}
        else:
            # All three may still play: asked again, as at any table of the queue.
            assert [s.of("ddz_invite")[-1]["ids"] for s in (sa, sb, sc)] == [[a.id, b.id, c.id]] * 3
            assert len(sa.of("ddz_invite")) == 2 and w.t.waiting == {}
    run(go())


def test_another_game_that_falls_short_puts_nobody_back_in_the_line():
    async def go():
        w = MatchWorld()
        three = await w.queued("a", "b", "c")
        w.peers = [p for p, _ in three]
        socks = [s for _, s in three]
        tid = socks[0].of("ddz_invite")[0]["table"]
        for p in w.peers:
            await w.t.answer(p, tid, True)
        await w.t.bid(w.peers[0], tid, 3)
        await play_out(w, tid)
        w.g.store.update_player(w.who["c"], shards=0)
        for p in w.peers:
            await w.t.again(p, tid)
        await w.t.idle()
        assert socks[0].of("ddz_over")[-1] == {"type": "ddz_over", "table": tid, "reason": "no_shards"}
        assert w.t.waiting == {} and w.t.lines == {}
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


@pytest.mark.parametrize("how", ["close", "leave", "dnd"])
def test_leaving_or_turning_invites_down_during_the_invite(how):
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        if how == "close":
            await w.bye(c)
        elif how == "leave":
            await w.t.leave(c, tid)
        else:
            w.t.set_dnd(c, True)
        await w.t.idle()
        reason = "gone" if how == "close" else "declined"
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
        twin, s_twin = w.member("a")
        with pytest.raises(Exception) as e:
            await w.t.queue(twin, BASE)
        assert e.value.code == "ddz_queued"
        # b waits; an invite in a room it is in, on its room connection, takes it out of the line while it is out,
        # so a, c and d sit down without it.
        b, sb = w.member("b")
        await w.t.queue(b, BASE)
        b_room, sb_room = w.member("b", room="r")
        x, _ = w.member("x", room="r")
        y, _ = w.member("y", room="r")
        await w.t.invite("r", x, [b_room.id, y.id], BASE)
        assert queue_msgs(sb)[-1] == {"base": None} and w.t.counts() == {BASE: 1}
        (c, sc), = await w.queued("c")
        assert w.t.by_save[w.who["b"]].room == "r" and [q.peer for q in w.t.lines[BASE]] == [a, c]
        (d, sd), = await w.queued("d")
        assert sd.of("ddz_invite")[0]["ids"] == [a.id, c.id, d.id] and w.t.lines == {}
        # Turned down by b itself: it waits again, in its place; inviting it again waits for the invite cooldown.
        invite = sb_room.of("ddz_invite")[0]["table"]
        await w.t.answer(b_room, invite, False)
        await w.t.idle()
        assert [q.peer for q in w.t.lines[BASE]] == [b] and queue_msgs(sb)[-1]["base"] == BASE
        with pytest.raises(Exception) as e:
            await w.t.invite("r", x, [b_room.id, y.id], BASE)
        assert e.value.code == "ddz_cooldown"
        # Its room connection turning invites down turns the invite down, and the place comes back: it belongs to the
        # dou dizhu connection that waits.
        held = w.t.waiting[w.who["b"]]
        await w.t.invite("r", y, [b_room.id, x.id], BASE)
        assert w.t.waiting == {}
        b_room.dnd = True
        w.t.set_dnd(b_room, True)
        await w.t.idle()
        assert sb_room.of("ddz_over")[-1]["reason"] == "declined"
        assert [q.peer for q in w.t.lines[BASE]] == [b] and w.t.waiting[w.who["b"]].seq == held.seq
        # Turning them down on the connection that waits gives no place back.
        b_room.dnd = False
        z, _ = w.member("z", room="r")
        await w.t.invite("r", z, [b_room.id, x.id], BASE)
        assert w.t.waiting == {}
        b.dnd = True
        w.t.set_dnd(b, True)
        await w.t.idle()
        assert w.t.by_save.get(w.who["b"]) is None and w.t.waiting == {}
    run(go())


@pytest.mark.parametrize("how", ["other_declines", "expires", "cancelled", "start_fails"])
def test_an_invite_that_comes_to_nothing_gives_the_invited_their_places_back(how):
    async def go():
        w = MatchWorld()
        (e, se), (b, sb) = await w.queued("e", "b")
        w.mono += 5
        (f, sf), = await w.queued("f", base=50)
        held = w.t.waiting[w.who["b"]]
        b_room, sb_room = w.member("b", room="r")
        x, sx = w.member("x", room="r")
        y, sy = w.member("y", room="r")
        await w.t.invite("r", x, [b_room.id, y.id], BASE)
        if how == "start_fails":
            w.g.store.update_player(w.who["y"], shards=0)
        tid = sx.of("ddz_invite")[0]["table"]
        assert [q.peer for q in w.t.lines[BASE]] == [e] and queue_msgs(sb)[-1] == {"base": None}
        await w.t.answer(b_room, tid, True)
        if how == "other_declines":
            await w.t.answer(y, tid, False)
        elif how == "expires":
            await w.timers.fire()
        elif how == "cancelled":
            await w.t.leave(x, tid)
        else:
            await w.t.answer(y, tid, True)
        await w.t.idle()
        assert tid not in w.t.by_id
        # Back where it was: behind e, which queued with it, its time waited kept.
        assert [q.peer for q in w.t.lines[BASE]] == [e, b]
        back = w.t.waiting[w.who["b"]]
        assert (back.since, back.seq) == (held.since, held.seq)
        assert queue_msgs(sb)[-1] == {"base": BASE, "waited": 5.0}
    run(go())



def test_inviting_in_a_room_takes_the_save_out_of_the_queue():
    async def go():
        w = MatchWorld()
        a, sa = w.member("a")
        a_room, _ = w.member("a", room="r")
        b, _ = w.member("b", room="r")
        c, _ = w.member("c", room="r")
        await w.t.queue(a, BASE)
        await w.t.invite("r", a_room, [b.id, c.id], BASE)
        assert queue_msgs(sa)[-1] == {"base": None} and w.t.waiting == {}
    run(go())


def test_a_room_connection_does_not_queue():
    async def go():
        w = MatchWorld()
        a, sa = w.member("a", room="r")
        with pytest.raises(Exception) as e:
            await w.t.queue(a, BASE)
        assert e.value.code == "bad_message" and w.t.waiting == {}
    run(go())


def test_a_new_dou_dizhu_connection_takes_the_seat_back_and_a_room_join_does_not():
    async def go():
        w = MatchWorld()
        _, s_left = w.member("stays", room="r-b", match=False)
        b_room, sb_room = w.member("b", room="r-b")
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        for p in (a, b, c):
            await w.t.answer(p, tid, True)
        await settle()
        t = w.t.by_id[tid]
        assert s_left.of("ddz_live") == [{"type": "ddz_live", "table": tid, "ids": [a.id, b_room.id, c.id], "on": True,
                                         "base": BASE}]
        assert w.t.holds(w.who["b"]) and not w.t.holds(w.who["stays"])
        await w.bye(b)
        assert t.seats[1].peer is None and sa.of("ddz_seat")[-1]["away"] is True and w.t.holds(w.who["b"])
        # A room join of the save does not take the seat, in any room, on any client.
        b_x, s_x = w.member("b", room="r-x")
        await w.t.joined("r-x", b_x)
        assert t.seats[1].peer is None and s_x.of("ddz_state") == []
        assert s_x.of("ddz_live") == [{"type": "ddz_live", "table": tid, "ids": [a.id, b_x.id, c.id], "on": True,
                                      "base": BASE}]
        # A new dou dizhu connection does, with its own nick: it hears it is ready first, then the whole game.
        b2, sb2 = w.lobby("b2", w.who["b"])
        await w.t.hello(b2)
        assert sb2.got[0] == {"type": "ddz_ready", "you": b2.id, "base": None, "table": tid}
        assert t.seats[1].peer is b2 and sb2.of("ddz_state")[0]["you"] == 1
        assert sa.of("ddz_seat")[-1] == {"type": "ddz_seat", "table": tid, "seat": 1, "id": b2.id, "away": False,
                                         "auto": False, "nick": "b2", "character": "嘉然", "plate": None}
        # The game is called off: a room none of the saves is in by then hears that it ended, and only that.
        await w.m.depart("r-b", b_room.id)
        for p in (a, b2, c):
            await w.bye(p)
        await settle()
        assert w.t.by_id == {} and [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3
        assert t.live_rooms == set() and s_left.of("ddz_live")[-1] == {"type": "ddz_live", "table": tid, "on": False}
        assert s_x.of("ddz_live")[-1] == {"type": "ddz_live", "table": tid, "ids": [a.id, b_x.id, c.id], "on": False}
        assert not w.t.holds(w.who["b"])
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


def hello(ws, nick, **extra):
    """Opens a dou dizhu connection for the save of [nick]; returns its ddz_ready."""
    ws.send_json({"type": "ddz_hello", "nick": nick, "token": tok(nick), **extra})
    return receive(ws, "ddz_ready")


def test_a_game_the_queue_made_over_the_socket(api):
    c, g, timers = api
    for name in ("a", "b", "c", "old"):
        save(g, name)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as d, \
            c.websocket_connect("/ws") as o, c.websocket_connect("/ws") as ar:
        ra, rb, rd = hello(a, "a"), hello(b, "b"), hello(d, "c")
        assert ra == {"type": "ddz_ready", "you": ra["you"], "base": None, "table": None}
        # An old client in r1, and a's room connection there.
        jo = matched(o, "old", "r1", match=False)
        jar = matched(ar, "a", "r1")
        assert {"ddz_match", "ddz_emote"} <= set(jar["features"]) and "ddz_match" not in jo["features"]
        assert "ddz_emote" not in jo["features"]
        # Room connections do not queue, whatever their client.
        for ws in (o, ar):
            ws.send_json({"type": "ddz_queue", "base": BASE})
            assert receive(ws, "error")["code"] == "bad_message"
        a.send_json({"type": "ddz_queue", "base": 123})
        assert receive(a, "error")["code"] == "bad_message"
        a.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(a, "ddz_queue") == {"type": "ddz_queue", "base": BASE, "waited": 0.0}
        assert receive(a, "ddz_waiting") == {"type": "ddz_waiting", "counts": [[BASE, 1]]}
        assert receive(ar, "ddz_waiting") == {"type": "ddz_waiting", "counts": [[BASE, 1]]}
        assert c.get("/api/ddz/lobby", headers={"X-Player-Token": tok("old")}).json()["tiers"][1]["waiting"] == 1
        b.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(b, "ddz_queue")["base"] == BASE
        d.send_json({"type": "ddz_queue", "base": BASE})
        invite = receive(d, "ddz_invite")
        assert invite["match"] is True and invite["ids"] == [ra["you"], rb["you"], rd["you"]] and "from" not in invite
        assert receive(a, "ddz_invite") == invite and receive(b, "ddz_invite") == invite
        tid = invite["table"]
        for ws in (a, b, d):
            ws.send_json({"type": "ddz_answer", "table": tid, "accept": True})
        deals = [receive(ws, "ddz_deal") for ws in (a, b, d)]
        assert [x["you"] for x in deals] == [0, 1, 2] and deals[0]["turn"] == 0
        # r1 sees the game of its member a, by a's member id there; the old client hears nothing of the queue.
        assert receive(o, "ddz_live")["ids"] == [jar["you"], rb["you"], rd["you"]]
        assert c.get("/api/ddz/lobby", headers={"X-Player-Token": tok("a")}).json()["seated"] is True
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
        assert receive(o, "ddz_live")["gains"] == {jar["you"]: 2700}
        assert receive(ar, "ddz_live")["on"] is True and receive(ar, "ddz_live")["on"] is False
    me = c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()
    assert me["shards"] == SHARDS + 2700


def test_hello_checks_the_save_the_nick_the_pet_and_the_plate_as_join_does(api, monkeypatch):
    c, g, timers = api
    save(g, "a")
    save(g, "坏a")
    monkeypatch.setattr(main.blocklist, "mask", lambda s: s.replace("坏", "*"))
    skin = next(iter(g.manifest.skins))
    with c.websocket_connect("/ws") as a:
        a.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(a, "error")["code"] == "not_joined"
        ready = hello(a, "坏a", character=skin, plate="achao")
        peer = main.tables.lobby[ready["you"]]
        assert peer.lobby and peer.room == "" and peer.token == player_id_for(tok("坏a"))
        # The nick masked, a skin the save does not own shown as its member, a plate it has not unlocked dropped.
        assert (peer.nick, peer.character, peer.plate) == ("*a", g.base_character(skin), None)
        hello_again = {"type": "ddz_hello", "nick": "a", "token": tok("a")}
        a.send_json(hello_again)
        assert receive(a, "error")["code"] == "already_joined"
        a.send_json({"type": "join", "room": "r", "nick": "a", "token": tok("a")})
        assert receive(a, "error")["code"] == "already_joined"
        # Room messages are not for it (opening and sitting go to the hall, calling stays a room's).
        for msg in ({"type": "tap", "count": 1}, {"type": "ddz_call", "table": "x", "id": "y"},
                    {"type": "emote", "emote": "x"}):
            a.send_json(msg)
            assert receive(a, "error")["code"] == "not_joined"
        a.send_json({"type": "leave"})
        a.send_json({"type": "ping"})
        receive(a, "pong")
        assert ready["you"] not in main.tables.lobby and not peer.active
    # A connection without a save (a guest token of none, one linked to an account) is refused, for good.
    with c.websocket_connect("/ws") as x:
        x.send_json({"type": "ddz_hello", "nick": "nobody", "token": ""})
        assert receive(x, "error") == {"type": "error", "code": "room_full", "message": "", "reason": "ddz_locked"}
        assert main.tables.lobby == {}
        # The server closed the connection.
        with pytest.raises(WebSocketDisconnect):
            x.receive_json()
    assert main.tables.lobby == {}


def test_hello_is_refused_without_the_game_or_on_an_old_client(api, monkeypatch):
    c, g, timers = api
    data = copy.deepcopy(Manifest.load().data)
    del data["economy"]["doudizhu"]
    monkeypatch.setattr(main, "game", Game(Store(":memory:"), Manifest(data), now=Clock()))
    with c.websocket_connect("/ws") as a:
        a.send_json({"type": "ddz_hello", "nick": "a", "token": tok("a")})
        assert receive(a, "error")["code"] == "no_ddz"
    assert main.tables.lobby == {}
    assert c.get("/api/ddz/lobby", headers={"X-Player-Token": tok("a")}).status_code == 404


def test_closing_the_dou_dizhu_connection_while_queued(api):
    c, g, timers = api
    for name in "ab":
        save(g, name)
    with c.websocket_connect("/ws") as a:
        hello(a, "a")
        a.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(a, "ddz_queue")["base"] == BASE
        assert main.tables.counts() == {BASE: 1}
    for _ in range(100):
        if not main.tables.waiting:
            break
        time.sleep(0.01)
    assert main.tables.waiting == {} and main.tables.lobby == {}


def test_the_lobby_shows_the_stakes_the_cap_and_the_rules(api, monkeypatch):
    c, g, timers = api
    rich = save(g, "rich", shards=DEPOSIT)
    save(g, "new", taps=99)
    get = lambda name: c.get("/api/ddz/lobby", headers={"X-Player-Token": tok(name)}).json()  # noqa: E731
    lobby = get("rich")
    assert lobby == {
        "tiers": [{"base": b, "deposit": b * CFG["capMult"] * 2, "afford": b <= BASE, "waiting": 0,
                   "tables": []}
                  for b in CFG["stakes"]],
        "net": 0, "cap": CFG["dailyWinCap"], "left": CFG["dailyWinCap"], "taps": 10_000, "minTaps": CFG["minTaps"],
        "account": True, "seated": False,
    }
    assert get("new")["taps"] == 99
    others = [save(g, n, shards=10_000_000) for n in "xy"]
    Bank(g).settle(Bank(g).start([rich, *others], 50), 0, True, 24)
    lobby = get("rich")
    assert lobby["net"] == 2160 and lobby["left"] == CFG["dailyWinCap"] - 2160
    monkeypatch.setattr(main.tables, "require_account", lambda: True)
    assert get("rich")["account"] is False


def test_emotes_go_through_the_table_to_every_seat_and_as_room_emotes_to_old_clients():
    async def go():
        # An invited table of room r: a and b on clients that know table emotes, c on 1.2.5.
        w = MatchWorld()
        tid = await w.playing()
        a, b, c = w.peers
        sa, sb, sc = w.socks
        a.ddz_match = b.ddz_match = True
        _, s_watch = w.join("watch", save(w.g, "watch"))
        w.t.emote(a, tid, "hi")
        assert sb.of("ddz_emote") == [{"type": "ddz_emote", "table": tid, "seat": 0, "emote": "hi"}]
        assert sc.of("emote") == [{"type": "emote", "id": a.id, "emote": "hi"}] and sc.of("ddz_emote") == []
        # Nobody hears it twice, the sender and the rest of the room nothing.
        assert sb.of("emote") == [] and sa.of("ddz_emote") == sa.of("emote") == [] and s_watch.got == []
        # At a table the queue made, the seats hear it in whatever room, or none.
        w2 = MatchWorld()
        (x, sx), (y, sy), (z, sz) = await w2.queued("x", "y", "z")
        t2 = sx.of("ddz_invite")[0]["table"]
        with pytest.raises(Exception) as e:
            w2.t.emote(x, t2, "hi")  # not before the game
        assert e.value.code == "ddz_gone"
        for p in (x, y, z):
            await w2.t.answer(p, t2, True)
        await settle()
        w2.t.emote(z, t2, "hi")
        heard = {"type": "ddz_emote", "table": t2, "seat": 2, "emote": "hi"}
        assert [s.of("ddz_emote") for s in (sx, sy, sz)] == [[heard], [heard], []]
        stranger, _ = w2.member("q")
        with pytest.raises(Exception) as e:
            w2.t.emote(stranger, t2, "hi")
        assert e.value.code == "ddz_gone"
    run(go())


def test_table_emotes_over_the_socket_are_owned_and_rate_limited(api):
    c, g, timers = api
    for name in "abc":
        save(g, name)
    free = next(iter(FREE_EMOTES))
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as d:
        ids = [hello(ws, n)["you"] for ws, n in ((a, "a"), (b, "b"), (d, "c"))]
        for ws in (a, b, d):
            ws.send_json({"type": "ddz_queue", "base": BASE})
            receive(ws, "ddz_queue")
        tid = receive(a, "ddz_invite")["table"]
        for ws in (a, b, d):
            ws.send_json({"type": "ddz_answer", "table": tid, "accept": True})
        for ws in (a, b, d):
            receive(ws, "ddz_deal")
        a.send_json({"type": "ddz_emote", "table": tid, "emote": "not-an-emote"})
        assert receive(a, "error")["code"] == "locked"
        a.send_json({"type": "ddz_emote", "table": tid, "emote": free})
        assert receive(b, "ddz_emote") == {"type": "ddz_emote", "table": tid, "seat": 0, "emote": free}
        a.send_json({"type": "ddz_emote", "table": tid, "emote": free})
        assert receive(a, "error")["code"] == "rate_limited"
        a.send_json({"type": "ddz_emote", "table": "nope", "emote": free})
        assert receive(a, "error")["code"] in ("ddz_gone", "rate_limited")
    assert ids


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
        else:
            w = MatchWorld()
            w.three()
            a, b, c = w.peers
            sa = w.socks[0]
            await w.t.invite("r", a, [b.id, c.id], BASE)
            tid = sa.of("ddz_invite")[0]["table"]
            await w.t.answer(b, tid, True)
        t = w.t.by_id[tid]
        task = asyncio.create_task(w.t.answer(c, tid, True))
        for _ in range(200):
            await asyncio.sleep(0.005)
            if t.phase == "starting":
                break
        assert t.phase == "starting"
        if match:
            # Its dou dizhu connection closes, and a new one says hello.
            await w.bye(b)
            b2, sb2 = w.lobby("b2", w.who["b"])
            await w.t.hello(b2)
        else:
            await w.m.depart("r", b.id)
            b2, sb2 = w.join("b2", w.pids[1], room="r")
            b2.ddz_match = True
            await w.t.joined("r", b2)
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


def test_closing_the_connection_during_a_table_of_the_queue_counts_as_declining():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        await w.t.answer(c, sa.of("ddz_invite")[0]["table"], True)
        # Accepted or not, leaving before all three did holds the save back: leaving and coming back cannot
        # rematch the same two at once.
        await w.bye(c)
        await w.t.idle()
        c2, sc2 = w.member("c")
        with pytest.raises(Exception) as e:
            await w.t.queue(c2, BASE)
        assert e.value.code == "ddz_match_cooldown"
        assert [x.peer for x in w.t.lines[BASE]] == [a, b]
    run(go())


def test_joining_or_moving_in_the_queue_reads_the_save_at_most_once_a_second_per_save(monkeypatch):
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
        await w.t.queue(b, 50)  # another save is not held up
        w.mono += QUEUE_INTERVAL
        await w.t.queue(a, 50)
        assert checks == [BASE, 50, 50] and queue_msgs(sa)[-1] == {"base": 50, "waited": 0.0}
    run(go())


def test_a_new_connection_of_the_save_does_not_get_round_the_queue_interval(monkeypatch):
    async def go():
        checks = []
        real = Bank.check
        monkeypatch.setattr(Bank, "check", lambda self, pids, base: checks.append(base) or real(self, pids, base))
        w = MatchWorld()
        a, _ = w.member("a")
        await w.t.queue(a, BASE)
        await w.bye(a)
        a2, _ = w.member("a")
        with pytest.raises(Exception) as e:
            await w.t.queue(a2, BASE)
        assert e.value.code == "rate_limited"
        # Two connections of one save asking at once: the second is held up before the save is read again.
        w.mono += 1
        a3, _ = w.member("a")
        await asyncio.gather(w.t.queue(a2, 50), w.t.queue(a3, 50), return_exceptions=True)
        assert checks == [BASE, 50]
    run(go())


def test_a_save_put_back_stays_behind_one_that_queued_before_it_at_the_same_time():
    async def go():
        w = MatchWorld()
        # g queues first, then an invite in its room holds it; a, b and c, queued at the same time, sit down.
        g, sg = w.member("g")
        await w.t.queue(g, BASE)
        g_room, sg_room = w.member("g", room="r")
        x, _ = w.member("x", room="r")
        y, _ = w.member("y", room="r")
        await w.t.invite("r", x, [g_room.id, y.id], BASE)
        (a, sa), (b, _), (c, _) = await w.queued("a", "b", "c")
        await w.t.answer(g_room, sg_room.of("ddz_invite")[0]["table"], False)
        await w.t.answer(a, sa.of("ddz_invite")[0]["table"], True)
        await w.timers.fire()
        await w.t.idle()
        assert [q.peer for q in w.t.lines[BASE]] == [g, a]
    run(go())


def test_saves_put_back_from_two_tables_keep_the_order_they_came_in():
    async def go():
        w = MatchWorld()
        (a, sa), (b, _), (c, _) = await w.queued("a", "b", "c")
        w.mono += 5
        (d, sd), (e, _), (f, _) = await w.queued("d", "e", "f")
        await w.t.answer(a, sa.of("ddz_invite")[0]["table"], True)
        await w.t.answer(d, sd.of("ddz_invite")[0]["table"], True)
        # Both lapse, the older table first: a has waited longer than d and stays ahead of it.
        await w.timers.fire()
        await w.t.idle()
        assert [x.peer for x in w.t.lines[BASE]] == [a, d]
        g, sg = w.member("g")
        await w.t.queue(g, BASE)
        assert sg.of("ddz_invite")[0]["ids"] == [a.id, d.id, g.id]
    run(go())


def test_a_newcomer_hears_the_counts_everyone_has_and_every_correction_after():
    async def go():
        w = MatchWorld()
        a, sa = w.member("a")
        await w.t.queue(a, BASE)
        b, _ = w.member("b")
        await w.t.queue(b, 50)  # within the second: the others hear it with the next send
        late, s_late = w.member("late", room="r-new")
        await w.t.joined("r-new", late)
        w.t.unqueue(b)  # back to what the others have
        w.mono += COUNTS_SEC
        await w.counts.fire()
        assert sa.of("ddz_waiting")[-1]["counts"] == [[BASE, 1]]
        assert s_late.of("ddz_waiting")[-1]["counts"] == [[BASE, 1]]
    run(go())


def test_a_room_connection_never_queues_over_the_socket(api):
    c, g, timers = api
    save(g, "old")
    save(g, "new")
    with c.websocket_connect("/ws") as o, c.websocket_connect("/ws") as n:
        matched(o, "old", "r1", match=False)
        matched(n, "new", "r1")
        for ws in (o, n):
            for base in (0, BASE):
                ws.send_json({"type": "ddz_queue", "base": base})
                assert receive(ws, "error")["code"] == "bad_message"


def test_a_save_turning_invites_down_on_one_device_queues_from_another_over_the_socket(api):
    c, g, timers = api
    save(g, "a")
    with c.websocket_connect("/ws") as ar, c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as a2:
        # One device in a room with invites turned down (click-through counts), the other with nothing on.
        joined(ar, "a", "r1", motionVersion=3, ddzMatch=True, dnd=True)
        ra = hello(a, "a")
        a.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(a, "ddz_queue")["base"] == BASE
        # Turned on again there: the place stays (the room connection's ddz_queue answers once the dnd is read).
        ar.send_json({"type": "dnd", "dnd": True})
        ar.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(ar, "error")["code"] == "bad_message"
        a.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(a, "ddz_queue")["base"] == BASE
        assert main.tables.waiting[player_id_for(tok("a"))].peer.id == ra["you"]
        # A dou dizhu connection turning them down itself is refused.
        a.send_json({"type": "ddz_queue", "base": 0})
        assert receive(a, "ddz_queue")["base"] is None
        hello(a2, "a", dnd=True)
        a2.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(a2, "error")["code"] == "ddz_dnd"


def test_a_new_dou_dizhu_connection_takes_the_seat_before_the_old_one_is_seen_to_go():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        for p in (a, b, c):
            await w.t.answer(p, tid, True)
        await settle()
        t = w.t.by_id[tid]
        b2, sb2 = w.member("b")
        await w.t.hello(b2)
        assert t.seats[1].peer is b2 and sb.of("ddz_closed") == [{"type": "ddz_closed", "table": tid}]
        await w.bye(b)
        await settle()
        assert t.seats[1].peer is b2 and sb2.of("ddz_state")[0]["you"] == 1
        # One that finishes saying hello late does not take it from the newer one.
        late, s_late = w.lobby("b", w.who["b"])
        late.join_seq = 0
        await w.t.hello(late)
        assert t.seats[1].peer is b2 and s_late.of("ddz_state") == []
    run(go())


def test_a_new_dou_dizhu_connection_takes_over_the_place_in_the_line():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb) = await w.queued("a", "b")
        w.mono += 7
        # Back on a new connection before the old one is seen to go: the place is kept, the old one is told.
        a2, sa2 = w.member("a")
        await w.t.hello(a2)
        assert sa2.got[0] == {"type": "ddz_ready", "you": a2.id, "base": BASE, "waited": 7.0, "table": None}
        assert queue_msgs(sa)[-1] == {"base": None} and [x.peer for x in w.t.lines[BASE]] == [a2, b]
        await w.bye(a)
        assert [x.peer for x in w.t.lines[BASE]] == [a2, b]
        (c, sc), = await w.queued("c")
        assert sa2.of("ddz_invite")[0]["ids"] == [a2.id, b.id, c.id] and sa.of("ddz_invite") == []
        # One turning invites down takes the save out instead.
        w2 = MatchWorld()
        (d, sd), = await w2.queued("d")
        d2, sd2 = w2.member("d")
        d2.dnd = True
        await w2.t.hello(d2)
        assert sd2.got[0]["base"] is None and w2.t.waiting == {}
        # Closed first: the place is gone, and the new connection queues again.
        w3 = MatchWorld()
        (e, se), = await w3.queued("e")
        await w3.bye(e)
        e2, se2 = w3.member("e")
        await w3.t.hello(e2)
        assert se2.got[0] == {"type": "ddz_ready", "you": e2.id, "base": None, "table": None} and w3.t.waiting == {}
    run(go())


def lobby_closed(name=None):
    """Waits for the dou dizhu connections to be let go (the endpoint's thread runs on its own)."""
    for _ in range(200):
        if name is None and not main.tables.lobby or name is not None and len(
                [p for p in main.tables.lobby.values() if p.nick == name]) <= 1:
            return
        time.sleep(0.01)


def test_a_newer_hello_of_the_save_takes_over_and_the_older_connection_is_told_and_closed(api):
    c, g, timers = api
    save(g, "a")
    with c.websocket_connect("/ws") as a1, c.websocket_connect("/ws") as a2:
        hello(a1, "a")
        a1.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(a1, "ddz_queue")["base"] == BASE
        r2 = hello(a2, "a")
        assert r2["base"] == BASE
        assert receive(a1, "error") == {"type": "error", "code": "room_full", "message": "", "reason": "ddz_queued"}
        lobby_closed("a")
        assert list(main.tables.lobby) == [r2["you"]]
        assert main.tables.waiting[player_id_for(tok("a"))].peer.id == r2["you"]


def test_dou_dizhu_connections_are_capped(api, monkeypatch):
    c, g, timers = api
    for name in "ab":
        save(g, name)
    monkeypatch.setattr(main, "LOBBY_MAX", 1)
    with c.websocket_connect("/ws") as a1, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as a2:
        hello(a1, "a")
        b.send_json({"type": "ddz_hello", "nick": "b", "token": tok("b")})
        assert receive(b, "error")["reason"] == "ddz_full"
        with pytest.raises(WebSocketDisconnect):
            b.receive_json()
        # Over the cap, a newer connection of a save already in takes the place of the older one.
        hello(a2, "a")
        assert receive(a1, "error")["reason"] == "ddz_queued"
        with pytest.raises(WebSocketDisconnect):
            a1.receive_json()
        lobby_closed("a")
        assert len(main.tables.lobby) == 1


def test_a_hello_that_came_first_but_got_through_last_gives_way_to_the_newer_one(api, monkeypatch):
    import threading

    c, g, timers = api
    save(g, "a")
    real = main._room_identity
    entered, release = threading.Event(), threading.Event()
    calls = []

    def slow(token, account_token):
        calls.append(token)
        if len(calls) == 1:
            entered.set()
            release.wait(5)
        return real(token, account_token)

    monkeypatch.setattr(main, "_room_identity", slow)
    with c.websocket_connect("/ws") as first, c.websocket_connect("/ws") as second:
        first.send_json({"type": "ddz_hello", "nick": "a", "token": tok("a")})
        assert entered.wait(5)
        r2 = hello(second, "a")
        release.set()
        # The first hello is the older one: it is refused and the newer connection keeps the save.
        assert receive(first, "error")["reason"] == "ddz_queued"
        assert list(main.tables.lobby) == [r2["you"]]
        second.send_json({"type": "ddz_queue", "base": BASE})
        assert receive(second, "ddz_queue")["base"] == BASE


def test_turning_invites_down_keeps_the_connection_that_does_out_of_the_queue_and_not_another_of_the_save():
    async def go():
        w = MatchWorld()
        a, sa = w.member("a")
        a_room, _ = w.member("a", room="r")
        # Its room connection turns invites down (as joining with dnd does): the dou dizhu connection queues all the
        # same.
        a_room.dnd = True
        await w.t.queue(a, BASE)
        (b, sb), = await w.queued("b")
        # Turned on on the connection that waits: the save is dropped when a table would be made with it.
        a.dnd = True
        (c, sc), = await w.queued("c")
        assert queue_msgs(sa)[-1] == {"base": None, "reason": "ddz_dnd"}
        assert [q.peer for q in w.t.lines[BASE]] == [b, c] and sb.of("ddz_invite") == []
        # Nor does it queue while it turns them down.
        w.mono += QUEUE_INTERVAL
        with pytest.raises(Exception) as e:
            await w.t.queue(a, BASE)
        assert e.value.code == "ddz_dnd"
        # Turned off there, the room connection still turning them down: matched, not dropped.
        a.dnd = False
        await w.t.queue(a, BASE)
        await w.t.idle()
        assert sb.of("ddz_invite")[0]["ids"] == [b.id, c.id, a.id] and w.t.waiting == {}
    run(go())


def test_a_save_of_a_table_the_queue_made_put_back_after_a_decline_stays_out_when_it_turns_invites_down():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        a_room, _ = w.member("a", room="r")
        a_room.dnd = True
        # b turns invites down on its dou dizhu connection once it accepted: the invite stands.
        await w.t.answer(b, tid, True)
        b.dnd = True
        w.t.set_dnd(b, True)
        assert tid in w.t.by_id and sa.of("ddz_over") == []
        await w.t.answer(c, tid, False)
        await w.t.idle()
        # a goes back, its room connection turning invites down; b, turning them down on the connection that waited,
        # does not.
        assert [q.peer for q in w.t.lines[BASE]] == [a] and w.who["b"] not in w.t.waiting
    run(go())


def test_a_member_of_a_room_playing_at_a_table_of_the_queue_is_shown_playing_to_the_whole_room():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        for p in (a, b, c):
            await w.t.answer(p, tid, True)
        await settle()
        x, sx = w.member("x", room="r")
        # a, playing from no room, joins r: x hears a is playing, by a's member id in r.
        a_room, sa_room = w.member("a", room="r")
        await w.t.joined("r", a_room)
        assert sx.of("ddz_live")[-1] == {"type": "ddz_live", "table": tid, "ids": [a_room.id, b.id, c.id], "on": True,
                                          "base": BASE}
        # Back on a new room connection, with a new member id: told again.
        await w.m.depart("r", a_room.id)
        a2, _ = w.member("a", room="r")
        await w.t.joined("r", a2)
        assert sx.of("ddz_live")[-1]["ids"] == [a2.id, b.id, c.id]
    run(go())


def test_a_nick_masked_again_or_changed_shows_at_the_table(monkeypatch):
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        for p in (a, b, c):
            await w.t.answer(p, tid, True)
        await settle()
        t = w.t.by_id[tid]
        monkeypatch.setattr(main, "tables", w.t)
        monkeypatch.setattr(main, "manager", w.m)
        monkeypatch.setattr(main.blocklist, "mask", lambda s: s.replace("坏", "*"))
        monkeypatch.setitem(main.raw_nicks, a.id, "坏a")
        a.raw_nick = "坏a"  # as its hello said
        await main._remask()
        assert a.nick == "*a" and t.seats[0].nick == "*a"
        told = {"type": "ddz_seat", "table": tid, "seat": 0, "id": a.id, "away": False, "auto": False, "nick": "*a",
                "character": "嘉然", "plate": None}
        assert sb.of("ddz_seat")[-1] == told and sc.of("ddz_seat")[-1] == told
        # Masking again with nothing new tells nothing.
        n = len(sb.of("ddz_seat"))
        await main._remask()
        assert len(sb.of("ddz_seat")) == n
        # Its own new pet shows the same way.
        b.character = "贝拉"
        w.t.restyle(b)
        assert t.seats[1].character == "贝拉" and sa.of("ddz_seat")[-1]["character"] == "贝拉"
    run(go())


def test_an_invited_save_back_on_a_new_dou_dizhu_connection_gets_its_place_there():
    async def go():
        w = MatchWorld()
        (e, se), (b, sb) = await w.queued("e", "b")
        held = w.t.waiting[w.who["b"]]
        b_room, _ = w.member("b", room="r")
        x, sx = w.member("x", room="r")
        y, _ = w.member("y", room="r")
        await w.t.invite("r", x, [b_room.id, y.id], BASE)
        tid = sx.of("ddz_invite")[0]["table"]
        # Its dou dizhu connection goes and a new one says hello while the invite is out.
        await w.bye(b)
        b2, sb2 = w.member("b")
        await w.t.hello(b2)
        await w.t.answer(y, tid, False)
        await w.t.idle()
        assert [q.peer for q in w.t.lines[BASE]] == [e, b2] and w.t.waiting[w.who["b"]].seq == held.seq
        assert queue_msgs(sb2)[-1]["base"] == BASE
    run(go())


def test_hello_with_a_token_of_no_save_is_refused_and_makes_none(api):
    c, g, timers = api
    pid = player_id_for(tok("never"))
    with c.websocket_connect("/ws") as x:
        x.send_json({"type": "ddz_hello", "nick": "never", "token": tok("never")})
        assert receive(x, "error")["reason"] == "ddz_locked"
    assert main.tables.lobby == {} and not g.store.has_player(pid)


def test_turning_invites_down_on_any_connection_keeps_the_save_from_being_invited_or_called_but_not_from_sitting():
    async def go():
        w = MatchWorld()
        a, sa = w.member("a", room="r")
        b, sb = w.member("b", room="r")
        c, sc = w.member("c", room="r")
        b_lobby, _ = w.member("b")
        b_lobby.dnd = True
        # What others send the save is turned down: an invite, a call.
        await w.t.invite("r", a, [b.id, c.id], BASE)
        assert sa.of("ddz_over")[-1]["reason"] == "declined" and sb.of("ddz_invite") == []
        await w.t.open("r", c, BASE)
        tid = sc.of("ddz_open")[-1]["table"]
        w.t.call("r", c, tid, b.id)
        assert sb.of("ddz_call") == []
        # What it does itself on its room connection is not: it sits down, and opens a table once up again.
        await w.t.sit("r", b, tid)
        assert w.t.by_id[tid].seat_of(b) is not None
        await w.t.leave(b, tid)
        w.mono += QUEUE_INTERVAL
        await w.t.open("r", b, BASE)
        assert w.t.by_save[w.who["b"]].seats[0].peer is b
        # The connection turning them down is refused.
        await w.t.leave(b, w.t.by_save[w.who["b"]].id)
        w.mono += QUEUE_INTERVAL
        for act in (lambda: w.t.hall_open(b_lobby, BASE), lambda: w.t.queue(b_lobby, BASE)):
            with pytest.raises(Exception) as e:
                await act()
            assert e.value.code == "ddz_dnd"
        b.dnd = True
        for act in (lambda: w.t.open("r", b, BASE), lambda: w.t.sit("r", b, tid)):
            with pytest.raises(Exception) as e:
                await act()
            assert e.value.code == "ddz_dnd"
    run(go())


def test_a_nick_masked_again_reaches_an_invite_and_a_seat_whose_member_is_away(monkeypatch):
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        for p in (a, b, c):
            p.raw_nick = "坏" + p.nick
        mask = lambda s: s.replace("坏", "*")  # noqa: E731
        # While the invite is out: everyone holding it hears the seats' new nicks.
        w.t.remask(mask)
        assert [m["nick"] for m in sb.of("ddz_seat")] == ["*a", "*b", "*c"]
        assert [s.nick for s in w.t.by_id[tid].seats] == ["*a", "*b", "*c"]
        for p in (a, b, c):
            await w.t.answer(p, tid, True)
        await settle()
        # a's connection goes; its seat, played for, is masked again all the same.
        await w.bye(a)
        n = len(sb.of("ddz_seat"))
        w.t.remask(lambda s: s.replace("坏", "#"))
        t = w.t.by_id[tid]
        assert t.seats[0].nick == "#a" and t.seats[0].peer is None
        told = sb.of("ddz_seat")[n:]
        assert {m["seat"]: m["nick"] for m in told} == {0: "#a", 1: "#b", 2: "#c"} and told[0]["away"] is True
        assert w.t._state(t, 1)["seats"][0]["nick"] == "#a"
    run(go())


def gate_start(monkeypatch):
    """Bank.start held until the returned event is set."""
    import threading

    gate = threading.Event()
    real = Bank.start

    def slow(self, pids, base):
        gate.wait(5)
        return real(self, pids, base)

    monkeypatch.setattr(Bank, "start", slow)
    return gate


async def starting(t):
    for _ in range(200):
        await asyncio.sleep(0.005)
        if t.phase == "starting":
            return
    raise AssertionError("never started")


def room_invite_of_a_queued_save(w):
    """b waits in the queue (on its dou dizhu connection) and is invited in room r by x with y."""
    async def go():
        (e, se), (b, sb) = await w.queued("e", "b")
        b_room, sb_room = w.member("b", room="r")
        x, sx = w.member("x", room="r")
        y, sy = w.member("y", room="r")
        await w.t.invite("r", x, [b_room.id, y.id], BASE)
        return e, (b, sb), (b_room, sb_room), (x, sx), (y, sy), sx.of("ddz_invite")[0]["table"]
    return go()


@pytest.mark.parametrize("how", ["fails", "cancelled"])
def test_a_refund_on_abort_that_fails_or_is_cancelled_lets_the_saves_go(monkeypatch, how):
    async def go():
        import threading

        import app.ddz as ddz
        monkeypatch.setattr(ddz, "REFUND_RETRY_SEC", (0.0,))
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        gate = gate_start(monkeypatch)
        refund_gate = threading.Event()
        real_refund = Bank.refund

        def refund(self, row):
            if how == "fails":
                raise RuntimeError("database down")
            refund_gate.wait(5)
            return real_refund(self, row)

        monkeypatch.setattr(Bank, "refund", refund)
        await w.t.answer(a, tid, True)
        await w.t.answer(b, tid, True)
        handler = asyncio.create_task(w.t.answer(c, tid, True))
        t = w.t.by_id[tid]
        await starting(t)
        for p in (a, b, c):
            await w.bye(p)
        gate.set()
        if how == "fails":
            await handler
            await w.t.idle()
        else:
            for _ in range(200):
                await asyncio.sleep(0.005)
                if t.phase == "settling":
                    break
            assert t.phase == "settling"
            for task in list(w.t._tasks):
                task.cancel()
            await asyncio.sleep(0.01)
        # The saves are free either way.
        assert w.t.by_id == {} and w.t.by_save == {}
        if how == "fails":
            # The game stays open: the next start of the server hands its deposits back.
            assert w.g.store.open_ddz_games() == [t.row]
        else:
            refund_gate.set()
            for _ in range(200):
                await asyncio.sleep(0.005)
                if not w.g.store.open_ddz_games():
                    break
            assert w.g.store.open_ddz_games() == []
            handler.cancel()
    run(go())


def test_a_start_task_cancelled_before_it_ran_ends_the_invite_and_gives_places_back():
    async def go():
        w = MatchWorld()
        e, (b, sb), (b_room, sb_room), (x, sx), (y, sy), tid = await room_invite_of_a_queued_save(w)
        await w.t.answer(b_room, tid, True)
        handler = asyncio.create_task(w.t.answer(y, tid, True))
        await asyncio.sleep(0)
        t = w.t.by_id[tid]
        assert t.phase == "starting"
        for task in list(w.t._tasks):
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await handler
        await w.t.idle()
        assert w.t.by_id == {} and sx.of("ddz_over")[-1]["reason"] == "error"
        assert [q.peer for q in w.t.lines[BASE]] == [e, b] and w.g.store.open_ddz_games() == []
    run(go())


def test_stopping_the_wait_during_a_room_invite_gives_up_the_place_it_holds():
    async def go():
        w = MatchWorld()
        e, (b, sb), (b_room, sb_room), (x, sx), (y, sy), tid = await room_invite_of_a_queued_save(w)
        w.t.unqueue(b)
        assert queue_msgs(sb)[-1] == {"base": None}
        await w.t.answer(y, tid, False)
        await w.t.idle()
        assert w.who["b"] not in w.t.waiting and [q.peer for q in w.t.lines[BASE]] == [e]
    run(go())


def test_everyone_leaving_while_the_deposits_are_taken_gives_the_invited_their_places_back(monkeypatch):
    async def go():
        w = MatchWorld()
        e, (b, sb), (b_room, sb_room), (x, sx), (y, sy), tid = await room_invite_of_a_queued_save(w)
        gate = gate_start(monkeypatch)
        await w.t.answer(b_room, tid, True)
        handler = asyncio.create_task(w.t.answer(y, tid, True))
        t = w.t.by_id[tid]
        await starting(t)
        for p in (x, b_room, y):
            await w.m.depart("r", p.id)
        gate.set()
        await handler
        await w.t.idle()
        assert w.t.by_id == {} and w.g.store.open_ddz_games() == []
        assert [q.peer for q in w.t.lines[BASE]] == [e, b]
    run(go())


@pytest.mark.parametrize("kind", ["room", "match"])
def test_turning_invites_down_on_another_connection_declines_an_invite_from_a_member_and_not_a_table_of_the_queue(kind):
    async def go():
        w = MatchWorld()
        if kind == "room":
            e, (b, sb), (b_room, sb_room), (x, sx), (y, sy), tid = await room_invite_of_a_queued_save(w)
            b.dnd = True
            w.t.set_dnd(b, True)
            assert sx.of("ddz_over")[-1] == {"type": "ddz_over", "table": tid, "reason": "declined", "by": b_room.id}
            await w.t.idle()
            assert w.who["b"] not in w.t.waiting
        else:
            (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
            tid = sa.of("ddz_invite")[0]["table"]
            b_room, _ = w.member("b", room="r")
            b_room.dnd = True
            w.t.set_dnd(b_room, True)
            # The table the queue made asks the dou dizhu connection that waited: it still waits for its answer.
            assert sa.of("ddz_over") == [] and tid in w.t.by_id and w.who["b"] not in w.t.match_refused
            b.dnd = True
            w.t.set_dnd(b, True)
            assert sa.of("ddz_over")[-1]["by"] == b.id and tid not in w.t.by_id
            assert w.who["b"] in w.t.match_refused and [q.peer for q in w.t.lines[BASE]] == [a, c]
    run(go())


def test_a_state_sent_is_a_snapshot_of_the_table():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        for p in (a, b, c):
            await w.t.answer(p, tid, True)
        await settle()
        t = w.t.by_id[tid]
        t.played.append(5)
        t.trick[1] = [9]
        st = w.t._state(t, 0)
        t.played.append(6)
        t.trick[1].append(10)
        t.trick[2] = [11]
        t.seats[0].hand.append(12)
        assert st["played"] == [5] and st["trick"] == [None, [9], None] and 12 not in st["hand"]
    run(go())


def test_a_new_connection_during_the_invite_of_a_table_of_the_queue_takes_the_ask_over():
    async def go():
        w = MatchWorld()
        (a, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[0]["table"]
        t = w.t.by_id[tid]
        await w.t.answer(a, tid, True)
        await w.t.answer(b, tid, True)
        w.mono += 4
        b2, sb2 = w.member("b")
        await w.t.hello(b2)
        assert sb2.got[0]["table"] == tid
        again = sb2.of("ddz_invite")[-1]
        assert again["ids"] == [a.id, b2.id, c.id] and again["accepted"] == [a.id, b2.id]
        assert again["sec"] == CFG["inviteSec"] - 4
        assert sa.of("ddz_seat")[-1]["id"] == b2.id and sa.of("ddz_answer")[-1]["id"] == b2.id
        # The old connection closing declines nothing.
        await w.bye(b)
        assert t.phase == "invite" and w.who["b"] not in w.t.match_refused
        await w.t.answer(c, tid, True)
        await settle()
        assert t.phase == "bid" and sb2.of("ddz_deal") and sb.of("ddz_deal") == []
    run(go())


def test_a_new_connection_turning_invites_down_turns_down_the_ask_it_takes_over():
    async def go():
        w = MatchWorld()
        (_, sa), (b, sb), (c, sc) = await w.queued("a", "b", "c")
        tid = sa.of("ddz_invite")[-1]["table"]
        await w.t.answer(b, tid, True)
        a2, sa2 = w.member("a")
        a2.dnd = True
        await w.t.hello(a2)
        # Not asked again: the table ends as on a decline by the save, the others back in the line.
        assert sa2.got[0] == {"type": "ddz_ready", "you": a2.id, "base": None, "table": None}
        assert not sa2.of("ddz_invite") and tid not in w.t.by_id and w.who["a"] not in w.t.by_save
        assert sb.of("ddz_over")[-1] == {"type": "ddz_over", "table": tid, "reason": "declined", "by": a2.id}
        assert queue_msgs(sa2)[-1] == {"base": None, "reason": "ddz_match_cooldown", "retry": 60.0}
        assert sorted(w.t.waiting) == sorted([w.who["b"], w.who["c"]])
        # An ask already accepted is taken over as it stands.
        w2 = MatchWorld()
        (d, sd), (e, _), (f, _) = await w2.queued("d", "e", "f")
        tid2 = sd.of("ddz_invite")[-1]["table"]
        await w2.t.answer(d, tid2, True)
        d2, sd2 = w2.member("d")
        d2.dnd = True
        await w2.t.hello(d2)
        assert sd2.got[0]["table"] == tid2 and sd2.of("ddz_invite")[-1]["table"] == tid2
        assert w2.t.by_id[tid2].seats[0].peer is d2
        await w.t.idle()
        await w2.t.idle()

    run(asyncio.wait_for(go(), 10))


def test_a_new_connection_turning_invites_down_turns_down_the_seat_of_an_open_table_offered_to_it():
    async def go():
        from test_ddz_open import OpenWorld
        from app.ddz import FILL_SEC
        w = OpenWorld()
        ((x, _),), rtid = await w.opened("x")
        q, sq = w.queuer("q")
        w.mono += FILL_SEC
        await w.t.queue(q, BASE)
        assert sq.of("ddz_invite")[-1]["table"] == rtid
        q2, sq2 = w.member("q", room=None)
        q2.dnd = True
        await w.t.hello(q2)
        t = w.t.by_id[rtid]
        assert sq2.got[0]["table"] is None and not sq2.of("ddz_invite")
        assert sq2.of("ddz_over")[-1] == {"type": "ddz_over", "table": rtid, "reason": "declined"}
        assert all(s.token != w.who["q"] for s in t.seats) and w.who["q"] not in w.t.by_save
        assert w.who["q"] in w.t.match_refused
        await w.t.idle()

    run(asyncio.wait_for(go(), 10))
