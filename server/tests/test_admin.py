import pytest

import app.main as main
from app.game import day_of

from test_accounts import GUEST, bearer, env, play  # noqa: F401  (env is a fixture)

KEY = {"X-Admin-Key": "admin-secret"}


@pytest.fixture()
def admin_env(env, monkeypatch):
    monkeypatch.setattr(main, "ADMIN_KEY", "admin-secret")
    return env


def link(c, token, guest):
    headers = {"X-Player-Token": guest}
    play(c, headers)
    assert c.post("/api/account/link", headers={**headers, **bearer(token)}).status_code == 200


def test_admin_routes_hide_without_the_key(admin_env, monkeypatch):
    c, *_ = admin_env
    assert c.get("/admin/stats").status_code == 404
    assert c.get("/admin/stats", headers={"X-Admin-Key": "wrong"}).status_code == 404
    assert c.get("/admin/stats", headers=KEY).status_code == 200
    monkeypatch.setattr(main, "ADMIN_KEY", "")
    assert c.get("/admin/stats", headers={"X-Admin-Key": ""}).status_code == 404


def test_stats_count_saves_links_and_daily_activity(admin_env):
    c, g, *_ = admin_env
    link(c, "tok-alice", GUEST)
    play(c, {"X-Player-Token": "o" * 32})
    c.post("/api/resonance/draw", json={"count": 2}, headers=bearer("tok-alice"))
    g.now.t += 86400
    # same client session as the first report, so the next sequence number
    batch = {"session": "test-session-0001", "sequence": 2, "taps": 10}
    assert c.post("/api/activity", json=batch, headers=bearer("tok-alice")).json()["credited"] == 10

    body = c.get("/admin/stats?days=3", headers=KEY).json()
    assert body["totals"] == {"saves": 2, "linked": 1, "guests": 1, "activeToday": 1, "rooms": 0, "online": 0}
    series = body["series"]
    assert [d["day"] for d in series] == [day_of(g.now.t - 2 * 86400), day_of(g.now.t - 86400), day_of(g.now.t)]
    assert series[0] == {"day": series[0]["day"], "active": 0, "newSaves": 0, "items": 0}
    assert series[1]["active"] == 2 and series[1]["newSaves"] == 2 and series[1]["items"] >= 2
    assert series[2]["active"] == 1 and series[2]["newSaves"] == 0


def test_days_follow_china_standard_time():
    # 2027-01-15 16:30 UTC is already the 16th in UTC+8
    assert day_of(1_800_030_600.0) == "2027-01-16"


def test_accounts_list_filters_by_ids(admin_env):
    c, *_ = admin_env
    link(c, "tok-alice", GUEST)
    link(c, "tok-bob", "b" * 32)
    every = c.get("/admin/accounts", headers=KEY).json()
    assert every["total"] == 2 and {a["userId"] for a in every["accounts"]} == {"u-alice", "u-bob"}
    one = c.get("/admin/accounts?ids=u-bob,u-nobody", headers=KEY).json()
    assert one["total"] == 1 and one["accounts"][0]["userId"] == "u-bob"
    assert set(one["accounts"][0]) == {"userId", "linkedAt", "shards", "owned", "taps", "lastActive"}
    assert c.get("/admin/accounts?ids=", headers=KEY).json() == {"total": 0, "accounts": []}
    assert len(c.get("/admin/accounts?limit=1&offset=1", headers=KEY).json()["accounts"]) == 1


def test_adjusting_shards_never_goes_below_zero(admin_env):
    c, *_ = admin_env
    link(c, "tok-alice", GUEST)
    before = c.get("/api/me", headers=bearer("tok-alice")).json()["shards"]
    r = c.post("/admin/accounts/u-alice/shards", json={"delta": 50}, headers=KEY)
    assert r.json() == {"shards": before + 50}
    r = c.post("/admin/accounts/u-alice/shards", json={"delta": -(before + 51)}, headers=KEY)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_shards"
    assert c.post("/admin/accounts/u-alice/shards", json={"delta": -(before + 50)}, headers=KEY).json() == {"shards": 0}
    assert c.post("/admin/accounts/u-nobody/shards", json={"delta": 1}, headers=KEY).status_code == 409


def test_unlinking_frees_the_account_and_gives_the_save_back_to_its_guest_token(admin_env):
    c, *_ = admin_env
    link(c, "tok-alice", GUEST)
    assert c.get("/api/me", headers={"X-Player-Token": GUEST}).status_code == 401
    assert c.post("/admin/accounts/u-alice/unlink", headers=KEY).json() == {"ok": True}
    assert c.get("/api/me", headers={"X-Player-Token": GUEST}).json()["totals"]["taps"] == 30
    assert c.get("/api/me", headers=bearer("tok-alice")).json()["detail"]["code"] == "account_not_linked"
    assert c.post("/admin/accounts/u-alice/unlink", headers=KEY).status_code == 409
