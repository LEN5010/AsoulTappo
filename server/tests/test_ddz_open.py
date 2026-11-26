"""Open dou dizhu tables: opened in a room at a stake, sat at by the room's members, started by the third."""
import asyncio

import pytest

from app.ddz import FILL_SEC, MATCH_RETRY_SEC, OPEN_SEC, QUEUE_INTERVAL, RETRY_SEC, Bank
from test_ddz import BASE, DEPOSIT, SHARDS, api, play_out, save  # noqa: F401
from test_ddz_match import MatchWorld, matched, queue_msgs, receive  # noqa: F401
from test_duel import settle


class OpenWorld(MatchWorld):
    """Members in room r by default, on clients that open tables."""

    def member(self, name, room="r", match=True, **kw):
        return super().member(name, room=room, match=match, **kw)

    def queuer(self, name, **kw):
        """A dou dizhu connection of the save named [name], in no room: the queue's."""
        return super().member(name, room=None, **kw)

    async def opened(self, *names, base=BASE):
        """[names] in room r, the first opening a table at [base] and the others sitting down; returns the members
        and the table id."""
        out = [self.member(n) for n in names]
        await self.t.open("r", out[0][0], base)
        tid = out[0][1].of("ddz_open")[-1]["table"]
        for peer, _ in out[1:]:
            self.mono += QUEUE_INTERVAL
            await self.t.sit("r", peer, tid)
        return out, tid

    async def settled(self):
        """Waits for the work the tables run on their own (a start taking the deposits, matching) to be done."""
        await self.t.idle()
        await settle()


def run(coro):
    return asyncio.run(coro)


def seat(peer):
    return {"id": peer.id, "nick": peer.nick, "character": peer.character}


def last_open(sock):
    return {k: v for k, v in sock.of("ddz_open")[-1].items() if k != "type"}


# ------------------------------------------------------------------ opening and sitting
def test_opening_a_table_seats_the_opener_and_the_third_to_sit_starts_the_game():
    async def go():
        w = OpenWorld()
        (a, sa), (b, sb) = w.member("a"), w.member("b")
        await w.t.open("r", a, BASE)
        tid = sa.of("ddz_open")[0]["table"]
        assert last_open(sa) == {"table": tid, "base": BASE, "deposit": DEPOSIT, "you": 0,
                                 "seats": [seat(a), None, None], "sec": OPEN_SEC}
        assert w.t.by_save[w.who["a"]].id == tid
        w.mono += 10
        await w.t.sit("r", b, tid)
        assert last_open(sb) == {"table": tid, "base": BASE, "deposit": DEPOSIT, "you": 1,
                                 "seats": [seat(a), seat(b), None], "sec": OPEN_SEC - 10}
        assert last_open(sa)["seats"] == [seat(a), seat(b), None]
        # Sitting is consent: the third takes the last seat, the three deposits go and the cards are dealt.
        c, sc = w.member("c")
        await w.t.sit("r", c, tid, 2)
        await w.settled()
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS - DEPOSIT] * 3
        assert [s.of("ddz_deal")[0]["you"] for s in (sa, sb, sc)] == [0, 1, 2]
        assert [m.get("starting") for m in sc.of("ddz_open")] == [True] and sa.of("ddz_live")[-1]["on"] is True
        assert w.t.by_id[tid].phase == "bid"
    run(go())


def test_a_seat_picked_that_is_taken_gives_the_next_empty_one():
    async def go():
        w = OpenWorld()
        ((_, sa), (_, sb)), tid = await w.opened("a", "b")
        c, sc = w.member("c")
        await w.t.sit("r", c, tid, 1)
        await w.settled()
        assert sb.of("ddz_deal")[0]["you"] == 1 and sc.of("ddz_deal")[0]["you"] == 2
    run(go())


@pytest.mark.parametrize("how, code", [
    ("old", "bad_message"), ("guest", "ddz_locked"), ("poor", "no_shards"), ("taps", "ddz_locked"),
    ("account", "ddz_account"), ("dnd", "ddz_dnd"), ("busy", "ddz_busy"), ("stake", "bad_message"),
])
def test_who_may_not_open_a_table(how, code):
    async def go():
        w = OpenWorld(require_account=how == "account")
        if how == "guest":
            peer, _ = w.join("guest", None, room="r")
            peer.ddz_match = True
        else:
            peer, _ = w.member("a", match=how != "old", taps=9_999 if how == "taps" else 10_000,
                               shards=DEPOSIT - 1 if how == "poor" else SHARDS)
        peer.dnd = how == "dnd"
        if how == "busy":
            await w.t.open("r", peer, BASE)
            w.mono += QUEUE_INTERVAL
        with pytest.raises(Exception) as e:
            await w.t.open("r", peer, 123 if how == "stake" else BASE)
        assert getattr(e.value, "code", None) == code
        assert len(w.t.by_id) == (1 if how == "busy" else 0)
    run(go())


@pytest.mark.parametrize("how, code", [
    ("old", "bad_message"), ("poor", "no_shards"), ("dnd", "ddz_dnd"), ("busy", "ddz_busy"),
    ("elsewhere", "ddz_gone"), ("gone", "ddz_gone"), ("full", "ddz_gone"), ("twice", "ddz_busy"),
])
def test_who_may_not_sit(how, code):
    async def go():
        w = OpenWorld()
        ((a, sa),), tid = await w.opened("a")
        peer, _ = w.member("b", room="r2" if how == "elsewhere" else "r", match=how != "old",
                           shards=DEPOSIT - 1 if how == "poor" else SHARDS)
        peer.dnd = how == "dnd"
        if how == "busy":
            x, _ = w.member("x")
            await w.t.open("r", x, 50)
            await w.t.sit("r", peer, w.t.by_save[w.who["x"]].id)
            w.mono += QUEUE_INTERVAL
        if how == "gone":
            await w.t.leave(a, tid)
        if how == "full":
            for n in "cd":
                p, _ = w.member(n)
                await w.t.sit("r", p, tid)
            await w.settled()
        if how == "twice":
            await w.t.sit("r", peer, tid)
            w.mono += QUEUE_INTERVAL
        with pytest.raises(Exception) as e:
            await w.t.sit("r2" if how == "elsewhere" else "r", peer, tid)
        assert getattr(e.value, "code", None) == code
    run(go())


