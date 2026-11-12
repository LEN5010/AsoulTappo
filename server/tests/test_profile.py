"""Profiles room members open: up to three showcase cards from the loadout, and collection progress."""
import json
import time

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import MAX_SHOWCASE, Game, GameError, player_id_for
from app.manifest import Manifest
from app.rooms import PROFILE_INTERVAL
from app.store import Store
from fixtures import Clock

TOKEN = "profile-player-token-01"
OTHER = "profile-player-token-02"
M = Manifest.load()
CARDS = list(M.cards)


def game():
    g = Game(Store(":memory:"), M, now=Clock())
    g.status(TOKEN)
    return g, player_id_for(TOKEN)


def give(g, pid, items):
    for item in items:
        g.store.add_item(pid, item, 0)


def test_the_showcase_takes_up_to_three_owned_cards():
    g, pid = game()
    give(g, pid, [f"card:{c}" for c in CARDS[:4]])
    assert g.get_loadout(TOKEN)["showcase"] == []
    assert g.set_loadout(TOKEN, {"showcase": CARDS[:3]})["showcase"] == CARDS[:3]
    # repeats count once
    assert g.set_loadout(TOKEN, {"showcase": [CARDS[1], CARDS[1]]})["showcase"] == [CARDS[1]]
    with pytest.raises(GameError) as e:
        g.set_loadout(TOKEN, {"showcase": CARDS[:MAX_SHOWCASE + 1]})
    assert e.value.code == "bad_item"
    with pytest.raises(GameError) as e:
        g.set_loadout(TOKEN, {"showcase": ["no-such-card"]})
    assert e.value.code == "bad_item"
    with pytest.raises(GameError) as e:
        g.set_loadout(TOKEN, {"showcase": [CARDS[5]]})
    assert e.value.code == "locked"
    assert g.set_loadout(TOKEN, {"showcase": []})["showcase"] == []


def test_other_loadout_writes_keep_the_showcase():
    g, pid = game()
    give(g, pid, [f"card:{CARDS[0]}"])
    g.set_loadout(TOKEN, {"showcase": [CARDS[0]]})
    g.set_loadout(TOKEN, {"character": "嘉然"})
    assert g.get_loadout(TOKEN)["showcase"] == [CARDS[0]]


def test_a_stored_card_the_save_does_not_hold_leaves_only_its_slot():
    g, pid = game()
    give(g, pid, [f"card:{CARDS[0]}", f"card:{CARDS[2]}"])
    g.store.update_player(pid, loadout=json.dumps({"showcase": [CARDS[0], CARDS[1], CARDS[2]]}))
    assert g.get_loadout(TOKEN)["showcase"] == [CARDS[0], CARDS[2]]


def test_progress_counts_as_the_album_does():
    g, pid = game()
    owned = g.store.owned(pid)
    progress = g.collection_progress(owned)
    emotes = [e["key"] for s in M.data["emoteSets"] for e in s["emotes"]]
    assert progress == {"cards": [0, len(M.cards)], "emotes": [len(M.starter), len(emotes)], "skins": [0, len(M.skins)]}
    give(g, pid, [f"card:{CARDS[0]}", f"char:{next(iter(M.skins))}", next(iter(M.starter))])
    progress = g.collection_progress(g.store.owned(pid))
    # an owned starter emote is not counted twice
    assert progress["cards"][0] == 1 and progress["skins"][0] == 1 and progress["emotes"][0] == len(M.starter)


def test_a_member_without_a_save_has_no_progress():
    g, _ = game()
    assert g.member_profile(None) == {"showcase": [], "progress": None}


def test_a_token_without_a_save_shows_nothing_and_makes_no_save():
    g, _ = game()
    assert g.member_profile(OTHER) == {"showcase": [], "progress": None}
    assert not g.store.has_player(player_id_for(OTHER))


def test_room_members_ask_for_each_others_profiles(monkeypatch):
    g, pid = game()
    give(g, pid, [f"card:{c}" for c in CARDS[:2]])
    g.set_loadout(TOKEN, {"showcase": [CARDS[1], CARDS[0]]})
    monkeypatch.setattr(main, "game", g)
    main.manager.rooms.clear()
    with TestClient(main.app) as c, c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        a.send_json({"type": "join", "room": "profiles", "nick": "a", "token": TOKEN, "motionVersion": 3})
        ja = a.receive_json()
        assert ja["features"] == ["poke", "profile", "cheer", "status"]
        b.send_json({"type": "join", "room": "profiles", "nick": "b", "motionVersion": 3})
        jb = b.receive_json()
        a.receive_json()  # b joined
        b.send_json({"type": "profile", "id": ja["you"]})
        reply = b.receive_json()
        assert reply["type"] == "profile" and reply["id"] == ja["you"]
        assert reply["showcase"] == [CARDS[1], CARDS[0]]
        assert reply["progress"]["cards"] == [2, len(M.cards)]
        # b joined without a save
        time.sleep(PROFILE_INTERVAL)
        a.send_json({"type": "profile", "id": jb["you"]})
        assert a.receive_json() == {"type": "profile", "id": jb["you"], "showcase": [], "progress": None}
        # too soon after the last one, then a member not in the room
        a.send_json({"type": "profile", "id": jb["you"]})
        assert a.receive_json()["code"] == "rate_limited"
        time.sleep(PROFILE_INTERVAL)
        a.send_json({"type": "profile", "id": "nobody"})
        assert a.receive_json()["code"] == "no_member"
