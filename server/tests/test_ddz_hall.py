"""The dou dizhu hall: public open tables, sat down at from dou dizhu connections, and hall tables of no room."""
import asyncio

import pytest

import app.main as main
from app.ddz import AUTO_SEC, FILL_SEC, LOBBY_TABLES, OPEN_SEC, QUEUE_INTERVAL
from app.tracking import COUNT_KEYS
from test_ddz import BASE, CFG, DEPOSIT, SHARDS, api, play_out, save, tok  # noqa: F401
from test_ddz_match import hello, queue_msgs, receive
from test_ddz_open import OpenWorld, last_open, seat
from test_duel import settle

KEYS = ("ddz_ask", "ddz_ask_timeout", "ddz_ask_decline", "ddz_start_match", "ddz_start_open", "ddz_start_hall",
        "ddz_start_invite")


def run(coro):
    return asyncio.run(coro)


def face(peer):
    return {"nick": peer.nick, "character": peer.character}


def counts(w):
    """Today's dou dizhu counts so far, every key there."""
    got = {k: n for (_, k), n in w.g.tracker._counts.items()}
    return {k: got.get(k, 0) for k in KEYS}


def counted(**kw):
    return {k: kw.get(k, 0) for k in KEYS}


async def hall(w, *names, base=BASE):
    """Dou dizhu connections of [names], each sitting down at [base] in turn (ddz_open); returns them and the table
    id the first sat at."""
    out = []
    for n in names:
        peer, sock = w.queuer(n)
        w.mono += QUEUE_INTERVAL
        await w.t.hall_open(peer, base)
        out.append((peer, sock))
    return out, out[0][1].of("ddz_open")[-1]["table"]


async def play_to_end(w, tid):
    """Every seat leads its lowest card and passes otherwise; a seat played for moves when the timers fire."""
    t = w.t.by_id[tid]
    while t.phase == "play":
        s = t.seats[t.turn]
        if s.peer is None or s.quit:
            await w.timers.fire()
        else:
            await w.t.play(s.peer, tid, [] if t.last is not None else [s.hand[0]])
    await settle()


async def hall_game(w, *names):
    """[names] at a hall table, a game dealt and the landlord found (seat 0 bids 3); returns them and the table id."""
    out, tid = await hall(w, *names)
    await w.settled()
    w.peers = [p for p, _ in out]
    await w.t.bid(w.peers[0], tid, 3)
    return out, tid


# ------------------------------------------------------------------ sitting down
def test_sitting_down_at_a_stake_opens_a_hall_table_when_none_waits():
    async def go():
        w = OpenWorld()
        ((a, sa),), tid = await hall(w, "a")
        t = w.t.by_id[tid]
        assert t.hall and t.open and t.room is None and not t.match and t.phase == "open"
        assert last_open(sa) == {"table": tid, "base": BASE, "deposit": DEPOSIT, "you": 0,
                                 "seats": [seat(a), None, None], "sec": OPEN_SEC}
        assert t.seats[0].roam and t.seats[0].accepted and w.t.holds(w.who["a"])
        # The next one at the stake sits down there; at another stake a table of its own opens.
        b, sb = w.queuer("b")
        await w.t.hall_open(b, BASE)
        assert last_open(sb) == {"table": tid, "base": BASE, "deposit": DEPOSIT, "you": 1,
                                 "seats": [seat(a), seat(b), None], "sec": OPEN_SEC}
        assert last_open(sa)["seats"] == [seat(a), seat(b), None]
        c, sc = w.queuer("c")
        await w.t.hall_open(c, 50)
        assert last_open(sc)["table"] != tid and last_open(sc)["you"] == 0 and len(w.t.by_id) == 2
        # Rooms hear nothing of a hall table.
        _, s_room = w.member("watch")
        w.mono += 1
        await w.counts.fire()
        assert s_room.of("ddz_tables") == [] and w.t._tables_sent == {}
    run(go())


