from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from app.store import STARTER_SHARDS, Store, day_of


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "monitor_server.py"
SPEC = importlib.util.spec_from_file_location("monitor_server", SCRIPT)
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)

# Three minutes before midnight in China.
NOW = datetime(2026, 11, 19, 15, 57, tzinfo=timezone.utc).timestamp()
OK = (0, 0)


class Watcher:
    def __init__(self, tmp_path):
        self.db = tmp_path / "watch ?#.db"
        self.state = tmp_path / "state.json"
        self.now = NOW
        self.env = {
            "ASOULTAPPO_MONITOR_DB": str(self.db),
            "ASOULTAPPO_MONITOR_STATE": str(self.state),
            "ASOULTAPPO_MONITOR_URL": "http://localhost:8000/",
        }
        self.mail = []
        self.mail_error = None

    def run(self, *arguments, probes=(OK, OK, OK)):
        clock = 0.0
        readings = iter(probes)
        self.sleeps = []
        self.requests = []

        def sleep(seconds):
            nonlocal clock
            clock += seconds
            self.sleeps.append(seconds)

        def open_probe(url, *, timeout):
            nonlocal clock
            self.requests.append((url, timeout, clock))
            elapsed, result = next(readings)
            clock += elapsed
            if isinstance(result, Exception):
                raise result
            if isinstance(result, bytes):
                return io.BytesIO(result)
            return io.BytesIO(json.dumps({"status": "ok", "waited": result}).encode())

        return monitor.main(arguments, environ=self.env, clock=lambda: self.now, monotonic=lambda: clock,
                            sleep=sleep, opener=open_probe, mail_sender=self.send_mail)

    def send_mail(self, subject, body, **kwargs):
        self.mail.append((subject, body))
        if self.mail_error:
            raise self.mail_error

    def enable_mail(self):
        self.env.update(ASOULTAPPO_MONITOR_RESEND_KEY="test-key", ASOULTAPPO_MONITOR_FROM="from@example.test",
                        ASOULTAPPO_MONITOR_TO="to@example.test")


@pytest.fixture
def watcher(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda path: SimpleNamespace(free=3_000_000_000))
    return Watcher(tmp_path)


@pytest.fixture
def store(watcher):
    db = Store(str(watcher.db))
    yield db
    db.close()


@pytest.mark.parametrize(("recent", "hour", "alerts"), [(39, 119, False), (40, 119, True), (39, 120, True)])
def test_new_saves(watcher, store, capsys, recent, hour, alerts):
    with store.transaction():
        for number in range(hour):
            age = 600 if number < recent else 3600
            store.get_player(f"save-{number}", NOW - age)
        store.get_player("old", NOW - 3601)
        store.get_player("future", NOW + 1)

    assert watcher.run() == 0
    output = capsys.readouterr().out
    if alerts:
        assert f"异常：新增存档，10 分钟 {recent} 个，阈值 ≥ 40。60 分钟 {hour} 个，阈值 ≥ 120" in output
    else:
        assert output == "巡检完成，异常 0 项\n"
    assert "save-" not in output
    assert watcher.mail == []


@pytest.mark.parametrize(("readings", "alerts"), [
    (((3, 3), (0, 3.1), OK), False),
    (((3.1, 0), (0, 3.2), OK), True),
    (((10, TimeoutError()), (0, b"invalid json"), OK), True),
])
def test_stalls(watcher, store, capsys, readings, alerts):
    assert watcher.run(probes=readings) == 0
    output = capsys.readouterr().out
    assert ("异常：存储探针，慢或失败 2/3 次" in output) is alerts
    assert watcher.sleeps == [5, 5]
    assert watcher.requests == [
        ("http://localhost:8000/healthz/store", 10, 0),
        ("http://localhost:8000/healthz/store", 10, 5 + readings[0][0]),
        ("http://localhost:8000/healthz/store", 10, 10 + readings[0][0] + readings[1][0]),
    ]


