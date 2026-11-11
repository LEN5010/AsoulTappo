import pytest

import app.main as main
from app.cards import DropConfig
from app.game import Game, GameError, day_of, player_id_for
from app.manifest import Manifest
from app.store import Store

from fixtures import Clock, SeqRng, tiny_manifest
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


# ------------------------------------------------------------------ shard ledger
TOKEN = "ledger-player-token-0001"


def ledger(g, pid, day=None):
    rows = g.store.ledger_of(pid, [day or day_of(g.now())])
    return {r["source"]: (r["amount"], r["count"]) for r in rows}


def test_ledger_follows_starter_taps_draws_duplicates_crafting_and_checkin():
    g = Game(Store(":memory:"), tiny_manifest(), DropConfig(max_taps_per_sec=10**5), SeqRng(0.0), Clock())
    pid = g.status(TOKEN)["player"]
    assert ledger(g, pid) == {"starter": (1600, 1)}
    g.now.t += 1
    before = g.status(TOKEN)["shards"]
    out = g.report_activity(TOKEN, 30, "ledger-session-01", 1)
    assert ledger(g, pid)["tap"] == (out["shards"] - before, 30)
    # a batch already seen credits nothing and writes nothing
    g.report_activity(TOKEN, 30, "ledger-session-01", 1)
    assert ledger(g, pid)["tap"][1] == 30

    drops = g.resonate(TOKEN, 5)["drops"]
    repeats = [d["shards"] for d in drops if d["shards"] > 0]
    assert repeats, "the draw should hit a repeat that turns into shards"
    assert ledger(g, pid)["draw"] == (-5 * 160, 5)
    assert ledger(g, pid)["duplicate"] == (sum(repeats), len(repeats))

    owned = g.store.owned(pid)
    item = next(i for i, it in g.manifest.items.items()
                if it["kind"] in ("card", "emote") and not it["source"] and i not in g.manifest.starter
                and i not in owned and g.manifest.craft_cost.get(it["rarity"] or "") is not None)
    cost = g.manifest.craft_cost[g.manifest.items[item]["rarity"]]
    g.craft(TOKEN, item)
    assert ledger(g, pid)["craft"] == (-cost, 1)

    prize = g.checkin(TOKEN)["prize"]["shards"]
    assert ledger(g, pid)["checkin"] == (prize, 1)
    # every change went through the ledger
    assert sum(a for a, _ in ledger(g, pid).values()) == g.status(TOKEN)["shards"]


def test_ledger_follows_scratch_cards():
    # 0.06 lands on the 200-shard prize
    g = Game(Store(":memory:"), Manifest.load(), rng=SeqRng(0.06), now=Clock())
    pid = g.status(TOKEN)["player"]
    card = g.scratch_buy(TOKEN)["card"]
    assert ledger(g, pid)["scratch_buy"] == (-500, 1)
    assert "scratch_prize" not in ledger(g, pid)
    assert g.scratch_reveal(TOKEN, card["id"])["prize"]["shards"] == 200
    g.scratch_reveal(TOKEN, card["id"])
    assert ledger(g, pid)["scratch_prize"] == (200, 1)


def test_ledger_follows_duel_bets_prizes_and_refunds():
    g = Game(Store(":memory:"), Manifest.load(), now=Clock())
    a, b = "a" * 16, "b" * 16
    for pid in (a, b):
        g.store.get_player(pid, g.now())
        g.store.update_player(pid, taps_total=10_000)
    first = g.duel_start(a, b, 150)
    assert ledger(g, a)["duel_bet"] == ledger(g, b)["duel_bet"] == (-150, 1)
    assert g.duel_settle(first, a) and not g.duel_settle(first, a)
    assert ledger(g, a)["duel_prize"] == (250, 1) and "duel_prize" not in ledger(g, b)
    g.now.t += 86400
    second = g.duel_start(a, b, 150)
    g.duel_settle(second, None)
    assert ledger(g, a)["duel_refund"] == ledger(g, b)["duel_refund"] == (150, 1)
    assert ledger(g, a)["duel_bet"] == (-150, 1)


