import json
import threading

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import Game, GameError, player_id_for
from app.manifest import Manifest
from app.park import Park
from app.redeem import ALPHABET, LOCK_COUNT, LOCK_SECONDS, TRIES, TRY_WINDOW, Redeem, generate, normalize, shown
from app.store import Store, day_of

from fixtures import Clock, tiny_manifest
from test_accounts import bearer, env  # noqa: F401  (env is a fixture)
from test_admin import link

TOKEN = "redeem-player-token-0001"
OTHER = "redeem-player-token-0002"
KEY = {"X-Admin-Key": "admin-secret"}


def setup(manifest=None):
    clock = Clock()
    g = Game(Store(":memory:"), manifest or Manifest.load(), now=clock)
    park = Park(lambda: g)
    r = Redeem(lambda: g, park)
    return g, r, clock


def make(r, shards=100, coins=0, count=1, uses=1, expires=0.0, note="测试", custom="", actor="len"):
    return r.create(shards, coins, count, uses, expires, note, custom, actor)["codes"]


def code_of(r, **kw):
    return make(r, **kw)[0]["code"]


def error(fn, *args):
    with pytest.raises(GameError) as e:
        fn(*args)
    return e.value


# ------------------------------------------------------------------- format
def test_generated_codes_avoid_confusable_characters_and_show_in_groups():
    assert len(ALPHABET) == len(set(ALPHABET)) == 31
    assert not set("0O1IL") & set(ALPHABET)
    for _ in range(200):
        c = generate()
        assert len(c) == 12 and set(c) <= set(ALPHABET)
    assert shown("K7QM3XRPWD9H", False) == "K7QM-3XRP-WD9H"
    assert shown("ASOUL2026", True) == "ASOUL2026"
    assert normalize(" k7qm-3xrp wd9h\n") == "K7QM3XRPWD9H"


# ------------------------------------------------------------------- redeem
def test_a_code_pays_shards_and_coins_once_whatever_the_case_and_dashes():
    g, r, clock = setup()
    pid = player_id_for(TOKEN)
    g.status(TOKEN)
    g.store.update_player(pid, coins=Manifest.load().park["coin"]["hold"])
    before = g.status(TOKEN)["shards"]
    code = code_of(r, shards=300, coins=2)
    assert code.count("-") == 2
    out = r.redeem(TOKEN, code.lower().replace("-", " "), False)
    assert out["redeemed"] == {"shards": 300, "coins": 2}
    assert out["shards"] == before + 300
    # Coins from codes ignore the holding cap.
    assert out["park"]["coins"] == Manifest.load().park["coin"]["hold"] + 2
    day = day_of(clock())
    assert g.store.ledger_amount(pid, day, "redeem") == 300
    assert [row for row in g.store.coin_ledger_by_day(day) if row["source"] == "redeem"][0]["amount"] == 2
    assert error(r.redeem, TOKEN, code, False).code == "already_redeemed"
    assert g.status(TOKEN)["shards"] == before + 300


def test_a_one_person_code_is_used_up_by_the_first_save():
    _, r, _ = setup()
    code = code_of(r)
    r.redeem(TOKEN, code, False)
    assert error(r.redeem, OTHER, code, False).code == "code_used_up"


def test_a_universal_code_serves_n_saves_once_each():
    g, r, _ = setup()
    code = code_of(r, uses=3)
    tokens = [f"redeem-universal-token-{i:04d}" for i in range(4)]
    for t in tokens[:3]:
        assert r.redeem(t, code, False)["redeemed"]["shards"] == 100
    assert error(r.redeem, tokens[0], code, False).code == "already_redeemed"
    assert error(r.redeem, tokens[3], code, False).code == "code_used_up"
    assert r.find(code, 10)["codes"][0]["used"] == 3


def test_expired_disabled_and_unknown_codes():
    g, r, clock = setup()
    expiring = code_of(r, expires=clock() + 60)
    disabled = make(r)[0]
    r.disable(disabled["id"], "len")
    clock.t += 60
    assert error(r.redeem, TOKEN, expiring, False).code == "code_expired"
    # A disabled code reads like one that never existed.
    assert error(r.redeem, TOKEN, disabled["code"], False).code == "bad_code"
    assert error(r.redeem, TOKEN, "ZZZZ-ZZZZ-ZZZZ", False).code == "bad_code"


def test_an_expired_code_already_redeemed_says_so():
    g, r, clock = setup()
    code = code_of(r, uses=5, expires=clock() + 60)
    r.redeem(TOKEN, code, False)
    clock.t += 120
    assert error(r.redeem, TOKEN, code, False).code == "already_redeemed"
    assert error(r.redeem, OTHER, code, False).code == "code_expired"