def test_sitting_down_at_a_stake_takes_the_fullest_public_table_rooms_included_then_the_oldest():
    async def go():
        w = OpenWorld()
        ((h, sh),), htid = await hall(w, "h")
        w.mono += 5
        ((x, sx), (y, sy)), rtid = await w.opened("x", "y")
        # The room's table has two seats taken, the hall's one: the room's is fuller.
        q, sq = w.queuer("q")
        await w.t.hall_open(q, BASE)
        assert w.t.by_save[w.who["q"]].id == rtid and last_open(sq)["you"] == 2
        assert last_open(sx)["seats"] == [seat(x), seat(y), seat(q)] and last_open(sx).get("starting") is True
        await w.settled()
        assert [s.of("ddz_deal")[0]["you"] for s in (sx, sy, sq)] == [0, 1, 2]
        # Among tables as full, the oldest: a room's opened after the hall table loses to it.
        w.mono += 5
        z, _ = w.member("z")
        await w.t.open("r", z, BASE)
        p, sp = w.queuer("p")
        await w.t.hall_open(p, BASE)
        assert w.t.by_save[w.who["p"]].id == htid and last_open(sp)["you"] == 1
    run(go())


def test_a_room_that_bans_the_save_keeps_its_tables_from_it():
    async def go():
        w = OpenWorld()
        ((x, _),), rtid = await w.opened("x")
        b, sb = w.queuer("b")
        w.m.rooms["r"].banned.add(w.who["b"])
        with pytest.raises(Exception) as e:
            await w.t.hall_sit(b, rtid)
        assert e.value.code == "ddz_gone"
        assert w.t.lobby_tables(w.who["b"]) == {} and w.t.lobby_tables()[BASE][0]["table"] == rtid
        await w.t.hall_open(b, BASE)
        assert w.t.by_save[w.who["b"]].hall and last_open(sb)["you"] == 0
    run(go())


def test_sitting_at_a_table_from_a_dou_dizhu_connection_and_the_room_list_shows_the_stranger():
    async def go():
        w = OpenWorld()
        _, s_watch = w.member("watch")
        ((a, sa),), rtid = await w.opened("a")
        q, sq = w.queuer("q")
        await w.t.hall_sit(q, rtid, 2)
        assert last_open(sq) == {"table": rtid, "base": BASE, "deposit": DEPOSIT, "you": 2,
                                 "seats": [seat(a), None, seat(q)], "sec": OPEN_SEC}
        assert w.t.by_id[rtid].seats[2].roam and w.t.holds(w.who["q"])
        w.mono += 1
        await w.counts.fire()
        assert s_watch.of("ddz_tables")[-1]["tables"] == [{"table": rtid, "base": BASE,
                                                          "seats": [seat(a), None, seat(q)]}]
        # The save comes into the room on another connection: the room knows the seat by that member id, and the
        # join does not take the seat.
        q_room, sq_room = w.member("q")
        await w.t.joined("r", q_room)
        w.mono += 1
        await w.counts.fire()
        mine = {"id": q_room.id, "nick": "q", "character": "嘉然"}
        assert s_watch.of("ddz_tables")[-1]["tables"][0]["seats"] == [seat(a), None, mine]
        assert sq_room.of("ddz_tables")[-1]["tables"][0]["seats"][2] == mine
        assert w.t.by_id[rtid].seats[2].peer is q and sq_room.of("ddz_open") == []
        # Leaving the room again: the seat's own id.
        await w.m.depart("r", q_room.id)
        w.mono += 1
        await w.counts.fire()
        assert s_watch.of("ddz_tables")[-1]["tables"][0]["seats"][2] == seat(q)
        # A hall table: sitting at the seat asked for.
        ((h, sh),), htid = await hall(w, "h", base=50)
        b, sb = w.queuer("b")
        await w.t.hall_sit(b, htid, 2)
        assert last_open(sh)["seats"] == [seat(h), None, seat(b)] and last_open(sb)["you"] == 2
        # Calling stays a room's.
        with pytest.raises(Exception) as e:
            w.t.call("r", a, htid, w.member("m")[0].id)
        assert e.value.code == "ddz_gone"
    run(go())