@pytest.mark.parametrize(("growth", "free", "alerts"), [
    (50_000_000, 3_000_000_000, False),
    (51_000_000, 3_000_000_000, True),
    (0, 2_900_000_000, True),
])
def test_size_includes_wal_and_uses_oldest_recent_sample(watcher, monkeypatch, growth, free, alerts):
    Store(str(watcher.db)).close()
    initial_size = watcher.db.stat().st_size
    with Path(str(watcher.db) + "-wal").open("wb") as wal:
        wal.truncate(growth)
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda path: SimpleNamespace(free=free))
    args = monitor.parse_args([], watcher.env)
    state = {"sizes": [[NOW - 3601, 0], [NOW - 500, initial_size], [NOW - 300, initial_size + growth]]}

    problem = monitor.check_size(args, state, NOW)

    assert bool(problem) is alerts
    assert state["sizes"][0] == [NOW - 500, initial_size]
    assert state["sizes"][-1] == [NOW, initial_size + growth]
    if growth > 50_000_000:
        assert "增长 51.00 MB，阈值 > 50 MB" in problem
    if free < 3_000_000_000:
        assert "剩余 2.90 GB，阈值 < 3 GB" in problem


@pytest.mark.parametrize("excess", [0, 1])
def test_shards_same_day(watcher, store, capsys, excess):
    day = day_of(NOW)
    store.add_ledger("private-id", day, "tap", 500)
    store.add_ledger("private-id", day, "draw", -1000)
    store.add_ledger("private-id", day_of(NOW - 86400), "old", 9_000_000)
    watcher.run()
    capsys.readouterr()

    watcher.now += 60
    store.add_ledger("private-id", day, "tap", 1_099_999 + excess)
    store.add_ledger("private-id", day, "starter", 500_000)
    store.add_ledger("private-id", day, "checkin", 400_000)
    store.add_ledger("private-id", day, "cheer", 1)
    store.add_ledger("private-id", day, "draw", -9_000_000)
    assert watcher.run() == 0
    output = capsys.readouterr().out
    if excess:
        assert "本次增加 2000001，阈值 > 2000000。tap +1100000，starter +500000，checkin +400000" in output
        assert all(value not in output for value in ("private-id", "draw", "old", "cheer"))
    else:
        assert output == "巡检完成，异常 0 项\n"
    assert set(monitor.load_state(watcher.state)["shards"]["sums"]) == {"tap", "starter", "checkin", "cheer"}


def test_shard_rollover_uses_china_day(watcher, store, capsys):
    store.add_ledger("save", "2026-11-19", "tap", 5_000_000)
    watcher.run()
    capsys.readouterr()
    watcher.now += 180
    store.add_ledger("save", "2026-11-20", "starter", 3_000_000)

    assert watcher.run() == 0
    assert capsys.readouterr().out == "巡检完成，异常 0 项\n"
    assert monitor.load_state(watcher.state)["shards"] == {"day": "2026-11-20", "sums": {"starter": 3_000_000}}
    store.add_ledger("save", "2026-11-20", "starter", 2_000_001)
    watcher.run()
    assert "异常：碎片发放" in capsys.readouterr().out


def test_reminder_and_recovery(watcher, store, capsys):
    watcher.enable_mail()
    stalled = ((4, 0), (4, 0), OK)
    watcher.run(probes=stalled)
    assert watcher.mail[-1][1].startswith("异常：存储探针")
    watcher.now += 3599
    watcher.run(probes=stalled)
    assert len(watcher.mail) == 1
    watcher.now += 1
    watcher.run(probes=stalled)
    assert len(watcher.mail) == 2
    assert watcher.mail[-1][1].startswith("持续异常：存储探针")
    watcher.now += 300
    watcher.run()
    watcher.run()
    assert len(watcher.mail) == 3
    assert watcher.mail[-1][1] == "恢复：存储探针"
    watcher.run(probes=stalled)
    assert len(watcher.mail) == 4
    assert watcher.mail[-1][1].startswith("异常：存储探针")


def test_missing_database_is_reported_and_other_checks_run(watcher, capsys):
    assert watcher.run(probes=((4, 0), (4, 0), OK)) == 0
    output = capsys.readouterr().out
    assert "异常：数据库读取，读取失败，锁等待上限 2 秒" in output
    assert "异常：存储探针" in output
    assert not watcher.db.exists()
    Store(str(watcher.db)).close()
    watcher.run()
    assert "恢复：数据库读取" in capsys.readouterr().out


def test_locked_database_keeps_last_shard_sample(watcher, monkeypatch, capsys):
    store = Store(str(watcher.db))
    store.add_ledger("save", day_of(NOW), "tap", 200)
    store.close()
    watcher.run()
    capsys.readouterr()
    baseline = monitor.load_state(watcher.state)["shards"]

    real_connect = sqlite3.connect

    def connect(database, *, uri, timeout):
        assert timeout == 2
        return real_connect(database, uri=uri, timeout=0)

    with closing(real_connect(watcher.db)) as writer:
        writer.execute("PRAGMA journal_mode=DELETE")
        writer.execute("BEGIN EXCLUSIVE")
        monkeypatch.setattr(monitor.sqlite3, "connect", connect)
        assert watcher.run() == 0

    assert "异常：数据库读取" in capsys.readouterr().out
    assert monitor.load_state(watcher.state)["shards"] == baseline


