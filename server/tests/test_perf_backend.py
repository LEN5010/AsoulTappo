"""Slow requests kept apart from the rest and the park's settlements in short write transactions: what each piece of
that work keeps the same, and what it saves."""
import asyncio
import json
import sqlite3
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Barrier, Event, Thread

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
import test_race_park as rp
from app import accounts as accounts_module, game as game_module, park_race
from app.accounts import MainAccounts, http_me
from app.game import Game, GameError, player_id_for
from app.lottery import SPEND, Lottery
from app.manifest import Manifest
from app.park import Park
from app.store import Store, day_of
from fixtures import Clock, SeqRng, tiny_manifest
from test_accounts import USERS, FakeMain
from test_ddz import save, tok
from test_lottery import Picks, at

PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy", "no_proxy")


def clear_proxy_env(monkeypatch):
    """None of the proxy variables the shell running the tests may set, and no opener urlopen kept from another test
    (it keeps the proxies of the call that built it)."""
    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setattr(urllib.request, "_opener", None)


def without_proxies(monkeypatch):
    """No proxy from the environment or from the system settings."""
    clear_proxy_env(monkeypatch)
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})


# ------------------------------------------------------------------ store
def test_a_zero_row_park_gift_leaves_no_write_transaction(tmp_path):
    path = str(tmp_path / "gifts.db")
    store = Store(path)
    store.get_player("p1", 0)
    day = "2026-11-23"
    assert store.grant_park_gift("p1", day, 3, 0)
    assert not store.grant_park_gift("p1", day, 3, 0)
    assert not store.grant_park_gift("missing", day, 3, 0)
    assert not store._db.in_transaction
    other = sqlite3.connect(path, timeout=0)
    with other:
        other.execute("UPDATE players SET coins = coins + 1 WHERE id = 'p1'")
    assert store.get_player("p1", 0)["coins"] == 4
    assert store.coin_ledger_of("p1", 1)[0]["amount"] == 3
    other.close()
    store.close()


def test_rollback_keeps_committed_counts_and_activity_hot():
    store = Store()
    ids = frozenset({"card:c1"})
    day = "2026-11-23"
    store.add_item("unrelated", "card:c1", 0)
    assert store.count_items("unrelated", ids) == 1
    assert store.count_items("changed", ids) == 0
    store.mark_active("unrelated", day)
    with pytest.raises(RuntimeError, match="rollback"):
        with store.transaction():
            store.add_item("changed", "card:c1", 0)
            assert store.count_items("changed", ids) == 1
            store.mark_active("changed", "2026-11-24")
            raise RuntimeError("rollback")

    sql = []
    store._db.set_trace_callback(sql.append)
    assert store.count_items("unrelated", ids) == 1
    assert store.count_items("changed", ids) == 0
    store.mark_active("unrelated", day)
    assert sql == []
    store.mark_active("changed", "2026-11-24")
    assert store.totals("2026-11-24")["activeToday"] == 1
    store.close()


def test_a_refused_single_write_leaves_the_caches_as_committed():
    store = Store()
    ids = frozenset({"card:c1"})
    store.get_player("p1", 0)
    assert store.count_items("p1", ids) == 0

    def deny_commit(action, operation, *_):
        if action == sqlite3.SQLITE_TRANSACTION and operation == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    store._db.set_authorizer(deny_commit)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            store.add_item("p1", "card:c1", 0)
        with pytest.raises(sqlite3.DatabaseError):
            store.mark_active("p1", "2026-11-26")
    finally:
        store._db.set_authorizer(None)
    assert not store._db.in_transaction
    assert store.count_items("p1", ids) == 0 and not store.has_item("p1", "card:c1")
    assert store.totals("2026-11-26")["activeToday"] == 0
    store.mark_active("p1", "2026-11-26")
    assert store.totals("2026-11-26")["activeToday"] == 1
    store.close()


def test_an_immediate_transaction_takes_over_a_write_left_open(tmp_path):
    store = Store(str(tmp_path / "open.db"))
    store.get_player("p1", 0)
    with store.lock:
        # A write outside a transaction that returns before its commit (an IntegrityError, say).
        store._db.execute("UPDATE players SET coins = 7 WHERE id = 'p1'")
    assert store._db.in_transaction
    with store.transaction(immediate=True) as st:
        st.update_player("p1", shards=9)
    assert not store._db.in_transaction
    other = sqlite3.connect(str(tmp_path / "open.db"))
    assert other.execute("SELECT coins, shards FROM players WHERE id = 'p1'").fetchone() == (7, 9)
    other.close()
    store.close()