@pytest.mark.parametrize("how, code", [
    ("guest", "ddz_locked"), ("poor", "no_shards"), ("dnd", "ddz_dnd"), ("busy", "ddz_busy"),
    ("stake", "bad_message"), ("room", "bad_message"), ("rate", "rate_limited"), ("full", "ddz_gone"),
    ("nothing", "ddz_gone"),
])
def test_who_may_not_sit_down_in_the_hall(how, code):
    async def go():
        w = OpenWorld()
        ((a, _), (b, _)), tid = await hall(w, "a", "b")
        if how == "guest":
            peer, _ = w.lobby("guest", None)
        elif how == "room":
            peer, _ = w.member("c")
        else:
            peer, _ = w.queuer("c", shards=DEPOSIT - 1 if how == "poor" else SHARDS)
        peer.dnd = how == "dnd"
        if how == "busy":
            await w.t.hall_sit(peer, tid)
            await w.settled()
        if how == "rate":
            await w.t.queue(peer, 50)
        if how == "full":
            d, _ = w.queuer("d")
            await w.t.hall_sit(d, tid)
        with pytest.raises(Exception) as e:
            if how == "stake":
                await w.t.hall_open(peer, 123)
            else:
                await w.t.hall_sit(peer, "nope" if how == "nothing" else tid)
        assert getattr(e.value, "code", None) == code
        await w.settled()
        if how in ("guest", "poor", "dnd", "room", "rate"):
            with pytest.raises(Exception) as e:
                w.mono += 0 if how == "rate" else QUEUE_INTERVAL
                await w.t.hall_open(peer, BASE)
            assert getattr(e.value, "code", None) == code
    run(go())


def test_a_room_connection_turning_invites_down_does_not_keep_the_save_from_the_hall():
    async def go():
        w = OpenWorld()
        ((a, _), (b, _)), tid = await hall(w, "a", "b")
        c, sc = w.queuer("c")
        c_room, _ = w.member("c")
        c_room.dnd = True
        w.t.set_dnd(c_room, True)
        w.mono += QUEUE_INTERVAL
        await w.t.hall_sit(c, tid)
        await w.settled()
        assert sc.of("ddz_deal")[0]["you"] == 2
        # A new hall table, opened by a save whose room connection turns invites down.
        d, sd = w.queuer("d")
        d_room, _ = w.member("d")
        d_room.dnd = True
        w.mono += QUEUE_INTERVAL
        await w.t.hall_open(d, BASE)
        assert last_open(sd)["you"] == 0 and w.t.by_save[w.who["d"]].hall
    run(go())


def test_the_queue_cooldown_does_not_keep_a_save_from_sitting_and_sitting_leaves_the_queue():
    async def go():
        w = OpenWorld()
        q, sq = w.queuer("q")
        w.t.match_refused[w.who["q"]] = w.mono + 60
        await w.t.hall_open(q, BASE)
        assert last_open(sq)["you"] == 0
        await w.t.leave(q, last_open(sq)["table"])
        b, sb = w.queuer("b")
        await w.t.queue(b, 50)
        w.mono += QUEUE_INTERVAL
        await w.t.hall_open(b, BASE)
        assert queue_msgs(sb)[-1] == {"base": None} and w.t.waiting == {}
    run(go())


# ------------------------------------------------------------------ standing up, putting away
def test_anyone_stands_up_and_the_table_goes_once_nobody_sits_there():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb), ), tid = await hall(w, "a", "b")
        # Seat 0 standing up puts nothing away: b still sits there.
        await w.t.leave(a, tid)
        assert sa.of("ddz_closed") == [{"type": "ddz_closed", "table": tid}] and sb.of("ddz_over") == []
        assert last_open(sb)["seats"] == [None, seat(b), None] and w.who["a"] not in w.t.by_save
        # Someone sits down in seat 0 again, then leaves by closing its connection.
        c, sc = w.queuer("c")
        await w.t.hall_sit(c, tid, 0)
        assert last_open(sb)["seats"] == [seat(c), seat(b), None]
        await w.bye(c)
        assert last_open(sb)["seats"] == [None, seat(b), None] and w.who["c"] not in w.t.by_save
        await w.t.leave(b, tid)
        assert sb.of("ddz_closed")[-1] == {"type": "ddz_closed", "table": tid}
        assert w.t.by_id == {} and w.t.by_save == {} and w.timers.live() == []
    run(go())


