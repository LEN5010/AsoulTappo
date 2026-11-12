"""What the admin pages read: clients, room samples, counts, tap flags, the admin log and the analyses."""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main
from app.analytics import _start_of
from app.game import Game, day_of, player_id_for
from app.store import Store
from app.tracking import Tracker, client_version

from fixtures import Clock, tiny_manifest
from test_accounts import GUEST, bearer, env, play  # noqa: F401  (env is a fixture)
from test_admin import KEY, admin_env, link  # noqa: F401  (admin_env is a fixture)

ACTOR = {**KEY, "X-Admin-Actor": "%E5%B0%8F%E6%98%8E"}  # 小明, as the main site sends it


def make():
    clock = Clock()
    return Game(Store(":memory:"), tiny_manifest(), now=clock), clock


# ------------------------------------------------------------------ clients
def test_versions_read_from_the_header():
    assert client_version("1.2.0") == "1.2.0" and client_version("v1.2.0-rc.1") == "1.2.0-rc.1"
    assert client_version("") == "" and client_version("dev") == "other"


def test_requests_record_the_client_of_the_save(admin_env):
    c, g, *_ = admin_env
    headers = {"X-Player-Token": GUEST, "X-Client-Version": "1.2.0"}
    # The first request makes the save; the client is written by the next one.
    c.get("/api/me", headers=headers)
    c.get("/api/me", headers=headers)
    pid = player_id_for(GUEST)
    row = g.store.get_player(pid, g.now())
    assert row["client_version"] == "1.2.0"
    c.get("/api/me", headers={**headers, "X-Client-Version": "1.2.1"})
    detail = c.get(f"/admin/saves/{pid}", headers=KEY).json()
    assert detail["clientVersion"] == "1.2.1" and "platform" not in detail


def test_an_unchanged_client_is_not_written_again():
    g, _ = make()
    g.store.get_player("p1", g.now())
    writes = []
    real = g.store.set_client
    g.store.set_client = lambda *a: writes.append(a) or real(*a)
    for _ in range(3):
        g.tracker.client("p1", "1.2.0")
    g.tracker.client("nobody", "1.2.0")
    g.tracker.client("nobody", "1.2.0")
    assert writes == [("p1", "1.2.0"), ("nobody", "1.2.0"), ("nobody", "1.2.0")]


# ------------------------------------------------------------------ rooms and counts
def test_room_numbers_count_members_saves_and_listed_rooms():
    peer = lambda token: SimpleNamespace(token=token)  # noqa: E731
    rooms = [SimpleNamespace(peers={"a": peer("s1"), "b": peer("s1"), "c": peer(None)}, public=True, host="a"),
             SimpleNamespace(peers={"d": peer("s2")}, public=True, host="gone"),
             SimpleNamespace(peers={}, public=False, host=None)]
    assert Tracker.room_numbers(rooms) == {"rooms": 2, "members": 4, "saves": 2, "largest": 3, "public": 1}
    assert Tracker.room_numbers([]) == {"rooms": 0, "members": 0, "saves": 0, "largest": 0, "public": 0}


def test_a_sample_writes_the_minute_and_the_counts_so_far():
    g, clock = make()
    g.tracker.count("poke")
    g.tracker.count("poke", 2)
    g.tracker.count("emote", 0)
    clock.t = 1_800_000_030.0
    g.tracker.sample({"rooms": 1, "members": 2, "saves": 2, "largest": 2, "public": 0})
    assert g.store.room_samples(0) == [{"ts": 1_800_000_000, "rooms": 1, "members": 2, "saves": 2, "largest": 2,
                                        "public": 0}]
    assert g.store.daily_counts("") == [{"day": day_of(clock.t), "key": "poke", "count": 3}]
    g.tracker.count("poke")
    g.tracker.flush()
    assert g.store.daily_counts("")[0]["count"] == 4


def test_room_joins_pokes_and_emotes_are_counted(admin_env):
    c, g, *_ = admin_env
    play(c, {"X-Player-Token": GUEST})
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        a.send_json({"type": "join", "room": "r1", "nick": "a", "character": "嘉然", "token": GUEST})
        you = a.receive_json()["you"]
        b.send_json({"type": "join", "room": "r1", "nick": "b", "character": "嘉然"})
        b.receive_json()
        a.receive_json()  # member_joined
        b.send_json({"type": "poke", "id": you})
        b.receive_json()
        a.send_json({"type": "emote", "emote": "thumbup"})
        a.receive_json()
    g.tracker.flush()
    counts = {r["key"]: r["count"] for r in g.store.daily_counts("")}
    assert counts == {"room_join": 2, "poke": 1, "emote": 1}


