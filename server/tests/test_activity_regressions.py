import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest

from app import guard as guard_file
from app.game import Game
from app.guard import Batch, Guard
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
    assert result["credited"] == 0 and result["tapCooldown"] == 60 and result["autoStrikes"] == 0
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


# ------------------------------------------------------------------ the guard
class Streak(Guard):
    """A stand-in for the private rules: input counts as automatic for `span` seconds once `need` batches in a row
    were all sent by other software."""

    def __init__(self, need=3, span=1800.0):
        self.need, self.span = need, span
        self.seen = []

    def judge(self, batch, notes):
        self.seen.append(batch)
        whole = batch.taps > 0 and batch.injected == batch.taps
        notes["run"] = notes.get("run", 0) + 1 if whole else 0
        return self.span if notes["run"] >= self.need else 0.0


def make_guarded(guard, path=":memory:"):
    clock = Clock()
    game = Game(Store(str(path)), tiny_manifest(), now=clock, guard=guard)
    game.status(TOKEN)
    return game, clock


def send(game, clock, taps, injected, sequence, session="s", every=20.0):
    clock.t += every
    return game.report_activity(TOKEN, taps, session, sequence, injected=injected)


def test_the_guard_gets_the_headers_of_a_batch_but_not_of_what_rooms_see():
    guard = Streak()
    game, clock = make_guarded(guard)
    clock.t += 20
    game.report_activity(TOKEN, 10, "s", 1, injected=2, headers={"origin": "o"})
    assert guard.seen[0].headers == {"origin": "o"} and guard.seen[1].headers == {}
    send(game, clock, 10, None, 2)
    assert guard.seen[2].headers == {}


def test_no_guard_judges_nothing():
    game, clock = make()
    result = None
    for i in range(1, 40):
        result = send(game, clock, 160, 160, i)
    assert result["autoInput"] == 0 and result["tapCooldown"] == 0 and result["credited"] == 160
    assert not game.auto_input(result["player"])


def test_two_callers_can_read_an_expired_room_guard_result():
    game, clock = make()
    pid = game.status(TOKEN)["player"]
    game._auto[pid] = clock.t - 1
    ready = Barrier(2)

    def shared_clock():
        ready.wait(timeout=5)
        return clock.t

    game.now = shared_clock
    with ThreadPoolExecutor(max_workers=2) as threads:
        checks = [threads.submit(game.auto_input, pid) for _ in range(2)]
        assert [check.result() for check in checks] == [False, False]
    assert pid not in game._auto


def test_the_guard_sees_each_batch_as_sent_and_keeps_notes_per_session():
    guard = Streak()
    game, clock = make_guarded(guard)
    pid = game.status(TOKEN)["player"]
    send(game, clock, 40, None, 1)
    send(game, clock, 40, 55, 2)       # more than the taps: taken as all of them
    send(game, clock, 40, 40, 1, "other", every=7.0)
    # A client that tells injected presses apart has the rest judged too, as the stream its rooms are shown.
    assert [(b.taps, b.injected, b.elapsed) for b in guard.seen] == [
        (40, None, 0.0), (40, 40, 20.0), (0, 0, 20.0), (40, 40, 0.0), (0, 0, 0.0)]
    kept = {"v": 2, "all": {"run": 1}, "shown": {"run": 0}}
    assert json.loads(game.store.activity_session(pid, "s")["guard"]) == kept
    assert json.loads(game.store.activity_session(pid, "other")["guard"]) == kept
    # A batch sent again is not judged twice.
    game.report_activity(TOKEN, 40, "s", 2, injected=40)
    assert len(guard.seen) == 5