def test_a_save_of_the_queue_offered_a_seat_goes_back_to_the_line_when_the_table_goes():
    async def go():
        w = OpenWorld()
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        # An empty seat of a hall table is due at once: the save of the queue is asked as the table opens.
        ((a, sa),), tid = await hall(w, "a")
        assert sq.of("ddz_invite") == [{"type": "ddz_invite", "table": tid, "ids": [a.id, q.id, ""], "base": BASE,
                                        "deposit": DEPOSIT, "sec": CFG["inviteSec"], "match": True,
                                        "seats": [seat(a), seat(q), None], "accepted": [a.id]}]
        assert last_open(sa)["seats"] == [seat(a), {"pending": True}, None]
        await w.t.leave(a, tid)
        assert sq.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "gone"}]
        assert queue_msgs(sq)[-1]["base"] == BASE and [x.peer for x in w.t.lines[BASE]] == [q]
        assert w.t.by_id == {} and w.who["q"] not in w.t.match_refused
        assert counts(w) == counted(ddz_ask=1)
    run(go())


def test_the_time_to_wait_starts_over_at_each_seat_taken():
    async def go():
        w = OpenWorld()
        ((a, sa),), tid = await hall(w, "a")
        w.mono += OPEN_SEC - 10
        b, sb = w.queuer("b")
        await w.t.hall_sit(b, tid)
        assert last_open(sb)["sec"] == OPEN_SEC and last_open(sa)["sec"] == OPEN_SEC
        w.mono += 10
        await w.timers.fire()
        assert w.t.by_id[tid].phase == "open"
        # Standing up takes no seat; a seat of the queue accepted counts as one taken.
        await w.t.leave(b, tid)
        q, sq = w.queuer("q")
        w.mono += OPEN_SEC - 20
        await w.t.queue(q, BASE)
        assert last_open(sa)["sec"] == 10
        await w.t.answer(q, tid, True)
        assert last_open(sq)["sec"] == OPEN_SEC
        w.mono += OPEN_SEC - 1
        await w.timers.fire()
        assert w.t.by_id[tid].phase == "open"
        w.mono += 1
        await w.timers.fire()
        for s in (sa, sq):
            assert s.of("ddz_over")[-1] == {"type": "ddz_over", "table": tid, "reason": "expired"}
        assert w.t.by_id == {} and w.t.by_save == {}
    run(go())


def test_a_save_queueing_is_offered_a_seat_of_a_hall_table_at_once_and_the_third_to_sit_starts():
    async def go():
        w = OpenWorld()
        ((a, sa),), tid = await hall(w, "a")
        q, sq = w.queuer("q")
        await w.t.queue(q, BASE)
        await w.t.idle()
        assert sq.of("ddz_invite")[0]["ids"] == [a.id, q.id, ""]
        await w.t.answer(q, tid, True)
        # The fullest table at the stake takes the next to sit down; the game starts.
        b, sb = w.queuer("b")
        await w.t.hall_open(b, BASE)
        await w.settled()
        assert [s.of("ddz_deal")[0]["you"] for s in (sa, sq, sb)] == [0, 1, 2]
        assert [w.shards(w.who[n]) for n in ("a", "q", "b")] == [SHARDS - DEPOSIT] * 3
        assert counts(w) == counted(ddz_ask=1, ddz_start_hall=1)
    run(go())


def test_a_seat_that_cannot_pay_at_the_start_is_let_go_and_the_table_waits_again():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb), (c, sc)), tid = await hall(w, "a", "b", "c")
        assert w.t.by_id[tid].phase == "starting"
        # Seat 0's save cannot pay by the time the deposits are taken: a room's opener would put the table away.
        w.g.store.update_player(w.who["a"], shards=0)
        await w.settled()
        assert sa.of("ddz_over")[-1] == {"type": "ddz_over", "table": tid, "reason": "no_shards"}
        assert last_open(sb)["seats"] == [None, seat(b), seat(c)] and w.t.by_id[tid].phase == "open"
        assert w.who["a"] not in w.t.by_save and counts(w) == counted()
    run(go())


def test_the_three_standing_up_while_the_deposits_are_taken_puts_the_table_away():
    async def go():
        w = OpenWorld()
        out, tid = await hall(w, "a", "b", "c")
        for peer, _ in out:
            await w.t.leave(peer, tid)
        await w.settled()
        assert w.t.by_id == {} and w.t.by_save == {} and counts(w) == counted()
        assert [w.shards(w.who[n]) for n in "abc"] == [SHARDS] * 3
    run(go())