def test_ledger_rows_roll_back_with_their_change():
    g = Game(Store(":memory:"), tiny_manifest(), now=Clock())
    pid = g.status(TOKEN)["player"]
    g.store.update_player(pid, shards=10)
    for fail in (lambda: g.resonate(TOKEN, 1), lambda: g.admin_adjust_save_shards(pid, -11)):
        with pytest.raises(GameError) as e:
            fail()
        assert e.value.code == "no_shards"
    with pytest.raises(RuntimeError):
        with g.store.transaction() as st:
            st.add_ledger(pid, day_of(g.now()), "draw", -160)
            raise RuntimeError("abort")
    assert ledger(g, pid) == {"starter": (1600, 1)}


# ------------------------------------------------------------------ economy
def test_economy_series_sums_sources_taps_and_capped_saves(admin_env):
    c, g, *_ = admin_env
    t = g.now()
    today, yesterday, before = day_of(t), day_of(t - 86400), day_of(t - 2 * 86400)
    old, new, fresh = "a" * 16, "b" * 16, "c" * 16
    g.store.get_player(old, t - 10 * 86400)
    g.store.get_player(new, t - 86400)
    g.store.get_player(fresh, t)
    for pid, source, amount, count in ((old, "tap", 10400, 50000), (new, "tap", 10399, 30000),
                                       (fresh, "tap", 100, 10), (old, "draw", -1600, 10), (new, "admin", -5, 1)):
        g.store.add_ledger(pid, today, source, amount, count)

    body = c.get("/admin/economy?days=3", headers=KEY).json()
    assert (body["scope"], body["newDays"], body["cap"]) == ("all", 7, 10400)
    assert [d["day"] for d in body["series"]] == [before, yesterday, today]
    assert body["series"][0] == {"day": before, "players": 0, "issued": 0, "spent": 0, "sources": {}, "draws": 0,
                                 "taps": {"players": 0, "p50": 0, "p90": 0, "max": 0}, "capped": 0}
    assert body["series"][1]["players"] == 1 and body["series"][1]["sources"] == {"starter": {"amount": 1600, "count": 1}}
    row = body["series"][2]
    assert row["players"] == 3 and row["issued"] == 10400 + 10399 + 100 + 1600 and row["spent"] == 1605
    assert row["draws"] == 10 and row["sources"]["tap"] == {"amount": 20899, "count": 80010}
    # nearest rank over [10, 30000, 50000]; 10399 is one shard short of the cap and still counts
    assert row["taps"] == {"players": 3, "p50": 30000, "p90": 50000, "max": 50000} and row["capped"] == 2

    first_day = c.get("/admin/economy?days=3&scope=new&newDays=1", headers=KEY).json()["series"]
    assert first_day[2]["players"] == 1 and first_day[2]["issued"] == 1700 and first_day[2]["capped"] == 0
    assert first_day[1]["players"] == 1  # `new` on the day it was created
    two_days = c.get("/admin/economy?days=3&scope=new&newDays=2", headers=KEY).json()["series"][2]
    assert two_days["players"] == 2 and two_days["capped"] == 1 and two_days["taps"]["max"] == 30000

    for bad in ("scope=old", "days=0", "days=91", "newDays=0", "newDays=31"):
        assert c.get(f"/admin/economy?{bad}", headers=KEY).status_code == 422


def test_economy_defaults_to_fourteen_days(admin_env):
    c, *_ = admin_env
    assert len(c.get("/admin/economy", headers=KEY).json()["series"]) == 14


# ------------------------------------------------------------------ saves
SAVE_KEYS = {"player", "userId", "created", "lastActive", "shards", "owned", "taps", "drawn", "tapCooldown"}


