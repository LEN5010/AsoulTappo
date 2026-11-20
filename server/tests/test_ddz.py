"""Dou dizhu in rooms: who may sit down, invites, bidding, plays, autopilot, payment, and paying once."""
import asyncio
import copy
import random

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import ddz_rules as rules
from app.ddz import AUTO_AFTER, AUTO_SEC, DEAL_SEC, MAX_DEALS, RETRY_SEC, Bank, Tables
from app.game import Game, GameError, PlayerId, player_id_for
from app.manifest import Manifest
from app.rooms import RoomManager
from app.store import Store
from fixtures import Clock, SeqRng
from test_ddz_rules import cards_of
from test_duel import ManualTimers, Sock, settle

M = Manifest.load()
CFG = M.ddz
SHARDS = 100_000
BASE = 250
DEPOSIT = BASE * CFG["capMult"] * 2


def test_the_example_numbers():
    assert CFG == {"stakes": [50, 250, 500], "capMult": 24, "rake": 10, "inviteSec": 15, "bidSec": 15,
                   "playSec": 30, "againSec": 30, "dailyWinCap": 50000, "minTaps": 10000}


# ------------------------------------------------------------------ helpers
def save(g, name, taps=10_000, shards=SHARDS):
    pid = PlayerId(player_id_for(f"{name}-ddz-token-0001"))
    g.store.get_player(pid, g.now())
    g.store.update_player(pid, taps_total=taps, shards=shards)
    return pid


class Stacked(random.Random):
    """Deals a deck the test lays out: shuffle() puts [deck] in place, randrange() answers [first]."""

    def __init__(self, deck=None, first=0):
        super().__init__(1)
        self.deck, self.first = deck, first

    def shuffle(self, x):
        if self.deck is None:
            super().shuffle(x)
        else:
            x[:] = self.deck

    def randrange(self, *a):
        return self.first


def deck_of(*hands, bottom=None):
    """A deck whose three hands start with [hands] (ranks), padded with what is left, lowest first."""
    used = []
    picked = []
    for h in hands:
        cards = []
        for r in h:
            c = next(c for c in rules.DECK if rules.rank(c) == r and c not in used)
            used.append(c)
            cards.append(c)
        picked.append(cards)
    low = [c for c in rules.DECK if c not in used]
    tail = []
    for r in bottom or []:
        c = next(c for c in low if rules.rank(c) == r)
        low.remove(c)
        tail.append(c)
    deck = []
    for cards in picked:
        need = 17 - len(cards)
        deck += cards + low[:need]
        low = low[need:]
    return deck + low[:3 - len(tail)] + tail


class World:
    def __init__(self, manifest=None, rng=None):
        self.clock = Clock()
        self.g = Game(Store(":memory:"), manifest or Manifest.load(), rng=SeqRng(.5), now=self.clock)
        self.m = RoomManager()
        self.timers = ManualTimers()
        self.mono = 1000.0
        self.rng = rng or Stacked()
        self.t = Tables(lambda: self.g, lambda: self.m, timers=self.timers, clock=lambda: self.mono, rng=self.rng)
        self.m.on_depart = self.t.departed
        self.bank = Bank(self.g)

    def join(self, nick, pid=None, room="r", ddz=True):
        sock = Sock()
        peer = self.m.join(room, nick, "嘉然", sock, token=pid)
        peer.ddz = ddz
        # Heard at once, without the writer task: the tests read what was told right after telling it.
        peer.enqueue = lambda data, done=None: sock.got.append(data) if peer.active else None
        return peer, sock

    def shards(self, pid):
        return self.g.store.get_player(pid, self.clock.t)["shards"]

    def three(self, **kw):
        self.pids = [save(self.g, n, **kw) for n in "abc"]
        joined = [self.join(n, pid) for n, pid in zip("abc", self.pids)]
        self.peers = [p for p, _ in joined]
        self.socks = [s for _, s in joined]
        return self.peers, self.socks, self.pids

    async def invited(self, base=BASE, **kw):
        peers, socks, pids = self.three(**kw)
        await self.t.invite("r", peers[0], [peers[1].id, peers[2].id], base)
        await settle()
        return socks[0].of("ddz_invite")[0]["table"]

    async def dealt(self, base=BASE, **kw):
        tid = await self.invited(base, **kw)
        await self.t.answer(self.peers[1], tid, True)
        await self.t.answer(self.peers[2], tid, True)
        await settle()
        return tid

    async def playing(self, bids=(3,), **kw):
        """Dealt with seat `first` bidding [bids] in turn; returns the table id."""
        tid = await self.dealt(**kw)
        table = self.t.by_id[tid]
        for b in bids:
            await self.t.bid(self.peers[table.turn], tid, b)
        await settle()
        return tid

    def last(self, kind, seat=0):
        return self.socks[seat].of(kind)[-1]


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ the bank
def test_deposit_is_the_most_a_landlord_can_lose():
    bank = World().bank
    assert bank.deposit(250) == 250 * 24 * 2
    with pytest.raises(GameError) as e:
        bank.deposit(123)
    assert e.value.code == "bad_message"


def test_who_wins_what_and_what_is_burnt():
    bank = World().bank
    # The landlord (seat 1) wins at 6 times 100: 1200 less a tenth, the farmers lose 600 each.
    assert bank.deltas(100, 6, 1, True) == ([-600, 1080, -600], 120)
    # The farmers win: 600 less a tenth each, the landlord loses 1200.
    assert bank.deltas(100, 6, 1, False) == ([540, -1200, 540], 120)
    # The cut is rounded down, in the winners' favour.
    assert bank.deltas(10, 1, 0, False) == ([-20, 9, 9], 2)
    assert bank.deltas(15, 1, 0, True) == ([27, -15, -15], 3)


def test_start_takes_three_deposits_and_settle_pays_once():
    w = World()
    pids = [save(w.g, n) for n in "abc"]
    row = w.bank.start(pids, BASE)
    assert [w.shards(p) for p in pids] == [SHARDS - DEPOSIT] * 3
    assert w.bank.settle(row, 0, True, 6) == [2700, -1500, -1500]
    assert [w.shards(p) for p in pids] == [SHARDS + 2700, SHARDS - 1500, SHARDS - 1500]
    assert w.bank.settle(row, 0, True, 6) is None and not w.bank.refund(row)
    assert [w.shards(p) for p in pids] == [SHARDS + 2700, SHARDS - 1500, SHARDS - 1500]
    assert [w.bank.net(p) for p in pids] == [2700, -1500, -1500]
    day = w.g.store.ledger_amount
    from app.game import day_of
    today = day_of(w.clock.t)
    assert day(pids[0], today, "ddz_deposit") == -DEPOSIT and day(pids[0], today, "ddz_return") == DEPOSIT + 2700
    assert day(pids[1], today, "ddz_return") == DEPOSIT - 1500


