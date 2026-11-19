"""On a server with main-site accounts, rock-paper-scissors and dou dizhu are played from saves linked to an account."""
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.accounts import MainAccounts
from app.ddz import Bank, Tables
from app.duel import Duels
from app.game import Game, GameError
from app.manifest import Manifest
from app.store import Store

from fixtures import Clock, SeqRng
from test_accounts import FakeMain
from test_ddz import BASE, Stacked
from test_ddz import World as DdzWorld
from test_ddz import save as ddz_save
from test_duel import ManualTimers, World as DuelWorld, refused, run, save, settle


def raises(code, fn, *args):
    with pytest.raises(GameError) as e:
        fn(*args)
    assert e.value.code == code
    return e.value


# ------------------------------------------------------------------ rock-paper-scissors
def test_duels_need_both_saves_linked_where_accounts_are_on():
    g = Game(Store(":memory:"), Manifest.load(), now=Clock())
    a, b = save(g, "a"), save(g, "b")
    # without accounts guest saves play as before
    assert g.duel_check(a, b, 150)["bet"] == 150
    assert raises("duel_account", g.duel_check, a, b, 150, True).message
    assert raises("duel_account", g.duel_start, a, b, 150, True).message
    g.store.link_account("u-a", a, g.now())
    assert raises("duel_target_account", g.duel_check, a, b, 150, True).message
    assert raises("duel_target_account", g.duel_start, a, b, 150, True).message
    g.store.link_account("u-b", b, g.now())
    assert g.duel_check(a, b, 150, True)["bet"] == 150
    shards = g.store.get_player(a, g.now())["shards"]
    assert g.duel_start(a, b, 150, True) and g.store.get_player(a, g.now())["shards"] == shards - 150


def test_too_few_taps_is_told_before_the_missing_account():
    g = Game(Store(":memory:"), Manifest.load(), now=Clock())
    a, b = save(g, "a", taps=0), save(g, "b", taps=0)
    raises("duel_locked", g.duel_check, a, b, 150, True)
    g.store.update_player(a, taps_total=10_000)
    g.store.link_account("u-a", a, g.now())
    raises("duel_target_locked", g.duel_check, a, b, 150, True)


class AccountDuels(DuelWorld):
    def __init__(self):
        super().__init__()
        self.d = Duels(lambda: self.g, lambda: self.m, timers=self.timers, clock=lambda: self.mono, rng=SeqRng(0),
                       require_account=lambda: True)
        self.m.on_depart = self.d.departed


def test_an_invite_from_or_to_a_guest_save_is_refused():
    async def go():
        w = AccountDuels()
        a, sa, a_pid, b, sb, b_pid = w.pair()
        await refused("duel_account", lambda: w.d.invite("r", a, b.id, 150))
        w.g.store.link_account("u-a", a_pid, w.clock.t)
        await refused("duel_target_account", lambda: w.d.invite("r", a, b.id, 150))
        assert sb.of("duel_invite") == [] and w.d.by_save == {}
        w.g.store.link_account("u-b", b_pid, w.clock.t)
        await w.d.invite("r", a, b.id, 150)
        await settle()
        assert sb.of("duel_invite")
    run(go())


def test_an_account_unlinked_before_the_answer_takes_no_bets():
    async def go():
        w = AccountDuels()
        a, sa, a_pid, b, sb, b_pid = w.pair()
        w.g.store.link_account("u-a", a_pid, w.clock.t)
        w.g.store.link_account("u-b", b_pid, w.clock.t)
        await w.d.invite("r", a, b.id, 150)
        await settle()
        w.g.store.unlink_account("u-b")
        before = w.shards(a_pid), w.shards(b_pid)
        await w.d.answer(b, sb.of("duel_invite")[0]["duel"], True)
        await settle()
        assert sa.of("duel_over")[-1]["reason"] == "duel_target_account"
        assert (w.shards(a_pid), w.shards(b_pid)) == before and w.d.by_save == {}
    run(go())