def test_saves_search_by_player_id_prefix_and_by_main_user_id(admin_env):
    c, g, *_ = admin_env
    link(c, "tok-alice", GUEST)
    pid = player_id_for(GUEST)
    by_prefix = c.get(f"/admin/saves?q={pid[:6].upper()}", headers=KEY).json()["saves"]
    assert [s["player"] for s in by_prefix] == [pid] and by_prefix[0]["userId"] == "u-alice"
    assert set(by_prefix[0]) == SAVE_KEYS and by_prefix[0]["taps"] == 30
    assert c.get("/admin/saves?q=u-alice", headers=KEY).json()["saves"] == by_prefix

    t = g.now()
    g.store.get_player("abcd000000000001", t)
    g.store.get_player("abcd000000000002", t)
    g.store.update_player("abcd000000000001", last_activity=t + 5)
    guests = c.get("/admin/saves?q=abcd", headers=KEY).json()["saves"]
    assert [s["player"] for s in guests] == ["abcd000000000001", "abcd000000000002"]
    assert all(s["userId"] is None for s in guests)
    assert len(c.get("/admin/saves?q=abcd&limit=1", headers=KEY).json()["saves"]) == 1
    # too short for a prefix, and no such user
    assert c.get("/admin/saves?q=abc", headers=KEY).json() == {"saves": []}
    assert c.get("/admin/saves?q=%20", headers=KEY).json() == {"saves": []}
    assert c.get("/admin/saves", headers=KEY).status_code == 422
    assert c.get("/admin/saves?q=", headers=KEY).status_code == 422
    assert c.get("/admin/saves?q=abcd&limit=51", headers=KEY).status_code == 422


def test_save_detail_shows_pity_today_recent_drops_and_a_week_of_ledger(admin_env):
    c, g, *_ = admin_env
    headers = {"X-Player-Token": GUEST}
    play(c, headers)
    c.post("/api/resonance/draw", json={"count": 2}, headers=headers)
    pid = player_id_for(GUEST)
    body = c.get(f"/admin/saves/{pid}", headers=KEY).json()
    assert set(body) == SAVE_KEYS | {"pity", "today", "recent", "ledger"}
    assert body["userId"] is None and body["drawn"] == 2
    assert set(body["pity"]) == {"legendary", "skin", "scratch"}
    today = day_of(g.now())
    assert body["today"] == {"day": today, "taps": 30, "tapShards": ledger(g, pid)["tap"][0]}
    assert len(body["recent"]) == 2
    assert [d["day"] for d in body["ledger"]] == [day_of(g.now() - i * 86400) for i in range(6, -1, -1)]
    assert body["ledger"][0]["sources"] == {}
    assert set(body["ledger"][-1]["sources"]) == {"starter", "tap", "draw"} | (
        {"duplicate"} if "duplicate" in ledger(g, pid) else set())

    r = c.get("/admin/saves/ffff000000000000", headers=KEY)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_save"
    assert not g.store.has_player("ffff000000000000")


def test_guest_saves_take_shard_adjustments_and_record_them(admin_env):
    c, g, *_ = admin_env
    headers = {"X-Player-Token": GUEST}
    play(c, headers)
    pid = player_id_for(GUEST)
    before = c.get("/api/me", headers=headers).json()["shards"]
    assert c.post(f"/admin/saves/{pid}/shards", json={"delta": 50}, headers=KEY).json() == {"shards": before + 50}
    assert c.post(f"/admin/saves/{pid}/shards", json={"delta": -20}, headers=KEY).json() == {"shards": before + 30}
    # opposite deltas of one day net into one row
    assert ledger(g, pid)["admin"] == (30, 2)
    r = c.post(f"/admin/saves/{pid}/shards", json={"delta": -(before + 31)}, headers=KEY)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_shards"
    assert ledger(g, pid)["admin"] == (30, 2)
    r = c.post("/admin/saves/ffff000000000000/shards", json={"delta": 5}, headers=KEY)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_save"
    assert not g.store.has_player("ffff000000000000")


def test_account_adjustments_are_recorded_in_the_ledger(admin_env):
    c, g, *_ = admin_env
    link(c, "tok-alice", GUEST)
    c.post("/admin/accounts/u-alice/shards", json={"delta": 50}, headers=KEY)
    assert ledger(g, player_id_for(GUEST))["admin"] == (50, 1)


def test_new_admin_routes_hide_without_the_key(admin_env):
    c, *_ = admin_env
    pid = "ffff000000000000"
    for method, path in (("get", "/admin/economy"), ("get", "/admin/saves?q=u-alice"), ("get", f"/admin/saves/{pid}"),
                         ("post", f"/admin/saves/{pid}/shards")):
        r = getattr(c, method)(path, **({"json": {"delta": 1}} if method == "post" else {}))
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