def test_opening_or_sitting_takes_a_save_out_of_the_queue_and_reads_it_at_most_once_a_second():
    async def go():
        w = OpenWorld()
        a, sa = w.member("a")
        b, sb = w.member("b")
        aq, saq = w.queuer("a")
        bq, sbq = w.queuer("b")
        await w.t.queue(bq, 50)
        w.mono += QUEUE_INTERVAL
        await w.t.queue(aq, BASE)
        with pytest.raises(Exception) as e:
            await w.t.open("r", a, BASE)
        assert e.value.code == "rate_limited"
        w.mono += QUEUE_INTERVAL
        await w.t.open("r", a, BASE)
        assert queue_msgs(saq)[-1] == {"base": None} and w.who["a"] not in w.t.waiting
        await w.t.sit("r", b, sa.of("ddz_open")[-1]["table"])
        assert queue_msgs(sbq)[-1] == {"base": None} and w.t.waiting == {}
    run(go())


# ------------------------------------------------------------------ standing up, putting away
def test_standing_up_disbanding_and_the_time_running_out_take_nothing():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        await w.t.leave(b, tid)
        assert sb.of("ddz_closed") == [{"type": "ddz_closed", "table": tid}]
        assert last_open(sa)["seats"] == [seat(a), None, None] and w.who["b"] not in w.t.by_save
        w.mono += QUEUE_INTERVAL
        await w.t.sit("r", b, tid)
        await w.t.leave(a, tid)
        assert sa.of("ddz_closed")[-1] == {"type": "ddz_closed", "table": tid}
        assert sb.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "disband", "by": a.id}]
        assert w.t.by_id == {} and w.t.by_save == {}
        w.mono += QUEUE_INTERVAL
        await w.t.open("r", a, BASE)
        w.mono += OPEN_SEC - 1
        await w.timers.fire()
        assert len(w.t.by_id) == 1
        w.mono += 1
        await w.timers.fire()
        assert sa.of("ddz_over")[-1] == {"type": "ddz_over", "table": sa.of("ddz_open")[-1]["table"],
                                         "reason": "expired"}
        assert w.t.by_id == {} and w.timers.live() == []
        assert [w.shards(w.who[n]) for n in "ab"] == [SHARDS] * 2
    run(go())


def test_a_member_leaving_the_room_stands_up_and_the_opener_leaving_puts_the_table_away():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        c, sc = w.member("c")
        await w.m.depart("r", b.id)
        assert last_open(sa)["seats"] == [seat(a), None, None] and w.who["b"] not in w.t.by_save
        w.mono += QUEUE_INTERVAL
        await w.t.sit("r", c, tid)
        await w.m.depart("r", a.id)
        assert sc.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "disband", "by": a.id}]
        assert w.t.by_id == {} and w.t.by_save == {} and w.timers.live() == []
    run(go())


@pytest.mark.parametrize("how", ["sat", "from_the_queue"])
def test_a_newer_connection_of_the_save_on_a_client_without_open_tables_leaves_the_seat_where_it_is(how):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        name, room, at = "b", "r", 1
        if how == "from_the_queue":
            name, room, at = "q", "r-q", 2
            q, sq = w.queuer("q")
            w.mono += FILL_SEC
            await w.t.queue(q, BASE)
            await w.t.answer(q, tid, True)
        held = w.t.by_id[tid].seats[at].peer
        # The same save on a 1.2.5 client: it has no keys for the table, so the seat stays with the one that has.
        old, s_old = w.member(name, room=room, match=False)
        await w.t.joined(room, old)
        assert w.t.by_id[tid].seats[at].peer is held and s_old.of("ddz_open") == []
        assert held.ddz_match and (held.lobby if how == "from_the_queue" else w.m.rooms[room].peers[held.id] is held)
    run(go())


# ------------------------------------------------------------------ the start
def test_the_third_seat_takes_the_deposits_in_one_go_and_lets_go_of_a_seat_that_cannot_pay(monkeypatch):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        # b spent its shards after sitting down.
        w.g.store.update_player(w.who["b"], shards=DEPOSIT - 1)
        starts = []
        real = Bank.try_start
        monkeypatch.setattr(Bank, "try_start",
                            lambda self, pids, base: starts.append(list(pids)) or real(self, pids, base))
        c, sc = w.member("c")
        await w.t.sit("r", c, tid)
        await w.settled()
        assert len(starts) == 1
        assert sb.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "no_shards"}]
        assert last_open(sa)["seats"] == [seat(a), None, seat(c)] and last_open(sc)["you"] == 2
        assert w.t.by_id[tid].phase == "open" and w.who["b"] not in w.t.by_save
        assert [w.shards(w.who[n]) for n in "ac"] == [SHARDS] * 2 and w.shards(w.who["b"]) == DEPOSIT - 1
        d, sd = w.member("d")
        await w.t.sit("r", d, tid)
        await w.settled()
        assert [s.of("ddz_deal")[0]["you"] for s in (sa, sd, sc)] == [0, 1, 2]
        assert [w.shards(w.who[n]) for n in "acd"] == [SHARDS - DEPOSIT] * 3
    run(go())


def test_the_opener_that_cannot_pay_at_the_start_puts_the_table_away():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        w.g.store.update_player(w.who["a"], shards=0)
        c, sc = w.member("c")
        await w.t.sit("r", c, tid)
        await w.settled()
        assert sa.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "no_shards"}]
        for s in (sb, sc):
            assert s.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "disband", "by": a.id}]
        assert w.t.by_id == {} and w.t.by_save == {} and [w.shards(w.who[n]) for n in "bc"] == [SHARDS] * 2
    run(go())


def test_open_tables_over_the_socket(api):
    c, g, timers = api
    for name in ("a", "b", "old"):
        save(g, name)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as o:
        matched(a, "a", "r1")
        matched(b, "b", "r1")
        matched(o, "old", "r1", match=False)
        o.send_json({"type": "ddz_open", "base": BASE})
        assert receive(o, "error")["code"] == "bad_message"
        a.send_json({"type": "ddz_open", "base": BASE})
        tid = receive(a, "ddz_open")["table"]
        o.send_json({"type": "ddz_sit", "table": tid})
        assert receive(o, "error")["code"] == "bad_message"
        b.send_json({"type": "ddz_sit", "table": tid, "seat": 2})
        assert receive(b, "ddz_open")["you"] == 2
        b.send_json({"type": "ddz_leave", "table": tid})
        assert receive(b, "ddz_closed")["table"] == tid