def test_codes_need_an_account_when_the_server_has_them():
    g, r, _ = setup()
    code = code_of(r)
    assert error(r.redeem, TOKEN, code, True).code == "login_required"
    g.store.link_account("u-1", player_id_for(TOKEN), g.now())
    assert r.redeem(TOKEN, code, True)["redeemed"]["shards"] == 100


def test_a_server_without_the_park_pays_shards_and_answers_without_park():
    g, r, _ = setup(tiny_manifest())
    out = r.redeem(TOKEN, code_of(r, shards=50), False)
    assert out["redeemed"] == {"shards": 50, "coins": 0} and "park" not in out
    assert error(make, r, 0, 1).code == "bad_reward"


# ------------------------------------------------------------------ lockout
def wrong(r, token=TOKEN, n=1):
    return [error(r.redeem, token, f"WRONG{i}", False).code for i in range(n)]


def test_five_wrong_codes_in_ten_minutes_lock_the_save_for_fifteen():
    g, r, clock = setup()
    code = code_of(r)
    assert wrong(r, n=TRIES - 1) == ["bad_code"] * (TRIES - 1)
    # A right code does not count, and does not clear the wrong ones.
    r.redeem(TOKEN, code, False)
    e = error(r.redeem, TOKEN, "WRONG", False)
    assert e.code == "too_many_tries" and e.seconds == LOCK_SECONDS
    other = code_of(r)
    clock.t += LOCK_SECONDS - 10
    e = error(r.redeem, TOKEN, other, False)
    assert e.code == "too_many_tries" and e.seconds == 10
    # Another save is not locked.
    assert wrong(r, OTHER) == ["bad_code"]
    clock.t += 10
    assert r.redeem(TOKEN, other, False)["redeemed"]["shards"] == 100
    # The lock started the count over.
    assert wrong(r, n=TRIES - 1) == ["bad_code"] * (TRIES - 1)
    assert g.store.redeem_locks_since(0, 10)[0]["locks"] == 1


def test_wrong_codes_older_than_ten_minutes_are_forgotten():
    _, r, clock = setup()
    wrong(r, n=TRIES - 1)
    clock.t += TRY_WINDOW
    assert wrong(r, n=TRIES - 1) == ["bad_code"] * (TRIES - 1)
    assert wrong(r) == ["too_many_tries"]


def test_disabled_codes_count_as_wrong_and_lockouts_are_counted():
    g, r, clock = setup()
    disabled = make(r)[0]
    r.disable(disabled["id"])
    for _ in range(TRIES - 1):
        assert error(r.redeem, TOKEN, disabled["code"], False).code == "bad_code"
    assert error(r.redeem, TOKEN, disabled["code"], False).code == "too_many_tries"
    g.tracker.flush()
    with g.store.lock:
        n = g.store._db.execute("SELECT count FROM daily_counts WHERE day = ? AND key = ?",
                                (day_of(clock()), LOCK_COUNT)).fetchone()[0]
    assert n == 1
    rows = g.store.redeem_locks_since(clock() - 1, 10)
    assert [(x["player_id"], x["locks"]) for x in rows] == [(player_id_for(TOKEN), 1)]


def test_wrong_codes_from_a_guest_on_an_account_server_do_not_count():
    _, r, _ = setup()
    for _ in range(TRIES + 1):
        assert error(r.redeem, TOKEN, "WRONG", True).code == "login_required"
    assert wrong(r) == ["bad_code"]