# ------------------------------------------------------------------ a game and after
def test_a_game_at_a_hall_table_plays_to_the_end_and_three_asking_play_again():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb), (c, sc)), tid = await hall_game(w, "a", "b", "c")
        await play_out(w, tid)
        assert sa.of("ddz_result")[-1]["winner"] == "landlord" and w.t.by_id[tid].phase == "over"
        for p in (a, b, c):
            await w.t.again(p, tid)
        await w.settled()
        assert sa.of("ddz_deal")[-1]["deal"] == 1 and len(sb.of("ddz_deal")) == 2
        assert counts(w) == counted(ddz_start_hall=2)
    run(go())


@pytest.mark.parametrize("how", ["leaves_after", "away_during"])
def test_seat_0_gone_and_the_others_asking_again_opens_the_table_again(how):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb), (c, sc)), tid = await hall_game(w, "a", "b", "c")
        if how == "away_during":
            await w.bye(a)
        await play_to_end(w, tid)
        assert w.t.by_id[tid].phase == "over"
        if how == "leaves_after":
            await w.t.leave(a, tid)
            assert sa.of("ddz_closed")[-1] == {"type": "ddz_closed", "table": tid}
        assert w.who["a"] not in w.t.by_save and w.t.by_id[tid].phase == "over"
        await w.t.again(b, tid)
        assert w.t.by_id[tid].phase == "over"
        await w.t.again(c, tid)
        t = w.t.by_id[tid]
        assert t.phase == "open" and t.opened_at == w.mono and t.seats[0].empty
        assert last_open(sb) == {"table": tid, "base": BASE, "deposit": DEPOSIT, "you": 1,
                                 "seats": [None, seat(b), seat(c)], "sec": OPEN_SEC}
    run(go())


@pytest.mark.parametrize("asks", ["", "c"])
def test_when_the_time_to_ask_runs_out_anyone_still_there_who_asked_keeps_the_table(asks):
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb), (c, sc)), tid = await hall_game(w, "a", "b", "c")
        await play_out(w, tid)
        for name, (peer, _) in zip("abc", ((a, sa), (b, sb), (c, sc))):
            if name in asks:
                await w.t.again(peer, tid)
        w.mono += CFG["againSec"]
        await w.timers.fire()
        if asks:
            assert last_open(sc)["seats"] == [None, None, seat(c)] and w.t.by_id[tid].phase == "open"
            assert sa.of("ddz_closed")[-1] == sb.of("ddz_closed")[-1] == {"type": "ddz_closed", "table": tid}
            assert set(w.t.by_save) == {w.who["c"]}
        else:
            assert w.t.by_id == {} and w.t.by_save == {}
            assert all(s.of("ddz_closed")[-1] == {"type": "ddz_closed", "table": tid} for s in (sa, sb, sc))
    run(go())


def test_everyone_leaving_after_the_game_closes_the_table():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb), (c, sc)), tid = await hall_game(w, "a", "b", "c")
        await play_out(w, tid)
        await w.t.leave(a, tid)
        await w.bye(b)
        assert w.t.by_id[tid].phase == "over"
        await w.t.leave(c, tid)
        assert w.t.by_id == {} and w.t.by_save == {}
    run(go())


def test_everyone_away_by_the_end_closes_the_table():
    async def go():
        w = OpenWorld()
        ((a, _), (b, _), (c, _)), tid = await hall_game(w, "a", "b", "c")
        # Two away: the game goes on for the third, played for with the others.
        await w.bye(a)
        await w.bye(b)
        await play_to_end(w, tid)
        assert w.t.by_id[tid].phase == "over"
        await w.t.leave(c, tid)
        assert w.t.by_id == {} and w.t.by_save == {}
    run(go())