def test_the_new_indexes_come_to_a_database_from_before_them(tmp_path):
    path = str(tmp_path / "legacy.db")
    old = sqlite3.connect(path)
    # room_restore from before the room names, which Store._migrate adds.
    old.executescript("""
        CREATE TABLE room_restore (room TEXT PRIMARY KEY, public INTEGER NOT NULL, host TEXT, banned TEXT NOT NULL,
                                   saved REAL NOT NULL);
        INSERT INTO room_restore VALUES ('r1', 1, NULL, '[]', 5);
    """)
    old.close()
    for _ in range(2):
        store = Store(path)
        db = store._db
        indexes = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert {"park_news_ts", "lottery_tickets_jackpot", "park_race_bets_totals", "park_link_settled",
                "park_link_settled_at", "park_scratch_revealed"} <= indexes
        plans = {
            "park_link_settled_at": "SELECT id FROM park_link WHERE settled_at < 1",
            "park_scratch_revealed": "SELECT id FROM park_scratch_cards WHERE revealed > 0 AND ts < 1",
            "park_race_bets_totals": "SELECT kind, member, SUM(coins) FROM park_race_bets WHERE race_id = 1 "
                                     "GROUP BY kind, member",
        }
        for index, sql in plans.items():
            assert index in " ".join(r[3] for r in db.execute(f"EXPLAIN QUERY PLAN {sql}"))
        store.close()


def test_news_cache_keeps_id_order_and_excludes_pruned_or_rolled_back_rows():
    store = Store()
    first = store.add_park_news(20, "first", "", "", "{}")
    older = store.add_park_news(10, "older", "", "", "{}")
    last = store.add_park_news(21, "last", "", "", "{}")

    def news(since):
        return [row["id"] for row in store.park_news_since(since, 2)]

    assert news(10) == [older, last]
    sql = []
    store._db.set_trace_callback(sql.append)
    assert news(10) == [older, last]
    assert sql == []
    assert news(11) == [first, last]
    assert store.prune_park_news(21, 1) == 1
    assert news(0) == [first, last]
    assert store.prune_park_news(21, 1) == 1
    assert news(0) == [last]
    with pytest.raises(RuntimeError, match="rollback"):
        with store.transaction():
            extra = store.add_park_news(22, "extra", "", "", "{}")
            assert news(0) == [last, extra]
            raise RuntimeError("rollback")
    assert news(0) == [last]
    store.close()


def test_news_of_a_busy_window_is_read_by_id_and_a_quiet_one_by_time():
    store = Store()
    for i in range(50):
        store.add_park_news(1000 + i, "old", "", "", "{}")
    busy = [store.add_park_news(5000 + i, "busy", "", "", "{}") for i in range(8)]
    sql = []
    store._db.set_trace_callback(sql.append)
    # The newest five ids are all in the window: one read of five rows.
    assert [r["id"] for r in store.park_news_since(4000, 5)] == busy[-5:]
    assert len(sql) == 1 and "INDEXED BY" not in sql[0]
    # Only three since then: the time index finds them, and they come in id order.
    store._park_news_cache = None
    sql.clear()
    assert [r["id"] for r in store.park_news_since(5005, 5)] == busy[-3:]
    assert len(sql) == 2 and "INDEXED BY park_news_ts" in sql[1]
    plan = " ".join(r[3] for r in store._db.execute(
        "EXPLAIN QUERY PLAN SELECT id FROM park_news INDEXED BY park_news_ts WHERE ts >= 1 ORDER BY id DESC LIMIT 5"))
    assert "park_news_ts" in plan
    # None at all, and no limit: the same answers as before.
    store._park_news_cache = None
    assert store.park_news_since(9000, 5) == []
    store._park_news_cache = None
    assert [r["id"] for r in store.park_news_since(5005, -1)] == busy[-3:]
    # An item with an earlier time but a later id (a clock set back) is still in its place by id.
    back = store.add_park_news(5006.5, "back", "", "", "{}")
    assert [r["id"] for r in store.park_news_since(5006, 3)] == [busy[6], busy[7], back]
    store.close()


