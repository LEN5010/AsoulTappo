"""Watching dou dizhu games: who may watch which table, the one hand a watcher sees, what it hears, and when it ends."""
import asyncio

import pytest

from app.ddz import COUNTS_SEC, QUEUE_INTERVAL, WATCH_INTERVAL, WATCH_MAX
from test_ddz import BASE, CFG, api, joined, save, tok  # noqa: F401
from test_ddz_match import receive
from test_ddz_open import OpenWorld

SNAPSHOT_KEYS = {"type", "table", "seat", "hand", "phase", "seats", "base", "cap", "deal", "bid", "landlord", "bottom",
                 "mult", "bombs", "turn", "lead", "trick", "sec", "of", "result"}
DEAL_KEYS = {"type", "table", "seats", "hand", "base", "cap", "deal", "turn", "sec", "dealSec", "watch"}


class WatchWorld(OpenWorld):
    """Members in room r on clients that open tables and watch games, unless told otherwise."""

    def member(self, name, room="r", match=True, watch=True, **kw):
        peer, sock = super().member(name, room=room, match=match, **kw)
        peer.ddz_watch = watch and match
        return peer, sock

    def queuer(self, name, watch=True, **kw):
        peer, sock = super().queuer(name, **kw)
        peer.ddz_watch = watch
        return peer, sock

    async def game(self, *names, old=()):
        """[names] open and fill a table in room r and the cards are dealt; members named in [old] are on clients
        that do not watch. Returns the members and the table."""
        out = [self.member(n, watch=n not in old) for n in names]
        await self.t.open("r", out[0][0], BASE)
        tid = out[0][1].of("ddz_open")[-1]["table"]
        for peer, _ in out[1:]:
            self.mono += QUEUE_INTERVAL
            await self.t.sit("r", peer, tid)
        await self.settled()
        return out, self.t.by_id[tid]

    def watch(self, peer, table, seat=0):
        """[peer] asks to watch [table] from [seat], a second after its last ask."""
        self.mono += WATCH_INTERVAL
        self.t.watch(peer, table if isinstance(table, str) else table.id, seat)

    async def bid(self, table, bid=3):
        await self.t.bid(table.seats[table.turn].peer, table.id, bid)

    async def play_out(self, table):
        """The landlord bids 3; each seat leads its lowest card and passes otherwise, until someone is out of cards."""
        if table.phase == "bid":
            await self.bid(table)
        while table.phase == "play":
            s = table.seats[table.turn]
            await self.t.play(s.peer, table.id, [] if table.last is not None else [s.hand[0]])
        await self.settled()


def run(coro):
    return asyncio.run(coro)


def code_of(fn, *a):
    with pytest.raises(Exception) as e:
        fn(*a)
    return getattr(e.value, "code", None)


def keys_in(x):
    """Every dict key anywhere in [x]."""
    if isinstance(x, dict):
        return set(x) | set().union(*(keys_in(v) for v in x.values()))
    if isinstance(x, list):
        return set().union(*(keys_in(v) for v in x)) if x else set()
    return set()


def card_lists(x):
    """Every list of ints anywhere in [x]."""
    if isinstance(x, dict):
        return [lst for v in x.values() for lst in card_lists(v)]
    if isinstance(x, list):
        if x and all(isinstance(v, int) and not isinstance(v, bool) for v in x):
            return [x]
        return [lst for v in x for lst in card_lists(v)]
    return []


def leaked(msgs, hands, bottom, view):
    """The cards of hands a watcher may not see (all but [view]'s; all three when [view] is None) and of the bottom
    before the landlord takes it, that reach it in [msgs] before the result: none may, in any list of any message of
    a table."""
    hidden = set(bottom).union(*(set(h) for i, h in enumerate(hands) if i != view))
    out = []
    # The messages of a table (the queue's waiting counts, [[base, saves], ...], are not cards).
    for m in (m for m in msgs if "table" in m):
        if m["type"] == "ddz_result":
            break
        if m["type"] == "ddz_play":
            hidden -= set(m["cards"])
        if m["type"] == "ddz_landlord":
            hidden -= set(m["bottom"])
        for lst in card_lists(m):
            out += [c for c in lst if c in hidden]
    return out


