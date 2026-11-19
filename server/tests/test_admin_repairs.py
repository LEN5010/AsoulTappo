"""Admin repairs: resetting one save's collection, a grant to every save, and emptying saves never used."""
from app.game import day_of, player_id_for

from test_accounts import GUEST, bearer, env, play  # noqa: F401  (env is a fixture)
from test_admin import KEY, admin_env, link  # noqa: F401  (admin_env is a fixture)


def guest(n: int) -> dict:
    return {"X-Player-Token": f"{n:032d}"}


def pid_of(headers: dict) -> str:
    return player_id_for(headers["X-Player-Token"])


def log_entries(c, action):
    return [e for e in c.get("/admin/log", headers=KEY).json()["entries"] if e["action"] == action]


def ledger(g, pid):
    return {r["source"]: (r["amount"], r["count"]) for r in g.store.ledger_of(pid, [day_of(g.now())])}


# ------------------------------------------------------------------ reset
def test_reset_empties_the_collection_and_pity_and_keeps_the_rest(admin_env):
    c, g, *_ = admin_env
    link(c, "tok-alice", GUEST)
    me = c.get("/api/me", headers=bearer("tok-alice")).json()
    pid = me["player"]
    c.post("/api/resonance/draw", json={"count": 5}, headers=bearer("tok-alice"))
    g.store.save_banner_draws(pid, "pool-a", 3, 9, ["epic"])
    g.store.update_player(pid, draw_pity=359, skin_pity=159)
    items = len(g.store.owned(pid))
    assert items and g.store.count_items(pid, g.collectible_ids) > 0
    before = g.store.get_player(pid, g.now())
    drops = g.store.recent_drops(pid)

    r = c.post(f"/admin/saves/{pid}/reset", json={"reason": "script"}, headers={**KEY, "X-Admin-Actor": "len"})
    assert r.status_code == 200
    assert r.json() == {"items": items, "bannerDraws": 1, "pity": {"legendary": 359, "skin": 159}}

    after = g.store.get_player(pid, g.now())
    assert g.store.owned(pid) == {} and g.store.banner_draws(pid) == {}
    assert (after["draw_pity"], after["skin_pity"]) == (0, 0)
    # the cached collectible count is dropped with the items
    assert g.store.count_items(pid, g.collectible_ids) == 0
    for field in ("shards", "taps_total", "loadout", "drawn_total"):
        assert after[field] == before[field]
    assert g.store.recent_drops(pid) == drops and g.store.account_for_player(pid) == "u-alice"

    entry = log_entries(c, "reset")[0]
    assert entry["player"] == pid and entry["actor"] == "len" and entry["reason"] == "script"
    assert entry["detail"] == {"items": items, "bannerDraws": 1, "pity": {"legendary": 359, "skin": 159}}


def test_reset_of_a_missing_save_and_without_the_key(admin_env):
    c, *_ = admin_env
    r = c.post(f"/admin/saves/{'f' * 16}/reset", headers=KEY)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_save"
    play(c, guest(1))
    assert c.post(f"/admin/saves/{pid_of(guest(1))}/reset").status_code == 404
    assert c.post(f"/admin/saves/{pid_of(guest(1))}/reset", headers={"X-Admin-Key": "wrong"}).status_code == 404
    assert log_entries(c, "reset") == []


# ------------------------------------------------------------------ grants
def test_a_grant_goes_to_every_save_but_the_excluded_once_per_key(admin_env):
    c, g, *_ = admin_env
    for n in range(3):
        play(c, guest(n))
    ids = [pid_of(guest(n)) for n in range(3)]
    # an admin ledger row of the day already there is added to, not replaced
    c.post(f"/admin/saves/{ids[0]}/shards", json={"delta": 5}, headers=KEY)
    shards = {pid: g.store.get_player(pid, g.now())["shards"] for pid in ids}

    body = {"shards": 6400, "key": "2026-11-19-40draws", "exclude": [ids[2], "0" * 16], "reason": "补发"}
    r = c.post("/admin/grants", json=body, headers=KEY)
    assert r.status_code == 200
    assert r.json() == {"shards": 6400, "saves": 2, "skipped": 1, "key": "2026-11-19-40draws"}
    assert [g.store.get_player(pid, g.now())["shards"] - shards[pid] for pid in ids] == [6400, 6400, 0]
    assert ledger(g, ids[0])["admin"] == (6405, 2) and ledger(g, ids[1])["admin"] == (6400, 1)
    assert "admin" not in ledger(g, ids[2])
    entry = log_entries(c, "grant_all")[0]
    assert entry["detail"] == r.json() and entry["reason"] == "补发" and entry["player"] is None

    # the same key again, even with other numbers, gives nothing
    r = c.post("/admin/grants", json={**body, "shards": 1, "exclude": []}, headers=KEY)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "grant_done"
    assert [g.store.get_player(pid, g.now())["shards"] - shards[pid] for pid in ids] == [6400, 6400, 0]
    assert len(log_entries(c, "grant_all")) == 1
    # surrounding spaces name the same grant
    assert c.post("/admin/grants", json={**body, "key": " 2026-11-19-40draws "}, headers=KEY).status_code == 409

    assert c.post("/admin/grants", json={"shards": 10, "key": "another"}, headers=KEY).json()["saves"] == 3