def test_a_new_dou_dizhu_connection_takes_a_hall_seat_back():
    async def go():
        w = OpenWorld()
        ((a, sa), (b, sb)), tid = await hall(w, "a", "b")
        # While the table waits: a newer connection of the save takes the seat from the older one.
        a2, sa2 = w.queuer("a")
        await w.t.hello(a2)
        assert sa2.of("ddz_ready")[-1]["table"] == tid and last_open(sa2)["you"] == 0
        assert sa.of("ddz_closed")[-1] == {"type": "ddz_closed", "table": tid}
        assert w.t.by_id[tid].seats[0].peer is a2 and last_open(sb)["seats"][0] == seat(a2)
        # During the game: a room join does not take it, a new dou dizhu connection does.
        c, _ = w.queuer("c")
        w.mono += QUEUE_INTERVAL
        await w.t.hall_open(c, BASE)
        await w.settled()
        await w.bye(b)
        b_room, sb_room = w.member("b")
        await w.t.joined("r", b_room)
        assert w.t.by_id[tid].seats[1].peer is None and sb_room.of("ddz_state") == []
        b2, sb2 = w.queuer("b")
        await w.t.hello(b2)
        assert w.t.by_id[tid].seats[1].peer is b2 and sb2.of("ddz_state")[0]["you"] == 1
        assert counts(w) == counted(ddz_start_hall=1)
    run(go())


# ------------------------------------------------------------------ the lobby
def test_the_lobby_lists_the_public_tables_fullest_then_oldest_at_most_four():
    async def go():
        w = OpenWorld()
        ((h1, _),), htid = await hall(w, "h1")
        rooms = []
        for n in "pqrst":
            w.mono += 1
            m, sm = w.member(n)
            await w.t.open("r", m, BASE)
            rooms.append(sm.of("ddz_open")[-1]["table"])
        # A seat offered to a save of the queue counts as taken: the hall table, oldest, gets it.
        w.mono += FILL_SEC
        q, _ = w.queuer("qq")
        await w.t.queue(q, BASE)
        assert w.t.by_save[w.who["qq"]].id == htid
        # The fourth room table gets a second seat taken: as full as the hall table, younger.
        u, _ = w.member("u")
        await w.t.sit("r", u, rooms[3])
        listed = w.t.lobby_tables()
        assert list(listed) == [BASE] and len(listed[BASE]) == LOBBY_TABLES
        assert listed[BASE][0] == {"table": htid, "seats": [face(h1), {"pending": True}, None]}
        assert listed[BASE][1] == {"table": rooms[3], "seats": [face(w.t.by_id[rooms[3]].seats[0]), face(u), None]}
        assert [x["table"] for x in listed[BASE][2:]] == rooms[:2]
        assert "id" not in str(listed) and "room" not in str(listed)
        # A full table, starting, is never listed.
        await w.t.answer(q, htid, True)
        c, _ = w.queuer("c")
        await w.t.hall_sit(c, htid)
        assert w.t.by_id[htid].phase == "starting" and htid not in [x["table"] for x in w.t.lobby_tables()[BASE]]
        await w.settled()
    run(go())


def test_the_hall_over_the_socket(api):  # noqa: F811
    c, g, timers = api
    for name in ("a", "b"):
        save(g, name)
    get = lambda name: c.get("/api/ddz/lobby", headers={"X-Player-Token": tok(name)}).json()  # noqa: E731
    assert all(t["tables"] == [] for t in get("b")["tiers"])
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ra, rb = hello(a, "a"), hello(b, "b")
        a.send_json({"type": "ddz_open", "base": BASE})
        opened = receive(a, "ddz_open")
        tid = opened["table"]
        pet = opened["seats"][0]["character"]
        assert opened["you"] == 0 and opened["seats"] == [{"id": ra["you"], "nick": "a", "character": pet}, None, None]
        tier = next(t for t in get("b")["tiers"] if t["base"] == BASE)
        assert tier["tables"] == [{"table": tid, "seats": [{"nick": "a", "character": pet}, None, None]}]
        assert get("a")["seated"] is True
        b.send_json({"type": "ddz_sit", "table": tid, "seat": 2})
        assert receive(b, "ddz_open")["you"] == 2
        assert receive(a, "ddz_open")["seats"][2]["nick"] == "b"
        b.send_json({"type": "ddz_call", "table": tid, "id": ra["you"]})
        assert receive(b, "error")["code"] == "not_joined"
        b.send_json({"type": "ddz_leave", "table": tid})
        assert receive(b, "ddz_closed") == {"type": "ddz_closed", "table": tid}
        assert receive(a, "ddz_open")["seats"][2] is None