# ------------------------------------------------------------------ settlements on a file database
def test_a_void_counts_again_when_a_bet_lands_after_its_read(tmp_path, monkeypatch):
    g, races, clock, (pid, other) = rp.make(path=str(tmp_path / "void.db"))
    races.tick()
    races.bet(rp.TOKEN, rp.T0, "win", rp.MEMBERS[0], 3)
    read = g.store.race_refunds
    reads = []

    def late_bet(race_id):
        out = read(race_id)
        if not reads:
            # A bet another request had under way when the window closed lands after the read.
            now, clock.t = clock.t, rp.T0 + 1
            races.bet(rp.OTHER, rp.T0, "top2", rp.MEMBERS[1], 4)
            clock.t = now
        reads.append(out)
        return out

    monkeypatch.setattr(g.store, "race_refunds", late_bet)
    clock.t = rp.T0 + rp.CFG["betting"] + park_race.START_GRACE + 1
    races.tick()
    assert [counts for _, counts in reads] == [1, 2]
    assert g.store.race_get(rp.T0)["status"] == "void"
    for p in (pid, other):
        assert g.store.get_player(p, clock())["coins"] == 50
    g.store.close()


def test_a_draw_counts_again_when_a_ticket_lands_after_its_read(tmp_path, monkeypatch):
    clock = Clock()
    g = Game(Store(str(tmp_path / "draw.db")), Manifest.load(), now=clock)
    park = Park(lambda: g)
    lot = Lottery(lambda: g, park, pick=Picks("123"))
    pids = []
    for token in ("draw-late-token-0001", "draw-late-token-0002"):
        pid = g.status(token)["player"]
        g.store.update_player(pid, coins=50, taps_total=10_000, gift_day=day_of(clock()))
        pids.append(pid)
    lot.buy("draw-late-token-0001", ["123"])
    read = g.store.lottery_draw_tickets
    reads = []

    def late_ticket(day):
        rows = read(day)
        if not reads:
            with g.store.transaction() as st:
                park.spend(st, pids[1], 1, SPEND, clock())
                st.add_lottery_tickets(day, pids[1], ["123"], clock())
        reads.append(len(rows))
        return rows

    monkeypatch.setattr(g.store, "lottery_draw_tickets", late_ticket)
    at(clock, g.manifest.park["lottery"]["drawAt"])
    before = [g.store.get_player(p, clock())["shards"] for p in pids]
    assert lot.tick() == [day_of(clock())]
    assert reads == [1, 2]
    gains = [g.store.get_player(p, clock())["shards"] - b for p, b in zip(pids, before)]
    assert gains[0] == gains[1] > 0
    assert json.loads(g.store.lottery_last_drawn()["result"])["winners"]["top"] == 2
    g.store.close()


# ------------------------------------------------------------------ one computation for many requests
def track_joiners(monkeypatch, module, workers):
    joined = Barrier(workers)

    class TrackedFuture(Future):
        def result(self, timeout=None):
            if not self.done():
                joined.wait(timeout=5)
            return super().result(timeout)

    monkeypatch.setattr(module, "Future", TrackedFuture)
    return joined


def test_cold_board_requests_share_one_computation_per_account_mode(monkeypatch):
    store = Store()
    g = Game(store, tiny_manifest(), now=Clock())
    token = "board-perf-token-1"
    pid = player_id_for(token)
    store.add_item(pid, "card:c1", g.now())
    joined = track_joiners(monkeypatch, game_module, 6)
    release = Event()
    calls = []
    calculate = g._calculate_board

    def calculate_blocked(require_account):
        calls.append(require_account)
        assert release.wait(5)
        return calculate(require_account)

    monkeypatch.setattr(g, "_calculate_board", calculate_blocked)
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = [pool.submit(g.board, token, False) for _ in range(6)]
        try:
            joined.wait(timeout=5)
            assert calls == [False]
        finally:
            release.set()
        assert [request.result(5)["me"]["rank"] for request in pending] == [1] * 6
    assert g.board(token, True)["me"]["off"] == "account"
    assert g.board(token, False)["me"]["rank"] == 1
    assert calls == [False, True]
    store.close()


def test_a_board_that_failed_is_worked_out_again_by_the_next_request(monkeypatch):
    store = Store()
    g = Game(store, tiny_manifest(), now=Clock())
    token = "board-perf-token-2"
    store.add_item(player_id_for(token), "card:c1", g.now())
    calculate = g._calculate_board
    fail = [True]

    def flaky(require_account):
        if fail.pop():
            raise sqlite3.OperationalError("database is locked")
        return calculate(require_account)

    monkeypatch.setattr(g, "_calculate_board", flaky)
    with pytest.raises(sqlite3.OperationalError):
        g.board(token, False)
    assert g._board_pending == {}
    fail.append(False)
    assert g.board(token, False)["me"]["rank"] == 1
    store.close()