# ------------------------------------------------------------------ the room
def test_the_room_hears_its_open_tables_at_most_once_a_second():
    async def go():
        w = OpenWorld()
        _, s_watch = w.member("watch")
        _, s_old = w.member("old", match=False)
        _, s_far = w.member("far", room="r2")
        ((a, sa),), tid = await w.opened("a")
        shown = [{"table": tid, "base": BASE, "seats": [seat(a), None, None]}]
        assert s_watch.of("ddz_tables") == [{"type": "ddz_tables", "tables": shown}]
        assert sa.of("ddz_tables")[-1]["tables"] == shown
        # Old clients and other rooms hear nothing of it.
        assert s_old.of("ddz_tables") == [] and s_far.of("ddz_tables") == []
        b, _ = w.member("b")
        await w.t.sit("r", b, tid)
        assert len(s_watch.of("ddz_tables")) == 1
        w.mono += 1
        await w.counts.fire()
        shown = [{"table": tid, "base": BASE, "seats": [seat(a), seat(b), None]}]
        assert s_watch.of("ddz_tables")[-1]["tables"] == shown
        # Someone coming in hears what the room was told last.
        n, sn = w.member("n")
        await w.t.joined("r", n)
        assert sn.of("ddz_tables") == [{"type": "ddz_tables", "tables": shown}]
        old2, s_old2 = w.member("old2", match=False)
        await w.t.joined("r", old2)
        assert s_old2.of("ddz_tables") == []
        # The game starting takes the table off; the room hears an empty list once.
        c, _ = w.member("c")
        await w.t.sit("r", c, tid)
        await w.settled()
        w.mono += 1
        await w.counts.fire()
        assert s_watch.of("ddz_tables")[-1] == {"type": "ddz_tables", "tables": []} and w.t._tables_sent == {}
        n2, sn2 = w.member("n2")
        await w.t.joined("r", n2)
        assert sn2.of("ddz_tables") == []
    run(go())


def test_a_table_put_away_leaves_the_room_list():
    async def go():
        w = OpenWorld()
        _, s_watch = w.member("watch")
        ((a, _),), tid = await w.opened("a")
        x, _ = w.member("x")
        w.mono += 1
        await w.t.open("r", x, 50)
        await w.counts.fire()
        assert [t["table"] for t in s_watch.of("ddz_tables")[-1]["tables"]] == [tid, w.t.by_save[w.who["x"]].id]
        await w.m.depart("r", a.id)
        w.mono += 1
        await w.counts.fire()
        assert [t["base"] for t in s_watch.of("ddz_tables")[-1]["tables"]] == [50]
    run(go())


# ------------------------------------------------------------------ filled from the queue
INVITE_SEC = 15


def test_an_empty_seat_waiting_a_minute_goes_to_the_save_that_waited_longest_in_the_queue():
    async def go():
        w = OpenWorld()
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        q2, _ = w.queuer("q2")
        await w.t.queue(q2, BASE)
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        w.mono += FILL_SEC - 2
        await w.timers.fire()
        assert w.t.by_id[tid].seats[2].empty
        w.mono += 1
        await w.timers.fire()
        assert queue_msgs(sq)[-1] == {"base": None} and [x.peer for x in w.t.lines[BASE]] == [q2]
        assert sq.of("ddz_invite") == [{"type": "ddz_invite", "table": tid, "ids": [a.id, b.id, q.id], "base": BASE,
                                        "deposit": DEPOSIT, "sec": INVITE_SEC, "match": True,
                                        "seats": [seat(a), seat(b), seat(q)], "accepted": [a.id, b.id]}]
        assert last_open(sa)["seats"] == [seat(a), seat(b), {"pending": True}]
        assert w.t._room_tables("r")[0]["seats"][2] == {"pending": True}
        # Accepting seats it on its dou dizhu connection; the seats taken do not answer again.
        await w.t.answer(q, tid, True)
        await w.settled()
        assert [s.of("ddz_deal")[0]["you"] for s in (sa, sb, sq)] == [0, 1, 2]
        assert sa.of("ddz_live")[-1]["on"] is True and [m.get("starting") for m in sq.of("ddz_open")] == [True]
        assert sq.of("ddz_live") == [] and w.t.holds(w.who["q"]) and not w.t.holds(w.who["a"])
        # The seat of the queue is taken again on a new dou dizhu connection, not by a room join.
        await w.bye(q)
        q_room, s_room = w.member("q", room="r-z")
        await w.t.joined("r-z", q_room)
        assert w.t.by_id[tid].seats[2].peer is None and s_room.of("ddz_state") == []
        q3, sq3 = w.queuer("q")
        await w.t.hello(q3)
        assert w.t.by_id[tid].seats[2].peer is q3 and sq3.of("ddz_state")[0]["you"] == 2
        # Emotes cross between the room's seats and the one in no room.
        w.t.emote(q3, tid, "hi")
        w.t.emote(a, tid, "yo")
        heard = {"type": "ddz_emote", "table": tid, "seat": 2, "emote": "hi"}
        assert sa.of("ddz_emote") == sb.of("ddz_emote")[:1] == [heard]
        assert sq3.of("ddz_emote") == [{"type": "ddz_emote", "table": tid, "seat": 0, "emote": "yo"}]
    run(go())


def test_a_dou_dizhu_connection_of_a_save_seated_in_a_room_leaves_the_seat_to_the_room_and_does_not_queue():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        bq, sbq = w.queuer("b")
        await w.t.hello(bq)
        assert w.t.by_id[tid].seats[1].peer is b and sbq.of("ddz_open") == [] and not w.t.holds(w.who["b"])
        w.mono += QUEUE_INTERVAL
        with pytest.raises(Exception) as e:
            await w.t.queue(bq, BASE)
        assert e.value.code == "ddz_busy"
        # Standing up frees the save for the queue.
        await w.t.leave(b, tid)
        w.mono += QUEUE_INTERVAL
        await w.t.queue(bq, BASE)
        assert queue_msgs(sbq)[-1] == {"base": BASE, "waited": 0.0}
        # Sitting down again in the room takes it out.
        w.mono += QUEUE_INTERVAL
        await w.t.sit("r", b, tid)
        assert queue_msgs(sbq)[-1] == {"base": None} and w.t.waiting == {}
    run(go())


def test_a_save_queueing_for_a_seat_waiting_that_long_already_is_asked_at_once_one_seat_at_a_time():
    async def go():
        w = OpenWorld()
        ((a, sa),), tid = await w.opened("a")
        w.mono += FILL_SEC
        await w.timers.fire()
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        q2, sq2 = w.queuer("q2")
        await w.t.queue(q2, BASE)
        await w.t.idle()
        assert sq.of("ddz_invite")[0]["ids"] == [a.id, q.id, ""] and sq.of("ddz_invite")[0]["seats"][2] is None
        assert sq2.of("ddz_invite") == [] and [x.peer for x in w.t.lines[BASE]] == [q2]
        await w.t.answer(q, tid, True)
        assert sq2.of("ddz_invite")[0]["accepted"] == [a.id, q.id]
        assert last_open(sq) == {"table": tid, "base": BASE, "deposit": DEPOSIT, "you": 1,
                                 "seats": [seat(a), seat(q), {"pending": True}], "sec": OPEN_SEC - FILL_SEC}
    run(go())