def test_a_grant_takes_positive_shards_only_and_hides_without_the_key(admin_env):
    c, g, *_ = admin_env
    play(c, guest(1))
    for shards in (0, -5, 1_000_001):
        assert c.post("/admin/grants", json={"shards": shards, "key": "k"}, headers=KEY).status_code == 422
    assert c.post("/admin/grants", json={"shards": 5, "key": "  "}, headers=KEY).status_code == 422
    assert c.post("/admin/grants", json={"shards": 5, "key": "k"}).status_code == 404
    # the refused calls used up nothing: the key still works
    assert c.post("/admin/grants", json={"shards": 5, "key": "k"}, headers=KEY).status_code == 200


# ------------------------------------------------------------------ emptying unused saves
def test_emptying_unused_saves_counts_first_then_needs_the_count(admin_env):
    c, g, *_ = admin_env
    start = g.now()
    g.store.add_update_reward("1.2.5", 300, start - 1)
    reward = g.store.update_rewards()[0]["id"]
    # three script saves: made, drawn with the starter shards, one of them claimed the update reward
    bulk = [guest(n) for n in range(3)]
    for h in bulk:
        c.get("/api/me", headers=h)
        assert c.post("/api/resonance/draw", json={"count": 2}, headers=h).status_code == 200
    g.store.add_update_claim(reward, pid_of(bulk[0]), start)
    g.store.save_banner_draws(pid_of(bulk[1]), "pool-a", 1, 2)
    # saves in the range that were used in some way
    tapped = guest(10)
    play(c, tapped)
    linked = guest(11)
    c.get("/api/me", headers=linked)
    g.store.link_account("u-x", pid_of(linked), start)
    named = guest(12)
    c.get("/api/me", headers=named)
    g.store.set_room_nick(pid_of(named), "nick")
    dressed = guest(13)
    c.get("/api/me", headers=dressed)
    g.store.update_player(pid_of(dressed), loadout='{"character": null}')
    kept = [tapped, linked, named, dressed]
    # an unused save made after the range
    g.now.t += 3600
    late = guest(20)
    c.get("/api/me", headers=late)

    ids = sorted(pid_of(h) for h in bulk)
    rng = {"createdFrom": start - 1, "createdTo": start + 60}
    totals = {}
    for pid in ids:
        for source, (amount, count) in ledger(g, pid).items():
            t = totals.setdefault(source, {"amount": 0, "count": 0})
            t["amount"] += amount
            t["count"] += count
    before = {pid: g.store.get_player(pid, g.now()) for pid in map(pid_of, kept + [late])}
    held = {pid: g.store.owned(pid) for pid in before}

    dry = c.post("/admin/saves/empty", json=rng, headers=KEY).json()
    assert dry == {"saves": 3, "createdFrom": start - 1, "createdTo": start + 60, "ledger": totals, "dryRun": True}
    assert totals["starter"] == {"amount": 4800, "count": 3} and totals["draw"]["count"] == 6
    assert all(g.store.owned(pid) for pid in ids) and log_entries(c, "cleanup_bulk") == []

    for expect in (None, 2, 4):
        r = c.post("/admin/saves/empty", json={**rng, "dryRun": False, "expect": expect}, headers=KEY)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "empty_changed"
    assert all(g.store.owned(pid) for pid in ids)

    shards = sum(g.store.get_player(pid, g.now())["shards"] for pid in ids)
    drops = sum(len(g.store.drops_page(pid, None, 100)) for pid in ids)
    items = sum(len(g.store.owned(pid)) for pid in ids)
    rows = sum(len(ledger(g, pid)) for pid in ids)
    r = c.post("/admin/saves/empty", json={**rng, "dryRun": False, "expect": 3, "reason": "bulk"}, headers=KEY)
    assert r.status_code == 200
    out = r.json()
    assert out["saves"] == 3 and out["dryRun"] is False and out["ledger"] == totals and out["shards"] == shards
    assert out["deleted"] == {"items": items, "drops": drops, "bannerDraws": 1, "shardLedger": rows}

    for pid in ids:
        p = g.store.get_player(pid, g.now())
        assert g.store.has_player(pid) and (p["shards"], p["draw_pity"], p["skin_pity"]) == (0, 0, 0)
        assert g.store.owned(pid) == {} and g.store.drops_page(pid, None, 10) == [] and ledger(g, pid) == {}
        assert g.store.banner_draws(pid) == {}
    # the save that claimed the reward still has the claim, so its token cannot claim it again
    assert g.store.open_update_rewards(pid_of(bulk[0])) == []
    for pid, p in before.items():
        assert g.store.get_player(pid, g.now())["shards"] == p["shards"] and g.store.owned(pid) == held[pid]

    entry = log_entries(c, "cleanup_bulk")[0]
    assert entry["reason"] == "bulk" and entry["detail"] == {k: v for k, v in out.items() if k != "dryRun"}
    # the emptied saves still match, with nothing left to take
    again = c.post("/admin/saves/empty", json={**rng, "dryRun": False, "expect": 3}, headers=KEY).json()
    assert again["ledger"] == {} and again["shards"] == 0 and set(again["deleted"].values()) == {0}


def test_emptying_needs_a_range_and_the_key(admin_env):
    c, g, *_ = admin_env
    c.get("/api/me", headers=guest(1))
    rng = {"createdFrom": g.now() - 1, "createdTo": g.now() + 1}
    assert c.post("/admin/saves/empty", json=rng).status_code == 404
    assert c.post("/admin/saves/empty", json={**rng, "dryRun": False, "expect": 1}).status_code == 404
    assert c.post("/admin/saves/empty", json={**rng, "createdTo": rng["createdFrom"]}, headers=KEY).status_code == 422
    assert c.post("/admin/saves/empty", json=rng, headers=KEY).json()["saves"] == 1
    assert log_entries(c, "cleanup_bulk") == []
