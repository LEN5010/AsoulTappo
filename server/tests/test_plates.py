"""Name plates from the manifest's `plates`: 阿草's plate, unlocked by every emote of the scratch set."""
import json

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import Game, GameError, player_id_for
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock, tiny_manifest

TOKEN = "plate-player-token-0001"
M = Manifest.load()
ACHAO = [f"emote:{k}" for k in M.scratch_emotes]


def game(manifest=None):
    g = Game(Store(":memory:"), manifest or Manifest.load(), now=Clock())
    g.status(TOKEN)
    return g, player_id_for(TOKEN)


def give(g, pid, items):
    for item in items:
        g.store.add_item(pid, item, 0)


def test_manifest_lists_the_achao_plate():
    assert M.data["plates"] == [{"id": "achao", "name": "阿草", "emoteSet": "achao"}]
    assert M.plates == {"achao": ACHAO} and len(ACHAO) == 20
    # plate ids are worn in the same field as card ids, so they never meet
    assert not set(M.plates) & set(M.cards)


def test_a_manifest_without_plates_knows_none():
    assert tiny_manifest().plates == {}
    data = {**M.data, "plates": [{"id": "x", "name": "x", "emoteSet": "nope"}]}
    assert Manifest(data).plates == {}  # a set it does not know unlocks nothing
    g, _ = game(tiny_manifest())
    with pytest.raises(GameError) as e:
        g.set_loadout(TOKEN, {"plate": "achao"})
    assert e.value.code == "bad_item"


def test_the_plate_needs_every_emote_of_the_set():
    g, pid = game()
    give(g, pid, ACHAO[:-1])
    with pytest.raises(GameError) as e:
        g.set_loadout(TOKEN, {"plate": "achao"})
    assert e.value.code == "locked"
    assert g.room_plate(TOKEN, "achao") is None
    give(g, pid, ACHAO[-1:])
    assert g.set_loadout(TOKEN, {"plate": "achao"})["plate"] == "achao"
    assert g.room_plate(TOKEN, "achao") == "achao"
    assert g.room_plate(None, "achao") is None
    # other keys keep it, and it reads back
    assert g.set_loadout(TOKEN, {"favorites": [M.scratch_emotes[0]]})["plate"] == "achao"
    assert g.get_loadout(TOKEN)["plate"] == "achao"
    assert g.set_loadout(TOKEN, {"plate": ""})["plate"] is None


def test_a_stored_plate_is_kept_only_with_its_set():
    g, pid = game()
    g.store.update_player(pid, loadout=json.dumps({"plate": "achao", "favorites": []}))
    assert g.get_loadout(TOKEN)["plate"] is None
    give(g, pid, ACHAO)
    assert g.get_loadout(TOKEN)["plate"] == "achao"
    # a write of another key goes through the stored loadout and keeps the plate
    g.set_loadout(TOKEN, {"character": "嘉然"})
    assert json.loads(g.store.get_player(pid, 0)["loadout"])["plate"] == "achao"


def test_a_room_shows_the_plate_once_the_set_is_whole(monkeypatch):
    g, pid = game()
    monkeypatch.setattr(main, "game", g)
    main.manager.rooms.clear()
    with TestClient(main.app) as c, c.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "room": "r1", "nick": "a", "character": "嘉然", "token": TOKEN, "plate": "achao"})
        welcome = ws.receive_json()
        me = next(m for m in welcome["members"] if m["id"] == welcome["you"])
        assert me["plate"] is None
        ws.send_json({"type": "state", "plate": "achao"})
        assert ws.receive_json()["code"] == "locked"
        give(g, pid, ACHAO)
        ws.send_json({"type": "state", "plate": "achao"})
        assert ws.receive_json() == {"type": "state", "id": welcome["you"], "character": "嘉然", "nick": "a",
                                     "plate": "achao", "status": None}