# ------------------------------------------------------------------ counts
def test_the_count_keys_end_with_the_dou_dizhu_counts():
    assert COUNT_KEYS[-len(KEYS):] == KEYS


def test_asks_of_the_queue_and_how_they_end_are_counted():
    async def go():
        w = OpenWorld()
        # A table the queue made: asked once, declined once.
        out = [w.queuer(n) for n in "abc"]
        for p, _ in out:
            w.mono += QUEUE_INTERVAL
            await w.t.queue(p, BASE)
        await w.t.idle()
        tid = out[0][1].of("ddz_invite")[-1]["table"]
        await w.t.answer(out[2][0], tid, False)
        await w.t.idle()
        assert counts(w) == counted(ddz_ask=1, ddz_ask_decline=1)
        # Another, the time running out.
        d, _ = w.queuer("d")
        await w.t.queue(d, BASE)
        await w.t.idle()
        assert counts(w) == counted(ddz_ask=2, ddz_ask_decline=1)
        await w.timers.fire()
        assert counts(w) == counted(ddz_ask=2, ddz_ask_decline=1, ddz_ask_timeout=1)
        w.t.clear()
        # Seats of open tables offered to the queue: taken over by a new connection (nothing), let run out, left.
        w.mono += 100
        ((h, _),), htid = await hall(w, "h")
        q, _ = w.queuer("q")
        await w.t.queue(q, BASE)
        q2, _ = w.queuer("q")
        await w.t.hello(q2)
        assert counts(w) == counted(ddz_ask=3, ddz_ask_decline=1, ddz_ask_timeout=1)
        w.mono += CFG["inviteSec"]
        await w.timers.fire()
        assert counts(w) == counted(ddz_ask=3, ddz_ask_decline=1, ddz_ask_timeout=2)
        e, _ = w.queuer("e")
        await w.t.queue(e, BASE)
        await w.bye(e)
        assert counts(w) == counted(ddz_ask=4, ddz_ask_decline=2, ddz_ask_timeout=2)
    run(go())


def test_games_are_counted_by_their_kind_of_table():
    async def go():
        w = OpenWorld()
        # Invited, in a room.
        x, _ = w.member("x")
        y, _ = w.member("y")
        z, _ = w.member("z")
        await w.t.invite("r", x, [y.id, z.id], BASE)
        tid = w.t.by_save[w.who["x"]].id
        await w.t.answer(y, tid, True)
        await w.t.answer(z, tid, True)
        await w.settled()
        # A room's open table, a stranger from the hall among its seats.
        _, otid = await w.opened("o1", "o2")
        h, _ = w.queuer("h")
        await w.t.hall_sit(h, otid)
        await w.settled()
        # The queue.
        out = [w.queuer(n) for n in "abc"]
        for p, _ in out:
            await w.t.queue(p, 50)
        await w.t.idle()
        mtid = out[0][1].of("ddz_invite")[-1]["table"]
        for p, _ in out:
            await w.t.answer(p, mtid, True)
        await w.settled()
        assert w.t.by_id[mtid].match and not w.t.by_id[otid].match and not w.t.by_id[tid].match
        assert counts(w) == counted(ddz_ask=1, ddz_start_invite=1, ddz_start_open=1, ddz_start_match=1)
    run(go())