def test_input_judged_automatic_is_flagged_and_still_paid():
    game, clock = make_guarded(Streak())
    pid = game.status(TOKEN)["player"]
    assert send(game, clock, 40, 40, 1)["autoInput"] == 0
    assert send(game, clock, 40, 40, 2)["autoInput"] == 0
    result = send(game, clock, 40, 40, 3)
    assert result["autoInput"] == 1800 and result["tapCooldown"] == 0 and result["credited"] == 40
    # Its client kept every one of those presses out of the room, so the room has nothing of it to hide.
    assert not game.auto_input(pid)
    # Each further batch judged automatic keeps it going; the day's flags count the start once.
    assert send(game, clock, 40, 40, 4)["autoInput"] == 1800
    flags = game.store.tap_flags_of(day_of_clock(clock), 10)
    assert [(r["player_id"], r["auto"], r["injected"]) for r in flags] == [(pid, 1, 160)]
    # A hand again: it runs out half an hour after the last such batch, and a new run counts as a new start.
    result = send(game, clock, 40, 0, 5)
    assert result["autoInput"] == 1780
    clock.t += 1780
    assert game.status(TOKEN)["autoInput"] == 0 and not game.auto_input(pid)
    for i in range(6, 9):
        result = send(game, clock, 40, 40, i)
    assert result["autoInput"] == 1800
    assert game.store.tap_flags_of(day_of_clock(clock), 10)[0]["auto"] == 2


def test_automatic_input_is_remembered_across_a_restart(tmp_path):
    path = tmp_path / "game.db"
    game, clock = make_guarded(Busy(), path)
    pid = game.status(TOKEN)["player"]
    send(game, clock, 120, None, 1)
    assert game.auto_input(pid)
    game.store.close()
    again = Game(Store(str(path)), tiny_manifest(), now=clock, guard=Busy(at=10_000))
    assert again.status(TOKEN)["autoInput"] == 1800
    # Rooms hear of it with the save's next report.
    assert not again.auto_input(pid)
    clock.t += 20
    again.report_activity(TOKEN, 5, "s", 2)
    assert again.auto_input(pid)


def test_a_guard_that_fails_costs_no_taps_and_keeps_its_notes():
    class Broken(Streak):
        def judge(self, batch, notes):
            if batch.taps == 13:
                notes["half"] = "written"
                raise RuntimeError("bug")
            return super().judge(batch, notes)

    game, clock = make_guarded(Broken())
    pid = game.status(TOKEN)["player"]
    send(game, clock, 40, 40, 1)
    result = send(game, clock, 13, 13, 2)
    assert result["credited"] == 13 and result["autoInput"] == 0
    assert json.loads(game.store.activity_session(pid, "s")["guard"]) == {"v": 2, "all": {"run": 1}, "shown": {"run": 0}}


class Busy(Guard):
    """Another stand-in: a batch of `at` taps or more counts as automatic, whoever sent them."""

    def __init__(self, at=100, span=1800.0):
        self.at, self.span = at, span

    def judge(self, batch, notes):
        return self.span if batch.taps >= self.at else 0.0


def test_rooms_hide_a_save_only_while_what_they_are_shown_is_automatic():
    game, clock = make_guarded(Busy())
    pid = game.status(TOKEN)["player"]
    # 120 presses, 90 of them from other software: the status says so, the 30 the room is shown are a hand's.
    result = send(game, clock, 120, 90, 1)
    assert result["autoInput"] == 1800 and not game.auto_input(pid)
    # 120 presses none of which the system marked: the room is shown all of them.
    result = send(game, clock, 120, 0, 2)
    assert result["autoInput"] == 1800 and game.auto_input(pid)
    # It lasts as long as the judgement says, whatever the batches after it are.
    send(game, clock, 10, 0, 3)
    assert game.auto_input(pid)
    clock.t += 1800
    assert not game.auto_input(pid)


def test_a_client_that_cannot_tell_is_judged_once_for_both():
    game, clock = make_guarded(Busy())
    pid = game.status(TOKEN)["player"]
    result = send(game, clock, 120, None, 1)
    assert result["autoInput"] == 1800 and game.auto_input(pid)
    assert json.loads(game.store.activity_session(pid, "s")["guard"]) == {"v": 2, "all": {}, "shown": {}}


