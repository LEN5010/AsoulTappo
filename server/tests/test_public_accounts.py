"""Public rooms on a server with main-site accounts: the list and listing a room need an account, joining by id does not."""
import app.main as main
from test_accounts import GUEST, bearer, env  # noqa: F401  (env is the fixture with a fake main site)

OTHER_GUEST = "h" * 32


def join(ws, nick, **who):
    ws.send_json({"type": "join", "room": "r1", "nick": nick, **who})
    return ws.receive_json()


def test_the_list_needs_a_signed_in_account(env):
    c, *_ = env
    r = c.get("/rooms")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "account_required"
    r = c.get("/rooms", headers={"X-Player-Token": GUEST})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "account_required"
    r = c.get("/rooms", headers=bearer("tok-nobody"))
    assert r.status_code == 401 and r.json()["detail"]["code"] == "account_expired"
    # bob has no save linked: the list is shown all the same
    assert c.get("/rooms", headers=bearer("tok-bob")).json() == {"rooms": []}


def test_a_main_site_outage_answers_503_not_an_empty_list(env):
    c, g, fake, clock = env
    fake.down = True
    r = c.get("/rooms", headers=bearer("tok-alice"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "account_unavailable"


def test_only_a_host_signed_in_lists_the_room_and_guests_join_by_id(env):
    c, g, *_ = env
    c.post("/api/account/link", headers=bearer("tok-alice"))
    with c.websocket_connect("/ws") as guest, c.websocket_connect("/ws") as alice:
        jg = join(guest, "游客", token=GUEST)
        join(alice, "alice", accountToken="tok-alice")
        guest.receive_json()  # member_joined alice
        # the guest host has a save but no account
        guest.send_json({"type": "set_public", "public": True})
        assert guest.receive_json()["code"] == "host_needs_account"
        # taking the room off the list is always allowed
        guest.send_json({"type": "set_public", "public": False})
        assert guest.receive_json() == {"type": "room_info", "host": jg["you"], "public": False}
        guest.send_json({"type": "leave"})
        alice.receive_json()  # member_left
        assert alice.receive_json()["host"] != jg["you"]  # alice hosts now
        alice.send_json({"type": "set_public", "public": True})
        assert alice.receive_json()["public"] is True
        assert [r["room"] for r in c.get("/rooms", headers=bearer("tok-bob")).json()["rooms"]] == ["r1"]
        # a guest save joins the public room by its id; a connection without a save still cannot
        with c.websocket_connect("/ws") as other, c.websocket_connect("/ws") as nobody:
            assert join(other, "游客2", token=OTHER_GUEST)["type"] == "joined"
            refused = join(nobody, "无存档")
            assert refused["code"] == "room_full" and refused["reason"] == "need_save"
            alice.receive_json()  # member_joined
        alice.receive_json()  # member_left


def test_an_account_without_a_save_cannot_list_the_room(env):
    c, *_ = env
    with c.websocket_connect("/ws") as bob:
        join(bob, "bob", accountToken="tok-bob")
        bob.send_json({"type": "set_public", "public": True})
        assert bob.receive_json()["code"] == "host_needs_save"


def test_the_room_stays_public_when_the_host_passes_to_a_guest(env):
    c, *_ = env
    c.post("/api/account/link", headers=bearer("tok-alice"))
    with c.websocket_connect("/ws") as guest:
        with c.websocket_connect("/ws") as alice:
            join(alice, "alice", accountToken="tok-alice")
            jg = join(guest, "游客", token=GUEST)
            alice.receive_json()
            alice.send_json({"type": "set_public", "public": True})
            alice.receive_json()
            guest.receive_json()
        assert guest.receive_json()["type"] == "member_left"
        assert guest.receive_json() == {"type": "room_info", "host": jg["you"], "public": True}
        assert [r["room"] for r in c.get("/rooms", headers=bearer("tok-bob")).json()["rooms"]] == ["r1"]
        # the guest host may take it off the list, but not put it back
        guest.send_json({"type": "set_public", "public": False})
        assert guest.receive_json()["public"] is False
        guest.send_json({"type": "set_public", "public": True})
        assert guest.receive_json()["code"] == "host_needs_account"


def test_a_server_without_accounts_keeps_the_open_list_and_the_save_rule(env, monkeypatch):
    c, *_ = env
    monkeypatch.setattr(main, "accounts", None)
    monkeypatch.setattr(main, "MAIN_API_URL", "")
    assert c.get("/rooms").json() == {"rooms": []}
    with c.websocket_connect("/ws") as guest:
        jg = join(guest, "游客", token=GUEST)
        guest.send_json({"type": "set_public", "public": True})
        assert guest.receive_json() == {"type": "room_info", "host": jg["you"], "public": True}
    with c.websocket_connect("/ws") as nobody:
        join(nobody, "无存档")
        nobody.send_json({"type": "set_public", "public": True})
        assert nobody.receive_json()["code"] == "host_needs_save"