# ------------------------------------------------------------- concurrency
def race(fn, args_list):
    """Runs fn(*args) for each args at once; returns each result's code ("ok" or the error)."""
    barrier = threading.Barrier(len(args_list))
    out = [None] * len(args_list)

    def run(i, args):
        barrier.wait()
        try:
            fn(*args)
            out[i] = "ok"
        except GameError as e:
            out[i] = e.code

    threads = [threading.Thread(target=run, args=(i, a)) for i, a in enumerate(args_list)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def test_two_saves_racing_for_the_last_use_get_one_each_at_most():
    for _ in range(20):
        g, r, _ = setup()
        code = code_of(r, uses=2)
        r.redeem("redeem-first-token-00001", code, False)
        assert sorted(race(r.redeem, [(TOKEN, code, False), (OTHER, code, False)])) == ["code_used_up", "ok"]
        row = r.find(code, 1)["codes"][0]
        assert row["used"] == 2
        assert len(r.claims(row["id"], 10)["claims"]) == 2


def test_one_save_racing_itself_redeems_once():
    for _ in range(20):
        g, r, _ = setup()
        code = code_of(r, uses=5)
        before = g.status(TOKEN)["shards"]
        assert sorted(race(r.redeem, [(TOKEN, code, False)] * 3)) == ["already_redeemed", "already_redeemed", "ok"]
        assert g.status(TOKEN)["shards"] == before + 100


# -------------------------------------------------------------------- admin
def test_batches_make_distinct_codes_and_log_the_note():
    g, r, clock = setup()
    codes = make(r, shards=50, coins=1, count=20, note="11 月 QQ 群活动", actor="len")
    assert len({c["code"] for c in codes}) == 20
    first = codes[0]
    assert {k: first[k] for k in ("shards", "coins", "uses", "used", "expires", "disabled", "custom", "createdBy")} == {
        "shards": 50, "coins": 1, "uses": 1, "used": 0, "expires": None, "disabled": None, "custom": False,
        "createdBy": "len"}
    entry = g.admin_log(None, 1)["entries"][0]
    assert entry["action"] == "code_create" and entry["actor"] == "len" and entry["reason"] == "11 月 QQ 群活动"
    assert entry["detail"]["count"] == 20 and entry["detail"]["ids"] == [codes[0]["id"], codes[-1]["id"]]


def test_custom_codes():
    g, r, _ = setup()
    assert code_of(r, custom="asoul-2026", uses=100) == "ASOUL2026"
    assert r.redeem(TOKEN, "Asoul 2026", False)["redeemed"]["shards"] == 100
    assert error(make, r, 100, 0, 1, 1, 0.0, "", "ASOUL 2026").code == "code_taken"
    assert error(make, r, 100, 0, 2, 1, 0.0, "", "OTHER2026").code == "bad_count"
    assert error(make, r, 100, 0, 1, 1, 0.0, "", "A!").code == "bad_code_text"
    assert code_of(r, custom="然然生日快乐") == "然然生日快乐"


def test_creating_checks_the_reward_and_the_expiry():
    _, r, clock = setup()
    assert error(make, r, 0, 0).code == "bad_reward"
    assert error(make, r, 10, 0, 1, 1, clock() - 1).code == "bad_expiry"


def test_search_finds_codes_by_part_of_code_or_note_and_pages():
    _, r, _ = setup()
    a = make(r, note="QQ 群")[0]
    make(r, count=3, note="B 站抽奖")
    assert [c["id"] for c in r.find("qq", 10)["codes"]] == []
    assert [c["id"] for c in r.find("QQ 群", 10)["codes"]] == [a["id"]]
    assert [c["id"] for c in r.find(a["code"][5:9].lower(), 10)["codes"]] == [a["id"]]
    page = r.find("", 2)["codes"]
    assert len(page) == 2 and page[0]["id"] > page[1]["id"]
    rest = r.find("", 10, page[-1]["id"])["codes"]
    assert len(rest) == 2 and rest[0]["id"] < page[-1]["id"]


def test_disabling_stops_a_code_once_and_logs_it():
    g, r, _ = setup()
    c = make(r, uses=10, note="群活动")[0]
    r.redeem(TOKEN, c["code"], False)
    out = r.disable(c["id"], "len")
    assert out["disabled"] is not None
    assert r.disable(c["id"], "len")["disabled"] == out["disabled"]
    entries = [e for e in g.admin_log(None, 10)["entries"] if e["action"] == "code_disable"]
    assert len(entries) == 1 and entries[0]["reason"] == "群活动" and entries[0]["detail"]["code"] == c["code"]
    assert error(r.redeem, OTHER, c["code"], False).code == "bad_code"
    assert error(r.disable, 9999).code == "no_code"
    assert error(r.claims, 9999, 10).code == "no_code"


def test_claims_list_saves_and_accounts():
    g, r, clock = setup()
    c = make(r, uses=5)[0]
    g.store.link_account("u-1", player_id_for(OTHER), clock())
    r.redeem(TOKEN, c["code"], False)
    clock.t += 5
    r.redeem(OTHER, c["code"], False)
    out = r.claims(c["id"], 10)
    assert out["code"]["used"] == 2
    assert out["claims"] == [{"player": player_id_for(OTHER), "userId": "u-1", "ts": clock()},
                             {"player": player_id_for(TOKEN), "userId": None, "ts": clock() - 5}]


# --------------------------------------------------------------------- HTTP
@pytest.fixture()
def http(env, monkeypatch):
    """A server with main-site accounts (env) and the admin key."""
    monkeypatch.setattr(main, "ADMIN_KEY", "admin-secret")
    return env


def test_http_redeem_needs_a_linked_account_on_an_account_server(http):
    c, g, *_ = http
    code = c.post("/admin/codes", json={"shards": 70, "uses": 5}, headers=KEY).json()["codes"][0]["code"]
    guest = {"X-Player-Token": "h" * 32}
    c.get("/api/me", headers=guest)
    r = c.post("/api/redeem", json={"code": code}, headers=guest)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "login_required"
    link(c, "tok-alice", "a" * 32)
    me = bearer("tok-alice")
    before = c.get("/api/me", headers=me).json()["shards"]
    r = c.post("/api/redeem", json={"code": code.lower()}, headers=me)
    assert r.status_code == 200, r.text
    body = r.json()
    # The tiny manifest has no park.
    assert body["redeemed"] == {"shards": 70, "coins": 0} and body["shards"] == before + 70 and "park" not in body
    r = c.post("/api/redeem", json={"code": code}, headers=me)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_redeemed"


def test_http_lockout_answers_429_with_the_seconds(http):
    c, *_ = http
    link(c, "tok-alice", "a" * 32)
    me = bearer("tok-alice")
    for _ in range(TRIES - 1):
        r = c.post("/api/redeem", json={"code": "nope"}, headers=me)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "bad_code"
    r = c.post("/api/redeem", json={"code": "nope"}, headers=me)
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "too_many_tries" and r.json()["detail"]["seconds"] == LOCK_SECONDS
    assert r.headers["Retry-After"] == str(LOCK_SECONDS)


def test_http_redeem_on_a_server_without_accounts_with_the_park(monkeypatch):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), now=clock)
    monkeypatch.setattr(main, "game", g)
    monkeypatch.setattr(main, "accounts", None)
    monkeypatch.setattr(main, "ADMIN_KEY", "admin-secret")
    c = TestClient(main.app)
    code = c.post("/admin/codes", json={"coins": 3, "note": "n"}, headers=KEY).json()["codes"][0]["code"]
    r = c.post("/api/redeem", json={"code": code}, headers={"X-Player-Token": TOKEN})
    assert r.status_code == 200, r.text
    assert r.json()["redeemed"] == {"shards": 0, "coins": 3} and r.json()["park"]["coins"] == 3


