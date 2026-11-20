"""Open dou dizhu tables: opened in a room at a stake, sat at by the room's members, started by the third."""
import asyncio

import pytest

from app.ddz import OPEN_SEC, QUEUE_INTERVAL, Bank
from test_ddz import BASE, DEPOSIT, SHARDS, api, save  # noqa: F401
from test_ddz_match import MatchWorld, matched, queue_msgs, receive  # noqa: F401
from test_duel import settle


class OpenWorld(MatchWorld):
    """Members in room r by default, on clients that open tables."""

    def member(self, name, room="r", match=True, **kw):
        return super().member(name, room=room, match=match, **kw)

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
        await settle()
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS - DEPOSIT] * 3
        assert [s.of("ddz_deal")[0]["you"] for s in (sa, sb, sc)] == [0, 1, 2]
        assert sc.of("ddz_open") == [] and sa.of("ddz_live")[-1]["on"] is True
        assert w.t.by_id[tid].phase == "bid"
    run(go())


def test_a_seat_picked_that_is_taken_gives_the_next_empty_one():
    async def go():
        w = OpenWorld()
        ((_, sa), (_, sb)), tid = await w.opened("a", "b")
        c, sc = w.member("c")
        await w.t.sit("r", c, tid, 1)
        await settle()
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
            await settle()
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
        await w.t.queue(b, 50)
        w.mono += QUEUE_INTERVAL
        await w.t.queue(a, BASE)
        with pytest.raises(Exception) as e:
            await w.t.open("r", a, BASE)
        assert e.value.code == "rate_limited"
        w.mono += QUEUE_INTERVAL
        await w.t.open("r", a, BASE)
        assert queue_msgs(sa)[-1] == {"base": None} and w.who["a"] not in w.t.waiting
        await w.t.sit("r", b, sa.of("ddz_open")[-1]["table"])
        assert queue_msgs(sb)[-1] == {"base": None} and w.t.waiting == {}
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
        await settle()
        assert len(starts) == 1
        assert sb.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "no_shards"}]
        assert last_open(sa)["seats"] == [seat(a), None, seat(c)] and last_open(sc)["you"] == 2
        assert w.t.by_id[tid].phase == "open" and w.who["b"] not in w.t.by_save
        assert [w.shards(w.who[n]) for n in "ac"] == [SHARDS] * 2 and w.shards(w.who["b"]) == DEPOSIT - 1
        d, sd = w.member("d")
        await w.t.sit("r", d, tid)
        await settle()
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
        await settle()
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
        await settle()
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