@pytest.mark.parametrize("how", ["declined", "timeout", "gone", "dnd"])
def test_a_save_of_the_queue_that_does_not_take_the_seat_waits_and_the_next_is_asked(how):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        q2, sq2 = w.queuer("q2")
        await w.t.queue(q2, BASE)
        w.mono += FILL_SEC
        await w.timers.fire()
        assert sq.of("ddz_invite")
        if how == "declined":
            await w.t.answer(q, tid, False)
        elif how == "timeout":
            w.mono += INVITE_SEC
            await w.timers.fire()
        elif how == "gone":
            await w.bye(q)
        else:
            w.t.set_dnd(q, True)
        if how != "gone":
            assert sq.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": how if how != "dnd" else
                                          "declined"}]
            assert queue_msgs(sq)[-1] == {"base": None, "reason": "ddz_match_cooldown", "retry": MATCH_RETRY_SEC}
        q_again, _ = w.queuer("q")
        w.mono += QUEUE_INTERVAL
        with pytest.raises(Exception) as e:
            await w.t.queue(q_again, BASE)
        assert e.value.code == "ddz_match_cooldown"
        # The seat is open again and goes to the next at once; the two seated stay as they were.
        assert sq2.of("ddz_invite")[0]["ids"] == [a.id, b.id, q2.id]
        assert last_open(sa)["seats"] == [seat(a), seat(b), {"pending": True}] and w.who["q"] not in w.t.by_save
    run(go())


def test_a_save_of_the_queue_turning_invites_down_on_a_room_connection_is_still_asked_and_keeps_the_seat():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        # Its room connection joins another room turning invites down meanwhile.
        q_room, _ = w.member("q", room="r2")
        q_room.dnd = True
        w.mono += FILL_SEC
        await w.timers.fire()
        # Asked on the dou dizhu connection that waits, its room connection turning invites down.
        assert sq.of("ddz_invite")[0]["ids"] == [a.id, b.id, q.id]
        w.t.set_dnd(q_room, True)
        assert sq.of("ddz_over") == [] and last_open(sa)["seats"] == [seat(a), seat(b), {"pending": True}]
        await w.t.answer(q, tid, True)
        await w.settled()
        assert sq.of("ddz_deal")[0]["you"] == 2
    run(go())


def test_a_table_put_away_while_a_save_of_the_queue_is_asked_puts_it_back_in_its_place():
    async def go():
        w = OpenWorld()
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        w.mono += 5
        q2, _ = w.queuer("q2")
        await w.t.queue(q2, BASE)
        ((a, _),), tid = await w.opened("a")
        w.mono += FILL_SEC
        await w.timers.fire()
        assert w.t.by_id[tid].seats[1].token == w.who["q"]
        await w.t.leave(a, tid)
        await w.t.idle()
        assert sq.of("ddz_over")[-1] == {"type": "ddz_over", "table": tid, "reason": "disband", "by": a.id}
        assert [x.peer for x in w.t.lines[BASE]] == [q, q2] and queue_msgs(sq)[-1] == {"base": BASE, "waited": 65.0}
    run(go())


@pytest.mark.parametrize("how", ["leave", "depart", "expired", "opener_poor", "error"])
def test_a_save_of_the_queue_waiting_at_a_table_put_away_goes_back_to_its_place(how, monkeypatch):
    async def go():
        w = OpenWorld()
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        w.mono += 5
        ((a, _),), tid = await w.opened("a")
        w.mono += FILL_SEC
        await w.timers.fire()
        await w.t.answer(q, tid, True)
        assert w.t.by_id[tid].seats[1].accepted and w.t.waiting == {}
        if how in ("opener_poor", "error"):
            b, _ = w.member("b")
            if how == "opener_poor":
                w.g.store.update_player(w.who["a"], shards=0)
            else:
                monkeypatch.setattr(Bank, "try_start", lambda *x: 1 / 0)
            w.mono += QUEUE_INTERVAL
            await w.t.sit("r", b, tid)
            await w.settled()
        elif how == "leave":
            await w.t.leave(a, tid)
        elif how == "depart":
            await w.m.depart("r", a.id)
        else:
            w.mono += OPEN_SEC
            await w.timers.fire()
        await w.t.idle()
        reason = {"expired": "expired", "error": "error"}.get(how, "disband")
        assert sq.of("ddz_over")[-1]["reason"] == reason and tid not in w.t.by_id
        assert queue_msgs(sq)[-1]["base"] == BASE and queue_msgs(sq)[-1]["waited"] >= FILL_SEC + 5
        assert [x.peer for x in w.t.lines[BASE]] == [q] and w.who["q"] not in w.t.by_save
        # It waits since it first did: ahead of one that queues now.
        late, _ = w.queuer("late")
        await w.t.queue(late, BASE)
        assert [x.peer for x in w.t.lines[BASE]] == [q, late]
    run(go())


def test_a_save_of_the_queue_that_stood_up_or_played_at_an_open_table_does_not_go_back_to_the_line():
    async def go():
        w = OpenWorld()
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        ((a, _), (b, _)), tid = await w.opened("a", "b")
        w.mono += FILL_SEC
        await w.timers.fire()
        await w.t.answer(q, tid, True)
        await w.settled()
        table = w.t.by_id[tid]
        w.peers = [a, b, q]
        await w.t.bid(a, tid, 3)
        await play_out(w, tid)
        # The opener and the save of the queue ask for another game, b leaves: the table waits again, then goes.
        await w.t.again(a, tid)
        await w.t.again(q, tid)
        await w.t.leave(b, tid)
        assert sq.of("ddz_open")[-1]["seats"][1] is None and table.seats[2].peer is q
        await w.t.leave(a, tid)
        await w.t.idle()
        assert sq.of("ddz_over")[-1]["reason"] == "disband" and queue_msgs(sq)[-1] == {"base": None}
        assert w.t.waiting == {} and w.t.lines == {}
        # Standing up from a table that waits is the save's own doing: it is out, as by a cancel.
        w.mono += QUEUE_INTERVAL
        await w.t.queue(q, BASE)
        ((c, _),), tid = await w.opened("c")
        w.mono += FILL_SEC
        await w.timers.fire()
        await w.t.answer(q, tid, True)
        await w.t.leave(q, tid)
        await w.t.idle()
        assert w.t.waiting == {} and w.t.by_id[tid].seats[1].empty
    run(go())