def since(sock, n):
    return sock.got[n:]


# ------------------------------------------------------------------ the one hand a watcher sees
def test_a_watcher_sees_the_hand_of_its_seat_and_nothing_of_the_others():
    async def go():
        w = WatchWorld()
        # a holds games of the card counter: its counter comes on once the landlord is known.
        w.who["a"] = save(w.g, "a")
        w.g.store.update_player(w.who["a"], ddz_counter=5)
        ((a, sa), (b, sb), (c, sc)), t = await w.game("a", "b", "c")
        v, sv = w.member("v")
        hands, bottom = [list(s.hand) for s in t.seats], list(t.bottom)
        w.watch(v, t, 1)
        snap = sv.of("ddz_watch")[0]
        assert set(snap) == SNAPSHOT_KEYS
        assert snap["table"] == t.id and snap["seat"] == 1 and snap["hand"] == hands[1] and snap["phase"] == "bid"
        assert snap["bottom"] == [] and snap["result"] is None and snap["cap"] == CFG["capMult"]
        assert snap["seats"] == [{"id": p.id, "nick": p.nick, "character": p.character, "left": 17, "bid": None,
                                  "auto": False, "away": False, "again": False} for p in (a, b, c)]
        await w.play_out(t)
        msgs = sv.got
        assert leaked(msgs, hands, bottom, 1) == []
        assert not {"you", "played", "counter"} & keys_in(msgs)
        # Everything public reached it, marked as watched; the counter the seats turned on did not.
        kinds = {m["type"] for m in msgs}
        assert {"ddz_bid", "ddz_landlord", "ddz_play", "ddz_result"} <= kinds and "ddz_counter" not in kinds
        assert all(m.get("watch") is True for m in msgs if m["type"] in ("ddz_bid", "ddz_landlord", "ddz_play",
                                                                          "ddz_result"))
        assert sa.of("ddz_counter") and not any(m.get("watch") for m in sa.got)
        result = {k: v for k, v in sv.of("ddz_result")[0].items() if k != "watch"}
        assert result == sa.of("ddz_result")[0]
        # Watching from the result on shows it whole.
        w.watch(v, t, 2)
        snap = sv.of("ddz_watch")[-1]
        assert snap["phase"] == "over" and snap["result"] == sa.of("ddz_result")[0]
        assert snap["hand"] == t.seats[2].hand
    run(go())


def test_another_seat_brings_its_hand_and_asks_are_held_to_one_a_second():
    async def go():
        w = WatchWorld()
        _, t = await w.game("a", "b", "c")
        v, sv = w.member("v")
        w.watch(v, t, 0)
        assert code_of(w.t.watch, v, t.id, 2) == "rate_limited"
        assert t.watchers[v.id][1] == 0
        w.watch(v, t, 2)
        assert [m["seat"] for m in sv.of("ddz_watch")] == [0, 2]
        assert sv.of("ddz_watch")[-1]["hand"] == t.seats[2].hand and t.watchers[v.id][1] == 2
        assert len(t.watchers) == 1
        # Stopping is never held up, and is told nothing.
        n = len(sv.got)
        w.t.watch(v, "", 0)
        assert v.watching is None and t.watchers == {} and [m["type"] for m in since(sv, n)] == []
    run(go())


