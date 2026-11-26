"""Feedback from the settings page (app/feedback.py) and the admin pages that read it."""
import pytest

import app.feedback as feedback
import app.main as main

from test_accounts import GUEST, bearer, env, play  # noqa: F401  (env is a fixture)

KEY = {"X-Admin-Key": "admin-secret"}
GUEST_HEADERS = {"X-Player-Token": GUEST, "X-Client-Version": "1.2.6"}


def token(n):
    return {"X-Player-Token": f"feedback-token-{n:04d}-{'x' * 12}"}


@pytest.fixture()
def fb(env, monkeypatch):
    monkeypatch.setattr(main, "ADMIN_KEY", "admin-secret")
    monkeypatch.setattr(feedback, "_addresses", {})
    monkeypatch.setattr(feedback, "_addresses_day", "")
    monkeypatch.setattr(feedback, "_requests", {})
    return env


def send(c, headers, text="背包里的表情一直在抖", **extra):
    return c.post("/api/feedback", json={"text": text, **extra}, headers=headers)


def test_a_save_sends_feedback_and_the_admin_reads_it(fb):
    c, g, *_ = fb
    play(c, GUEST_HEADERS)
    r = send(c, GUEST_HEADERS, "  背包里的表情一直在抖  ", contact=" QQ 123 ", system="Mozilla/5.0 (Windows NT 10.0)",
             log="line 1\nline 2\n")
    assert r.status_code == 200 and r.json()["left"] == feedback.PER_SAVE - 1
    page = c.get("/admin/feedback", headers=KEY).json()
    assert page["next"] is None
    [row] = page["feedback"]
    assert row["text"] == "背包里的表情一直在抖" and row["contact"] == "QQ 123"
    assert row["version"] == "1.2.6" and row["system"] == "Mozilla/5.0 (Windows NT 10.0)"
    assert row["player"] == str(main.player_id_for(GUEST)) and row["mainUserId"] is None
    assert row["logSize"] == len("line 1\nline 2\n") and "log" not in row
    one = c.get(f"/admin/feedback/{row['id']}", headers=KEY).json()
    assert one["log"] == "line 1\nline 2\n"


def test_the_admin_list_names_the_account_of_a_linked_save(fb):
    c, *_ = fb
    play(c, GUEST_HEADERS)
    assert c.post("/api/account/link", headers={**GUEST_HEADERS, **bearer("tok-alice")}).status_code == 200
    assert send(c, {**bearer("tok-alice"), "X-Client-Version": "1.2.6"}).status_code == 200
    assert c.get("/admin/feedback", headers=KEY).json()["feedback"][0]["mainUserId"] == "u-alice"


def test_a_save_sends_so_many_a_day(fb):
    c, g, *_ = fb
    play(c, GUEST_HEADERS)
    for n in range(feedback.PER_SAVE):
        assert send(c, GUEST_HEADERS).json()["left"] == feedback.PER_SAVE - n - 1
    over = send(c, GUEST_HEADERS)
    assert over.status_code == 429 and over.json()["detail"]["code"] == "feedback_limit"
    g.now.t += 24 * 3600
    assert send(c, GUEST_HEADERS).status_code == 200


def test_an_address_and_the_server_send_so_many_a_day(fb, monkeypatch):
    c, g, *_ = fb
    monkeypatch.setattr(feedback, "PER_ADDRESS", 2)
    monkeypatch.setattr(main, "_address", lambda request: "203.0.113.7")
    for n in range(3):
        play(c, token(n))
    assert send(c, token(0)).status_code == 200
    assert send(c, token(1)).status_code == 200
    over = send(c, token(2))
    assert over.status_code == 429 and over.json()["detail"]["code"] == "feedback_limit"
    # another address is counted on its own, up to what the server keeps a day
    monkeypatch.setattr(main, "_address", lambda request: "203.0.113.8")
    monkeypatch.setattr(feedback, "PER_SERVER", 3)
    assert send(c, token(2)).status_code == 200
    full = send(c, token(2))
    assert full.status_code == 429 and full.json()["detail"]["code"] == "feedback_full"


