"""One address may start only so many saves within an hour (main.NEW_SAVES_PER_HOUR)."""
from types import SimpleNamespace

import pytest

import app.main as main

from test_accounts import env  # noqa: F401  (env is a fixture)


def token(n):
    return {"X-Player-Token": f"new-save-token-{n:04d}-{'x' * 12}"}


@pytest.fixture()
def limited(env, monkeypatch):
    where = ["203.0.113.7"]
    monkeypatch.setattr(main, "NEW_SAVES_PER_HOUR", 2)
    monkeypatch.setattr(main, "_new_saves", {})
    monkeypatch.setattr(main, "_address", lambda request: where[0])
    return env[0], env[1], where


def test_an_address_starts_only_so_many_saves_within_the_hour(limited):
    c, g, where = limited
    assert c.get("/api/me", headers=token(1)).status_code == 200
    assert c.get("/api/me", headers=token(2)).status_code == 200
    third = c.get("/api/me", headers=token(3))
    assert third.status_code == 429 and third.json()["detail"]["code"] == "too_many_saves"
    assert not g.store.has_player(main.player_id_for(token(3)["X-Player-Token"]))
    # the saves it has go on as before, and another address is counted on its own
    assert c.get("/api/me", headers=token(1)).status_code == 200
    where[0] = "203.0.113.8"
    assert c.get("/api/me", headers=token(3)).status_code == 200
    where[0] = "203.0.113.7"
    assert c.get("/api/me", headers=token(4)).status_code == 429
    g.now.t += main.NEW_SAVE_SECONDS
    assert c.get("/api/me", headers=token(4)).status_code == 200


def test_a_token_asking_again_before_its_save_is_made_counts_once(limited):
    c, g, _ = limited
    request, who = SimpleNamespace(), main.PlayerId("a" * 16)
    main._may_start_save(request, who)
    main._may_start_save(request, who)
    main._may_start_save(request, main.PlayerId("b" * 16))
    with pytest.raises(main.HTTPException) as refused:
        main._may_start_save(request, main.PlayerId("c" * 16))
    assert refused.value.status_code == 429


def test_no_limit_when_it_is_off_or_the_request_is_from_this_machine(env, monkeypatch):
    c, *_ = env
    monkeypatch.setattr(main, "_new_saves", {})
    monkeypatch.setattr(main, "NEW_SAVES_PER_HOUR", 1)
    for n in range(3):  # the test client has no address to count
        assert c.get("/api/me", headers=token(10 + n)).status_code == 200
    monkeypatch.setattr(main, "_address", lambda request: "203.0.113.9")
    monkeypatch.setattr(main, "NEW_SAVES_PER_HOUR", 0)
    for n in range(3):
        assert c.get("/api/me", headers=token(20 + n)).status_code == 200


def test_the_address_a_request_is_counted_under():
    def of(host):
        return main._address(SimpleNamespace(client=SimpleNamespace(host=host) if host is not None else None))
    assert of("203.0.113.7") == "203.0.113.7"
    assert of("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == of("2001:db8:1:2::1") == "2001:db8:1:2::/64"
    assert of("127.0.0.1") is None and of("::1") is None
    assert of("testclient") is None and of(None) is None