def test_a_save_of_the_queue_freed_by_an_invite_ending_takes_a_seat_waiting_for_it():
    async def go():
        w = OpenWorld()
        ((a, sa),), tid = await w.opened("a")
        # q waits in the queue and is invited to a game in the room meanwhile: no seat goes to it while the invite is
        # out.
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        q_room, sq_room = w.member("q")
        x, _ = w.member("x", match=False)
        y, _ = w.member("y", match=False)
        await w.t.invite("r", x, [q_room.id, y.id], BASE)
        w.mono += FILL_SEC
        w.t._open_changed(w.t.by_id[tid])
        assert sq_room.of("ddz_invite")[-1].get("match") is None and w.t.by_id[tid].seats[1].empty
        assert sq.of("ddz_invite") == []
        # Turned down: still waiting, it is asked to the seat at once.
        await w.t.answer(q_room, sq_room.of("ddz_invite")[-1]["table"], False)
        await w.t.idle()
        assert sq.of("ddz_invite")[-1] == {"type": "ddz_invite", "table": tid, "ids": [a.id, q.id, ""],
                                           "base": BASE, "deposit": DEPOSIT, "sec": INVITE_SEC, "match": True,
                                           "seats": [seat(a), seat(q), None], "accepted": [a.id]}
    run(go())


def test_saves_of_the_queue_back_from_a_three_that_fell_through_take_a_seat_waiting_for_them(monkeypatch):
    async def go():
        w = OpenWorld()
        ((a, sa),), tid = await w.opened("a")
        (q1, s1), (q2, _) = w.queuer("q1"), w.queuer("q2")
        for q in (q1, q2):
            await w.t.queue(q, BASE)
        # A third joins: the three are read while the seats come due, and the third may not play after all.
        gate = Gate(monkeypatch, "refusals")
        held, = gate.hold(1)
        q3, _ = w.queuer("q3")
        task = asyncio.create_task(w.t.queue(q3, BASE))
        await until(lambda: gate.calls == 1)
        w.mono += FILL_SEC
        await w.timers.fire()
        assert w.t.by_id[tid].seats[1].empty
        w.g.store.update_player(w.who["q3"], shards=0)
        held.set()
        await task
        await w.t.idle()
        assert s1.of("ddz_invite")[-1]["table"] == tid and w.t.by_id[tid].seats[1].token == w.who["q1"]
    run(go())


# ------------------------------------------------------------------ calling members to the table
def test_the_opener_calls_members_of_the_room_to_the_table():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        c, sc = w.member("c")
        w.t.call("r", a, tid, c.id)
        assert sc.of("ddz_call") == [{"type": "ddz_call", "table": tid, "from": a.id, "base": BASE,
                                      "deposit": DEPOSIT, "sec": INVITE_SEC, "seats": [seat(a), seat(b), None]}]
        with pytest.raises(Exception) as e:
            w.t.call("r", a, tid, c.id)
        assert e.value.code == "ddz_cooldown"
        w.mono += RETRY_SEC
        w.t.call("r", a, tid, c.id)
        assert len(sc.of("ddz_call")) == 2
        # Turning invites down: never called, and the opener is not told.
        d, sd = w.member("d")
        d.dnd = True
        w.t.call("r", a, tid, d.id)
        assert sd.of("ddz_call") == []
        await w.t.sit("r", c, tid)
        await w.settled()
        assert sc.of("ddz_deal")[0]["you"] == 2
    run(go())


@pytest.mark.parametrize("how, code", [
    ("seated", "ddz_gone"), ("old", "ddz_target_old"), ("busy", "ddz_target_busy"), ("nobody", "no_member"),
    ("elsewhere", "no_member"), ("self", "ddz_self"), ("guest", "ddz_target_locked"),
])
def test_who_may_not_be_called(how, code):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        caller = b if how == "seated" else a
        if how == "guest":
            target, _ = w.join("guest", None, room="r")
            target.ddz_match = True
        elif how == "self":
            target, _ = w.member("a")
        else:
            target, _ = w.member("t", room="r2" if how == "elsewhere" else "r", match=how != "old")
        if how == "busy":
            await w.t.open("r", target, 50)
        with pytest.raises(Exception) as e:
            w.t.call("r", caller, tid, "nobody" if how == "nobody" else target.id)
        assert getattr(e.value, "code", None) == code
    run(go())


def test_members_carry_whether_their_client_opens_tables(api):
    c, g, timers = api
    for name in ("a", "old"):
        save(g, name)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as o:
        matched(a, "a", "r1")
        jo = matched(o, "old", "r1", match=False)
        assert [m["ddzMatch"] for m in jo["members"]] == [True, False]
        a.send_json({"type": "ddz_open", "base": BASE})
        tid = receive(a, "ddz_open")["table"]
        a.send_json({"type": "ddz_call", "table": tid, "id": jo["you"]})
        assert receive(a, "error")["code"] == "ddz_target_old"
        o.send_json({"type": "ddz_call", "table": tid, "id": jo["you"]})
        assert receive(o, "error")["code"] == "bad_message"


# ------------------------------------------------------------------ after a game
async def played(w, *names):
    """[names] at an open table of room r, a game played out to its result; returns the members and the table id."""
    out, tid = await w.opened(*names)
    await w.settled()
    w.peers = [p for p, _ in out]
    await w.t.bid(w.peers[0], tid, 3)
    await play_out(w, tid)
    assert w.t.by_id[tid].phase == "over"
    return out, tid


def test_those_who_ask_for_another_game_keep_their_seats_and_the_table_opens_again():
    async def go():
        w = OpenWorld()
        _, s_watch = w.member("watch")
        ((a, sa), (b, sb), (c, sc)), tid = await played(w, "a", "b", "c")
        after = [w.shards(w.who[n]) for n in "abc"]
        await w.t.again(a, tid)
        await w.t.again(b, tid)
        await w.t.leave(c, tid)
        assert sc.of("ddz_closed")[-1] == {"type": "ddz_closed", "table": tid} and w.who["c"] not in w.t.by_save
        assert last_open(sa) == {"table": tid, "base": BASE, "deposit": DEPOSIT, "you": 0,
                                 "seats": [seat(a), seat(b), None], "sec": OPEN_SEC}
        assert last_open(sb)["you"] == 1 and w.t.by_id[tid].phase == "open"
        w.mono += 1
        await w.counts.fire()
        assert s_watch.of("ddz_tables")[-1]["tables"] == [{"table": tid, "base": BASE,
                                                          "seats": [seat(a), seat(b), None]}]
        assert [w.shards(w.who[n]) for n in "abc"] == after
        # The same rules as before: anyone of the room sits down, the queue fills a seat after a minute.
        d, sd = w.member("d")
        await w.t.sit("r", d, tid)
        await w.settled()
        assert [s.of("ddz_deal")[-1]["you"] for s in (sa, sb, sd)] == [0, 1, 2] and sa.of("ddz_deal")[-1]["deal"] == 1
        assert [w.shards(w.who[n]) for n in "abd"] == [after[0] - DEPOSIT, after[1] - DEPOSIT, SHARDS - DEPOSIT]
    run(go())


