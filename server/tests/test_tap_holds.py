import pytest

from app.game import Game
from app.guard import FileGuard, Verdict
from app.store import Store, day_of
from fixtures import Clock, tiny_manifest
from test_accounts import BATCH, GUEST, env  # noqa: F401  (env is a fixture)
from test_admin import KEY, admin_env  # noqa: F401  (admin_env is a fixture)


@pytest.mark.parametrize("release_kwargs, release_reason", [({}, ""), ({"json": {"reason": " resume "}}, "resume")])
def test_admin_hold_and_release_stop_and_resume_tap_income(admin_env, release_kwargs, release_reason):
    client, game, *_ = admin_env
    headers = {"X-Player-Token": GUEST}
    before = client.get("/api/me", headers=headers).json()
    pid = before["player"]
    save = f"/admin/saves/{pid}"
    assert client.get(save, headers=KEY).json()["held"] is False
    assert client.get("/admin/holds", headers=KEY).json() == {"holds": []}

    since = game.now()
    operator = {**KEY, "X-Admin-Actor": "%20%E7%AE%A1%E7%90%86%E5%91%98%20"}
    hold = client.post(f"{save}/hold", headers=operator, json={"reason": " pause "})
    assert hold.status_code == 200 and hold.json() == {"held": True}
    holds = {"holds": [{"player": pid, "since": since, "actor": "管理员", "reason": "pause"}]}
    assert client.get("/admin/holds", headers=KEY).json() == holds
    assert client.get(save, headers=KEY).json()["held"] is True
    assert client.get(f"/admin/saves?q={pid}", headers=KEY).json()["saves"][0]["held"] is True
    assert client.get("/api/me", headers=headers).json() == before

    game.now.t += 20
    repeated_hold = client.post(f"{save}/hold", headers=KEY, json={"reason": "still paused"})
    assert repeated_hold.status_code == 200 and repeated_hold.json() == {"held": True}
    assert client.get("/admin/holds", headers=KEY).json() == holds
    held = client.post("/api/activity", headers=headers, json={**BATCH, "taps": 30}).json()
    assert held == {**before, "credited": 0}
    day = day_of(game.now())
    flags = game.store.tap_flags_of(day, 10)[0]
    assert (flags["dropped"], flags["server_cooldowns"], flags["client_cooldowns"]) == (30, 0, 0)
    assert game.store.ledger_amount(pid, day, "tap") == 0

    release = client.post(f"{save}/release", headers=operator, **release_kwargs)
    assert release.status_code == 200 and release.json() == {"held": False}
    repeated_release = client.post(f"{save}/release", headers=KEY, json={"reason": "already resumed"})
    assert repeated_release.status_code == 200 and repeated_release.json() == {"held": False}
    assert client.get("/admin/holds", headers=KEY).json() == {"holds": []}
    assert client.get(save, headers=KEY).json()["held"] is False
    game.now.t += 20
    paid = client.post("/api/activity", headers=headers, json={**BATCH, "sequence": 2, "taps": 30}).json()
    assert paid["credited"] == 30 and paid["shards"] > before["shards"]

    log = client.get(save, headers=KEY).json()["log"]
    assert [(e["action"], e["player"], e["actor"], e["reason"]) for e in log] == [
        ("release", pid, "管理员", release_reason), ("hold", pid, "管理员", "pause"),
    ]


def test_hold_routes_require_admin_and_an_existing_save(admin_env):
    client, game, *_ = admin_env
    pid = "ffff000000000000"
    save = f"/admin/saves/{pid}"
    assert client.get("/admin/holds").status_code == 404
    missing = client.get(save, headers=KEY)
    assert missing.status_code == 409
    for action, body in (("hold", {"reason": "pause"}), ("release", None)):
        path = f"{save}/{action}"
        assert client.post(path, json=body).status_code == 404
        result = client.post(path, headers=KEY, json=body)
        assert (result.status_code, result.json()) == (missing.status_code, missing.json())
    assert not game.store.has_player(pid)
    assert client.get("/admin/holds", headers=KEY).json() == {"holds": []}
    assert client.get("/admin/log", headers=KEY).json() == {"entries": []}


def test_held_save_keeps_rule_calls_and_rule_cooldowns(admin_env):
    client, game, *_ = admin_env
    headers = {"X-Player-Token": GUEST}
    first = client.get("/api/me", headers=headers).json()
    pid = first["player"]
    calls = []

    def judge(batch, notes):
        calls.append(("judge", batch.taps))
        return 0

    def daily(batch, judged, notes):
        calls.append(("daily", batch.taps))
        return Verdict(cooldown=90, void_day=True) if batch.sequence == 3 else 0

    def seen(save, method, path, headers, now):
        calls.append(("seen", save, method, path))

    def report(sequence):
        game.now.t += 20
        result = client.post("/api/activity", headers=headers,
                             json={**BATCH, "sequence": sequence, "taps": 30, "injected": 2}).json()
        assert calls == [("seen", pid, "POST", "/api/activity"), ("judge", 30), ("daily", 30), ("judge", 28)]
        calls.clear()
        return result

    game.guard = FileGuard(judge, daily_cooldown=daily, seen=seen)
    paid = report(1)
    assert paid["credited"] == 30 and paid["shards"] > first["shards"]
    assert client.post(f"/admin/saves/{pid}/hold", headers=KEY, json={"reason": "pause"}).status_code == 200

    held = report(2)
    assert (held["credited"], held["tapCooldown"]) == (0, 0)
    cooled = report(3)
    assert (cooled["credited"], cooled["tapCooldown"], cooled["autoStrikes"]) == (0, 90, 1)
    assert cooled["shards"] == first["shards"]


def test_tap_hold_persists_after_reopening_the_store(tmp_path):
    path = str(tmp_path / "holds.db")
    clock = Clock()
    game = Game(Store(path), tiny_manifest(), now=clock)
    pid = game.status(GUEST)["player"]
    game.admin_set_tap_hold(pid, True)
    game.store.close()

    game = Game(Store(path), tiny_manifest(), now=clock)
    clock.t += 86400
    assert game.admin_save(pid)["held"] is True
    assert game.report_activity(GUEST, 30)["credited"] == 0
    game.admin_set_tap_hold(pid, False)
    assert game.report_activity(GUEST, 30)["credited"] == 30
    game.store.close()
