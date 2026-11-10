import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.cards import DropConfig
from app.game import Game, player_id_for
from app.store import Store

from fixtures import Clock, SeqRng, tiny_manifest

TOKEN = "t" * 32
H = {"X-Player-Token": TOKEN}
BATCH = {"session": "test-session-0001", "sequence": 1}


@pytest.fixture()
def client(monkeypatch):
    g = Game(Store(":memory:"), tiny_manifest(), DropConfig(max_taps_per_sec=10**5),
             SeqRng(0.0), Clock())
    g.status(TOKEN)
    g.now.t += 1
    monkeypatch.setattr(main, "game", g)
    main.manager.rooms.clear()
    with TestClient(main.app) as c:  # one portal/event loop shared by all sockets
        yield c


def test_token_required(client):
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/activity", json={**BATCH, "taps": 1}).status_code == 401
    assert client.get("/api/me", headers={"X-Player-Token": "short"}).status_code == 401


def test_activity_resonance_collection_flow(client):
    r = client.post("/api/activity", json={**BATCH, "taps": 25}, headers=H).json()
    assert r["credited"] == r["totals"]["taps"] == 25
    # 2800 * ln(1.025) = 69.1
    assert r["shards"] == 1669 and r["income"]["taps"] == 25
    r = client.post("/api/resonance/draw", json={"count": 10}, headers=H).json()
    assert len(r["drops"]) == 10 and r["resonance"]["total"] == 10
    assert client.get("/api/collection", headers=H).json()["owned"]
    assert client.get("/api/me", headers=H).json()["totals"]["owned"] > 0
    main.game.store.update_player(r["player"], shards=0)
    assert client.post("/api/resonance/draw", json={}, headers=H).status_code == 409
    assert client.post("/api/cards/draw", json={}, headers=H).status_code == 404
    assert client.post("/api/boxes/open", json={}, headers=H).status_code == 404
    assert client.post("/api/resonance/draw", json={"count": 101}, headers=H).status_code == 422
    assert client.post("/api/resonance/draw", json={"count": 0}, headers=H).status_code == 422
    assert client.post("/api/resonance/draw", json={}).status_code == 401
    assert client.post("/api/presence", json={"session": "test-session-0001"}, headers=H).status_code == 200


def test_craft_and_loadout_routes(client):
    assert client.post("/api/craft", json={"item": "emote:e.03"}, headers=H).json()["shards"] == 1120
    assert client.post("/api/craft", json={"item": "nope"}, headers=H).status_code == 400
    lo = client.post("/api/loadout", json={"character": "嘉然", "favorites": ["e.01"]}, headers=H).json()
    assert lo == {"character": "嘉然", "favorites": ["e.01"], "plate": None}
    assert client.get("/api/loadout", headers=H).json() == lo
    assert client.post("/api/craft", json={"item": "card:c1"}, headers=H).status_code == 200
    assert client.post("/api/loadout", json={"character": "嘉然山海经"}, headers=H).status_code == 400


def test_checkin_routes_once_a_day(client):
    assert client.get("/api/me", headers=H).json()["checkin"] == {"available": True}
    month = client.get("/api/checkin", headers=H).json()
    assert month["available"] and month["days"] == []
    r = client.post("/api/checkin", headers=H).json()
    assert r["prize"] == {"index": 0, "shards": 80, "day": month["today"]} and r["shards"] == 1680
    again = client.post("/api/checkin", headers=H)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "checked_in"
    assert client.get("/api/checkin", headers=H).json()["days"] == [{"day": month["today"], "prize": 0, "shards": 80}]
    assert client.post("/api/checkin").status_code == 401


def test_ws_emotes_need_ownership_and_are_rate_limited(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "room": "r", "nick": "a", "token": TOKEN})
        joined = ws.receive_json()
        assert joined["members"][0]["uid"]
        ws.send_json({"type": "emote", "emote": "e.02"})
        assert ws.receive_json()["code"] == "locked"
        ws.send_json({"type": "emote", "emote": "e.01"})          # starter
        assert ws.receive_json() == {"type": "emote", "id": joined["you"], "emote": "e.01"}
        ws.send_json({"type": "emote", "emote": "e.01"})          # too soon
        assert ws.receive_json()["code"] == "rate_limited"


def test_ws_plates_are_checked_against_the_save(client):
    for cid in ("c4", "c5"):
        main.game.store.add_item(player_id_for(TOKEN), f"card:{cid}", 0)
    with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        a.send_json({"type": "join", "room": "r", "nick": "a", "token": TOKEN, "plate": "c5"})
        ja = a.receive_json()
        assert ja["members"][0]["plate"] == "c5"
        b.send_json({"type": "join", "room": "r", "nick": "b", "token": "u" * 32, "plate": "c5"})
        jb = b.receive_json()
        assert [m["plate"] for m in jb["members"] if m["id"] == jb["you"]] == [None]  # not owned: dropped
        a.receive_json()  # member_joined(b)
        b.send_json({"type": "state", "plate": "c5"})
        assert b.receive_json()["code"] == "locked"
        a.send_json({"type": "state", "plate": ""})
        # join without a character: the default "default" is not a character, so the first member shows
        off = {"type": "state", "id": ja["you"], "character": "嘉然", "nick": "a", "plate": None}
        assert a.receive_json() == off and b.receive_json() == off
        a.send_json({"type": "state", "plate": "c5"})
        assert b.receive_json()["plate"] == "c5"


def test_activity_validation(client):
    assert client.post("/api/activity", json={**BATCH, "taps": -1}, headers=H).status_code == 422
    assert client.post("/api/activity", json={}, headers=H).status_code == 422
    assert client.post("/api/activity", json={**BATCH, "taps": 1, "cooldown": -1}, headers=H).status_code == 422


def test_activity_takes_the_client_cooldown(client):
    r = client.post("/api/activity", json={**BATCH, "taps": 30, "cooldown": 45}, headers=H).json()
    assert r["credited"] == 0 and r["tapCooldown"] == 45
    assert client.get("/api/me", headers=H).json()["tapCooldown"] == 45


def test_manifest_and_packs_routes():
    c = TestClient(main.app)
    m = c.get("/api/manifest").json()
    assert len(m["cards"]) > 0
    idx = c.get("/packs/index.json").json()
    assert idx["packs"]
    first = idx["packs"][0]["files"][0]
    r = c.get("/packs/" + first["path"])
    assert r.status_code == 200 and len(r.content) == first["size"]
