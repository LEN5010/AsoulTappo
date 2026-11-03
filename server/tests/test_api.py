import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.cards import DropConfig
from app.game import Game
from app.store import Store

from fixtures import Clock, SeqRng, tiny_manifest

TOKEN = "t" * 32
H = {"X-Player-Token": TOKEN}


@pytest.fixture()
def client(monkeypatch):
    g = Game(Store(":memory:"), tiny_manifest(), DropConfig(taps_per_box=10, max_taps_per_sec=10**5),
             SeqRng(0.0), Clock())
    monkeypatch.setattr(main, "game", g)
    main.manager.rooms.clear()
    with TestClient(main.app) as c:  # one portal/event loop shared by all sockets
        yield c


def test_token_required(client):
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/activity", json={"taps": 1}).status_code == 401
    assert client.get("/api/me", headers={"X-Player-Token": "short"}).status_code == 401


def test_activity_open_collection_flow(client):
    assert client.post("/api/boxes/open", headers=H).status_code == 409
    r = client.post("/api/activity", json={"taps": 25}, headers=H).json()
    assert r["boxes"] == 2 and r["credited"] == 25
    r = client.post("/api/boxes/open", headers=H).json()
    assert r["card"] == "c1" and r["new"] is True and r["boxes"] == 1
    col = client.get("/api/collection", headers=H).json()
    assert col["owned"] == {"c1": 1}
    assert client.get("/api/me", headers=H).json()["totals"]["owned"] == 1


def test_activity_validation(client):
    assert client.post("/api/activity", json={"taps": -1}, headers=H).status_code == 422
    assert client.post("/api/activity", json={}, headers=H).status_code == 422


def test_decor_rest_and_ws_member_list(client):
    client.post("/api/activity", json={"taps": 25}, headers=H)
    client.post("/api/boxes/open", headers=H)
    assert client.post("/api/decor", json={"badge": "frame-s1"}, headers=H).status_code == 400
    assert client.post("/api/decor", json={"frame": "frame-s1"}, headers=H).status_code == 400  # locked
    assert client.post("/api/decor", json={"badge": "badge-s1"}, headers=H).json()["badge"] == "badge-s1"
    with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        a.send_json({"type": "join", "room": "r", "nick": "a", "character": "嘉然", "token": TOKEN})
        ja = a.receive_json()
        assert ja["members"][0]["badge"] == "badge-s1" and ja["members"][0]["frame"] is None
        assert TOKEN not in str(ja)
        b.send_json({"type": "join", "room": "r", "nick": "b", "character": "嘉然"})
        jb = b.receive_json()
        assert {m["nick"]: m["badge"] for m in jb["members"]} == {"a": "badge-s1", "b": None}
        a.receive_json()  # member_joined
        # clearing via ws state is broadcast
        a.send_json({"type": "state", "badge": ""})
        assert a.receive_json()["type"] == "state"
        s = b.receive_json()
        assert s["type"] == "state" and s["badge"] is None and s["id"] == ja["you"]


def test_ws_state_decor_needs_token_and_unlock(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "room": "r", "nick": "a"})
        ws.receive_json()
        ws.send_json({"type": "state", "badge": "badge-s1"})
        assert ws.receive_json()["code"] == "locked"
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "room": "r2", "nick": "a", "token": TOKEN})
        ws.receive_json()
        ws.send_json({"type": "state", "badge": "badge-s1"})
        assert ws.receive_json()["code"] == "locked"   # token ok, but no card of that series yet
        ws.send_json({"type": "state", "badge": "nope"})
        assert ws.receive_json()["code"] == "bad_decor"


def test_manifest_and_packs_routes():
    c = TestClient(main.app)
    m = c.get("/api/manifest").json()
    assert len(m["cards"]) > 0
    idx = c.get("/packs/index.json").json()
    assert idx["packs"]
    first = idx["packs"][0]["files"][0]
    r = c.get("/packs/" + first["path"])
    assert r.status_code == 200 and len(r.content) == first["size"]