def test_refuses_an_empty_text_a_save_not_made_yet_and_an_oversized_log(fb):
    c, g, *_ = fb
    play(c, GUEST_HEADERS)
    empty = send(c, GUEST_HEADERS, "   ")
    assert empty.status_code == 400 and empty.json()["detail"]["code"] == "bad_feedback"
    fresh = send(c, token(9))
    assert fresh.status_code == 409 and fresh.json()["detail"]["code"] == "no_save"
    assert not g.store.has_player(main.player_id_for(token(9)["X-Player-Token"]))
    assert send(c, GUEST_HEADERS, log="x" * (feedback.LOG_MAX + 1)).status_code == 422
    assert send(c, GUEST_HEADERS, "字" * (feedback.TEXT_MAX + 1)).status_code == 422
    assert c.get("/admin/feedback", headers=KEY).json()["feedback"] == []


def test_the_admin_pages_through_and_deletes(fb, monkeypatch):
    c, *_ = fb
    monkeypatch.setattr(feedback, "PER_SAVE", 10)
    play(c, GUEST_HEADERS)
    ids = [send(c, GUEST_HEADERS, f"第 {n} 条").json()["id"] for n in range(5)]
    first = c.get("/admin/feedback?limit=3", headers=KEY).json()
    assert [r["id"] for r in first["feedback"]] == ids[:1:-1] and first["next"] == ids[2]
    rest = c.get(f"/admin/feedback?limit=3&before={first['next']}", headers=KEY).json()
    assert [r["id"] for r in rest["feedback"]] == ids[1::-1] and rest["next"] is None
    assert c.delete(f"/admin/feedback/{ids[0]}", headers=KEY).json() == {"ok": True}
    assert c.delete(f"/admin/feedback/{ids[0]}", headers=KEY).status_code == 409
    assert c.get(f"/admin/feedback/{ids[0]}", headers=KEY).status_code == 409
    assert c.get("/admin/feedback", headers={"X-Admin-Key": "wrong"}).status_code == 404


def test_a_resent_request_gets_its_receipt_again_and_counts_once(fb, monkeypatch):
    c, g, *_ = fb
    monkeypatch.setattr(feedback, "PER_ADDRESS", 2)
    monkeypatch.setattr(main, "_address", lambda request: "203.0.113.7")
    play(c, GUEST_HEADERS)
    rid = "0f9c3a52-6b1e-4d2a-9c7e-2f4b8a1d3e5c"
    first = send(c, GUEST_HEADERS, requestId=rid)
    again = send(c, GUEST_HEADERS, requestId=rid)
    assert first.status_code == again.status_code == 200
    assert again.json() == first.json() == {"id": first.json()["id"], "left": feedback.PER_SAVE - 1}
    assert len(c.get("/admin/feedback", headers=KEY).json()["feedback"]) == 1
    # the address counted the feedback once, so one more goes through
    assert send(c, GUEST_HEADERS).status_code == 200
    assert send(c, GUEST_HEADERS).status_code == 429
    # another save's request of the same id is its own feedback
    play(c, token(1))
    monkeypatch.setattr(main, "_address", lambda request: "203.0.113.8")
    other = send(c, token(1), requestId=rid)
    assert other.status_code == 200 and other.json()["id"] != first.json()["id"]


def test_the_last_feedback_of_the_day_resent_gets_its_receipt_not_the_limit(fb):
    c, g, *_ = fb
    play(c, GUEST_HEADERS)
    for _ in range(feedback.PER_SAVE - 1):
        assert send(c, GUEST_HEADERS).status_code == 200
    last = send(c, GUEST_HEADERS, requestId="last-one")
    assert last.json()["left"] == 0
    again = send(c, GUEST_HEADERS, requestId="last-one")
    assert again.status_code == 200 and again.json() == last.json()
    assert send(c, GUEST_HEADERS, requestId="a-new-one").status_code == 429


def test_a_request_id_is_short_letters_digits_and_dashes(fb):
    c, g, *_ = fb
    play(c, GUEST_HEADERS)
    assert send(c, GUEST_HEADERS, requestId="x" * 65).status_code == 422
    assert send(c, GUEST_HEADERS, requestId="a b").status_code == 422
    assert send(c, GUEST_HEADERS, requestId="").status_code == 200
    assert send(c, GUEST_HEADERS, requestId="").json()["left"] == feedback.PER_SAVE - 2

