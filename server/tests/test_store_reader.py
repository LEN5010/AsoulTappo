"""The admin pages' statistics read a database file through a read-only connection of their own."""
import threading

import pytest

from app import analytics
from app.cards import DropConfig
from app.game import Game, day_of
from app.store import DAY_OFFSET, Store

from fixtures import Clock, SeqRng, tiny_manifest

# Every Store method the admin statistics call, with arguments that reach the rows made in `game` below.
def calls(g):
    today = day_of(g.now())
    cards = [f"card:{cid}" for cid in g.manifest.cards]
    return {
        "totals": (today,), "daily": ("2000-01-01", DAY_OFFSET), "card_counts": (cards, cards[-1:]),
        "ledger_since": ("2000-01-01",), "retention": ("2000-01-01", DAY_OFFSET, (1, 3, 7)),
        "active_saves": ("2000-01-01",), "drops_by_day": (0, DAY_OFFSET), "room_samples": (0,),
        "daily_counts": ("",), "duels_by_day": (0, DAY_OFFSET), "ledger_by_day": ("2000-01-01", "tap"),
        "tap_flags_of": (today, 50), "top_tappers": (today, 50), "ledger_day": (today,),
        "ddz_winnings": (0, g.now() + 86400), "coin_ledger_by_day": ("2000-01-01",),
    }


@pytest.fixture()
def game(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    g = Game(store, tiny_manifest(), DropConfig(max_taps_per_sec=10**5), SeqRng(0.0), Clock())
    tokens = [f"reader-token-{n:04d}" for n in range(4)]
    for n, token in enumerate(tokens):
        g.status(token)
        g.now.t += 1
        g.report_activity(token, 20 + n, f"reader-session-{n:04d}", 1)
        g.resonate(token, 3)
        g.now.t += 86400 * (n % 2)
    # taps on the last day too, for the day's tap lists
    g.now.t += 1
    g.report_activity(tokens[1], 15, "reader-session-0001", 2)
    pids = [g.status(t)["player"] for t in tokens]
    store.link_account("u-1", pids[0], g.now())
    store.add_tap_flags(day_of(g.now()), pids[1], dropped=3, server=1, auto=2)
    store.add_room_sample(int(g.now()) // 60 * 60, {"rooms": 1, "members": 2, "saves": 2, "largest": 2, "public": 0})
    store.add_daily_counts({(day_of(g.now()), "poke"): 4})
    store.add_coin_ledger(pids[2], day_of(g.now()), "gift", 3)
    duel = store.add_duel(pids[0], pids[1], 150, 250, day_of(g.now()), g.now())
    store.close_duel(duel, "won", pids[0], g.now())
    ddz = store.add_ddz_game(pids[:3], 10, 480, day_of(g.now()), g.now())
    store.close_ddz_game(ddz, "settled", 0, 2, 4, g.now())
    store.set_ddz_deltas(ddz, [36, -20, -20])
    yield g
    store.close()


def everything(g):
    out = {name: getattr(g.store, name)(*args) for name, args in calls(g).items()}
    out["admin_stats"] = g.admin_stats(7)
    out["admin_economy"] = g.admin_economy(7)
    out["insights"] = analytics.insights(g, 7)
    out["online"] = analytics.online(g, 7, {})
    out["anomalies"] = analytics.anomalies(g, None)
    return out


def test_the_statistics_read_the_same_as_on_the_main_connection(game):
    assert game.store._reader is not None
    mine = everything(game)
    # the rows made above all show up
    assert mine["totals"] == {"saves": 4, "linked": 1, "activeToday": mine["totals"]["activeToday"]}
    assert [name for name in calls(game) if not mine[name]] == []
    reader, game.store._reader = game.store._reader, None
    try:
        assert everything(game) == mine
    finally:
        game.store._reader = reader


def test_memory_databases_keep_one_connection():
    assert Store(":memory:")._reader is None


def _in_open_transaction(store, ready, release):
    """Holds Store._lock in a transaction with one save written and not yet committed."""
    with store.transaction() as st:
        st.get_player("f" * 16, 0.0)
        ready.set()
        release.wait(10)


def test_the_statistics_answer_while_a_transaction_holds_the_lock(game):
    store = game.store
    ready, release = threading.Event(), threading.Event()
    writer = threading.Thread(target=_in_open_transaction, args=(store, ready, release))
    writer.start()
    try:
        assert ready.wait(5)
        got = {}

        def read():
            got.update(everything(game))

        reader = threading.Thread(target=read)
        reader.start()
        reader.join(5)
        assert not reader.is_alive(), "a statistic waited for the transaction"
        # the save written in the open transaction is not there yet
        assert got["totals"]["saves"] == 4
    finally:
        release.set()
        writer.join(5)
    assert store.totals(day_of(game.now()))["saves"] == 5


def test_without_the_reader_the_same_read_waits_for_the_lock(game):
    """What the reader changes: on the main connection the read waits until the transaction ends."""
    store = game.store
    store._reader = None
    ready, release = threading.Event(), threading.Event()
    writer = threading.Thread(target=_in_open_transaction, args=(store, ready, release))
    writer.start()
    assert ready.wait(5)
    reader = threading.Thread(target=store.totals, args=(day_of(game.now()),))
    reader.start()
    reader.join(0.3)
    waited = reader.is_alive()
    release.set()
    writer.join(5)
    reader.join(5)
    assert waited
