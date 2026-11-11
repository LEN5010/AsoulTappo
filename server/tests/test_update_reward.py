import pytest

import app.main as main
from app.game import day_of, player_id_for

from test_accounts import GUEST, bearer, env  # noqa: F401  (env is a fixture)
from test_admin import link

KEY = {"X-Admin-Key": "admin-secret"}
ME = {"X-Player-Token": GUEST}
OTHER = {"X-Player-Token": "o" * 32}


@pytest.fixture()
def reward_env(env, monkeypatch):
    monkeypatch.setattr(main, "ADMIN_KEY", "admin-secret")
    return env


def on(version, headers=ME):
    return {**headers, "X-Client-Version": version}


def open_reward(c, version, shards):
    r = c.post("/admin/update-rewards", json={"version": version, "shards": shards}, headers=KEY)
    assert r.status_code == 200, r.text
    return r.json()["rewards"][0]


def test_status_lists_open_rewards_until_claimed(reward_env):
    c, g, *_ = reward_env
    assert c.get("/api/me", headers=ME).json()["updateRewards"] == []
    reward = open_reward(c, "1.2.0", 500)
    assert c.get("/api/me", headers=ME).json()["updateRewards"] == [{"id": reward["id"], "version": "1.2.0", "shards": 500}]

    before = c.get("/api/me", headers=ME).json()["shards"]
    r = c.post("/api/update-reward", headers=on("1.2.0")).json()
    assert r["reward"] == {"shards": 500, "ids": [reward["id"]]}
    assert r["shards"] == before + 500 and r["updateRewards"] == []
    assert g.store.ledger_amount(player_id_for(GUEST), day_of(g.now.t), "update") == 500

    # once per save
    again = c.post("/api/update-reward", headers=on("1.2.0"))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "no_reward"
    assert c.get("/api/me", headers=ME).json()["shards"] == before + 500


def test_only_clients_on_the_version_or_newer_claim(reward_env):
    c, *_ = reward_env
    open_reward(c, "1.2.0", 300)
    c.get("/api/me", headers=ME)
    for version in ("", "1.1.4", "1.2.0-rc.1", "latest"):
        r = c.post("/api/update-reward", headers=on(version))
        assert r.status_code == 409, version
    assert c.post("/api/update-reward", headers=on("1.3.1")).json()["reward"]["shards"] == 300


def test_every_reward_the_version_reaches_is_paid_at_once(reward_env):
    c, *_ = reward_env
    first = open_reward(c, "1.2.0", 200)
    second = open_reward(c, "1.3.0", 800)
    c.get("/api/me", headers=ME)
    # 1.2.x reaches only the first
    assert c.post("/api/update-reward", headers=on("1.2.5")).json()["reward"] == {"shards": 200, "ids": [first["id"]]}
    assert c.post("/api/update-reward", headers=on("1.3.0")).json()["reward"] == {"shards": 800, "ids": [second["id"]]}

    c.get("/api/me", headers=OTHER)
    both = c.post("/api/update-reward", headers=on("1.3.0", OTHER)).json()["reward"]
    assert both == {"shards": 1000, "ids": [first["id"], second["id"]]}


def test_an_ended_reward_is_gone_for_those_who_did_not_claim(reward_env):
    c, *_ = reward_env
    reward = open_reward(c, "1.2.0", 500)
    c.get("/api/me", headers=ME)
    c.get("/api/me", headers=OTHER)
    assert c.post("/api/update-reward", headers=on("1.2.0")).status_code == 200

    out = c.post(f"/admin/update-rewards/{reward['id']}/end", headers=KEY).json()["rewards"][0]
    assert out["ended"] is not None and out["claims"] == 1 and out["paid"] == 500
    assert c.get("/api/me", headers=OTHER).json()["updateRewards"] == []
    assert c.post("/api/update-reward", headers=on("1.2.0", OTHER)).status_code == 409
    # ending it twice, or one that never was, is a conflict and never a 404
    assert c.post(f"/admin/update-rewards/{reward['id']}/end", headers=KEY).status_code == 409
    assert c.post("/admin/update-rewards/999/end", headers=KEY).status_code == 409


def test_one_open_reward_per_version(reward_env):
    c, *_ = reward_env
    reward = open_reward(c, "v1.2.0", 500)
    assert reward["version"] == "1.2.0"
    twice = c.post("/admin/update-rewards", json={"version": "1.2.0", "shards": 500}, headers=KEY)
    assert twice.status_code == 409 and twice.json()["detail"]["code"] == "reward_open"
    c.post(f"/admin/update-rewards/{reward['id']}/end", headers=KEY)
    assert c.post("/admin/update-rewards", json={"version": "1.2.0", "shards": 100}, headers=KEY).status_code == 200
    assert [r["shards"] for r in c.get("/admin/update-rewards", headers=KEY).json()["rewards"]] == [100, 500]


def test_admin_checks_the_version_and_amount(reward_env):
    c, *_ = reward_env
    assert c.post("/admin/update-rewards", json={"version": "next", "shards": 500}, headers=KEY).status_code == 400
    for shards in (0, -5, 2_000_000):
        assert c.post("/admin/update-rewards", json={"version": "1.2.0", "shards": shards}, headers=KEY).status_code == 422
    assert c.get("/admin/update-rewards").status_code == 404
    assert c.get("/admin/update-rewards", headers=KEY).json() == {"rewards": []}


def test_a_linked_account_claims_for_its_save(reward_env):
    c, *_ = reward_env
    link(c, "tok-alice", GUEST)
    open_reward(c, "1.2.0", 500)
    before = c.get("/api/me", headers=bearer("tok-alice")).json()["shards"]
    r = c.post("/api/update-reward", headers={**bearer("tok-alice"), "X-Client-Version": "1.2.0"}).json()
    assert r["shards"] == before + 500