def test_when_the_time_to_ask_runs_out_the_table_opens_again_with_those_who_asked():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb), (c, sc)), tid = await played(w, "a", "b", "c")
        await w.t.again(a, tid)
        w.mono += 30
        await w.timers.fire()
        assert last_open(sa)["seats"] == [seat(a), None, None]
        for s in (sb, sc):
            assert s.of("ddz_closed")[-1] == {"type": "ddz_closed", "table": tid}
        assert set(w.t.by_save) == {w.who["a"]}
        w.mono += FILL_SEC
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        assert sq.of("ddz_invite")[0]["ids"] == [a.id, q.id, ""]
    run(go())


@pytest.mark.parametrize("how", ["opener_silent", "opener_leaves", "opener_departs"])
def test_without_the_opener_asking_the_table_closes_as_before(how):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb), (c, sc)), tid = await played(w, "a", "b", "c")
        await w.t.again(b, tid)
        if how == "opener_silent":
            await w.t.again(c, tid)
            w.mono += 30
            await w.timers.fire()
        elif how == "opener_leaves":
            await w.t.leave(a, tid)
        else:
            await w.m.depart("r", a.id)
        await w.settled()
        for s in (sb, sc):
            assert s.of("ddz_closed")[-1] == {"type": "ddz_closed", "table": tid}
        assert w.t.by_id == {} and w.t.by_save == {}
    run(go())


def test_three_asking_again_play_on_and_one_that_cannot_pay_is_let_go():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb), (c, sc)), tid = await played(w, "a", "b", "c")
        w.mono += OPEN_SEC
        w.g.store.update_player(w.who["c"], shards=0)
        for p in (a, b, c):
            await w.t.again(p, tid)
        await w.settled()
        assert sc.of("ddz_over")[-1] == {"type": "ddz_over", "table": tid, "reason": "no_shards"}
        assert last_open(sa)["seats"] == [seat(a), seat(b), None] and w.t.by_id[tid].phase == "open"
        # Waiting again as long as a table just opened, however long the first wait and the game took.
        w.mono += OPEN_SEC - 1
        await w.timers.fire()
        assert w.t.by_id[tid].phase == "open"
    run(go())


def test_a_room_no_seat_is_in_any_more_hears_only_that_the_game_ended():
    async def go():
        w = OpenWorld()
        q, sq = w.queuer("q")
        q_room, _ = w.member("q", room="r-q")
        _, s_left = w.member("watch-q", room="r-q")
        _, s_here = w.member("watch-r")
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        w.mono += FILL_SEC
        await w.t.queue(q, BASE)
        await w.t.answer(q, tid, True)
        await w.settled()
        # Room r-q sees its member q at the table by its member id there; r by q's seat id.
        assert s_left.of("ddz_live")[-1] == {"type": "ddz_live", "table": tid, "ids": [a.id, b.id, q_room.id],
                                             "on": True, "base": BASE}
        assert s_here.of("ddz_live")[-1]["ids"] == [a.id, b.id, q.id]
        # The save of the seat of the queue moves to another room during the game.
        await w.m.depart("r-q", q_room.id)
        q2, s_q2 = w.member("q", room="r-z")
        await w.t.joined("r-z", q2)
        w.peers = [a, b, q]
        await w.t.bid(a, tid, 3)
        await play_out(w, tid)
        assert s_left.of("ddz_live")[-1] == {"type": "ddz_live", "table": tid, "on": False}
        for s, ids in ((s_here, [a.id, b.id, q.id]), (s_q2, [a.id, b.id, q2.id])):
            end = s.of("ddz_live")[-1]
            assert end["on"] is False and end["ids"] == ids and end["gains"]
    run(go())


# ------------------------------------------------------------------ races
class Gate:
    """Holds a Bank method in its thread until the test lets it go; [n] calls are held, each by its own event. Counts
    the calls made and those done."""

    def __init__(self, monkeypatch, name):
        import threading

        self.events, self.calls, self.done = [], 0, 0
        real = getattr(Bank, name)
        self._threading = threading

        def held(bank, *a):
            i = self.calls
            self.calls += 1
            ev = self.events[i] if i < len(self.events) else None
            if ev is not None:
                ev.wait(5)
            try:
                return real(bank, *a)
            finally:
                self.done += 1

        monkeypatch.setattr(Bank, name, held)

    def hold(self, n):
        self.events = [self._threading.Event() for _ in range(n)]
        self.calls = 0
        return self.events


async def until(cond):
    for _ in range(400):
        if cond():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("never happened")


def test_two_sitting_down_at_the_last_seat_at_once(monkeypatch):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        gate = Gate(monkeypatch, "check")
        first, second = gate.hold(2)
        c, sc = w.member("c")
        d, sd = w.member("d")
        tc = asyncio.create_task(w.t.sit("r", c, tid))
        await until(lambda: gate.calls == 1)
        td = asyncio.create_task(w.t.sit("r", d, tid))
        await until(lambda: gate.calls == 2)
        second.set()
        await td
        first.set()
        with pytest.raises(Exception) as e:
            await tc
        assert e.value.code == "ddz_gone"
        await w.settled()
        assert [s.of("ddz_deal")[0]["you"] for s in (sa, sb, sd)] == [0, 1, 2] and sc.of("ddz_deal") == []
        assert w.shards(w.who["c"]) == SHARDS and w.who["c"] not in w.t.by_save
    run(go())


@pytest.mark.parametrize("who", ["member", "opener"])
def test_sitting_down_while_someone_leaves(monkeypatch, who):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        gate = Gate(monkeypatch, "check")
        held, = gate.hold(1)
        c, sc = w.member("c")
        task = asyncio.create_task(w.t.sit("r", c, tid))
        await until(lambda: gate.calls == 1)
        await w.m.depart("r", (b if who == "member" else a).id)
        held.set()
        if who == "member":
            await task
            assert last_open(sa)["seats"] == [seat(a), seat(c), None] and w.t.by_id[tid].phase == "open"
        else:
            with pytest.raises(Exception) as e:
                await task
            assert e.value.code == "ddz_gone" and w.t.by_save == {} and w.t.by_id == {}
    run(go())