def test_a_dealt_game_comes_to_each_watcher_with_its_seat_hand_and_another_game_keeps_the_seat():
    async def go():
        w = WatchWorld()
        ((a, sa), _, _), t = await w.game("a", "b", "c")
        v, sv = w.member("v")
        w.watch(v, t, 1)
        await w.play_out(t)
        for s in t.seats:
            await w.t.again(s.peer, t.id)
        await w.settled()
        assert t.phase == "bid" and t.watchers[v.id][1] == 1
        deal = sv.of("ddz_deal")[-1]
        assert set(deal) == DEAL_KEYS and deal["watch"] is True and deal["hand"] == t.seats[1].hand
        mine = sa.of("ddz_deal")[-1]
        assert deal["seats"] == mine["seats"] and deal["turn"] == mine["turn"] and "counter" in mine
        assert sv.of("ddz_again") and all(m["watch"] for m in sv.of("ddz_again"))
        n = sv.got.index(deal)
        hands, bottom = [list(s.hand) for s in t.seats], list(t.bottom)
        await w.play_out(t)
        assert leaked(since(sv, n), hands, bottom, 1) == []
        assert not {"you", "played", "counter"} & keys_in(sv.got)
    run(go())


# ------------------------------------------------------------------ hands not shown, member ids
def test_at_a_table_the_queue_made_only_the_seats_of_the_watchers_room_on_clients_that_watch_are_shown():
    async def go():
        w = WatchWorld()
        qs = [w.queuer(n, watch=n != "c") for n in "abc"]
        for p, _ in qs:
            await w.t.queue(p, BASE)
        await w.t.idle()
        tid = qs[0][1].of("ddz_invite")[0]["table"]
        for p, _ in qs:
            await w.t.answer(p, tid, True)
        await w.settled()
        t = w.t.by_id[tid]
        # a and c (an old client) are in room r on room connections; b is not.
        a_room, _ = w.member("a")
        w.member("c", watch=False)
        v, sv = w.member("v")
        await w.t.joined("r", v)
        hands = [list(s.hand) for s in t.seats]
        w.watch(v, t, 0)
        snap = sv.of("ddz_watch")[-1]
        assert snap["hand"] == hands[0]
        # The seats by the room's member ids: a by its room connection, b (not in the room) by its own.
        assert [s["id"] for s in snap["seats"]] == [a_room.id, qs[1][0].id, w.t._ids_in(w.m.rooms["r"], t)[2]]
        assert snap["seats"][0]["id"] != t.seats[0].id
        for seat in (1, 2):
            w.watch(v, t, seat)
            assert sv.of("ddz_watch")[-1]["hand"] is None
        w.mono += COUNTS_SEC
        await w.counts.fire()
        assert sv.of("ddz_watchers")[-1]["faces"] == [{"nick": "v", "character": v.character, "seat": None}]
        assert leaked(sv.got, hands, t.bottom, 0) == []
        # A seat's connection closing: the watcher hears of it by its room's member id.
        await w.bye(qs[0][0])
        said = [m for m in sv.of("ddz_seat") if m["seat"] == 0][-1]
        assert said["id"] == a_room.id and said["away"] is True and said["watch"] is True
        assert [m for m in qs[1][1].of("ddz_seat") if m["seat"] == 0][-1]["id"] == qs[0][0].id
    run(go())


def test_the_deal_of_a_table_the_queue_made_hides_the_seat_outside_the_room():
    async def go():
        w = WatchWorld()
        qs = [w.queuer(n) for n in "abc"]
        for p, _ in qs:
            await w.t.queue(p, BASE)
        await w.t.idle()
        tid = qs[0][1].of("ddz_invite")[0]["table"]
        a_room, _ = w.member("a")
        v, sv = w.member("v")
        for p, _ in qs:
            await w.t.answer(p, tid, True)
        await w.settled()
        m = w.t.by_id[tid]
        # Dealt before anyone watched: watch, then another game of the same three brings a deal.
        w.watch(v, m, 1)
        assert sv.of("ddz_watch")[-1]["hand"] is None
        w.watch(v, m, 0)
        await w.play_out(m)
        for s in m.seats:
            await w.t.again(s.peer, m.id)
        await w.settled()
        deal = sv.of("ddz_deal")[-1]
        assert deal["hand"] == m.seats[0].hand and deal["seats"][0]["id"] == a_room.id
        assert deal["seats"][1]["id"] == qs[1][0].id
    run(go())