# ------------------------------------------------------------------ paying a game
def test_a_payment_that_fails_is_tried_again_for_the_same_game_and_the_seats_wait_for_it(monkeypatch):
    import sqlite3

    async def go():
        w = OpenWorld()
        out, tid = await hall_game(w, "a", "b", "c")
        t = w.t.by_id[tid]
        before = [w.shards(s.token) for s in t.seats]
        socks = [sock for _, sock in out]
        real = w.g.store.set_ddz_deltas
        fails = [2]

        def flaky(*args):
            if fails[0]:
                fails[0] -= 1
                raise sqlite3.OperationalError("database is locked")
            return real(*args)

        monkeypatch.setattr(w.g.store, "set_ddz_deltas", flaky)
        await play_to_end(w, tid)
        # Unpaid: the seats stay held, nobody hears a result, and the game is open in the database.
        assert t.phase == "settling" and t.timer is not None and t.outcome is not None
        assert all(w.t.by_save[s.token] is t for s in t.seats)
        assert not any(sock.of("ddz_result") for sock in socks)
        assert w.g.store.ddz_game(t.row)["state"] == "open"
        assert [w.shards(s.token) for s in t.seats] == before
        await w.timers.fire()
        assert t.phase == "settling" and t.timer is not None
        await w.timers.fire()
        await settle()
        # Paid once, then told.
        assert t.phase == "over" and w.g.store.ddz_game(t.row)["state"] == "settled"
        result = socks[0].of("ddz_result")
        assert len(result) == 1 and all(len(sock.of("ddz_result")) == 1 for sock in socks)
        assert [w.shards(s.token) for s in t.seats] == [n + DEPOSIT + d for n, d in zip(before, result[0]["deltas"])]
        assert w.t.bank.settle(t.row, 0, True, 1) is None
        assert w.t.bank.refund_open() == 0

    run(asyncio.wait_for(go(), 10))


def test_a_payment_given_up_with_the_tables_cleared_leaves_the_game_open():
    async def go():
        w = OpenWorld()
        _, tid = await hall_game(w, "a", "b", "c")
        t = w.t.by_id[tid]

        def fail(*args):
            raise RuntimeError("database gone")

        w.g.store.set_ddz_deltas = fail
        await play_to_end(w, tid)
        assert t.phase == "settling" and t.timer is not None
        w.t.clear()
        assert t.timer is None and not w.t.by_save
        await w.timers.fire()
        assert w.g.store.ddz_game(t.row)["state"] == "open"

    run(asyncio.wait_for(go(), 10))


# ------------------------------------------------------------------ a room's bans and the queue
def test_an_empty_seat_is_not_offered_to_a_save_the_room_bans_which_keeps_its_place_in_the_line():
    async def go():
        w = OpenWorld()
        ((x, _),), rtid = await w.opened("x")
        b, sb = w.queuer("b")
        c, sc = w.queuer("c")
        w.m.rooms["r"].banned.add(w.who["b"])
        await w.t.queue(b, BASE)
        w.mono += QUEUE_INTERVAL
        await w.t.queue(c, BASE)
        w.mono += FILL_SEC
        await w.timers.fire()
        t = w.t.by_id[rtid]
        # The seat goes to the next in the line; the banned save still waits, first.
        assert not sb.of("ddz_invite") and sc.of("ddz_invite")[-1]["table"] == rtid
        assert w.t.by_save.get(w.who["b"]) is None and w.t.by_save[w.who["c"]] is t
        assert [q.token for q in w.t.lines[BASE]] == [w.who["b"]]
        await w.t.idle()

    run(asyncio.wait_for(go(), 10))


def test_a_save_the_room_bans_after_its_seat_was_offered_goes_back_to_its_place_in_the_line():
    async def go():
        w = OpenWorld()
        ((x, _),), rtid = await w.opened("x")
        b, sb = w.queuer("b")
        w.mono += FILL_SEC
        await w.t.queue(b, BASE)
        t = w.t.by_id[rtid]
        assert w.t.by_save[w.who["b"]] is t and sb.of("ddz_invite")[-1]["table"] == rtid
        since = t.seats[1].since
        w.m.rooms["r"].banned.add(w.who["b"])
        await w.t.answer(b, rtid, True)
        assert sb.of("ddz_over")[-1] == {"type": "ddz_over", "table": rtid, "reason": "gone"}
        assert w.t.by_save.get(w.who["b"]) is None and all(s.token != w.who["b"] for s in t.seats)
        # Back in the line where it was, with no cooldown, and told it waits.
        assert w.t.waiting[w.who["b"]].since == since and w.who["b"] not in w.t.match_refused
        assert sb.of("ddz_queue")[-1]["base"] == BASE
        # Another save in the line gets the seat.
        c, sc = w.queuer("c")
        w.mono += QUEUE_INTERVAL
        await w.t.queue(c, BASE)
        assert sc.of("ddz_invite")[-1]["table"] == rtid and w.t.by_save.get(w.who["b"]) is None
        await w.t.idle()

    run(asyncio.wait_for(go(), 10))