@pytest.mark.parametrize("available", [True, False])
def test_same_token_accounts_share_the_first_success_or_failure(monkeypatch, available):
    joined = track_joiners(monkeypatch, accounts_module, 6)
    release = Event()
    calls = []

    def fetch(_url, token):
        calls.append(token)
        assert release.wait(5)
        if not available:
            raise OSError("upstream offline")
        return 200, {"user": {"id": "u"}}

    accounts = MainAccounts("https://main.test", fetch)
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = [pool.submit(accounts.user_for, "same-token") for _ in range(6)]
        try:
            joined.wait(timeout=5)
            assert calls == ["same-token"]
        finally:
            release.set()
        for request in pending:
            if available:
                assert request.result(5) == {"id": "u"}
            else:
                with pytest.raises(GameError) as exc:
                    request.result(5)
                assert exc.value.code == "account_unavailable"
    assert calls == ["same-token"]


# ------------------------------------------------------------------ the main site over HTTP
class Upstream:
    """A local HTTP server answering every GET with a user; [close_after] answers close their connection."""

    def __init__(self, close_after=(), user="local"):
        self.sockets = []
        self.requests = []
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                upstream.sockets.append(self.connection)
                upstream.requests.append((self.path, self.headers["Authorization"], self.headers["X-Game-Key"]))
                body = json.dumps({"user": {"id": user}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                if len(upstream.requests) in close_after:
                    self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01})

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()


def test_account_http_reuses_sockets_and_reconnects_after_a_close(monkeypatch):
    without_proxies(monkeypatch)
    monkeypatch.setattr(accounts_module, "_idle", type(accounts_module._idle)())
    with Upstream(close_after=(2,)) as up:
        url = f"http://127.0.0.1:{up.port}/api/auth/me"
        for _ in range(3):
            assert http_me(url, "token", "key") == (200, {"user": {"id": "local"}})
        assert up.sockets[0] is up.sockets[1] and up.sockets[1] is not up.sockets[2]
        assert up.requests == [("/api/auth/me", "Bearer token", "key")] * 3


def test_account_http_goes_through_the_proxy_the_environment_names(monkeypatch):
    clear_proxy_env(monkeypatch)
    with Upstream(user="via-proxy") as proxy:
        monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{proxy.port}")
        # The main site's host is only reachable through the proxy (it does not resolve here).
        assert http_me("http://main.invalid/api/auth/me", "token", "key") == (200, {"user": {"id": "via-proxy"}})
        assert proxy.requests == [("http://main.invalid/api/auth/me", "Bearer token", "key")]


def test_account_http_connects_itself_to_a_host_the_proxy_leaves_out(monkeypatch):
    clear_proxy_env(monkeypatch)
    monkeypatch.setattr(accounts_module, "_idle", type(accounts_module._idle)())
    with Upstream() as up:
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")  # nothing listens there
        monkeypatch.setenv("no_proxy", "127.0.0.1")
        url = f"http://127.0.0.1:{up.port}/api/auth/me"
        for _ in range(2):
            assert http_me(url, "token") == (200, {"user": {"id": "local"}})
        assert up.sockets[0] is up.sockets[1]


def test_account_http_keeps_its_connections_after_urlopen_made_its_own_opener(monkeypatch):
    without_proxies(monkeypatch)
    monkeypatch.setattr(accounts_module, "_idle", type(accounts_module._idle)())
    # urlopen keeps the opener it builds on its first call (another module's request, say).
    monkeypatch.setattr(urllib.request, "_opener", urllib.request.build_opener())
    with Upstream() as up:
        url = f"http://127.0.0.1:{up.port}/api/auth/me"
        for _ in range(2):
            assert http_me(url, "token") == (200, {"user": {"id": "local"}})
        assert up.sockets[0] is up.sockets[1]


def test_account_http_uses_an_installed_opener(monkeypatch):
    without_proxies(monkeypatch)
    seen = []

    class Recording(urllib.request.BaseHandler):
        def http_request(self, req):
            seen.append(req.full_url)
            return req

    monkeypatch.setattr(urllib.request, "_opener", urllib.request.build_opener(Recording()))
    with Upstream() as up:
        url = f"http://127.0.0.1:{up.port}/api/auth/me"
        assert http_me(url, "token") == (200, {"user": {"id": "local"}})
    assert seen == [url]