# ------------------------------------------------------------------ tap flags
def test_cooldowns_and_dropped_taps_are_flagged_per_day():
    g, clock = make()
    token = "flagged-player-token-001"
    g.status(token)
    pid = player_id_for(token)
    day = day_of(clock.t)
    clock.t += 20
    g.report_activity(token, 300, "fast", 1)
    clock.t += 20
    g.report_activity(token, 300, "fast", 2)
    clock.t += 20
    g.report_activity(token, 300, "fast", 3)  # too fast for 40 seconds: a cooldown, the batch dropped
    clock.t += 1
    g.report_activity(token, 7, "fast", 4)  # during the cooldown
    rows = g.store.tap_flags_of(day, 10)
    assert [(r["player_id"], r["server_cooldowns"], r["client_cooldowns"], r["dropped"], r["credited"])
            for r in rows] == [(pid, 1, 0, 307, 600)]

    clock.t += 120
    g.report_activity(token, 10, "guarded", 1, cooldown=50)
    clock.t += 5
    g.report_activity(token, 0, "guarded", 2, cooldown=45)  # the same cooldown, told again
    assert g.store.tap_flags_of(day, 10)[0]["client_cooldowns"] == 1


# ------------------------------------------------------------------ admin log
def test_admin_changes_are_logged_with_who_and_why(admin_env, monkeypatch):
    c, g, *_ = admin_env
    # The notice and the blocklist set below are module state: put them back afterwards.
    monkeypatch.setattr(main, "notice", main.notice)
    monkeypatch.setattr(main, "blocklist", main.blocklist)
    link(c, "tok-alice", GUEST)
    pid = player_id_for(GUEST)
    c.post(f"/admin/saves/{pid}/shards", json={"delta": 50, "reason": "补偿 11-11 掉线"}, headers=ACTOR)
    c.post("/admin/accounts/u-alice/shards", json={"delta": -20}, headers=KEY)
    c.post("/admin/accounts/u-alice/shards", json={"delta": 0}, headers=ACTOR)  # nothing changed, nothing logged
    reward = c.post("/admin/update-rewards", json={"version": "v1.2.0", "shards": 100}, headers=ACTOR).json()
    c.post(f"/admin/update-rewards/{reward['rewards'][0]['id']}/end", headers=ACTOR)
    c.put("/admin/notice", json={"minVersion": "1.1.3", "announcements": [{"id": "a", "title": "维护"}]}, headers=ACTOR)
    c.put("/admin/blocked-words", json={"words": ["x", "y"]}, headers=ACTOR)
    c.post("/admin/accounts/u-alice/unlink", json={"reason": "用户要求"}, headers=ACTOR)

    entries = c.get("/admin/log", headers=KEY).json()["entries"]
    assert [(e["action"], e["actor"], e["player"], e["detail"], e["reason"]) for e in entries] == [
        ("unlink", "小明", pid, {"userId": "u-alice"}, "用户要求"),
        ("blocked_words", "小明", None, {"count": 2}, ""),
        ("notice", "小明", None, {"minVersion": "1.1.3", "announcements": ["维护"]}, ""),
        ("reward_end", "小明", None, {"id": reward["rewards"][0]["id"], "version": "1.2.0"}, ""),
        ("reward_open", "小明", None, {"version": "1.2.0", "shards": 100}, ""),
        ("shards", "", pid, {"delta": -20, "shards": entries[5]["detail"]["shards"]}, ""),
        ("shards", "小明", pid, {"delta": 50, "shards": entries[5]["detail"]["shards"] + 20}, "补偿 11-11 掉线"),
    ]
    assert [e["action"] for e in c.get(f"/admin/log?player={pid}", headers=KEY).json()["entries"]] == [
        "unlink", "shards", "shards"]
    page = c.get(f"/admin/log?limit=2&before={entries[1]['id']}", headers=KEY).json()["entries"]
    assert [e["id"] for e in page] == [entries[2]["id"], entries[3]["id"]]
    assert [e["action"] for e in c.get(f"/admin/saves/{pid}", headers=KEY).json()["log"]] == ["unlink", "shards", "shards"]
    # An unlink without a body, as the main site sent it before reasons.
    link(c, "tok-bob", "b" * 32)
    assert c.post("/admin/accounts/u-bob/unlink", headers=KEY).status_code == 200