# ------------------------------------------------------------------ dou dizhu
def test_every_seat_needs_a_linked_save_where_accounts_are_on():
    w = DdzWorld()
    pids = [ddz_save(w.g, n) for n in "abc"]
    assert Bank(w.g).check(pids, BASE)
    bank = Bank(w.g, require_account=True)
    assert raises("ddz_account", bank.check, pids, BASE).message == "登录 Asasfans 账号后才能斗地主"
    w.g.store.link_account("u-a", pids[0], w.clock.t)
    assert raises("ddz_target_account", bank.check, pids, BASE).message == "有人还没有登录 Asasfans 账号"
    w.g.store.link_account("u-b", pids[1], w.clock.t)
    raises("ddz_target_account", bank.check, pids, BASE)
    raises("ddz_target_account", bank.start, pids, BASE)
    assert [w.shards(p) for p in pids] == [w.shards(pids[0])] * 3
    w.g.store.link_account("u-c", pids[2], w.clock.t)
    assert bank.check(pids, BASE) and bank.start(pids, BASE)


class AccountTables(DdzWorld):
    def __init__(self):
        super().__init__()
        self.t = Tables(lambda: self.g, lambda: self.m, timers=self.timers, clock=lambda: self.mono, rng=Stacked(),
                        require_account=lambda: True)
        self.m.on_depart = self.t.departed


def test_a_table_with_a_guest_seat_is_refused_and_one_unlinked_before_the_deal_takes_nothing():
    async def go():
        w = AccountTables()
        peers, socks, pids = w.three()
        await refused("ddz_account", lambda: w.t.invite("r", peers[0], [peers[1].id, peers[2].id], BASE))
        for n, pid in enumerate(pids):
            w.g.store.link_account(f"u-{n}", pid, w.clock.t)
        await w.t.invite("r", peers[0], [peers[1].id, peers[2].id], BASE)
        await settle()
        tid = socks[0].of("ddz_invite")[0]["table"]
        await w.t.answer(peers[1], tid, True)
        w.g.store.unlink_account("u-2")
        before = [w.shards(p) for p in pids]
        await w.t.answer(peers[2], tid, True)
        await settle()
        assert socks[0].of("ddz_over")[-1]["reason"] == "ddz_account"
        assert [w.shards(p) for p in pids] == before and w.t.by_save == {}
    run(go())


# ------------------------------------------------------------------ over the socket
@pytest.fixture()
def api(monkeypatch):
    g = Game(Store(":memory:"), Manifest.load(), rng=SeqRng(.5), now=Clock())
    monkeypatch.setattr(main, "game", g)
    monkeypatch.setattr(main, "accounts", MainAccounts("https://main.test/api/", FakeMain(), lambda: 0.0))
    monkeypatch.setattr(main.duels, "timers", ManualTimers())
    main.manager.rooms.clear()
    main.duels.clear()
    with TestClient(main.app) as c:
        yield c, g
    main.manager.rooms.clear()
    main.duels.clear()


def joined(ws, nick, **who):
    ws.send_json({"type": "join", "room": "r1", "nick": nick, **who})
    return ws.receive_json()


def test_the_main_server_tells_a_guest_save_to_link_an_account(api):
    c, g = api
    alice, bob, guest = save(g, "alice"), save(g, "bob"), save(g, "guest")
    g.store.link_account("u-alice", alice, g.now())
    g.store.link_account("u-bob", bob, g.now())
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b, c.websocket_connect("/ws") as h:
        ja = joined(a, "a", accountToken="tok-alice")
        jb = joined(b, "b", accountToken="tok-bob")
        a.receive_json()  # member_joined
        jh = joined(h, "h", token="guest-duel-token-0001")
        a.receive_json(), b.receive_json()
        a.send_json({"type": "duel_invite", "id": jh["you"], "bet": 150})
        assert a.receive_json() == {"type": "error", "code": "duel_target_account", "message": "对方还没有登录 Asasfans 账号"}
        h.send_json({"type": "duel_invite", "id": ja["you"], "bet": 150})
        assert h.receive_json() == {"type": "error", "code": "duel_account", "message": "登录 Asasfans 账号后才能猜拳"}
        a.send_json({"type": "duel_invite", "id": jb["you"], "bet": 150})
        assert a.receive_json()["type"] == "duel_invite" and b.receive_json()["type"] == "duel_invite"
