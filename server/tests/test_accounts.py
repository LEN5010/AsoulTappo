import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.accounts import MainAccounts
from app.cards import DropConfig
from app.game import Game
from app.store import Store

from fixtures import Clock, SeqRng, tiny_manifest

GUEST = "g" * 32
BATCH = {"session": "test-session-0001", "sequence": 1}
USERS = {"tok-alice": {"id": "u-alice", "username": "alice", "email": "a@example.com"},
         "tok-bob": {"id": "u-bob", "username": "bob", "email": None}}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


class FakeMain:
    def __init__(self):
        self.calls = 0
        self.down = False

    def __call__(self, url, token):
        assert url == "https://main.test/api/auth/me"
        self.calls += 1
        if self.down:
            raise OSError("unreachable")
        return (200, {"user": USERS[token]}) if token in USERS else (401, None)


@pytest.fixture()
def env(monkeypatch):
    g = Game(Store(":memory:"), tiny_manifest(), DropConfig(max_taps_per_sec=10**5), SeqRng(0.0), Clock())
    fake = FakeMain()
    clock = [0.0]
    monkeypatch.setattr(main, "game", g)
    monkeypatch.setattr(main, "accounts", MainAccounts("https://main.test/api/", fake, lambda: clock[0]))
    monkeypatch.setattr(main, "MAIN_API_URL", "https://main.test/api")
    main.manager.rooms.clear()
    with TestClient(main.app) as c:
        yield c, g, fake, clock


def play(c, headers, taps=30):
    """Creates the save if needed, lets time pass so the taps are credited, then reports them."""
    c.get("/api/me", headers=headers)
    main.game.now.t += 1
    return c.post("/api/activity", json={**BATCH, "taps": taps}, headers=headers).json()


def test_info_reports_account_login(env, monkeypatch):
    c, *_ = env
    assert c.get("/api/info").json() == {"accountLogin": True, "mainApi": "https://main.test/api"}
    monkeypatch.setattr(main, "accounts", None)
    monkeypatch.setattr(main, "MAIN_API_URL", "")
    assert c.get("/api/info").json() == {"accountLogin": False, "mainApi": None}
    assert c.post("/api/account/link", headers=bearer("tok-alice")).status_code == 404


def test_linking_keeps_the_guest_save_and_retires_the_guest_token(env):
    c, g, *_ = env
    guest = {"X-Player-Token": GUEST}
    before = play(c, guest)
    c.post("/api/resonance/draw", json={"count": 2}, headers=guest)
    owned = c.get("/api/collection", headers=guest).json()["owned"]

    r = c.post("/api/account/link", headers={**guest, **bearer("tok-alice")})
    assert r.status_code == 200 and r.json()["linkedGuest"] is True
    me = c.get("/api/me", headers=bearer("tok-alice")).json()
    assert me["player"] == before["player"] and me["totals"]["taps"] == 30
    assert c.get("/api/collection", headers=bearer("tok-alice")).json()["owned"] == owned
    old = c.get("/api/me", headers=guest)
    assert old.status_code == 401 and old.json()["detail"]["code"] == "save_linked"


def test_new_device_gets_a_choice_between_saves(env):
    c, *_ = env
    c.post("/api/account/link", headers={"X-Player-Token": GUEST, **bearer("tok-alice")})
    other = {"X-Player-Token": "o" * 32}
    # an untouched guest on a new device just uses the account save
    assert c.post("/api/account/link", headers={**other, **bearer("tok-alice")}).status_code == 200
    play(c, other)
    r = c.post("/api/account/link", headers={**other, **bearer("tok-alice")})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "account_has_save" and detail["guest"]["taps"] == 30
    # both saves stay usable
    assert c.get("/api/me", headers=other).status_code == 200
    assert c.get("/api/me", headers=bearer("tok-alice")).status_code == 200


def test_account_without_save_and_a_save_of_another_account(env):
    c, *_ = env
    assert c.get("/api/me", headers=bearer("tok-bob")).json()["detail"]["code"] == "account_not_linked"
    assert c.get("/api/account", headers=bearer("tok-bob")).json() == {
        "user": {"id": "u-bob", "username": "bob", "email": None}, "save": None}
    r = c.post("/api/account/link", headers=bearer("tok-bob")).json()
    assert r["linkedGuest"] is False and r["save"]["shards"] == 1600
    c.post("/api/account/link", headers={"X-Player-Token": GUEST, **bearer("tok-alice")})
    taken = c.post("/api/account/link", headers={"X-Player-Token": GUEST, **bearer("tok-bob")})
    # bob already has a save, and alice's save is not a guest any more
    assert taken.status_code == 200 and taken.json()["save"]["shards"] == 1600


def test_expired_tokens_and_cache(env):
    c, _, fake, clock = env
    c.post("/api/account/link", headers=bearer("tok-alice"))
    calls = fake.calls
    for _ in range(3):
        assert c.get("/api/me", headers=bearer("tok-alice")).status_code == 200
    assert fake.calls == calls
    fake.down = True
    clock[0] += 301
    r = c.get("/api/me", headers=bearer("tok-alice"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "account_unavailable"
    fake.down = False
    r = c.get("/api/me", headers=bearer("tok-unknown"))
    assert r.status_code == 401 and r.json()["detail"]["code"] == "account_expired"


def test_room_join_uses_the_account_save(env):
    c, g, *_ = env
    c.post("/api/account/link", headers=bearer("tok-alice"))
    pid = g.store.linked_player("u-alice")
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        a.send_json({"type": "join", "room": "r1", "nick": "a", "accountToken": "tok-alice"})
        joined = a.receive_json()
        b.send_json({"type": "join", "room": "r1", "nick": "b", "token": GUEST})
        b.receive_json()
        a.receive_json()
    uid = joined["members"][0]["uid"]
    assert uid == g.profile_for(main.PlayerId(pid), "r1")["uid"]