@pytest.mark.parametrize("who, back", [("opener", False), ("member", False), ("member", True)])
def test_leaving_the_room_while_the_deposits_are_taken(monkeypatch, who, back):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        gate = Gate(monkeypatch, "try_start")
        held, = gate.hold(1)
        c, sc = w.member("c")
        task = asyncio.create_task(w.t.sit("r", c, tid))
        await until(lambda: gate.calls == 1)
        leaver = a if who == "opener" else b
        await w.m.depart("r", leaver.id)
        if back:
            b2, sb2 = w.member("b")
            await w.t.joined("r", b2)
        held.set()
        await task
        await w.settled()
        if back:
            # Back before the deposits went: it plays, as at an invited table.
            assert sb2.of("ddz_deal")[0]["you"] == 1 and [w.shards(w.who[n]) for n in "abc"] == [SHARDS - DEPOSIT] * 3
            return
        # Gone before the start: what was taken goes back.
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3 and sc.of("ddz_deal") == []
        if who == "opener":
            assert sc.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "disband", "by": a.id}]
            assert w.t.by_id == {} and w.t.by_save == {}
        else:
            assert last_open(sa)["seats"] == [seat(a), None, seat(c)] and w.who["b"] not in w.t.by_save
    run(go())


@pytest.mark.parametrize("how", ["third_departs", "member_stands", "opener_disbands"])
def test_the_last_to_sit_does_not_wait_for_the_deposits_and_standing_up_meanwhile_counts(monkeypatch, how):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        gate = Gate(monkeypatch, "try_start")
        held, = gate.hold(1)
        c, sc = w.member("c")
        # The sitter's connection is not held up while the database works: what it sends next (leaving the room) is
        # read before the cards could be dealt.
        await asyncio.wait_for(w.t.sit("r", c, tid), 1)
        await until(lambda: gate.calls == 1)
        if how == "third_departs":
            await w.m.depart("r", c.id)
        elif how == "member_stands":
            await w.t.leave(b, tid)
            assert sb.of("ddz_closed") == [{"type": "ddz_closed", "table": tid}]
        else:
            await w.t.leave(a, tid)
            assert sa.of("ddz_closed") == [{"type": "ddz_closed", "table": tid}]
        held.set()
        await w.settled()
        # Nobody pays for a game that never started.
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3
        assert all(s.of("ddz_deal") == [] for s in (sa, sb, sc))
        if how == "opener_disbands":
            for s in (sb, sc):
                assert s.of("ddz_over")[-1] == {"type": "ddz_over", "table": tid, "reason": "disband", "by": a.id}
            assert w.t.by_id == {} and w.t.by_save == {}
            return
        left, seats = ("c", [seat(a), seat(b), None]) if how == "third_departs" else ("b", [seat(a), None, seat(c)])
        assert last_open(sa)["seats"] == seats and w.t.by_id[tid].phase == "open"
        assert w.who[left] not in w.t.by_save
    run(go())


def test_coming_back_while_the_deposits_go_back_finds_the_seat_given_up(monkeypatch):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        start = Gate(monkeypatch, "try_start")
        taking, = start.hold(1)
        refund = Gate(monkeypatch, "refund")
        giving, = refund.hold(1)
        c, sc = w.member("c")
        task = asyncio.create_task(w.t.sit("r", c, tid))
        await until(lambda: start.calls == 1)
        await w.m.depart("r", b.id)
        taking.set()
        # Gone when the deposits were taken: decided then, so coming back while they go back changes nothing.
        await until(lambda: refund.calls == 1)
        b2, sb2 = w.member("b")
        await w.t.joined("r", b2)
        # Its deposit is not back yet: the save sits nowhere else meanwhile.
        x, _ = w.member("x")
        await w.t.open("r", x, BASE)
        w.mono += QUEUE_INTERVAL
        with pytest.raises(Exception) as e:
            await w.t.sit("r", b2, w.t.by_save[w.who["x"]].id)
        assert e.value.code == "ddz_busy" and w.t.by_save[w.who["b"]].id == tid
        giving.set()
        await task
        await w.settled()
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3
        assert w.t.by_id[tid].phase == "open" and last_open(sa)["seats"] == [seat(a), None, seat(c)]
        assert w.who["b"] not in w.t.by_save and sb2.of("ddz_open") == []
        # The table waits as it should: the next to sit starts it.
        d, sd = w.member("d")
        await w.t.sit("r", d, tid)
        await w.settled()
        assert [s.of("ddz_deal")[0]["you"] for s in (sa, sd, sc)] == [0, 1, 2]
        assert [w.shards(w.who[n]) for n in "acd"] == [SHARDS - DEPOSIT] * 3
    run(go())


def test_a_member_standing_up_while_the_deposits_are_taken_sits_nowhere_else_until_they_are_back(monkeypatch):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        x, _ = w.member("x")
        await w.t.open("r", x, BASE)
        other = w.t.by_save[w.who["x"]].id
        start = Gate(monkeypatch, "try_start")
        taking, = start.hold(1)
        refund = Gate(monkeypatch, "refund")
        giving, = refund.hold(1)
        c, sc = w.member("c")
        await w.t.sit("r", c, tid)
        await until(lambda: start.calls == 1)
        await w.t.leave(b, tid)
        assert sb.of("ddz_closed") == [{"type": "ddz_closed", "table": tid}]
        # Its deposit may be being taken, then handed back: until it is, the save is held.
        bq, _ = w.queuer("b")
        for attempt in (lambda: w.t.sit("r", b, other), lambda: w.t.queue(bq, BASE)):
            w.mono += QUEUE_INTERVAL
            with pytest.raises(Exception) as e:
                await attempt()
            assert e.value.code == "ddz_busy"
        taking.set()
        await until(lambda: refund.calls == 1)
        w.mono += QUEUE_INTERVAL
        with pytest.raises(Exception) as e:
            await w.t.sit("r", b, other)
        assert e.value.code == "ddz_busy"
        giving.set()
        await w.settled()
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3 and w.who["b"] not in w.t.by_save
        # Back, it is free: it sits down at the other table.
        w.mono += QUEUE_INTERVAL
        await w.t.sit("r", b, other)
        assert w.t.by_save[w.who["b"]].id == other
    run(go())