def test_refund_hands_the_deposits_back_once():
    w = World()
    pids = [save(w.g, n) for n in "abc"]
    row = w.bank.start(pids, BASE)
    assert w.bank.refund(row) and not w.bank.refund(row) and w.bank.settle(row, 0, True, 1) is None
    assert [w.shards(p) for p in pids] == [SHARDS] * 3 and [w.bank.net(p) for p in pids] == [0, 0, 0]


def test_shard_anomalies_count_winnings_on_settlement_day_and_skip_deposits():
    from app.analytics import anomalies
    from app.store import day_of

    w = World()
    pids = [save(w.g, n) for n in "abc"]
    refunded = w.bank.start(pids, BASE)
    settled = w.bank.start(pids, BASE)
    yesterday = day_of(w.clock.t)
    w.clock.t += 86400
    w.bank.refund(refunded)
    assert w.bank.settle(settled, 0, True, 1) == [450, -250, -250]
    assert anomalies(w.g, yesterday)["shards"] == []
    assert anomalies(w.g, None)["shards"] == [
        {"player": pids[0], "userId": None, "gained": 450, "sources": {"ddz_win": 450}}
    ]


def test_games_a_restart_cut_short_are_refunded(tmp_path):
    path = str(tmp_path / "ddz.db")
    g = Game(Store(path), Manifest.load(), now=Clock())
    pids = [save(g, n) for n in "abc"]
    Bank(g).start(pids, BASE)
    done = Bank(g).start(pids, 50)
    Bank(g).settle(done, 2, False, 3)
    g.store.close()
    g = Game(Store(path), Manifest.load(), now=Clock())
    assert Bank(g).refund_open() == 1 and Bank(g).refund_open() == 0
    assert g.store.get_player(pids[0], g.now())["shards"] == SHARDS + 135


@pytest.mark.parametrize("seat, change, code", [
    (0, {"taps": 9_999}, "ddz_locked"), (1, {"taps": 9_999}, "ddz_target_locked"),
    (0, {"shards": DEPOSIT - 1}, "no_shards"), (2, {"shards": DEPOSIT - 1}, "ddz_target_poor"),
])
def test_who_may_sit_down(seat, change, code):
    w = World()
    pids = [save(w.g, n) for n in "abc"]
    w.g.store.update_player(pids[seat], **{"taps_total" if k == "taps" else k: v for k, v in change.items()})
    with pytest.raises(GameError) as e:
        w.bank.check(pids, BASE)
    assert e.value.code == code
    with pytest.raises(GameError):
        w.bank.start(pids, BASE)
    assert [w.shards(p) for p in pids] == [SHARDS if i != seat or "shards" not in change else DEPOSIT - 1
                                           for i, p in enumerate(pids)]


def test_a_save_that_won_the_days_cap_starts_no_more_games():
    w = World()
    pids = [save(w.g, n, shards=10_000_000) for n in "abc"]
    # 24 times 500 for the landlord: 21600 after the cut. Below the day's cap the next game still starts (the third
    # one too, at 43200); past it, none does.
    for _ in range(3):
        w.bank.settle(w.bank.start(pids, 500), 0, True, 24)
    assert w.bank.net(pids[0]) == 64800
    with pytest.raises(GameError) as e:
        w.bank.check(pids, 50)
    assert e.value.code == "ddz_cap"
    with pytest.raises(GameError) as e:
        w.bank.check([pids[1], pids[0], pids[2]], 50)
    assert e.value.code == "ddz_target_cap"
    w.clock.t += 86400
    assert w.bank.check(pids, 50) == 2400


def test_status_carries_the_days_net():
    w = World()
    pids = [save(w.g, n) for n in "abc"]
    w.bank.settle(w.bank.start(pids, BASE), 1, False, 2)
    assert w.g.status("a-ddz-token-0001")["ddz"] == {"net": 450}
    assert w.g.status("b-ddz-token-0001")["ddz"] == {"net": -1000}


# ------------------------------------------------------------------ invites
def test_an_invite_reaches_the_three_and_starts_when_both_accept():
    async def go():
        w = World()
        tid = await w.invited()
        a, b, c = w.peers
        invite = {"type": "ddz_invite", "table": tid, "from": a.id, "ids": [a.id, b.id, c.id], "base": BASE,
                  "deposit": DEPOSIT, "sec": CFG["inviteSec"]}
        assert [s.got for s in w.socks] == [[invite]] * 3
        assert [h.delay for h in w.timers.live()] == [CFG["inviteSec"]]
        await w.t.answer(b, tid, True)
        assert w.last("ddz_answer", 2) == {"type": "ddz_answer", "table": tid, "id": b.id}
        assert [w.shards(p) for p in w.pids] == [SHARDS] * 3
        with pytest.raises(GameError):
            await w.t.answer(b, tid, True)  # one answer a seat
        with pytest.raises(GameError):
            await w.t.answer(a, tid, True)  # the inviter has none to give
        await w.t.answer(c, tid, True)
        await settle()
        assert [w.shards(p) for p in w.pids] == [SHARDS - DEPOSIT] * 3
        deals = [w.last("ddz_deal", i) for i in range(3)]
        assert [d["you"] for d in deals] == [0, 1, 2] and all(len(d["hand"]) == 17 for d in deals)
        assert sorted(sum((d["hand"] for d in deals), []) + w.t.by_id[tid].bottom) == list(range(54))
        assert deals[0]["seats"] == [{"id": p.id, "nick": p.nick, "character": "嘉然", "auto": False, "away": False}
                                     for p in w.peers]
        assert (deals[0]["base"], deals[0]["cap"], deals[0]["deal"], deals[0]["sec"]) == (BASE, 24, 1, CFG["bidSec"])
        # The first bid's time starts once the clients have dealt the cards out.
        assert deals[0]["dealSec"] == DEAL_SEC
        assert [h.delay for h in w.timers.live()] == [DEAL_SEC + CFG["bidSec"]]
        assert all(w.t.in_game(p) for p in w.peers)
    run(go())


