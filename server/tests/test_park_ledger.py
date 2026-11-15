"""GET /api/park/ledger: a save's own coin ledger and the codes it redeemed."""
from fastapi.testclient import TestClient

import app.main as main
from app.game import Game, player_id_for
from app.manifest import Manifest
from app.park import LEDGER_DAYS, Park
from app.redeem import HISTORY, Redeem
from app.store import Store, day_of

from fixtures import Clock, tiny_manifest

TOKEN = "ledger-player-token-0001"
OTHER = "ledger-player-token-0002"
KEY = {"X-Admin-Key": "admin-secret"}


def setup(manifest=None):
    clock = Clock()
    g = Game(Store(":memory:"), manifest or Manifest.load(), now=clock)
    park = Park(lambda: g)
    return g, park, Redeem(lambda: g, park), clock


def test_the_ledger_groups_by_day_newest_first_with_signed_amounts():
    g, park, _, clock = setup()
    pid = player_id_for(TOKEN)
    st = g.store
    st.add_coin_ledger(pid, "2026-11-01", "buy", 5, 5)
    st.add_coin_ledger(pid, "2026-11-01", "scratch", -2)
    st.add_coin_ledger(pid, "2026-11-01", "scratch", -1)
    st.add_coin_ledger(pid, "2026-11-03", "gift", 1)
    st.add_coin_ledger(pid, "2026-11-03", "race", -3)
    st.add_coin_ledger(pid, "2026-11-03", "stamp", 1, 1)
    # A stamp given and taken back on one day nets to nothing and is left out; so is a day with nothing else.
    st.add_coin_ledger(pid, "2026-11-03", "stamp", -1, 0)
    st.add_coin_ledger(pid, "2026-11-02", "stamp", 1, 1)
    st.add_coin_ledger(pid, "2026-11-02", "stamp", -1, 0)
    assert park.ledger(TOKEN) == {"days": [
        {"day": "2026-11-03", "items": [{"source": "gift", "amount": 1, "count": 1},
                                        {"source": "race", "amount": -3, "count": 1}]},
        {"day": "2026-11-01", "items": [{"source": "buy", "amount": 5, "count": 5},
                                        {"source": "scratch", "amount": -3, "count": 2}]},
    ]}


def test_the_ledger_shows_the_latest_days_with_rows_only():
    g, park, _, _ = setup()
    pid = player_id_for(TOKEN)
    days = [f"2026-10-{d:02d}" for d in range(1, LEDGER_DAYS + 3)]
    for d in days:
        g.store.add_coin_ledger(pid, d, "gift", 1)
    out = park.ledger(TOKEN)["days"]
    assert [d["day"] for d in out] == days[::-1][:LEDGER_DAYS]


def test_the_ledger_and_history_never_show_another_save():
    g, park, redeem, _ = setup()
    g.store.add_coin_ledger(player_id_for(OTHER), "2026-11-01", "buy", 9, 9)
    code = redeem.create(10, 0, 1, 5, 0.0, "n")["codes"][0]["code"]
    redeem.redeem(OTHER, code, False)
    assert park.ledger(TOKEN) == {"days": []}
    assert redeem.history(TOKEN) == {"redeems": []}
    assert len(redeem.history(OTHER)["redeems"]) == 1


def test_the_history_lists_codes_as_shown_newest_first_with_their_reward():
    g, park, redeem, clock = setup()
    first = redeem.create(30, 0, 1, 1, 0.0, "n")["codes"][0]["code"]
    custom = redeem.create(0, 2, 1, 5, 0.0, "n", "asoul2026")["codes"][0]["code"]
    redeem.redeem(TOKEN, first.replace("-", "").lower(), False)
    clock.t += 60
    redeem.redeem(TOKEN, custom, False)
    out = redeem.history(TOKEN)["redeems"]
    assert out == [{"code": "ASOUL2026", "ts": clock(), "shards": 0, "coins": 2},
                   {"code": first, "ts": clock() - 60, "shards": 30, "coins": 0}]
    assert len(first) == 14 and first.count("-") == 2
    # A code disabled later stays in the history of those who redeemed it.
    g.store.disable_redeem_code(g.store.redeem_code("ASOUL2026")["id"], clock())
    assert len(redeem.history(TOKEN)["redeems"]) == 2
    # Coins from a code reach the ledger under redeem.
    assert park.ledger(TOKEN)["days"][0]["items"] == [{"source": "redeem", "amount": 2, "count": 1}]


def test_the_history_keeps_the_latest_codes_only():
    g, _, redeem, clock = setup()
    codes = [c["code"] for c in redeem.create(1, 0, HISTORY + 2, 1, 0.0, "n")["codes"]]
    for c in codes:
        clock.t += 1
        redeem.redeem(TOKEN, c, False)
    out = redeem.history(TOKEN)["redeems"]
    assert len(out) == HISTORY
    assert [r["code"] for r in out] == codes[::-1][:HISTORY]


def test_http_ledger(monkeypatch):
    g, park, redeem, clock = setup()
    monkeypatch.setattr(main, "game", g)
    client = TestClient(main.app)
    assert client.get("/api/park/ledger").status_code == 401
    headers = {"X-Player-Token": TOKEN}
    pid = client.get("/api/me", headers=headers).json()["player"]
    g.store.add_coin_ledger(pid, day_of(clock()), "buy", 3, 3)
    code = redeem.create(0, 4, 1, 1, 0.0, "n")["codes"][0]["code"]
    redeem.redeem(TOKEN, code, False)
    r = client.get("/api/park/ledger", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"days", "redeems"}
    assert body["days"] == [{"day": day_of(clock()), "items": [{"source": "buy", "amount": 3, "count": 3},
                                                               {"source": "redeem", "amount": 4, "count": 1}]}]
    assert body["redeems"] == [{"code": code, "ts": clock(), "shards": 0, "coins": 4}]


def test_http_ledger_without_the_park(monkeypatch):
    g, *_ = setup(tiny_manifest())
    monkeypatch.setattr(main, "game", g)
    r = TestClient(main.app).get("/api/park/ledger", headers={"X-Player-Token": TOKEN})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_park"