# ------------------------------------------------------------------ who may watch what
@pytest.mark.parametrize("how, code", [
    ("open", None), ("invite", None), ("match_in", None), ("match_out", "ddz_gone"), ("elsewhere", "ddz_gone"),
    ("seated", "ddz_busy"), ("playing", "ddz_busy"), ("queued", None), ("waiting", None), ("guest", None),
    ("starting", "ddz_gone"), ("inviting", "ddz_gone"), ("opened", "ddz_gone"), ("nothing", "ddz_gone"),
])
def test_who_may_watch_which_table(how, code):
    async def go():
        w = WatchWorld()
        if how in ("match_in", "match_out"):
            qs = [w.queuer(n) for n in "abc"]
            for p, _ in qs:
                await w.t.queue(p, BASE)
            await w.t.idle()
            tid = qs[0][1].of("ddz_invite")[0]["table"]
            for p, _ in qs:
                await w.t.answer(p, tid, True)
            await w.settled()
            if how == "match_in":
                w.member("b")
        elif how == "invite":
            peers = [w.member(n)[0] for n in "abc"]
            await w.t.invite("r", peers[0], [peers[1].id, peers[2].id], BASE)
            tid = w.t.by_save[w.who["a"]].id
            for p in peers[1:]:
                await w.t.answer(p, tid, True)
            await w.settled()
        elif how == "elsewhere":
            out = [w.member(n, room="r2") for n in "abc"]
            await w.t.open("r2", out[0][0], BASE)
            tid = w.t.by_save[w.who["a"]].id
            for p, _ in out[1:]:
                w.mono += QUEUE_INTERVAL
                await w.t.sit("r2", p, tid)
            await w.settled()
        elif how == "starting":
            _, tid = await w.opened("a", "b")
            c, _ = w.member("c")
            await w.t.sit("r", c, tid)
            assert w.t.by_id[tid].phase == "starting"
        elif how == "inviting":
            peers = [w.member(n)[0] for n in "abc"]
            await w.t.invite("r", peers[0], [peers[1].id, peers[2].id], BASE)
            tid = w.t.by_save[w.who["a"]].id
        elif how == "opened":
            _, tid = await w.opened("a", "b")
        elif how == "nothing":
            tid = "nope"
        else:
            _, t = await w.game("a", "b", "c")
            tid = t.id
        if how == "seated":
            v, _ = w.member("a")  # another room connection of a seated save
        elif how == "guest":
            v, _ = w.join("guest", None, room="r")
            v.ddz_match = v.ddz_watch = True
        else:
            v, _ = w.member("v")
        if how == "playing":
            await w.game("v", "x", "y")  # on another connection of the save
        if how == "queued":
            q, _ = w.queuer("v")
            await w.t.queue(q, 50)
        if how == "waiting":
            w.mono += QUEUE_INTERVAL
            await w.t.open("r", v, 50)
        if code is None:
            w.watch(v, tid, 1)
            assert v.watching == tid and w.t.by_id[tid].watchers[v.id] == (v, 1)
        else:
            w.mono += WATCH_INTERVAL
            assert code_of(w.t.watch, v, tid, 1) == code
            assert v.watching is None
            if tid in w.t.by_id:
                assert w.t.by_id[tid].watchers == {}
    run(go())


def test_a_refused_ask_leaves_what_the_connection_watched():
    async def go():
        w = WatchWorld()
        _, t = await w.game("a", "b", "c")
        _, t2 = await w.game("d", "e", "f", )
        v, _ = w.member("v")
        w.watch(v, t, 0)
        w.mono += WATCH_INTERVAL
        assert code_of(w.t.watch, v, "nope", 0) == "ddz_gone"
        assert v.watching == t.id and v.id in t.watchers
        w.watch(v, t2, 2)
        assert v.watching == t2.id and v.id not in t.watchers and t2.watchers[v.id][1] == 2
    run(go())


