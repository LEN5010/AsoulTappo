import pytest

import app.main as main
from app.notice import Notice, version_key

from test_accounts import GUEST, env  # noqa: F401  (env is a fixture)
from test_room_host import join

KEY = {"X-Admin-Key": "admin-secret"}
ME = {"X-Player-Token": GUEST}


@pytest.fixture()
def notice_env(env, monkeypatch):
    monkeypatch.setattr(main, "ADMIN_KEY", "admin-secret")
    monkeypatch.setattr(main, "notice", Notice())
    monkeypatch.setattr(main.releases, "latest", lambda: {"version": "1.2.0", "notes": "n"})
    return env


def test_versions_sort_with_pre_releases_below_their_release():
    order = ["1.1.2", "1.1.3-rc.1", "1.1.3-rc.2", "1.1.3-rc.10", "1.1.3", "1.2.0", "1.10.0"]
    keys = [version_key(v) for v in order]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert version_key("v1.2.3+build") == version_key("1.2.3")
    assert version_key("latest") is None and version_key(None) is None


def test_no_minimum_refuses_nobody(notice_env):
    c, *_ = notice_env
    assert c.get("/api/me", headers=ME).status_code == 200
    out = c.get("/api/client/release").json()
    assert out == {"version": "1.2.0", "notes": "n", "minVersion": None, "announcements": []}


def test_a_minimum_refuses_older_and_versionless_clients(notice_env):
    c, *_ = notice_env
    r = c.put("/admin/notice", json={"minVersion": "1.1.3"}, headers=KEY)
    assert r.status_code == 200 and r.json()["minVersion"] == "1.1.3"
    for headers in (ME, {**ME, "X-Client-Version": "1.1.2"}, {**ME, "X-Client-Version": "1.1.3-rc.1"}):
        refused = c.get("/api/me", headers=headers)
        assert refused.status_code == 426 and refused.json()["detail"]["code"] == "client_outdated"
    for version in ("1.1.3", "1.2.0"):
        assert c.get("/api/me", headers={**ME, "X-Client-Version": version}).status_code == 200
    # The update check itself stays open to everyone.
    assert c.get("/api/client/release").json()["minVersion"] == "1.1.3"
    assert c.put("/admin/notice", json={"minVersion": ""}, headers=KEY).status_code == 200
    assert c.get("/api/me", headers=ME).status_code == 200


def test_an_outdated_client_cannot_join_a_room(notice_env):
    c, *_ = notice_env
    c.put("/admin/notice", json={"minVersion": "1.1.3"}, headers=KEY)
    with c.websocket_connect("/ws") as old, c.websocket_connect("/ws?v=1.1.3") as new:
        old.send_json({"type": "join", "room": "r1", "nick": "a", "character": "嘉然"})
        refused = old.receive_json()
        assert refused["type"] == "error" and refused["reason"] == "client_outdated"
        new.send_json({"type": "join", "room": "r1", "nick": "b", "character": "嘉然"})
        assert new.receive_json()["type"] == "joined"


def test_announcements_are_stored_and_expire(notice_env, monkeypatch):
    c, g, *_ = notice_env
    body = {"announcements": [
        {"id": "a1", "title": "维护", "body": "今晚十点"},
        {"id": "a2", "title": "过期", "until": 1.0},
    ]}
    assert c.put("/admin/notice", json=body, headers=KEY).status_code == 200
    shown = c.get("/api/client/release").json()["announcements"]
    assert [a["id"] for a in shown] == ["a1"]
    assert [a["id"] for a in c.get("/admin/notice", headers=KEY).json()["announcements"]] == ["a1", "a2"]
    # Kept across a restart.
    assert [a["id"] for a in main.load_notice(g.store).announcements] == ["a1", "a2"]


def test_notice_needs_the_key_and_a_real_version(notice_env):
    c, *_ = notice_env
    assert c.put("/admin/notice", json={"minVersion": "1.1.3"}).status_code == 404
    assert c.put("/admin/notice", json={"minVersion": "newest"}, headers=KEY).status_code == 422


def test_the_minimum_stands_in_when_the_release_list_is_down(notice_env, monkeypatch):
    c, *_ = notice_env
    monkeypatch.setattr(main.releases, "latest", lambda: None)
    assert c.get("/api/client/release").status_code == 503
    c.put("/admin/notice", json={"minVersion": "1.1.3"}, headers=KEY)
    assert c.get("/api/client/release").json()["version"] == "1.1.3"