def test_a_member_whose_connection_left_the_room_before_the_tables_hear_of_it_does_not_play(monkeypatch):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        gate = Gate(monkeypatch, "try_start")
        held, = gate.hold(1)
        c, sc = w.member("c")
        await w.t.sit("r", c, tid)
        await until(lambda: gate.calls == 1)
        # c's connection is out of the room, but the tables hear of it only after the duels, which take a while.
        w.m.leave("r", c.id)
        held.set()
        await w.settled()
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3
        assert all(s.of("ddz_deal") == [] for s in (sa, sb, sc))
        assert last_open(sa)["seats"] == [seat(a), seat(b), None] and w.who["c"] not in w.t.by_save
        # Told late: nothing more happens.
        await w.t.departed("r", c)
        assert last_open(sa)["seats"] == [seat(a), seat(b), None] and w.t.by_id[tid].phase == "open"
    run(go())


@pytest.mark.parametrize("fails", [1, "always"])
def test_handing_the_deposits_back_is_tried_again_and_left_to_the_next_start_when_it_keeps_failing(monkeypatch, fails):
    async def go():
        import sqlite3

        import app.ddz as ddz_module
        monkeypatch.setattr(ddz_module, "REFUND_RETRY_SEC", (0.0, 0.0))
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        gate = Gate(monkeypatch, "try_start")
        held, = gate.hold(1)
        real = Bank.refund
        tries = []

        def refund(bank, game_id):
            tries.append(game_id)
            if fails == "always" or len(tries) <= fails:
                raise sqlite3.OperationalError("database is locked")
            return real(bank, game_id)

        monkeypatch.setattr(Bank, "refund", refund)
        c, sc = w.member("c")
        await w.t.sit("r", c, tid)
        await until(lambda: gate.calls == 1)
        await w.t.leave(b, tid)
        held.set()
        await w.settled()
        if fails == 1:
            # The second try goes through: the table waits again as it would have.
            assert len(tries) == 2 and [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3
            assert last_open(sa)["seats"] == [seat(a), None, seat(c)] and w.t.by_id[tid].phase == "open"
            assert w.who["b"] not in w.t.by_save and w.g.store.open_ddz_games() == []
            return
        # Every try failed: the table goes and the saves are free; the game stays open, its deposits taken, for the
        # next start of the server to hand back.
        assert len(tries) == 3 and w.t.by_id == {} and w.t.by_save == {}
        assert [s.of("ddz_over")[-1] for s in (sa, sc)] == [{"type": "ddz_over", "table": tid, "reason": "error"}] * 2
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS - DEPOSIT] * 3
        assert w.g.store.open_ddz_games() == tries[:1]
        monkeypatch.setattr(Bank, "refund", real)
        assert Bank(w.g).refund_open() == 1
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3
    run(go())


def test_a_start_cut_off_by_the_server_stopping_is_handed_back_when_it_starts_again(monkeypatch):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        gate = Gate(monkeypatch, "try_start")
        held, = gate.hold(1)
        refunds = []
        # The process ends before anything hands the deposits back.
        monkeypatch.setattr(Bank, "refund", lambda bank, game_id: refunds.append(game_id) or False)
        c, sc = w.member("c")
        await w.t.sit("r", c, tid)
        await until(lambda: gate.calls == 1)
        for t in asyncio.all_tasks():
            if t is not asyncio.current_task():
                t.cancel()
        held.set()
        await until(lambda: len(refunds) == 1)
        # The game stays open, its deposits taken: nothing marked it handed back without handing them back.
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS - DEPOSIT] * 3
        assert w.g.store.open_ddz_games() == refunds
        monkeypatch.undo()
        # Starting again, the server hands back what open games hold.
        assert Bank(w.g).refund_open() == 1
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3 and w.g.store.open_ddz_games() == []
    run(go())


def test_a_start_cancelled_while_the_deposits_are_taken_hands_them_back(monkeypatch):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        gate = Gate(monkeypatch, "try_start")
        held, = gate.hold(1)
        c, sc = w.member("c")
        task = asyncio.create_task(w.t.sit("r", c, tid))
        await until(lambda: gate.calls == 1)
        table = w.t.by_id[tid]
        # Whatever awaits the start is cancelled (a connection's handler, the server stopping): the table goes, and
        # the transaction, which cannot be stopped half way, finishes in its thread.
        for t in asyncio.all_tasks():
            if t is not asyncio.current_task():
                t.cancel()
        await settle()
        assert table.phase == "done" and w.t.by_save == {}
        held.set()
        await until(lambda: gate.done == 1 and [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3)
        await w.settled()
        assert all(s.of("ddz_deal") == [] for s in (sa, sb, sc))
        assert task.cancelled() or task.done()
    run(go())


# ------------------------------------------------------------------ alongside invites
def test_invites_of_old_clients_go_on_beside_open_tables():
    async def go():
        w = OpenWorld()
        ((a, sa),), tid = await w.opened("a")
        old, s_old = w.member("old", match=False)
        old2, _ = w.member("old2", match=False)
        new, s_new = w.member("new")
        # Seated at an open table: busy for an invite.
        with pytest.raises(Exception) as e:
            await w.t.invite("r", old, [a.id, new.id], BASE)
        assert e.value.code == "ddz_target_busy"
        # An old client invites a new one and another old one; the new one answers as before.
        await w.t.invite("r", old, [new.id, old2.id], BASE)
        invite = s_new.of("ddz_invite")[0]
        assert invite["from"] == old.id and "match" not in invite
        await w.t.answer(new, invite["table"], True)
        await w.t.answer(old2, invite["table"], True)
        await w.settled()
        assert s_new.of("ddz_deal")[0]["you"] == 1 and s_old.of("ddz_tables") == []
        assert w.t.by_id[tid].phase == "open"
    run(go())


def test_the_seats_see_the_full_table_while_the_deposits_are_taken(monkeypatch):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await w.opened("a", "b")
        gate = Gate(monkeypatch, "try_start")
        held, = gate.hold(1)
        c, sc = w.member("c")
        task = asyncio.create_task(w.t.sit("r", c, tid))
        await until(lambda: gate.calls == 1)
        for i, s in enumerate((sa, sb, sc)):
            assert last_open(s) == {"table": tid, "base": BASE, "deposit": DEPOSIT, "you": i,
                                    "seats": [seat(a), seat(b), seat(c)], "sec": OPEN_SEC - QUEUE_INTERVAL,
                                    "starting": True}
        held.set()
        await task
        await w.settled()
        assert [s.of("ddz_deal")[0]["you"] for s in (sa, sb, sc)] == [0, 1, 2]
    run(go())