@pytest.mark.parametrize("how", ["declined", "timeout", "inviter_left", "invited_left", "taken_back"])
def test_an_invite_that_does_not_start_takes_nothing(how):
    async def go():
        w = World()
        tid = await w.invited()
        a, b, c = w.peers
        if how == "declined":
            await w.t.answer(b, tid, False)
            want = {"reason": "declined", "by": b.id}
        elif how == "timeout":
            await w.timers.fire()
            want = {"reason": "timeout"}
        elif how == "inviter_left":
            await w.m.depart("r", a.id)
            want = {"reason": "gone", "by": a.id}
        elif how == "invited_left":
            await w.m.depart("r", c.id)
            want = {"reason": "gone", "by": c.id}
        else:
            await w.t.leave(a, tid)
            want = {"reason": "gone", "by": a.id}
        await settle()
        heard = [s for s, p in zip(w.socks, w.peers) if p.active]
        assert all(s.of("ddz_over") == [{"type": "ddz_over", "table": tid, **want}] for s in heard)
        assert w.t.by_id == {} and w.t.by_save == {} and w.timers.live() == []
        assert [w.shards(p) for p in w.pids] == [SHARDS] * 3
    run(go())


def test_a_refusal_keeps_the_inviter_from_that_save_for_a_while():
    async def go():
        w = World()
        tid = await w.invited()
        a, b, c = w.peers
        await w.t.answer(b, tid, False)
        with pytest.raises(GameError) as e:
            await w.t.invite("r", a, [b.id, c.id], BASE)
        assert e.value.code == "ddz_cooldown"
        # The other way round is a new question.
        await w.t.invite("r", b, [a.id, c.id], BASE)
        w.t.clear()
        w.mono += RETRY_SEC
        await w.t.invite("r", a, [b.id, c.id], BASE)
    run(go())


def test_who_cannot_be_invited():
    async def go():
        w = World()
        peers, socks, pids = w.three()
        a, b, c = peers
        guest, _ = w.join("guest")
        old, _ = w.join("old", save(w.g, "old"), ddz=False)
        twin, _ = w.join("twin", pids[0])
        for ids, code in (([b.id, b.id], "ddz_self"), ([a.id, b.id], "ddz_self"), ([b.id, twin.id], "ddz_self"),
                          ([b.id, "nobody"], "no_member"), ([b.id, guest.id], "ddz_target_locked"),
                          ([b.id, old.id], "ddz_target_old")):
            with pytest.raises(GameError) as e:
                await w.t.invite("r", a, ids, BASE)
            assert e.value.code == code, ids
        with pytest.raises(GameError) as e:
            await w.t.invite("r", guest, [a.id, b.id], BASE)
        assert e.value.code == "ddz_locked"
        await w.t.invite("r", a, [b.id, c.id], BASE)
        d, _ = w.join("d", save(w.g, "d"))
        e2, _ = w.join("e", save(w.g, "e"))
        with pytest.raises(GameError) as e:
            await w.t.invite("r", d, [e2.id, c.id], BASE)
        assert e.value.code == "ddz_target_busy"
        with pytest.raises(GameError) as e:
            await w.t.invite("r", b, [d.id, e2.id], BASE)
        assert e.value.code == "ddz_busy"
    run(go())


def test_do_not_disturb_turns_the_invite_down_unseen():
    async def go():
        w = World()
        peers, socks, pids = w.three()
        a, b, c = peers
        c.dnd = True
        await w.t.invite("r", a, [b.id, c.id], BASE)
        assert [m["type"] for m in socks[0].got] == ["ddz_invite", "ddz_over"]
        assert socks[0].got[-1]["reason"] == "declined" and socks[1].got == [] and socks[2].got == []
        assert w.t.by_save == {}
        c.dnd = False
        w.t.refused.clear()
        await w.t.invite("r", a, [b.id, c.id], BASE)
        w.t.set_dnd(c, True)
        assert w.last("ddz_over", 1)["by"] == c.id and w.t.by_save == {}
    run(go())


def test_a_seat_short_of_shards_when_the_deposits_are_taken_ends_it_for_all():
    async def go():
        w = World()
        tid = await w.invited()
        w.g.store.update_player(w.pids[2], shards=10)
        await w.t.answer(w.peers[1], tid, True)
        await w.t.answer(w.peers[2], tid, True)
        await settle()
        assert all(s.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "no_shards"}] for s in w.socks)
        assert [w.shards(p) for p in w.pids] == [SHARDS, SHARDS, 10] and w.t.by_save == {}
    run(go())


# ------------------------------------------------------------------ bidding
def test_bids_go_round_once_and_the_highest_takes_the_bottom():
    async def go():
        w = World(rng=Stacked(first=1))
        tid = await w.dealt()
        a, b, c = w.peers
        t = w.t.by_id[tid]
        assert w.last("ddz_deal")["turn"] == 1
        with pytest.raises(GameError) as e:
            await w.t.bid(a, tid, 1)
        assert e.value.code == "ddz_turn"
        await w.t.bid(b, tid, 1)
        assert w.last("ddz_bid") == {"type": "ddz_bid", "table": tid, "seat": 1, "bid": 1, "turn": 2,
                                     "sec": CFG["bidSec"]}
        with pytest.raises(GameError) as e:
            await w.t.bid(c, tid, 1)  # not above the bid so far
        assert e.value.code == "ddz_bad"
        await w.t.bid(c, tid, 2)
        await w.t.bid(a, tid, 0)
        assert w.last("ddz_bid") == {"type": "ddz_bid", "table": tid, "seat": 0, "bid": 0}
        lord = w.last("ddz_landlord")
        assert lord == {"type": "ddz_landlord", "table": tid, "seat": 2, "bid": 2, "bottom": t.bottom, "mult": 2,
                        "turn": 2, "sec": CFG["playSec"]}
        assert len(t.seats[2].hand) == 20 and set(t.bottom) <= set(t.seats[2].hand)
        assert [h.delay for h in w.timers.live()] == [CFG["playSec"]]
    run(go())


def test_a_bid_of_three_ends_the_bidding():
    async def go():
        w = World(rng=Stacked(first=2))
        tid = await w.dealt()
        await w.t.bid(w.peers[2], tid, 3)
        assert w.last("ddz_landlord")["seat"] == 2 and w.last("ddz_landlord")["mult"] == 3
        assert len(w.socks[0].of("ddz_bid")) == 1
    run(go())