def test_a_table_takes_twenty_watchers_and_one_moving_to_another_seat_is_not_a_new_one():
    async def go():
        w = WatchWorld()
        w.m.max_size = 50
        _, t = await w.game("a", "b", "c")
        many = [w.member(f"v{i}")[0] for i in range(WATCH_MAX)]
        for v in many:
            w.watch(v, t, 0)
        late, _ = w.member("late")
        w.mono += WATCH_INTERVAL
        assert code_of(w.t.watch, late, t.id, 0) == "ddz_watch_full"
        w.watch(many[0], t, 2)
        assert len(t.watchers) == WATCH_MAX and t.watchers[many[0].id][1] == 2
        w.t.watch(many[1], "", 0)
        w.watch(late, t, 0)
        assert late.id in t.watchers
    run(go())


# ------------------------------------------------------------------ when watching ends
@pytest.mark.parametrize("how, reason", [
    ("closed", "closed"), ("reopen", "reopen"), ("gone", "gone"), ("nobid", "gone"), ("playing", "playing"),
    ("left", None), ("stopped", None),
])
def test_when_watching_ends(how, reason):
    async def go():
        w = WatchWorld()
        ((a, sa), (b, sb), (c, sc)), t = await w.game("a", "b", "c")
        v, sv = w.member("v")
        w.watch(v, t, 0)
        if how in ("closed", "reopen"):
            await w.play_out(t)
            if how == "closed":
                await w.t.leave(a, t.id)  # the opener leaving after the game closes the table
            else:
                await w.t.again(a, t.id)
                await w.t.again(b, t.id)
                await w.t.leave(c, t.id)
                assert t.phase == "open"
        elif how == "gone":
            for p in (a, b, c):
                await w.m.depart("r", p.id)
            await w.settled()
        elif how == "nobid":
            for _ in range(3):
                for _ in range(3):
                    await w.bid(t, 0)
            await w.settled()
        elif how == "playing":
            x, sx = w.member("x")
            y, _ = w.member("y")
            w.mono += QUEUE_INTERVAL
            await w.t.open("r", x, 50)
            t2 = w.t.by_save[w.who["x"]]
            for p in (y, v):
                w.mono += QUEUE_INTERVAL
                await w.t.sit("r", p, t2.id)
            await w.settled()
            kinds = [m["type"] for m in sv.got]
            # Told before its own deal.
            assert kinds.index("ddz_watch_end") < len(kinds) - 1 - kinds[::-1].index("ddz_deal")
        elif how == "left":
            await w.m.depart("r", v.id)
        else:
            w.t.watch(v, "", 0)
        ends = sv.of("ddz_watch_end")
        assert ends == ([{"type": "ddz_watch_end", "table": t.id, "reason": reason}] if reason else [])
        assert v.watching is None and t.watchers == {}
        # Nothing more of the table reaches it.
        n = len(sv.got)
        if t.id in w.t.by_id and t.phase in ("bid", "play"):
            w.t.auto(t.seats[t.turn].peer, t.id, True)
            await w.settled()
        assert [m for m in since(sv, n) if m.get("table") == t.id] == []
    run(go())


def test_clearing_the_tables_lets_the_watchers_go_without_a_word():
    async def go():
        w = WatchWorld()
        _, t = await w.game("a", "b", "c")
        v, sv = w.member("v")
        w.watch(v, t, 0)
        w.t.clear()
        assert v.watching is None and t.watchers == {} and sv.of("ddz_watch_end") == []
    run(go())


