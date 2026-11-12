import http.client

import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.accounts as accounts_module
from app.accounts import CACHE_SECONDS, RETRY_SECONDS, STALE_SECONDS, MainAccounts, http_me
from app.cards import DropConfig
from app.game import Game, GameError, player_id_for
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
        self.status = None  # an answer other than 200/401, e.g. 502
        self.error = None  # raised instead of answering
        self.revoked = set()

    def __call__(self, url, token):
        assert url == "https://main.test/api/auth/me"
        self.calls += 1
        if self.down:
            raise OSError("unreachable")
        if self.error:
            raise self.error
        if self.status:
            return self.status, None
        return (200, {"user": USERS[token]}) if token in USERS and token not in self.revoked else (401, None)


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


def test_linking_again_reports_the_guest_that_already_is_the_account_save(env):
    # The first answer never reached the client, so it signs in and links again with the same guest token.
    c, *_ = env
    guest = {"X-Player-Token": GUEST}
    play(c, guest)
    assert c.post("/api/account/link", headers={**guest, **bearer("tok-alice")}).json()["linkedGuest"] is True
    again = c.post("/api/account/link", headers={**guest, **bearer("tok-alice")})
    assert again.status_code == 200 and again.json()["linkedGuest"] is True


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
    clock[0] += 3601
    r = c.get("/api/me", headers=bearer("tok-alice"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "account_unavailable"
    fake.down = False
    clock[0] += RETRY_SECONDS
    r = c.get("/api/me", headers=bearer("tok-unknown"))
    assert r.status_code == 401 and r.json()["detail"]["code"] == "account_expired"


def accounts_with(fake):
    clock = [0.0]
    return MainAccounts("https://main.test/api", fake, lambda: clock[0]), clock


@pytest.mark.parametrize("failure", ["down", "status", "error"])
def test_a_failing_main_site_serves_the_last_answer_for_an_hour(failure):
    fake = FakeMain()
    accounts, clock = accounts_with(fake)
    alice = accounts.user_for("tok-alice")
    clock[0] = CACHE_SECONDS
    setattr(fake, failure, {"down": True, "status": 502,
                            "error": http.client.IncompleteRead(b"{")}[failure])
    assert accounts.user_for("tok-alice") == alice
    assert fake.calls == 2
    # A token never answered before has nothing to fall back to.
    with pytest.raises(GameError) as e:
        accounts.user_for("tok-bob")
    assert e.value.code == "account_unavailable"
    clock[0] = STALE_SECONDS
    assert accounts.user_for("tok-alice") == alice
    clock[0] = STALE_SECONDS + 1
    with pytest.raises(GameError) as e:
        accounts.user_for("tok-alice")
    assert e.value.code == "account_unavailable"


def test_after_a_failure_the_main_site_rests_for_the_retry_window():
    fake = FakeMain()
    accounts, clock = accounts_with(fake)
    accounts.user_for("tok-alice")
    clock[0] = CACHE_SECONDS
    fake.down = True
    accounts.user_for("tok-alice")
    fake.down = False
    clock[0] += RETRY_SECONDS - 1
    # Inside the window no token reaches the main site: stale answers or account_unavailable at once.
    assert accounts.user_for("tok-alice")["id"] == "u-alice"
    with pytest.raises(GameError) as e:
        accounts.user_for("tok-bob")
    assert e.value.code == "account_unavailable"
    assert fake.calls == 2
    clock[0] += 1
    assert accounts.user_for("tok-bob")["id"] == "u-bob"
    assert accounts.user_for("tok-alice")["id"] == "u-alice"
    assert fake.calls == 4


def test_a_failing_main_site_is_tried_by_one_request_at_a_time():
    fake = FakeMain()
    accounts, clock = accounts_with(fake)
    fake.down = True
    with pytest.raises(GameError):
        accounts.user_for("tok-alice")
    fake.down = False
    clock[0] += RETRY_SECONDS
    seen = []

    def slow(url, token):
        # A request arriving while this one waits on the main site is answered at once.
        with pytest.raises(GameError) as e:
            accounts.user_for("tok-bob")
        seen.append(e.value.code)
        return fake(url, token)

    accounts.fetch = slow
    assert accounts.user_for("tok-alice")["id"] == "u-alice"
    assert seen == ["account_unavailable"]
    assert fake.calls == 2
    # The main site answered, so nobody is held back any longer.
    accounts.fetch = fake
    assert accounts.user_for("tok-bob")["id"] == "u-bob"
    assert fake.calls == 3


def test_an_expired_token_is_forgotten_at_once():
    fake = FakeMain()
    accounts, clock = accounts_with(fake)
    accounts.user_for("tok-alice")
    clock[0] = CACHE_SECONDS
    fake.revoked.add("tok-alice")
    with pytest.raises(GameError) as e:
        accounts.user_for("tok-alice")
    assert e.value.code == "account_expired"
    # A 401 is an answer, not a failure: no retry window, and no stale fallback afterwards.
    fake.down = True
    with pytest.raises(GameError) as e:
        accounts.user_for("tok-alice")
    assert e.value.code == "account_unavailable"
    assert fake.calls == 3


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


def test_room_skins_are_checked_against_the_save(env):
    c, g, *_ = env
    skin = {"type": "join", "room": "r1", "nick": "a", "token": GUEST, "character": "嘉然山海经"}
    with c.websocket_connect("/ws") as a:
        # not owned: the member is shown instead, and the join still goes through
        a.send_json(skin)
        assert a.receive_json()["members"][0]["character"] == "嘉然"
    g.store.add_item(player_id_for(GUEST), "char:嘉然山海经", g.now())
    with c.websocket_connect("/ws") as a:
        a.send_json(skin)
        assert a.receive_json()["members"][0]["character"] == "嘉然山海经"


def test_unknown_characters_fall_back_to_the_first_member(env):
    c, *_ = env
    with c.websocket_connect("/ws") as a:
        a.send_json({"type": "join", "room": "r1", "nick": "a", "character": "nobody"})
        assert a.receive_json()["members"][0]["character"] == "嘉然"


def test_state_with_an_unowned_skin_is_locked_and_not_broadcast(env):
    c, *_ = env
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        # base characters need no token
        a.send_json({"type": "join", "room": "r1", "nick": "a", "character": "嘉然"})
        you = a.receive_json()["you"]
        b.send_json({"type": "join", "room": "r1", "nick": "b", "token": GUEST})
        b.receive_json()
        a.receive_json()  # member_joined(b)
        a.send_json({"type": "state", "character": "嘉然山海经", "nick": "a2"})
        assert a.receive_json()["code"] == "locked"
        a.send_json({"type": "state", "character": "嘉然", "nick": "a3"})
        expected = {"type": "state", "id": you, "character": "嘉然", "nick": "a3", "plate": None, "status": None}
        assert b.receive_json() == expected  # the locked message never reached b
        assert a.receive_json() == expected


def test_answers_are_reused_for_a_spread_of_times():
    fake = FakeMain()
    clock = [0.0]
    spreads = iter([0.0, 100.0, 0.0, 0.0])
    accounts = MainAccounts("https://main.test/api", fake, lambda: clock[0], lambda: next(spreads))
    accounts.user_for("tok-alice")
    accounts.user_for("tok-bob")
    # Answered together, asked again at different times.
    clock[0] = CACHE_SECONDS - 100
    accounts.user_for("tok-alice")
    accounts.user_for("tok-bob")
    assert fake.calls == 3
    clock[0] = CACHE_SECONDS
    accounts.user_for("tok-alice")
    assert fake.calls == 4


def test_lookups_carry_the_shared_key(monkeypatch):
    seen = {}

    class Answer:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"user": {"id": "u"}}'

    def urlopen(req, timeout):
        seen.clear()
        seen.update(req.header_items())
        return Answer()

    monkeypatch.setattr(accounts_module.urllib.request, "urlopen", urlopen)
    assert http_me("https://main.test/api/auth/me", "t", key="k") == (200, {"user": {"id": "u"}})
    assert seen["X-game-key"] == "k" and seen["Authorization"] == "Bearer t"
    http_me("https://main.test/api/auth/me", "t")
    assert "X-game-key" not in seen
