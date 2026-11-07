from concurrent.futures import ThreadPoolExecutor

from app.game import Game
from app.store import Store
from fixtures import Clock, tiny_manifest

TOKEN = "audit-player-token-0001"


def make(path=":memory:"):
    clock = Clock()
    game = Game(Store(str(path)), tiny_manifest(), now=clock)
    game.status(TOKEN)
    return game, clock


def test_fixed_time_and_new_sessions_do_not_create_rate_credit():
    game, clock = make()
    for i in range(40):
        result = game.report_activity(TOKEN, 5000, f"session-{i}", 1)
    assert result["totals"]["taps"] == 0
    clock.t += 1
    for i in range(40):
        result = game.report_activity(TOKEN, 5000, f"session-{i}", 2)
    assert result["totals"]["taps"] == 15


def test_fractional_credit_is_independent_of_batch_count():
    split, split_clock = make()
    whole, whole_clock = make()
    for _ in range(4):
        split_clock.t += 0.25
        split.report_activity(TOKEN, 5000)
    whole_clock.t += 1
    whole.report_activity(TOKEN, 5000)
    assert split.status(TOKEN)["totals"]["taps"] == whole.status(TOKEN)["totals"]["taps"] == 15


def test_first_twenty_second_batch_is_fully_credited():
    game, clock = make()
    clock.t += 20
    assert game.report_activity(TOKEN, 200)["credited"] == 200


def test_replay_does_not_change_progress_even_after_restart(tmp_path):
    path = tmp_path / "progress.db"
    game, clock = make(path)
    clock.t += 40
    first = game.report_activity(TOKEN, 600, "session", 1)
    game.store.close()
    game = Game(Store(str(path)), tiny_manifest(), now=clock)
    clock.t += 60
    replay = game.report_activity(TOKEN, 600, "session", 1)
    assert replay["totals"] == first["totals"]
    assert replay["totals"]["taps"] == first["totals"]["taps"] == 600
    assert replay["credited"] == 0
    assert game.report_activity(TOKEN, 10, "session", 2)["credited"] == 10


def test_concurrent_duplicate_batches_commit_once():
    game, clock = make()
    clock.t += 20
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: game.report_activity(TOKEN, 200, "session", 1), range(4)))
    assert game.status(TOKEN)["totals"]["taps"] == 200


def test_sequence_and_budget_rollback_with_progress(monkeypatch):
    game, clock = make()
    clock.t += 20
    original = game.store.save_activity_sequence

    def fail(*args):
        original(*args)
        raise RuntimeError("transaction interrupted")

    monkeypatch.setattr(game.store, "save_activity_sequence", fail)
    import pytest
    with pytest.raises(RuntimeError):
        game.report_activity(TOKEN, 200, "session", 1)
    monkeypatch.setattr(game.store, "save_activity_sequence", original)
    assert game.report_activity(TOKEN, 200, "session", 1)["credited"] == 200
    assert game.status(TOKEN)["totals"]["taps"] == 200


def test_concurrent_sessions_share_one_budget_per_save():
    game, clock = make()
    clock.t += 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: game.report_activity(TOKEN, 5000, f"conn-{i}", 1), range(16)))
    assert game.status(TOKEN)["totals"]["taps"] == 15