def test_a_refused_change_is_not_logged(admin_env):
    c, g, *_ = admin_env
    play(c, {"X-Player-Token": GUEST})
    pid = player_id_for(GUEST)
    assert c.post(f"/admin/saves/{pid}/shards", json={"delta": -10**6}, headers=ACTOR).status_code == 409
    assert c.get("/admin/log", headers=KEY).json() == {"entries": []}


# ------------------------------------------------------------------ insights
def test_insights_count_returns_only_on_days_that_are_over(admin_env):
    c, g, *_ = admin_env
    t0 = g.now()
    for i in range(3):
        g.store.get_player(f"aaaa00000000000{i}", t0)
    g.store.mark_active("aaaa000000000000", day_of(t0 + 86400))
    g.store.mark_active("aaaa000000000001", day_of(t0 + 86400))
    g.store.mark_active("aaaa000000000000", day_of(t0 + 3 * 86400))
    g.now.t = t0 + 3 * 86400
    body = c.get("/admin/insights?days=4", headers=KEY).json()
    first = body["retention"][0]
    assert first == {"day": day_of(t0), "size": 3, "d1": 2, "d3": None, "d7": None}
    g.now.t = t0 + 4 * 86400
    first = c.get("/admin/insights?days=5", headers=KEY).json()["retention"][0]
    assert first["d3"] == 1 and first["d7"] is None
    assert c.get("/admin/insights?days=91", headers=KEY).status_code == 422


def test_insights_mix_clients_and_collections_of_active_saves(admin_env):
    c, g, *_ = admin_env
    t = g.now()
    for pid, version, cards in (("p1", "1.2.0", ["c1", "c2"]), ("p2", "1.1.4", ["c1"]), ("p3", "1.2.0", []),
                                ("p4", "", []), ("p5", "1.10.0", [])):
        g.store.get_player(pid, t)
        g.store.set_client(pid, version)
        for card in cards:
            g.store.add_item(pid, f"card:{card}", t)
        if pid != "p5":
            g.store.mark_active(pid, day_of(t))
    g.store.log_drops("p1", [{"item": "card:c1", "rarity": "common", "new": True},
                             {"item": "card:c1", "rarity": "common", "new": False}], t)
    body = c.get("/admin/insights?days=2", headers=KEY).json()
    assert body["active"] == 4 and body["activeDays"] == 7
    assert body["versions"] == [{"name": "1.2.0", "count": 2}, {"name": "1.1.4", "count": 1},
                                {"name": "unknown", "count": 1}]
    assert "platforms" not in body
    total = len(g.manifest.cards)
    assert body["collection"]["total"] == total and len(body["collection"]["saves"]) == total + 1
    assert body["collection"]["saves"][:3] == [2, 1, 1]
    assert body["drops"][-1] == {"day": day_of(t), "rarities": {"common": {"count": 2, "new": 1}}}
    assert body["rarities"]["common"] == "普通" and body["rarities"]["skin"] == "皮肤"