def test_a_deal_nobody_bids_on_is_dealt_again_and_the_third_gives_the_deposits_back():
    async def go():
        w = World()
        tid = await w.dealt()
        t = w.t.by_id[tid]
        for deal in range(1, MAX_DEALS + 1):
            assert w.last("ddz_deal")["deal"] == deal
            for _ in range(3):
                await w.t.bid(w.peers[t.turn], tid, 0)
        await settle()
        assert all(s.of("ddz_over") == [{"type": "ddz_over", "table": tid, "reason": "nobid"}] for s in w.socks)
        assert [w.shards(p) for p in w.pids] == [SHARDS] * 3 and w.t.by_save == {} and w.timers.live() == []
        assert not any(w.t.in_game(p) for p in w.peers)
    run(go())


# ------------------------------------------------------------------ plays
def test_plays_must_be_the_seats_own_cards_a_hand_and_beat_the_last():
    async def go():
        w = World(rng=Stacked(deck_of([3, 3, 5, 6, 7, 8, 9, 9, 9, 9, 11, 11, 12, 12, 13, 13, 14],
                                      [3, 4, 4, 5, 5, 6, 7, 8, 10, 10, 11, 12, 13, 14, 14, 15, 15],
                                      [3, 4, 4, 5, 6, 6, 7, 7, 8, 10, 10, 11, 12, 13, 14, 15, 15]), first=0))
        tid = await w.playing()
        a, b, c = w.peers
        t = w.t.by_id[tid]
        hand = t.seats[0].hand

        async def bad(peer, cards, code="ddz_bad"):
            with pytest.raises(GameError) as e:
                await w.t.play(peer, tid, cards)
            assert e.value.code == code

        await bad(b, [t.seats[1].hand[0]], "ddz_turn")
        await bad(a, [])                                  # the lead cannot pass
        await bad(a, [t.seats[1].hand[0]])                # not its card
        await bad(a, [hand[0], hand[0]])                  # one card twice
        await bad(a, [hand[0], hand[2]])                  # 3 and 4 are no hand
        pair3 = [c for c in hand if rules.rank(c) == 3]
        await w.t.play(a, tid, pair3)
        assert w.last("ddz_play") == {"type": "ddz_play", "table": tid, "seat": 0, "cards": pair3, "left": 18,
                                      "mult": 3, "bombs": 0, "turn": 1, "lead": False, "sec": CFG["playSec"]}
        await bad(b, [t.seats[1].hand[0]])                # a single on a pair
        pair4 = [c for c in t.seats[1].hand if rules.rank(c) == 4][:2]
        await w.t.play(b, tid, pair4)
        await bad(c, [x for x in t.seats[2].hand if rules.rank(x) == 3][:2] or [t.seats[2].hand[0]])
        await w.t.play(c, tid, [x for x in t.seats[2].hand if rules.rank(x) == 6][:2])
        # A bomb beats it and doubles the stake.
        bomb = [x for x in t.seats[0].hand if rules.rank(x) == 9]
        await w.t.play(a, tid, bomb)
        assert (w.last("ddz_play")["mult"], w.last("ddz_play")["bombs"]) == (6, 1)
        await w.t.play(b, tid, [])
        await w.t.play(c, tid, [])
        # Both passed: the seat that played last leads whatever it likes.
        assert w.last("ddz_play") == {"type": "ddz_play", "table": tid, "seat": 2, "cards": [], "left": 15, "mult": 6,
                                      "bombs": 1, "turn": 0, "lead": True, "sec": CFG["playSec"]}
        await w.t.play(a, tid, [t.seats[0].hand[0]])
        assert w.last("ddz_play")["lead"] is False
    run(go())


async def play_out(w, tid, winner_first=True):
    """Every seat plays its lowest card when it leads and passes otherwise, until someone is out of cards."""
    t = w.t.by_id[tid]
    while t.phase == "play":
        seat = t.turn
        await w.t.play(w.peers[seat], tid, [] if t.last is not None else [t.seats[seat].hand[0]])
    await settle()


def test_the_landlord_wins_a_spring():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        await play_out(w, tid)
        result = w.last("ddz_result")
        t_hands = result["hands"]
        assert result == {"type": "ddz_result", "table": tid, "winner": "landlord", "landlord": 0, "bid": 3,
                          "bombs": 0, "spring": 1, "mult": 6, "base": BASE, "deltas": [2700, -1500, -1500],
                          "hands": t_hands, "sec": CFG["againSec"]}
        assert t_hands[0] == [] and len(t_hands[1]) == len(t_hands[2]) == 17
        assert [w.shards(p) for p in w.pids] == [SHARDS + 2700, SHARDS - 1500, SHARDS - 1500]
        assert all(s.of("ddz_result") == [result] for s in w.socks)
        assert not any(w.t.in_game(p) for p in w.peers) and w.t.by_id[tid].phase == "over"
    run(go())


def test_the_farmers_win_a_counter_spring_and_the_room_hears_who_won():
    async def go():
        # The landlord leads a 3, a farmer plays a straight flush of cards after it and is never beaten.
        w = World(rng=Stacked(deck_of([3], [4] + [15] * 4, []), first=0))
        tid = await w.playing(bids=(1,  0, 0))
        a, b, c = w.peers
        watcher, seen = w.join("w")
        t = w.t.by_id[tid]
        await w.t.play(a, tid, [t.seats[0].hand[0]])
        await w.t.play(b, tid, [x for x in t.seats[1].hand if rules.rank(x) == 4][:1])
        while t.phase == "play":
            seat = t.turn
            await w.t.play(w.peers[seat], tid, [] if seat != 1 else [t.seats[1].hand[0]])
        await settle()
        result = w.last("ddz_result")
        assert (result["winner"], result["spring"], result["mult"], result["deltas"]) == ("farmers", 2, 2, [-1000, 450, 450])
        assert seen.of("ddz_live") == [{"type": "ddz_live", "table": tid, "ids": [a.id, b.id, c.id], "on": False,
                                        "gains": {b.id: 450, c.id: 450}}]
    run(go())


def test_the_multiplier_stops_at_the_cap():
    async def go():
        w = World()
        tid = await w.playing()
        t = w.t.by_id[tid]
        t.bombs = 5
        assert t.mult(24) == 24 and t.mult(24, spring=True) == 24
        t.bombs = 2
        assert t.mult(24) == 12 and t.mult(24, spring=True) == 24
    run(go())