def test_notes_from_before_the_second_stream_are_read_as_the_first():
    guard = Streak(need=2)
    game, clock = make_guarded(guard)
    pid = game.status(TOKEN)["player"]
    send(game, clock, 40, 40, 1)
    with game.store.transaction() as st:
        row = st.activity_session(pid, "s")
        st.save_activity_sequence(pid, "s", row["sequence"], row["last_at"], row["fast_since"], '{"run":1}')
    assert send(game, clock, 40, 40, 2)["autoInput"] == 1800


def test_the_guard_file_is_loaded_by_path(tmp_path, monkeypatch):
    rules = tmp_path / "guard.py"
    rules.write_text("def judge(batch, notes):\n    notes['n'] = notes.get('n', 0) + 1\n"
                     "    return 60 if batch.taps > 100 else -5\n", encoding="utf-8")
    loaded = guard_file.load(rules)
    notes = {}
    assert loaded.judge(Batch(160, None, 20.0, 0.0), notes) == 60 and notes == {"n": 1}
    assert loaded.judge(Batch(10, None, 20.0, 0.0), notes) == 0
    assert loaded.seen is None
    monkeypatch.setenv(guard_file.ENV, str(rules))
    assert guard_file.load().judge(Batch(160, None, 20.0, 0.0), {}) == 60
    monkeypatch.delenv(guard_file.ENV)
    assert type(guard_file.load()) is Guard
    rules.write_text("calls = []\ndef judge(batch, notes):\n    return 0\n"
                     "def seen(*call):\n    calls.append(call)\n", encoding="utf-8")
    told = guard_file.load(rules)
    told.seen("save", "GET", "/api/me", {}, 1.0)
    assert told.seen.__globals__["calls"] == [("save", "GET", "/api/me", {}, 1.0)]
    (tmp_path / "empty.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="judge"):
        guard_file.load(tmp_path / "empty.py")


def day_of_clock(clock):
    from app.store import day_of
    return day_of(clock.t)


class ShownBreaks(Guard):
    """Fails on what a batch showed its rooms (no injected presses in it), judges the batch itself as Busy does."""

    def judge(self, batch, notes):
        if batch.injected == 0:
            raise ZeroDivisionError
        return 1800.0 if batch.taps >= 100 else 0.0


def test_a_rule_failing_on_what_rooms_were_shown_keeps_its_judgement_of_the_batch():
    game, clock = make_guarded(ShownBreaks())
    pid = game.status(TOKEN)["player"]
    result = send(game, clock, 120, 90, 1)
    assert result["autoInput"] == 1800 and result["credited"] > 0
    assert not game.auto_input(pid)


class Strikes(Streak):
    """The stand-in, giving a cooldown that doubles each `every` batches judged automatic."""

    def __init__(self, every=3, first=600.0):
        super().__init__(need=1)
        self.every, self.first = every, first

    def judge(self, batch, notes):
        span = super().judge(batch, notes)
        notes["hot"] = notes.get("hot", 0) + (1 if span else 0)
        return span

    def cooldown(self, batch, notes):
        if notes.get("hot", 0) // self.every <= notes.get("strikes", 0):
            return 0.0
        notes["strikes"] = notes.get("strikes", 0) + 1
        return self.first * 2 ** (notes["strikes"] - 1)


def test_the_guards_cooldown_stops_income_and_counts_a_strike_each_time():
    game, clock = make_guarded(Strikes())
    first = [send(game, clock, 40, 40, i) for i in (1, 2)]
    assert [r["credited"] for r in first] == [40, 40] and first[-1]["autoStrikes"] == 0
    # The third batch judged automatic draws the cooldown, and earns nothing itself.
    struck = send(game, clock, 40, 40, 3)
    assert (struck["credited"], struck["tapCooldown"], struck["autoStrikes"]) == (0, 600, 1)
    assert send(game, clock, 40, 0, 4)["credited"] == 0
    # Kept up through the cooldown: three more such batches, and the next one is twice as long.
    for i in (5, 6, 7):
        again = send(game, clock, 40, 40, i)
    assert (again["credited"], again["tapCooldown"], again["autoStrikes"]) == (0, 1200, 2)
    clock.t += 1200
    assert send(game, clock, 40, 0, 8, every=0.0)["credited"] == 40


def test_a_rule_file_may_name_a_cooldown(tmp_path):
    rules = tmp_path / "rules.py"
    rules.write_text("def judge(batch, notes):\n    return 60\n\ndef cooldown(batch, notes):\n    return -5 if batch.taps < 10 else 90\n")
    from app.guard import Batch, load
    guard = load(rules)
    assert guard.cooldown(Batch(3, None, 0.0, 0.0), {}) == 0.0
    assert guard.cooldown(Batch(30, None, 0.0, 0.0), {}) == 90.0
    rules.write_text("def judge(batch, notes):\n    return 60\n")
    assert load(rules).cooldown(Batch(30, None, 0.0, 0.0), {}) == 0.0


def test_auto_strikes_persist_across_a_restart_and_roll_at_china_midnight(tmp_path):
    path = tmp_path / "strikes.db"
    clock = Clock(datetime(2026, 11, 9, 15, 50, 0, tzinfo=timezone.utc).timestamp())
    game = Game(Store(str(path)), tiny_manifest(), now=clock, guard=Strikes())
    game.status(TOKEN)
    for i in (1, 2, 3):
        result = send(game, clock, 40, 40, i)
    assert result["autoStrikes"] == 1
    game.store.close()

    again = Game(Store(str(path)), tiny_manifest(), now=clock, guard=Strikes())
    assert again.status(TOKEN)["autoStrikes"] == 1
    for i in (4, 5, 6):
        result = send(again, clock, 40, 40, i)
    assert result["autoStrikes"] == 2

    # China midnight (16:00 UTC) starts a fresh day of strikes.
    clock.t += 600
    assert again.status(TOKEN)["autoStrikes"] == 0
    for i in (7, 8, 9):
        result = send(again, clock, 40, 40, i)
    assert result["autoStrikes"] == 1
    again.store.close()


def test_daily_rule_shares_only_accepted_batches_across_sessions_and_restarts(tmp_path):
    rules = tmp_path / "rules.py"
    rules.write_text(
        "def judge(batch, notes):\n    return 60 if batch.injected else 0\n"
        "def daily_cooldown(batch, judged, notes):\n"
        "    if judged and not batch.cooling:\n"
        "        notes['hits'] = notes.get('hits', 0) + 1\n"
        "        if notes['hits'] % 2 == 0:\n            return 90 * (1 + batch.strikes_today)\n"
        "    return 0\n"
    )
    path = tmp_path / "game.db"
    game, clock = make_guarded(guard_file.load(rules), path)
    first = send(game, clock, 30, 8, 1)
    assert first["credited"] == 30
    assert send(game, clock, 30, 8, 1)["credited"] == 0  # duplicate
    game.store.close()
    game = Game(Store(str(path)), tiny_manifest(), now=clock, guard=guard_file.load(rules))
    second = send(game, clock, 30, 8, 1, "new")
    assert (second["tapCooldown"], second["autoStrikes"], second["credited"]) == (90, 1, 0)
    send(game, clock, 30, 8, 2, "new")
    assert json.loads(game.store.guard_day(first["player"], day_of_clock(clock))) == {"hits": 2}
    assert send(game, clock, 30, 0, 3, "new", every=100)["credited"] == 30
    assert send(game, clock, 30, 8, 4, "new")["credited"] == 30
    assert send(game, clock, 30, 8, 2)["tapCooldown"] == 180
    tomorrow = send(game, clock, 30, 8, 3, every=86400)
    assert (tomorrow["tapCooldown"], tomorrow["autoStrikes"], tomorrow["credited"]) == (0, 0, 30)
