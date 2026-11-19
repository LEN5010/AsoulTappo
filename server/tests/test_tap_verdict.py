import json
from datetime import datetime, timezone

import pytest

from app.game import Game
from app.guard import FileGuard, Verdict, load
from app.store import Store, day_of
from fixtures import Clock, tiny_manifest

TOKEN = "tap-verdict-test-save"


def make_game(guard, clock=None):
    clock = clock or Clock()
    game = Game(Store(), tiny_manifest(), now=clock, guard=guard)
    pid = game.status(TOKEN)["player"]
    return game, clock, pid


def report(game, clock, sequence, taps=30):
    clock.t += 60
    return game.report_activity(TOKEN, taps, "test-session", sequence)


def test_file_verdict_withholds_with_the_same_accounting_as_a_cooldown(tmp_path):
    path = tmp_path / "rules.py"
    path.write_text(
        "from app.guard import Verdict\n"
        "def judge(batch, notes):\n    return 0\n"
        "def daily_cooldown(batch, judged, notes):\n"
        "    notes['batches'] = notes.get('batches', 0) + 1\n"
        "    return Verdict(withhold=True) if batch.sequence > 1 else 0\n"
    )
    game, clock, pid = make_game(load(path))
    first = report(game, clock, 1)
    store, today = game.store, day_of(clock())
    player = store.get_player(pid, clock())
    budget = store.activity_budget(pid)
    ledger = store.ledger_of(pid, [today])

    withheld = report(game, clock, 2, taps=50)

    assert (withheld["credited"], withheld["tapCooldown"], withheld["autoStrikes"]) == (0, 0, 0)
    assert "cheerTaps" not in withheld
    for key in ("totals", "dailyTaps", "income", "shards"):
        assert withheld[key] == first[key]
    assert store.get_player(pid, clock()) == player
    assert store.activity_budget(pid) == budget
    assert store.ledger_of(pid, [today]) == ledger
    flags = store.tap_flags_of(today, 10)[0]
    assert (flags["dropped"], flags["server_cooldowns"], flags["client_cooldowns"]) == (50, 0, 0)
    assert store.activity_session(pid, "test-session")["sequence"] == 2
    assert report(game, clock, 2)["credited"] == 0
    assert json.loads(store.guard_day(pid, today)) == {"batches": 2}
    assert store.tap_flags_of(today, 10)[0]["dropped"] == 50


def test_structured_cooldown_keeps_the_existing_strike_and_drop():
    guard = FileGuard(lambda batch, notes: 0, daily_cooldown=lambda *args: Verdict(cooldown=90, withhold=True))
    game, clock, _ = make_game(guard)

    result = report(game, clock, 1)

    assert (result["credited"], result["tapCooldown"], result["autoStrikes"]) == (0, 90, 1)
    flags = game.store.tap_flags_of(day_of(clock()), 10)[0]
    assert (flags["dropped"], flags["server_cooldowns"]) == (30, 1)


def test_void_day_reverses_only_earlier_tap_income_and_resets_at_china_midnight():
    verdict = Verdict()
    guard = FileGuard(lambda batch, notes: 0, daily_cooldown=lambda *args: verdict)
    midnight = datetime(2026, 11, 9, 16, tzinfo=timezone.utc).timestamp()
    game, clock, pid = make_game(guard, Clock(midnight - 600))
    store, today = game.store, day_of(clock())
    first = report(game, clock, 1)
    earned = store.ledger_amount(pid, today, "tap")
    assert earned > 0

    verdict = Verdict(void_day=True)
    second = report(game, clock, 2)
    assert second["credited"] == 30
    later = store.ledger_amount(pid, today, "tap") - earned
    assert later > 0
    assert second["shards"] == first["shards"] - earned + later
    assert store.ledger_amount(pid, today, "tap_void") == -earned

    verdict = Verdict(withhold=True, void_day=True)
    for seq in (3, 4):
        result = report(game, clock, seq)
        assert (result["credited"], result["shards"]) == (0, first["shards"] - earned)
    assert store.ledger_amount(pid, today, "tap_void") == -(earned + later)

    verdict = Verdict()
    last = report(game, clock, 5)
    assert last["shards"] > result["shards"]
    verdict = Verdict(withhold=True, void_day=True)
    clock.t = midnight - 60
    tomorrow = report(game, clock, 6)
    assert tomorrow["shards"] == last["shards"]
    assert tomorrow["dailyTaps"] == {"day": "2026-11-10", "count": 0}
    assert store.ledger_of(pid, ["2026-11-10"]) == []


def test_void_day_records_only_the_shards_it_can_take():
    verdict = Verdict()
    guard = FileGuard(lambda batch, notes: 0, daily_cooldown=lambda *args: verdict)
    game, clock, pid = make_game(guard)
    report(game, clock, 1)
    store, today = game.store, day_of(clock())
    earned = store.ledger_amount(pid, today, "tap")
    assert earned > 5
    store.update_player(pid, shards=5)

    verdict = Verdict(withhold=True, void_day=True)
    for seq in (2, 3):
        assert report(game, clock, seq)["shards"] == 0
        assert store.ledger_amount(pid, today, "tap_void") == -5

    store.update_player(pid, shards=earned)
    assert report(game, clock, 4)["shards"] == 5
    assert store.ledger_amount(pid, today, "tap_void") == -earned


@pytest.mark.parametrize("unserializable_notes", [False, True])
def test_broken_daily_rule_leaves_the_batch_payable(unserializable_notes):
    def daily(batch, judged, notes):
        if batch.sequence == 1:
            return 0
        if unserializable_notes:
            notes["bad"] = object()
            return Verdict(cooldown=90, withhold=True, void_day=True)
        raise RuntimeError("broken rule")

    game, clock, pid = make_game(FileGuard(lambda batch, notes: 0, daily_cooldown=daily))
    first = report(game, clock, 1)
    second = report(game, clock, 2)

    assert (second["credited"], second["tapCooldown"], second["autoStrikes"]) == (30, 0, 0)
    assert second["shards"] > first["shards"]
    assert game.store.ledger_amount(pid, day_of(clock()), "tap_void") == 0