def test_http_admin_codes(http):
    c, g, *_ = http
    assert c.post("/admin/codes", json={"shards": 1}).status_code == 404
    actor = {**KEY, "X-Admin-Actor": "%E5%B0%8F%E8%8D%89"}
    r = c.post("/admin/codes", json={"shards": 10, "count": 3, "uses": 1, "note": " 群活动 "}, headers=actor)
    assert r.status_code == 200, r.text
    codes = r.json()["codes"]
    assert len(codes) == 3 and all(len(x["code"]) == 14 for x in codes)
    assert g.admin_log(None, 1)["entries"][0]["actor"] == "小草"
    assert c.post("/admin/codes", json={"shards": 10, "count": 501}, headers=KEY).status_code == 422
    r = c.post("/admin/codes", json={"shards": 0}, headers=KEY)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_reward"
    r = c.post("/admin/codes", json={"shards": 5, "code": "ASOUL"}, headers=KEY)
    assert r.status_code == 200
    r = c.post("/admin/codes", json={"shards": 5, "code": "asoul"}, headers=KEY)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "code_taken"

    listed = c.get("/admin/codes", params={"q": "群活动"}, headers=KEY).json()["codes"]
    assert [x["id"] for x in listed] == [x["id"] for x in reversed(codes)]
    assert len(c.get("/admin/codes", params={"limit": 2}, headers=KEY).json()["codes"]) == 2

    link(c, "tok-alice", "a" * 32)
    assert c.post("/api/redeem", json={"code": codes[0]["code"]}, headers=bearer("tok-alice")).status_code == 200
    claims = c.get(f"/admin/codes/{codes[0]['id']}/claims", headers=KEY).json()
    assert claims["code"]["used"] == 1 and [x["userId"] for x in claims["claims"]] == ["u-alice"]

    r = c.post(f"/admin/codes/{codes[1]['id']}/disable", json={"reason": "发错了"}, headers=actor)
    assert r.status_code == 200 and r.json()["disabled"] is not None
    entry = g.admin_log(None, 1)["entries"][0]
    assert entry["action"] == "code_disable" and entry["reason"] == "发错了"
    assert c.post(f"/admin/codes/{codes[2]['id']}/disable", headers=KEY).status_code == 200
    for path in ("/admin/codes/9999/claims",):
        r = c.get(path, headers=KEY)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "no_code"
    r = c.post("/admin/codes/9999/disable", headers=KEY)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_code"
    detail = json.dumps(g.admin_log(None, 10)["entries"], ensure_ascii=False)
    # The log names codes it disabled, never the batch's codes.
    assert codes[0]["code"] not in detail