# ------------------------------------------------------------------ online
def test_online_folds_samples_into_days_and_the_last_day(admin_env):
    c, g, *_ = admin_env
    t = g.now()
    day = day_of(t)
    minute = int(t // 60 * 60)
    for i, members in enumerate((2, 5, 3)):
        g.store.add_room_sample(minute - 60 * i, {"rooms": 1, "members": members, "saves": members, "largest": members,
                                                  "public": 0})
    g.store.add_room_sample(minute - 2 * 86400, {"rooms": 9, "members": 9, "saves": 9, "largest": 1, "public": 0})
    g.tracker.count("poke", 4)
    g.tracker.count("cheer_round")
    g.tracker.flush()
    g.store.add_ledger("p1", day, "cheer", 20)
    g.store.add_ledger("p2", day, "cheer", 20)
    body = c.get("/admin/online?days=2", headers=KEY).json()
    assert body["now"] == {"rooms": 0, "members": 0, "saves": 0, "largest": 0, "public": 0}
    yesterday, today = body["series"]
    assert yesterday["samples"] == 0 and yesterday["peakMembers"] == 0
    assert today["samples"] == 3 and today["peakMembers"] == 5 and today["avgMembers"] == 3.3
    assert today["sharedMinutes"] == 3
    assert today["counts"]["poke"] == 4 and today["counts"]["cheer_round"] == 1 and today["counts"]["emote"] == 0
    assert today["cheer"] == {"shards": 40, "saves": 2}
    assert today["duels"] == {"played": 0, "bets": {}}
    assert sum(1 for p in body["recent"]) >= 1 and max(p["members"] for p in body["recent"]) == 5
    assert all(p["ts"] > t - 86400 for p in body["recent"])


def test_online_counts_finished_duels_on_the_day_they_ended(admin_env):
    c, g, *_ = admin_env
    today = day_of(g.now())
    midnight = _start_of(today)
    yesterday = day_of(midnight - 1)
    # (day opened, opened at, outcome, bet, ended at)
    for day, ts, state, bet, settled in ((yesterday, midnight - 10, "won", 150, midnight + 5),
                                         (today, midnight + 60, "refunded", 1500, midnight + 75),
                                         (yesterday, midnight - 300, "won", 150, midnight - 290),
                                         (today, midnight + 90, "open", 150, 0)):
        g.store._db.execute("INSERT INTO duels (a, b, bet, prize, day, ts, state, settled) "
                            "VALUES ('a', 'b', ?, 0, ?, ?, ?, ?)", (bet, day, ts, state, settled))
    g.store._db.commit()
    before, now = c.get("/admin/online?days=2", headers=KEY).json()["series"]
    assert now["duels"] == {"played": 2, "bets": {"150": 1, "1500": 1}}
    assert before["duels"] == {"played": 1, "bets": {"150": 1}}


def test_online_last_day_reaches_into_yesterday_for_one_day(admin_env):
    c, g, *_ = admin_env
    midnight = _start_of(day_of(g.now()))
    g.now.t = midnight + 2 * 3600
    for ts, members in ((midnight - 3600, 4), (midnight + 600, 2)):
        g.store.add_room_sample(int(ts), {"rooms": 1, "members": members, "saves": members, "largest": members,
                                          "public": 0})
    body = c.get("/admin/online?days=1", headers=KEY).json()
    assert [p["members"] for p in body["recent"]] == [4, 2]
    [today] = body["series"]
    assert today["samples"] == 1 and today["peakMembers"] == 2


# ------------------------------------------------------------------ anomalies
def test_anomalies_list_flagged_taps_and_earned_shards(admin_env):
    c, g, *_ = admin_env
    link(c, "tok-alice", GUEST)
    pid = player_id_for(GUEST)
    day = day_of(g.now())
    g.store.add_tap_flags(day, pid, dropped=40, server=2)
    g.store.add_tap_flags(day, "guest00000000001", client=1)
    g.store.add_ledger("guest00000000001", day, "scratch_prize", 30000)
    g.store.add_ledger("guest00000000001", day, "update", 1600)
    g.store.add_ledger("guest00000000001", day, "admin", 50000)
    g.store.add_ledger("guest00000000002", day, "tap", 900, 400000)
    body = c.get("/admin/anomalies", headers=KEY).json()
    assert body["day"] == day and body["tapCap"] == 10400
    assert [(r["player"], r["userId"], r["serverCooldowns"], r["dropped"]) for r in body["taps"]] == [
        (pid, "u-alice", 2, 40), ("guest00000000001", None, 0, 0)]
    assert body["taps"][0]["credited"] == 30 and body["taps"][0]["tapShards"] > 0
    top = body["shards"][0]
    assert top == {"player": "guest00000000001", "userId": None, "gained": 30000, "sources": {"scratch_prize": 30000}}
    # Starter shards, update rewards and admin adjustments are not earned by playing.
    assert all(not {"starter", "update", "admin"} & set(r["sources"]) for r in body["shards"])
    # A steady clicker below the cooldown rate shows among the most taps.
    assert [(r["player"], r["credited"], r["serverCooldowns"]) for r in body["heavy"]] == [
        ("guest00000000002", 400000, 0), (pid, 30, 2)]
    assert c.get("/admin/anomalies?day=2026-1-1", headers=KEY).status_code == 422
    assert c.get("/admin/anomalies?day=2020-01-01", headers=KEY).json()["taps"] == []


def test_analysis_routes_hide_without_the_key(admin_env):
    c, *_ = admin_env
    for path in ("/admin/insights", "/admin/online", "/admin/anomalies", "/admin/log"):
        r = c.get(path)
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}


def test_the_sampler_runs_with_the_app_and_flushes_on_shutdown(monkeypatch):
    g, _ = make()
    monkeypatch.setattr(main, "game", g)
    with TestClient(main.app):
        g.tracker.count("poke")
    assert g.store.daily_counts("") == [{"day": day_of(g.now()), "key": "poke", "count": 1}]
    assert json.loads(json.dumps(g.admin_log(None, 5))) == {"entries": []}