# ------------------------------------------------------------------ autopilot
def test_a_turn_left_to_run_out_is_played_for_and_the_second_turns_the_autopilot_on():
    async def go():
        w = World(rng=Stacked(deck_of([4, 4, 4, 6, 8, 8, 10, 10, 11, 12, 12, 13, 13, 14, 14, 15, 15], [3], []),
                              first=0))
        tid = await w.dealt()
        t = w.t.by_id[tid]
        await w.timers.fire()  # seat 0 lets its bid run out: a pass
        assert w.last("ddz_bid")["seat"] == 0 and w.last("ddz_bid")["bid"] == 0 and not t.seats[0].auto
        await w.t.bid(w.peers[1], tid, 1)
        await w.t.bid(w.peers[2], tid, 0)
        await w.t.play(w.peers[1], tid, [t.seats[1].hand[0]])  # the landlord leads a 3
        await w.t.play(w.peers[2], tid, [])
        assert [h.delay for h in w.timers.live()] == [CFG["playSec"]]
        await w.timers.fire()  # seat 0 again
        assert w.last("ddz_seat") == {"type": "ddz_seat", "table": tid, "seat": 0, "id": w.peers[0].id, "away": False,
                                      "auto": True}
        assert AUTO_AFTER == 2
        # Played for, it beats the 3 with its lowest single, keeping its pairs and its trio whole.
        assert w.last("ddz_play")["seat"] == 0 and rules.ranks(w.last("ddz_play")["cards"]) == [6]
        assert t.last == (0, w.last("ddz_play")["cards"])
        # From now on its turns take a moment; leading, it plays its lowest trio with its lowest single along.
        await w.t.play(w.peers[1], tid, [])
        await w.t.play(w.peers[2], tid, [])
        assert [h.delay for h in w.timers.live()] == [AUTO_SEC]
        await w.timers.fire()
        assert w.last("ddz_play")["seat"] == 0 and rules.ranks(w.last("ddz_play")["cards"]) == [4, 4, 4, 11]
        assert len(t.seats[0].hand) == 12
    run(go())


def test_a_seat_played_for_leads_a_run_and_passes_on_its_partner():
    async def go():
        w = World(rng=Stacked(deck_of([3, 4, 5, 6, 7, 8, 10, 10, 12, 13, 13, 14, 14, 14, 15, 15, 17], [11], [11, 11]),
                              first=0))
        tid = await w.playing(bids=(0, 3))
        a, b, c = w.peers
        t = w.t.by_id[tid]
        assert t.landlord == 1
        w.t.auto(a, tid, True)

        def of(seat, r, n=1):
            return [x for x in t.seats[seat].hand if rules.rank(x) == r][:n]

        await w.t.play(b, tid, of(1, 11))
        await w.t.play(c, tid, [])
        await w.timers.fire()
        # On the landlord's J: its one Q, not the big joker nor a card off a pair.
        assert rules.ranks(w.last("ddz_play")["cards"]) == [12]
        await w.t.play(b, tid, [])
        await w.t.play(c, tid, [])
        await w.timers.fire()
        # Leading: the longest run of singles its lowest card starts, then its lowest pair.
        assert rules.ranks(w.last("ddz_play")["cards"]) == [3, 4, 5, 6, 7, 8]
        await w.t.play(b, tid, [])
        await w.t.play(c, tid, [])
        await w.timers.fire()
        assert rules.ranks(w.last("ddz_play")["cards"]) == [10, 10]
        await w.t.play(b, tid, [])
        await w.t.play(c, tid, of(2, 11, 2))
        await w.timers.fire()
        # The other farmer's pair of Js stands, though its Ks would beat it.
        assert w.last("ddz_play")["seat"] == 0 and w.last("ddz_play")["cards"] == []
    run(go())


@pytest.mark.parametrize("broken", [lambda *a, **kw: 1 / 0, lambda hand, last, **kw: [99], lambda *a, **kw: []])
def test_a_play_chosen_wrong_falls_back_and_the_table_goes_on(monkeypatch, broken):
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        t = w.t.by_id[tid]
        w.t.auto(w.peers[0], tid, True)
        monkeypatch.setattr(rules, "choose", broken)
        low = t.seats[0].hand[0]
        await w.timers.fire()
        assert w.last("ddz_play")["seat"] == 0 and w.last("ddz_play")["cards"] == [low] and t.turn == 1
    run(go())


def test_the_member_takes_the_seat_back_with_its_full_time():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        t = w.t.by_id[tid]
        a = w.peers[0]
        w.t.auto(a, tid, True)
        assert t.seats[0].auto and [h.delay for h in w.timers.live()] == [AUTO_SEC]
        assert w.last("ddz_seat", 1) == {"type": "ddz_seat", "table": tid, "seat": 0, "id": a.id, "away": False,
                                         "auto": True, "turn": 0, "sec": AUTO_SEC}
        w.t.auto(a, tid, False)
        assert not t.seats[0].auto and [h.delay for h in w.timers.live()] == [CFG["playSec"]]
        assert w.last("ddz_seat", 1)["sec"] == CFG["playSec"]
        # A play by hand clears the count of turns left to run out.
        t.seats[0].timeouts = 1
        await w.t.play(a, tid, [t.seats[0].hand[0]])
        assert t.seats[0].timeouts == 0
    run(go())


def test_a_member_who_leaves_the_room_is_played_for_and_comes_back_to_its_seat():
    async def go():
        w = World(rng=Stacked(deck_of([rules.BIG_JOKER], [], []), first=0))
        tid = await w.playing()
        a, b, c = w.peers
        t = w.t.by_id[tid]
        # The big joker: nothing but a bomb beats it, and the seat played for keeps its bombs.
        await w.t.play(a, tid, [rules.BIG_JOKER + 36])
        await w.m.depart("r", b.id)
        await settle()
        assert w.last("ddz_seat") == {"type": "ddz_seat", "table": tid, "seat": 1, "id": b.id, "away": True,
                                      "auto": False}
        assert [h.delay for h in w.timers.live()] == [AUTO_SEC] and w.t.by_save[w.pids[1]] is t
        await w.timers.fire()
        assert w.last("ddz_play")["seat"] == 1 and w.last("ddz_play")["cards"] == []
        # Another save's join changes nothing; its own takes the seat with the whole game.
        w.join("stranger", save(w.g, "s"))
        b2, sock = w.join("b", w.pids[1])
        await w.t.joined("r", b2)
        assert w.last("ddz_seat") == {"type": "ddz_seat", "table": tid, "seat": 1, "id": b2.id, "away": False,
                                      "auto": False}
        live, state = sock.got
        assert live == {"type": "ddz_live", "table": tid, "ids": [a.id, b2.id, c.id], "on": True}
        assert state["type"] == "ddz_state" and state["you"] == 1 and state["hand"] == t.seats[1].hand
        assert state["phase"] == "play" and state["landlord"] == 0 and state["turn"] == 2 and state["bid"] == 3
        assert [s["left"] for s in state["seats"]] == [19, 17, 17] and state["trick"] == [t.trick[0], [], None]
        assert state["seats"][1] == {"id": b2.id, "nick": "b", "character": "嘉然", "left": 17, "bid": None,
                                     "auto": False, "away": False}
        assert state["bottom"] == t.bottom and state["lead"] is False and state["of"] == CFG["playSec"]
        w.peers[1], w.socks[1] = b2, sock
        await w.t.play(c, tid, [])
        await play_out(w, tid)
        assert w.last("ddz_result", 1)["winner"] == "landlord"
    run(go())