# ------------------------------------------------------------------ requests waiting on the event loop
def test_admin_statistics_queue_before_the_player_worker_pool(monkeypatch):
    store = Store()
    game = Game(store, tiny_manifest(), now=Clock())
    monkeypatch.setattr(main, "game", game)
    monkeypatch.setattr(main, "ADMIN_KEY", "local-key")
    monkeypatch.setattr(main, "_admin_slots", asyncio.Semaphore(2))
    release = Event()
    entered = []

    def slow_stats(_days):
        entered.append(True)
        release.wait(5)
        return {"totals": {}}

    monkeypatch.setattr(game, "admin_stats", slow_stats)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            async def get_me():
                while len(entered) < 2:
                    await asyncio.sleep(.001)
                return await client.get("/api/me", headers={"X-Player-Token": "player-perf-token"})

            jobs = [asyncio.create_task(client.get("/admin/stats", headers={"X-Admin-Key": "local-key"}))
                    for _ in range(42)]
            try:
                me = await asyncio.wait_for(get_me(), timeout=2)
                assert me.status_code == 200
                assert len(entered) == 2
            finally:
                release.set()
                answers = await asyncio.gather(*jobs)
        assert all(a.json()["totals"] == {"rooms": 0, "online": 0} for a in answers)

    main.manager.rooms.clear()
    asyncio.run(run())
    store.close()


@pytest.fixture()
def signed_in(monkeypatch):
    """A game with dou dizhu, the main site's account of alice cached, and no upstream slot free."""
    g = Game(Store(), Manifest.load(), rng=SeqRng(.5), now=Clock())
    fake = FakeMain()
    accounts = MainAccounts("https://main.test/api/", fake, lambda: 0.0)
    pid = save(g, "alice")
    g.store.link_account(USERS["tok-alice"]["id"], pid, g.now())
    assert accounts.user_for("tok-alice")["id"] == USERS["tok-alice"]["id"]
    monkeypatch.setattr(main, "game", g)
    monkeypatch.setattr(main, "accounts", accounts)
    monkeypatch.setattr(main, "_account_slots", asyncio.Semaphore(0))
    main.manager.rooms.clear()
    main.tables.clear()
    yield g, fake, pid
    main.manager.rooms.clear()
    main.tables.clear()


def test_http_account_reads_with_a_cached_answer_need_no_upstream_slot(signed_in):
    g, fake, pid = signed_in

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            bearer = {"Authorization": "Bearer tok-alice"}
            account = await asyncio.wait_for(client.get("/api/account", headers=bearer), timeout=2)
            assert account.status_code == 200 and account.json()["user"]["username"] == "alice"
            rooms = await asyncio.wait_for(client.get("/rooms", headers=bearer), timeout=2)
            assert rooms.json() == {"rooms": []}
            linked = await asyncio.wait_for(client.post("/api/account/link", headers=bearer), timeout=2)
            assert linked.json()["save"] == g.save_summary(pid)

    asyncio.run(run())
    assert fake.calls == 1


def test_room_connections_with_a_cached_account_need_no_upstream_slot(signed_in):
    g, fake, pid = signed_in
    with TestClient(main.app) as c:
        with c.websocket_connect("/ws") as room, c.websocket_connect("/ws") as ddz:
            room.send_json({"type": "join", "room": "r1", "nick": "alice", "accountToken": "tok-alice"})
            joined = room.receive_json()
            assert joined["type"] == "joined"
            assert main.manager.rooms["r1"].peers[joined["you"]].token == pid
            ddz.send_json({"type": "ddz_hello", "nick": "alice", "token": tok("nobody"), "accountToken": "tok-alice"})
            while (m := ddz.receive_json())["type"] != "ddz_ready":
                pass
            assert [p.token for p in main.tables.lobby.values()] == [pid]
    assert fake.calls == 1


def test_manifest_conditional_response_reuses_its_etag():
    client = TestClient(main.app)
    original = client.get("/api/manifest")
    tag = original.headers["etag"]
    assert original.json() == main.manifest.data
    assert original.headers["cache-control"] == "public, no-cache"
    cached = client.get("/api/manifest", headers={"If-None-Match": f'"unrelated", W/{tag}'})
    assert cached.status_code == 304 and cached.content == b""
    assert cached.headers["etag"] == tag
    assert client.get("/api/manifest", headers={"If-None-Match": '"unrelated"'}).status_code == 200