# ------------------------------------------------------------------ who watches
def test_the_seats_that_show_watchers_and_the_watchers_hear_who_watches_at_most_once_a_second():
    async def go():
        w = WatchWorld()
        ((a, sa), (b, sb), (c, sc)), t = await w.game("a", "b", "c", old=("c",))
        v1, s1 = w.member("v1")
        v2, s2 = w.member("v2")
        w.watch(v1, t, 0)
        want = {"type": "ddz_watchers", "table": t.id, "faces": [{"nick": "v1", "character": v1.character,
                                                                  "seat": 0}]}
        assert sa.of("ddz_watchers") == [want] and sb.of("ddz_watchers") == [want] and s1.of("ddz_watchers") == [want]
        # A seat whose client does not show watchers hears nothing, and its hand is not shown.
        assert sc.of("ddz_watchers") == []
        w.mono += WATCH_INTERVAL / 2
        w.t.watch(v2, t.id, 2)
        assert s2.of("ddz_watch")[-1]["hand"] is None
        assert len(sa.of("ddz_watchers")) == 1 and s2.of("ddz_watchers") == []
        w.mono += COUNTS_SEC
        await w.counts.fire()
        faces = [{"nick": "v1", "character": v1.character, "seat": 0},
                 {"nick": "v2", "character": v2.character, "seat": None}]
        assert [m["faces"] for m in sa.of("ddz_watchers")] == [want["faces"], faces]
        assert s2.of("ddz_watchers")[-1]["faces"] == faces and s1.of("ddz_watchers")[-1]["faces"] == faces
        # Moving to another seat's hand changes the list; the last to go leaves it empty.
        w.watch(v2, t, 1)
        await w.counts.fire()
        assert sa.of("ddz_watchers")[-1]["faces"][1]["seat"] == 1
        w.t.watch(v1, "", 0)
        await w.m.depart("r", v2.id)
        w.mono += COUNTS_SEC
        await w.counts.fire()
        assert sa.of("ddz_watchers")[-1]["faces"] == [] and sb.of("ddz_watchers")[-1]["faces"] == []
        assert sc.of("ddz_watchers") == []
        # Nothing changes, nothing is sent.
        n = len(sa.of("ddz_watchers"))
        w.mono += COUNTS_SEC
        await w.t.joined("r", w.member("n")[0])
        await w.counts.fire()
        assert len(sa.of("ddz_watchers")) == n
    run(go())


def test_a_watcher_back_within_the_second_hears_who_watches_and_a_seat_taken_again_hears_it_at_once():
    async def go():
        w = WatchWorld()
        ((a, sa), _, _), t = await w.game("a", "b", "c")
        v, sv = w.member("v")
        w.watch(v, t, 0)
        w.t.watch(v, "", 0)
        w.watch(v, t, 0)
        w.mono += COUNTS_SEC
        await w.counts.fire()
        # The list did not change meanwhile, but it comes again to the watcher back.
        assert [m["faces"] for m in sv.of("ddz_watchers")] == [[{"nick": "v", "character": v.character, "seat": 0}]] * 2
        # a's connection goes and a new one takes the seat again: after its state, who watches.
        await w.m.depart("r", a.id)
        a2, sa2 = w.member("a")
        await w.t.joined("r", a2)
        kinds = [m["type"] for m in sa2.got]
        assert kinds.index("ddz_watchers") > kinds.index("ddz_state")
        assert sa2.of("ddz_watchers")[-1]["faces"] == [{"nick": "v", "character": v.character, "seat": 0}]
        assert sv.of("ddz_watch")[-1]["hand"] == t.seats[0].hand
        # The seat's member, back on a client that does not show watchers, no longer shows its hand.
        await w.m.depart("r", a2.id)
        a3, sa3 = w.member("a", watch=False)
        await w.t.joined("r", a3)
        w.mono += COUNTS_SEC
        await w.counts.fire()
        assert sa3.of("ddz_watchers") == [] and not t.seats[0].watchable
        assert sv.of("ddz_watchers")[-1]["faces"] == [{"nick": "v", "character": v.character, "seat": None}]
        said = [m for m in sv.of("ddz_seat") if m["seat"] == 0][-1]
        assert said["id"] == a3.id and said["away"] is False and said["watch"] is True
    run(go())