def test_the_state_lists_every_card_played_this_deal():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        a, b, c = w.peers
        t = w.t.by_id[tid]
        assert w.t._state(t, 1)["played"] == []
        first = [t.seats[0].hand[0]]
        await w.t.play(a, tid, first)
        await w.t.play(b, tid, [])
        second = [next(x for x in t.seats[2].hand if rules.rank(x) > rules.rank(first[0]))]
        await w.t.play(c, tid, second)
        assert w.t._state(t, 1)["played"] == first + second
        w.t._deal(t)
        assert w.t._state(t, 1)["played"] == []
    run(go())


def test_rejoining_on_turn_updates_observers_and_other_seats():
    async def go():
        w = World(rng=Stacked(first=0))
        _, observer = w.join("observer", save(w.g, "observer"))
        tid = await w.playing()
        a, b, c = w.peers
        await w.m.depart("r", a.id)
        a2, _ = w.join("a", w.pids[0])
        await w.t.joined("r", a2)
        await settle()
        assert observer.of("ddz_live")[-1] == {"type": "ddz_live", "table": tid,
                                               "ids": [a2.id, b.id, c.id], "on": True}
        assert w.last("ddz_seat", 1) == {"type": "ddz_seat", "table": tid, "seat": 0, "id": a2.id,
                                         "away": False, "auto": False, "turn": 0, "sec": CFG["playSec"]}
    run(go())


def test_a_game_all_three_left_is_called_off():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        for p in w.peers:
            await w.m.depart("r", p.id)
        await settle()
        assert w.t.by_id == {} and w.t.by_save == {} and w.timers.live() == []
        assert [w.shards(p) for p in w.pids] == [SHARDS] * 3
    run(go())


def test_walking_away_from_the_table_leaves_the_seat_to_the_server():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        a, b, c = w.peers
        t = w.t.by_id[tid]
        await w.t.leave(a, tid)
        assert t.seats[0].quit and w.socks[0].of("ddz_seat") == []
        assert w.last("ddz_seat", 1) == {"type": "ddz_seat", "table": tid, "seat": 0, "id": a.id, "away": True,
                                         "auto": True}
        with pytest.raises(GameError):
            await w.t.play(a, tid, [t.seats[0].hand[0]])
        plays = len(w.socks[0].of("ddz_play"))
        while t.phase == "play":
            if t.turn == 0:
                await w.timers.fire()
            else:
                await w.t.play(w.peers[t.turn], tid, [] if t.last is not None else [t.seats[t.turn].hand[0]])
        await settle()
        # The one who walked away hears no more plays, only how it ended; the table does not wait for another game.
        assert len(w.socks[0].of("ddz_play")) == plays and len(w.socks[0].of("ddz_result")) == 1
        assert w.socks[1].of("ddz_closed") == [{"type": "ddz_closed", "table": tid}] and w.t.by_save == {}
    run(go())


# ------------------------------------------------------------------ another game
def test_another_game_starts_when_the_three_ask_for_it():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        await play_out(w, tid)
        a, b, c = w.peers
        before = [w.shards(p) for p in w.pids]
        assert [h.delay for h in w.timers.live()] == [CFG["againSec"]]
        await w.t.again(b, tid)
        await w.t.again(b, tid)
        assert w.socks[0].of("ddz_again") == [{"type": "ddz_again", "table": tid, "seat": 1}]
        await w.t.again(a, tid)
        await w.t.again(c, tid)
        await settle()
        assert [w.shards(p) for p in w.pids] == [x - DEPOSIT for x in before]
        assert len(w.socks[0].of("ddz_deal")) == 2 and w.last("ddz_deal")["deal"] == 1
        assert w.t.by_id[tid].phase == "bid" and all(w.t.in_game(p) for p in w.peers)
    run(go())


@pytest.mark.parametrize("how", ["timeout", "leave", "depart"])
def test_the_table_closes_when_the_time_runs_out_or_someone_goes(how):
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        await play_out(w, tid)
        if how == "timeout":
            await w.timers.fire()
        elif how == "leave":
            await w.t.leave(w.peers[1], tid)
        else:
            await w.m.depart("r", w.peers[2].id)
        await settle()
        assert w.socks[0].of("ddz_closed") == [{"type": "ddz_closed", "table": tid}]
        assert w.t.by_id == {} and w.t.by_save == {} and w.timers.live() == []
        with pytest.raises(GameError):
            await w.t.again(w.peers[0], tid)
    run(go())


# ------------------------------------------------------------------ over the socket
@pytest.fixture()
def api(monkeypatch):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), rng=SeqRng(.5), now=clock)
    monkeypatch.setattr(main, "game", g)
    timers = ManualTimers()
    monkeypatch.setattr(main.tables, "timers", timers)
    monkeypatch.setattr(main.tables, "rng", Stacked(first=0))
    main.manager.rooms.clear()
    main.tables.clear()
    with TestClient(main.app) as c:
        yield c, g, timers
    main.manager.rooms.clear()
    main.tables.clear()


def tok(name):
    return f"{name}-ddz-token-0001"


def joined(ws, nick, room="r1", **extra):
    ws.send_json({"type": "join", "room": room, "nick": nick, "token": tok(nick), "ddz": True, **extra})
    return ws.receive_json()


