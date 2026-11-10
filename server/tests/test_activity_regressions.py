from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

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


def test_daily_taps_include_credit_beyond_the_income_cap():
    game, clock = make()
    clock.t += 20
    result = game.report_activity(TOKEN, 200, "typing", 1)
    assert result["credited"] == result["totals"]["taps"] == result["dailyTaps"]["count"] == 200
    assert result["income"]["taps"] == 120
    assert result["dailyTaps"]["day"] == result["income"]["day"]
    clock.t += 20
    assert game.report_activity(TOKEN, 50, "other-device", 1)["dailyTaps"]["count"] == 250


def test_daily_taps_roll_at_china_midnight_on_presence_and_activity():
    clock = Clock(datetime(2026, 11, 9, 15, 59, 20, tzinfo=timezone.utc).timestamp())
    game = Game(Store(), tiny_manifest(), now=clock)
    game.status(TOKEN)
    clock.t += 20
    assert game.report_activity(TOKEN, 200)["dailyTaps"] == {"day": "2026-11-09", "count": 200}
    clock.t += 20
    assert game.presence(TOKEN, "present")["dailyTaps"] == {"day": "2026-11-10", "count": 0}
    result = game.report_activity(TOKEN, 10)
    assert result["dailyTaps"] == {"day": "2026-11-10", "count": 10}
    assert result["totals"]["taps"] == 210


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
    assert replay["dailyTaps"] == first["dailyTaps"]
    assert replay["totals"]["taps"] == first["totals"]["taps"] == 600
    assert replay["credited"] == 0
    assert game.report_activity(TOKEN, 10, "session", 2)["credited"] == 10


def test_concurrent_duplicate_batches_commit_once():
    game, clock = make()
    clock.t += 20
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: game.report_activity(TOKEN, 200, "session", 1), range(4)))
    assert game.status(TOKEN)["totals"]["taps"] == 200
    assert game.status(TOKEN)["dailyTaps"]["count"] == 200


def test_sequence_and_budget_rollback_with_progress(monkeypatch):
    game, clock = make()
    clock.t += 20
    original = game.store.save_activity_budget

    def fail(*args):
        original(*args)
        raise RuntimeError("transaction interrupted")

    monkeypatch.setattr(game.store, "save_activity_budget", fail)
    import pytest
    with pytest.raises(RuntimeError):
        game.report_activity(TOKEN, 200, "session", 1)
    monkeypatch.setattr(game.store, "save_activity_budget", original)
    assert game.status(TOKEN)["dailyTaps"]["count"] == 0
    assert game.report_activity(TOKEN, 200, "session", 1)["credited"] == 200
    assert game.status(TOKEN)["totals"]["taps"] == 200
    assert game.status(TOKEN)["dailyTaps"]["count"] == 200


def test_concurrent_sessions_share_one_budget_per_save():
    game, clock = make()
    clock.t += 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: game.report_activity(TOKEN, 5000, f"conn-{i}", 1), range(16)))
    assert game.status(TOKEN)["totals"]["taps"] == 15


def test_input_too_fast_for_a_hand_sits_out_a_cooldown():
    game, clock = make()
    clock.t += 20
    game.report_activity(TOKEN, 300, "fast", 1)
    clock.t += 20
    result = game.report_activity(TOKEN, 300, "fast", 2)
    assert result["credited"] == 300 and result["tapCooldown"] == 0
    clock.t += 20
    # 15 a second for 40 seconds: the batch is dropped and pays nothing.
    shards = game.status(TOKEN)["shards"]
    result = game.report_activity(TOKEN, 300, "fast", 3)
    assert result["credited"] == 0 and result["tapCooldown"] == 60
    assert result["shards"] == shards
    clock.t += 30
    assert game.report_activity(TOKEN, 10, "other", 1)["credited"] == 0
    result = game.report_activity(TOKEN, 10, "fast", 4)
    assert result["credited"] == 0 and result["tapCooldown"] == 30
    clock.t += 30
    result = game.report_activity(TOKEN, 10, "fast", 5)
    assert result["credited"] == 10 and result["tapCooldown"] == 0


def test_a_fast_typist_keeps_counting():
    game, clock = make()
    for sequence in range(1, 7):
        clock.t += 20
        result = game.report_activity(TOKEN, 160, "typing", sequence)
        assert result["credited"] == 160 and result["tapCooldown"] == 0


def test_a_fast_burst_with_a_slow_batch_between_starts_over():
    game, clock = make()
    for sequence, taps in enumerate((300, 300, 40, 300), start=1):
        clock.t += 20
        result = game.report_activity(TOKEN, taps, "bursts", sequence)
    assert result["tapCooldown"] == 0 and result["credited"] == 300


def test_a_cooldown_the_client_reports_stops_paying():
    game, clock = make()
    clock.t += 20
    shards = game.report_activity(TOKEN, 300, "guarded", 1)["shards"]
    assert shards > 1600
    clock.t += 40
    result = game.report_activity(TOKEN, 100, "guarded", 2, cooldown=50)
    assert result["credited"] == 0 and result["tapCooldown"] == 50
    assert result["shards"] == shards
    clock.t += 20
    # Never longer than the server's own cooldown, and a shorter report does not cut one short.
    assert game.report_activity(TOKEN, 0, "guarded", 3, cooldown=3600)["tapCooldown"] == 60
    assert game.report_activity(TOKEN, 0, "other", 1, cooldown=5)["tapCooldown"] == 60


def test_sessions_silent_for_thirty_days_are_pruned():
    game, clock = make()
    pid = game.status(TOKEN)["player"]
    game.store.save_activity_sequence(pid, "before-last-at", 4)  # last_at 0, as rows written by older servers
    game.report_activity(TOKEN, 10, "old", 3)
    clock.t += 30 * 86400 - 1
    game.report_activity(TOKEN, 10, "recent", 2)
    clock.t += 2
    assert game.prune_activity_sessions() == 2
    assert game.store.activity_session(pid, "old")["sequence"] == 0
    assert game.store.activity_session(pid, "before-last-at")["sequence"] == 0
    assert game.store.activity_session(pid, "recent")["sequence"] == 2
    # A pruned session that reports again starts over.
    assert game.report_activity(TOKEN, 0, "old", 1)["credited"] == 0
    assert game.store.activity_session(pid, "old")["sequence"] == 1