def test_database_read_is_read_only_and_uses_available_indexes(watcher, store, monkeypatch):
    store.get_player("recent", NOW - 300)
    day = day_of(NOW)
    expected = (1, 1, {"starter": STARTER_SHARDS})
    real_connect = sqlite3.connect
    statements = []
    queries = []

    def connect(database, **options):
        assert database == watcher.db.as_uri() + "?mode=ro"
        assert options == {"uri": True, "timeout": 2}
        db = real_connect(database, **options)
        db.set_trace_callback(statements.append)
        return db

    # Capture the real statements for query-plan checks.
    monkeypatch.setattr(monitor.sqlite3, "connect", connect)
    assert monitor.read_database(watcher.db, NOW, day) == expected
    assert statements[0] == "PRAGMA query_only=ON"
    assert len(statements) == 3
    for statement in statements[1:]:
        plan = store._db.execute("EXPLAIN QUERY PLAN " + statement).fetchall()
        queries.append(plan[0][3])
    assert "SEARCH" in queries[0] and "COVERING INDEX players_created" in queries[0]
    assert "SEARCH" in queries[1] and "shard_ledger" in queries[1] and "(day=?)" in queries[1]
    store._db.execute("DROP INDEX players_created")
    assert monitor.read_database(watcher.db, NOW, day) == expected


@pytest.mark.parametrize("corrupt", ["{broken", "[]", '{"sizes":[null]}', '{"alerts":{"x":null}}'])
def test_corrupt_state_recovers_and_no_key_prints(watcher, store, capsys, corrupt):
    watcher.state.write_text(corrupt, encoding="utf-8")
    assert watcher.run("--saves-10m", "0") == 0
    assert "异常：新增存档" in capsys.readouterr().out
    assert watcher.mail == []
    assert monitor.load_state(watcher.state)["alerts"]["新增存档"]["pending"] == []


def test_failed_send_retries_even_if_check_has_recovered(watcher, store, capsys):
    watcher.enable_mail()
    watcher.mail_error = HTTPError("https://api.resend.com/emails", 503, "unavailable", {}, io.BytesIO())
    assert watcher.run("--saves-10m", "0") == 0
    assert "告警邮件发送失败，HTTP 503，下次重试" in capsys.readouterr().out
    first_alert = watcher.mail[0][1]
    assert monitor.load_state(watcher.state)["alerts"]["新增存档"]["pending"] == [first_alert]

    watcher.mail_error = None
    watcher.now += 300
    assert watcher.run() == 0
    assert watcher.mail[1][1] == first_alert + "\n恢复：新增存档"
    assert monitor.load_state(watcher.state)["alerts"] == {}
    watcher.run()
    assert len(watcher.mail) == 2


@pytest.mark.parametrize("existing", [False, True])
def test_dry_run_prints_and_does_not_write(watcher, store, capsys, existing):
    if existing:
        watcher.state.write_bytes(b"{}\n")
    watcher.enable_mail()
    initial_files = set(watcher.db.parent.iterdir())
    assert watcher.run("--dry-run", "--saves-10m", "0", "--free-gb", "4", "--stall-seconds", "0",
                       "--stall-probes", "1", probes=((1, 0), OK, OK)) == 0
    assert watcher.mail == []
    assert set(watcher.db.parent.iterdir()) == initial_files
    if existing:
        assert watcher.state.read_bytes() == b"{}\n"
    output = capsys.readouterr().out
    assert "异常：新增存档" in output
    assert "异常：数据库容量" in output
    assert "异常：存储探针" in output


def test_resend_request_uses_plain_text():
    def open_resend(request, *, timeout):
        assert request.full_url == "https://api.resend.com/emails"
        assert request.get_method() == "POST"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["Content-type"] == "application/json"
        assert request.headers["User-agent"] == "asoultappo-monitor"
        assert timeout == 10
        assert json.loads(request.data) == {
            "from": "from@example.test", "to": ["to@example.test"], "subject": monitor.SUBJECT, "text": "恢复：存储探针",
        }
        return io.BytesIO()

    monitor.send_resend(monitor.SUBJECT, "恢复：存储探针", key="test-key", sender="from@example.test",
                        recipient="to@example.test", opener=open_resend)