def test_a_game_over_the_socket(api):
    c, g, timers = api
    for name in "abc":
        save(g, name)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as d:
        ja, jb = joined(a, "a"), joined(b, "b")
        a.receive_json()
        jd = joined(d, "c")
        a.receive_json(), b.receive_json()
        assert [m["ddz"] for m in jd["members"]] == [True, True, True]
        assert c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()["ddz"] == {"net": 0}
        assert c.get("/api/economy").json()["doudizhu"] == CFG
        a.send_json({"type": "ddz_invite", "ids": [jb["you"]], "base": BASE})
        assert a.receive_json()["code"] == "bad_message"
        a.send_json({"type": "ddz_invite", "ids": [jb["you"], jd["you"]], "base": BASE})
        invite = a.receive_json()
        assert invite["type"] == "ddz_invite" and b.receive_json() == invite and d.receive_json() == invite
        tid = invite["table"]
        b.send_json({"type": "ddz_answer", "table": tid, "accept": True})
        for ws in (a, b, d):
            assert ws.receive_json() == {"type": "ddz_answer", "table": tid, "id": jb["you"]}
        d.send_json({"type": "ddz_answer", "table": tid, "accept": True})
        for ws in (a, b, d):
            assert ws.receive_json()["type"] == "ddz_answer"
            assert ws.receive_json() == {"type": "ddz_live", "table": tid, "ids": invite["ids"], "on": True}
        deal = a.receive_json()
        b.receive_json(), d.receive_json()
        assert deal["type"] == "ddz_deal" and deal["turn"] == 0
        # the host cannot remove a member mid-game
        a.send_json({"type": "kick", "id": jb["you"]})
        assert a.receive_json()["code"] == "in_duel"
        a.send_json({"type": "ddz_bid", "table": tid, "bid": 4})
        assert a.receive_json()["code"] == "bad_message"
        a.send_json({"type": "ddz_bid", "table": tid, "bid": 3})
        for ws in (a, b, d):
            assert ws.receive_json()["type"] == "ddz_bid"
            assert ws.receive_json()["type"] == "ddz_landlord"
        b.send_json({"type": "ddz_play", "table": tid, "cards": [0]})
        assert b.receive_json() == {"type": "error", "code": "ddz_turn", "message": ""}
        a.send_json({"type": "ddz_play", "table": tid, "cards": [99]})
        assert a.receive_json()["code"] == "bad_message"
        hands = {0: list(main.tables.by_id[tid].seats[0].hand)}
        turn, left = 0, 20
        socks = {0: a, 1: b, 2: d}
        while left:
            if turn == 0:
                a.send_json({"type": "ddz_play", "table": tid, "cards": [hands[0].pop(0)]})
                left -= 1
            else:
                socks[turn].send_json({"type": "ddz_play", "table": tid, "cards": []})
            for ws in (a, b, d):
                assert ws.receive_json()["type"] == "ddz_play"
            turn = (turn + 1) % 3
        result = a.receive_json()
        assert result["type"] == "ddz_result" and result["deltas"] == [2700, -1500, -1500] and result["spring"] == 1
        assert a.receive_json()["gains"] == {ja["you"]: 2700}
        me = c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()
        assert me["shards"] == SHARDS + 2700 and me["ddz"] == {"net": 2700}


def test_a_server_without_the_game_answers_no_ddz(api, monkeypatch):
    c, g, timers = api
    data = copy.deepcopy(Manifest.load().data)
    del data["economy"]["doudizhu"]
    g2 = Game(Store(":memory:"), Manifest(data), now=Clock())
    monkeypatch.setattr(main, "game", g2)
    for name in "abc":
        save(g2, name)
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as d:
        joined(a, "a")
        jb = joined(b, "b")
        jd = joined(d, "c")
        a.receive_json(), a.receive_json()
        # Nobody is marked as able to play, and the status has no ddz part.
        assert [m["ddz"] for m in jd["members"]] == [False, False, False]
        assert "ddz" not in c.get("/api/me", headers={"X-Player-Token": tok("a")}).json()
        a.send_json({"type": "ddz_invite", "ids": [jb["you"], jd["you"]], "base": BASE})
        assert a.receive_json()["code"] == "no_ddz"


def test_a_new_connection_of_the_save_takes_the_seat_before_the_old_one_is_seen_to_go():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        t = w.t.by_id[tid]
        a, b, c = w.peers
        # b's client is back on a new connection; the server has not yet seen the old one go.
        b2, sock = w.join("b", w.pids[1])
        await w.t.joined("r", b2)
        assert t.seats[1].peer is b2 and sock.of("ddz_state")[0]["you"] == 1
        assert w.socks[1].of("ddz_closed") == [{"type": "ddz_closed", "table": tid}]
        assert w.last("ddz_seat", 0) == {"type": "ddz_seat", "table": tid, "seat": 1, "id": b2.id, "away": False,
                                         "auto": False}
        # The old connection's leaving, seen late, leaves the seat to the new one.
        await w.m.depart("r", b.id)
        await settle()
        assert t.seats[1].peer is b2 and not t.seats[1].auto and w.last("ddz_seat", 0)["id"] == b2.id
        w.peers[1], w.socks[1] = b2, sock
        await play_out(w, tid)
        assert w.last("ddz_result", 1)["winner"] == "landlord"
    run(go())


@pytest.mark.parametrize("room", ["r", "r2"])
def test_a_member_back_in_the_room_while_the_deposits_are_taken_gets_the_deal(monkeypatch, room):
    async def go():
        import threading

        gate = threading.Event()
        real = Bank.start

        def slow(self, pids, base):
            gate.wait(5)
            return real(self, pids, base)

        monkeypatch.setattr(Bank, "start", slow)
        w = World()
        tid = await w.invited()
        a, b, c = w.peers
        await w.t.answer(b, tid, True)
        t = w.t.by_id[tid]
        task = asyncio.create_task(w.t.answer(c, tid, True))
        for _ in range(200):
            await asyncio.sleep(0.005)
            if t.phase == "starting":
                break
        try:
            assert t.phase == "starting"
            # b leaves and comes back while the database takes the deposits.
            await w.m.depart("r", b.id)
            b2, sb2 = w.join("b2", w.pids[1], room=room)
            await w.t.joined(room, b2)
        finally:
            gate.set()
        await task
        await settle()
        if room == "r":
            assert t.seats[1].peer is b2 and not t.seats[1].auto
            deal = sb2.of("ddz_deal")
            assert len(deal) == 1 and deal[0]["you"] == 1 and len(deal[0]["hand"]) == 17
            assert deal[0]["seats"][1] == {"id": b2.id, "nick": "b2", "character": "嘉然", "auto": False, "away": False}
        else:
            # The seat is taken again in the table's room only; meanwhile it is played for.
            assert t.seats[1].peer is None and sb2.of("ddz_deal") == []
    run(go())