def test_watchers_nicks_follow_the_blocklist_and_emotes_reach_watchers():
    async def go():
        w = WatchWorld()
        ((a, sa), _, _), t = await w.game("a", "b", "c")
        v, sv = w.member("v")
        w.watch(v, t, 0)
        v.nick = "*"
        w.mono += COUNTS_SEC
        w.t.remask(lambda x: x)
        assert sa.of("ddz_watchers")[-1]["faces"][0]["nick"] == "*"
        w.t.emote(a, t.id, "wave")
        assert sv.of("ddz_emote") == [{"type": "ddz_emote", "table": t.id, "seat": 0, "emote": "wave", "watch": True}]
        with pytest.raises(ValueError):
            w.t._show(t, {"type": "ddz_counter", "table": t.id})
    run(go())


def test_watchers_do_not_count_as_seated():
    async def go():
        w = WatchWorld()
        _, t = await w.game("a", "b", "c")
        v, _ = w.member("v")
        w.watch(v, t, 0)
        assert w.who["v"] not in w.t.by_save and not w.t.in_game(v)
        w.mono += QUEUE_INTERVAL
        await w.t.open("r", v, 50)
        assert w.t.by_save[w.who["v"]].phase == "open" and v.watching == t.id
    run(go())


# ------------------------------------------------------------------ over the socket
def test_watching_over_the_socket(api):  # noqa: F811
    c, g, timers = api
    for name in ("a", "b", "d", "v", "old"):
        save(g, name)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as d, \
            c.websocket_connect("/ws") as v, c.websocket_connect("/ws") as o, c.websocket_connect("/ws") as q:
        ja, _, _, jv = [joined(ws, n, "r1", motionVersion=3, ddzMatch=True, ddzWatch=True)
                        for ws, n in ((a, "a"), (b, "b"), (d, "d"), (v, "v"))]
        jo = joined(o, "old", "r1", motionVersion=3, ddzMatch=True)
        assert "ddz_watch" in ja["features"] and "ddz_watch" in jv["features"] and "ddz_watch" not in jo["features"]
        a.send_json({"type": "ddz_open", "base": BASE})
        tid = receive(a, "ddz_open")["table"]
        b.send_json({"type": "ddz_sit", "table": tid})
        receive(b, "ddz_open")
        d.send_json({"type": "ddz_sit", "table": tid})
        hand = receive(b, "ddz_deal")["hand"]
        # A client that did not say ddzWatch, a seat out of range, a dou dizhu connection.
        o.send_json({"type": "ddz_watch", "table": tid})
        assert receive(o, "error")["code"] == "bad_message"
        v.send_json({"type": "ddz_watch", "table": tid, "seat": 3})
        assert receive(v, "error")["code"] == "bad_message"
        q.send_json({"type": "ddz_hello", "nick": "old", "token": tok("old"), "ddzWatch": True})
        receive(q, "ddz_ready")
        q.send_json({"type": "ddz_watch", "table": tid})
        assert receive(q, "error")["code"] == "not_joined"
        v.send_json({"type": "ddz_watch", "table": tid, "seat": 1})
        snap = receive(v, "ddz_watch")
        assert snap["seat"] == 1 and snap["hand"] == hand
        v.send_json({"type": "ddz_watch", "table": tid, "seat": 2})
        assert receive(v, "error")["code"] == "rate_limited"
        assert receive(b, "ddz_watchers")["faces"] == [{"nick": "v", "character": "嘉然", "seat": 1}]
        v.send_json({"type": "ddz_watch", "table": ""})
        v.send_json({"type": "ping"})
        while (m := v.receive_json())["type"] != "pong":
            assert m["type"] not in ("error", "ddz_watch", "ddz_watch_end")