def test_a_connection_that_finishes_joining_late_does_not_take_the_seat_from_a_newer_one():
    async def go():
        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        t = w.t.by_id[tid]
        pid = w.pids[1]
        # Two new connections of b's save; the newer one gets through joining first.
        old, s_old = w.join("b", pid)
        new, s_new = w.join("b", pid)
        assert old.join_seq < new.join_seq
        await w.t.joined("r", new)
        await w.t.joined("r", old)
        assert t.seats[1].peer is new and s_new.of("ddz_closed") == [] and s_old.of("ddz_state") == []
        # A newer occupant already gone from the room, its leaving not handled yet, gives way to an older one.
        w.m.leave("r", new.id)
        await w.t.joined("r", old)
        assert t.seats[1].peer is old and s_old.of("ddz_state")[-1]["you"] == 1
        await w.t.departed("r", new)
        assert t.seats[1].peer is old
        # A connection gone from the room before it got through joining takes no seat.
        await w.m.depart("r", old.id)
        late, s_late = w.join("b", pid)
        w.m.leave("r", late.id)
        await w.t.joined("r", late)
        assert t.seats[1].peer is None and s_late.of("ddz_state") == []
    run(go())


def test_a_new_connection_taking_the_seat_on_its_turn_keeps_the_time_of_the_turn():
    async def go():
        w = World(rng=Stacked(first=1))
        tid = await w.dealt()
        t = w.t.by_id[tid]
        deadline, step = t.deadline, t.step
        t.seats[1].timeouts = 1
        w.mono += 5
        left = round(deadline - w.mono, 1)
        # Handing the seat from one connection to another, over and over, does not give the turn its time again.
        b2, s2 = w.join("b", w.pids[1])
        await w.t.joined("r", b2)
        assert (t.deadline, t.step, t.seats[1].timeouts) == (deadline, step, 1)
        assert [h.delay for h in w.timers.live()] == [DEAL_SEC + CFG["bidSec"]]
        assert w.last("ddz_seat", 0)["sec"] == left and s2.of("ddz_state")[0]["sec"] == left
        # Back to a seat played for while it was away, the turn starts again with its full time, as before.
        await w.m.depart("r", b2.id)
        b3, _ = w.join("b", w.pids[1])
        await w.t.joined("r", b3)
        assert w.last("ddz_seat", 0)["sec"] == CFG["bidSec"] and t.deadline == w.mono + CFG["bidSec"]
    run(go())


def test_another_game_nobody_stayed_for_gives_the_deposits_back(monkeypatch):
    async def go():
        import threading

        w = World(rng=Stacked(first=0))
        tid = await w.playing()
        await play_out(w, tid)
        a, b, c = w.peers
        before = [w.shards(p) for p in w.pids]
        gate = threading.Event()
        real = Bank.start

        def slow(self, pids, base):
            gate.wait(5)
            return real(self, pids, base)

        monkeypatch.setattr(Bank, "start", slow)
        await w.t.again(a, tid)
        await w.t.again(b, tid)
        t = w.t.by_id[tid]
        task = asyncio.create_task(w.t.again(c, tid))
        for _ in range(200):
            await asyncio.sleep(0.005)
            if t.phase == "starting":
                break
        try:
            assert t.phase == "starting"
            # All three leave while the database takes the deposits.
            for p in (a, b, c):
                await w.m.depart("r", p.id)
        finally:
            gate.set()
        await task
        await settle()
        assert w.t.by_id == {} and w.t.by_save == {} and w.timers.live() == []
        assert [w.shards(p) for p in w.pids] == before
    run(go())


@pytest.mark.parametrize("again", [False, True])
def test_a_cancelled_handler_while_the_deposits_are_taken_leaves_the_start_to_the_table(monkeypatch, again):
    """The last to accept (or to ask for another game) has its connection handler cancelled while the database takes
    the deposits: the start goes on on the table's own task and deals."""
    async def go():
        import threading

        w = World(rng=Stacked(first=0))
        if again:
            tid = await w.playing()
            await play_out(w, tid)
        else:
            tid = await w.invited()
        a, b, c = w.peers
        gate = threading.Event()
        real = Bank.start

        def slow(self, pids, base):
            gate.wait(5)
            return real(self, pids, base)

        monkeypatch.setattr(Bank, "start", slow)
        if again:
            await w.t.again(a, tid)
            await w.t.again(b, tid)
            task = asyncio.create_task(w.t.again(c, tid))
        else:
            await w.t.answer(b, tid, True)
            task = asyncio.create_task(w.t.answer(c, tid, True))
        t = w.t.by_id[tid]
        for _ in range(200):
            await asyncio.sleep(0.005)
            if t.phase == "starting":
                break
        assert t.phase == "starting"
        task.cancel()
        await asyncio.sleep(0.01)
        gate.set()
        await w.t.idle()
        await settle()
        assert t.phase == "bid" and t.row is not None and w.t.by_id.get(tid) is t
        assert all(len(s.of("ddz_deal")) == (2 if again else 1) for s in w.socks)
        assert [w.shards(p) for p in w.pids][0] < SHARDS
    run(go())


def test_the_start_task_cancelled_while_the_deposits_are_taken_hands_them_back(monkeypatch):
    """The table's own start task is cancelled (the server stops) while the database takes the deposits: the table
    ends, the saves are free, and the transaction, done after, hands back what it took."""
    async def go():
        import threading

        w = World(rng=Stacked(first=0))
        tid = await w.invited()
        a, b, c = w.peers
        before = [w.shards(p) for p in w.pids]
        gate = threading.Event()
        real = Bank.start
        done = threading.Event()

        def slow(self, pids, base):
            gate.wait(5)
            try:
                return real(self, pids, base)
            finally:
                done.set()

        monkeypatch.setattr(Bank, "start", slow)
        await w.t.answer(b, tid, True)
        handler = asyncio.create_task(w.t.answer(c, tid, True))
        t = w.t.by_id[tid]
        for _ in range(200):
            await asyncio.sleep(0.005)
            if t.phase == "starting":
                break
        assert t.phase == "starting"
        for task in list(w.t._tasks):
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await handler
        assert w.t.by_id == {} and w.t.by_save == {}
        assert all(s.of("ddz_over")[-1]["reason"] == "error" for s in w.socks)
        gate.set()
        for _ in range(200):
            await asyncio.sleep(0.005)
            if done.is_set() and [w.shards(p) for p in w.pids] == before:
                break
        assert [w.shards(p) for p in w.pids] == before
        assert w.g.store.open_ddz_games() == []
    run(go())
