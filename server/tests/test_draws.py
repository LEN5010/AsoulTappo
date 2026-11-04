from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import Game, GameError, player_id_for
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock, SeqRng

TOKEN = "draw-player-token-0001"
SESSION = "running-session-0001"


def game(rng=None, path=":memory:"):
    clock = Clock()
    g = Game(Store(str(path)), Manifest.load(), rng=rng or SeqRng(.5), now=clock)
    g.status(TOKEN)
    return g, clock


def test_idle_running_time_earns_ticket_after_exactly_five_minutes():
    g, clock = game()
    g.presence(TOKEN, SESSION)
    for _ in range(14):
        clock.t += 20
        g.presence(TOKEN, SESSION)
    assert g.status(TOKEN)["draw"]["tickets"] == 0
    clock.t += 20
    result = g.presence(TOKEN, SESSION)
    assert result["draw"]["tickets"] == 1
    assert result["draw"]["seconds"] == 0
    assert result["totals"]["taps"] == 0


def test_heartbeats_overlap_once_and_pause_does_not_credit_offline_time():
    g, clock = game()
    g.presence(TOKEN, SESSION)
    clock.t += 10
    g.presence(TOKEN, "second-session-0001")
    clock.t += 10
    g.presence(TOKEN, SESSION)
    g.presence(TOKEN, "second-session-0001")
    assert g.status(TOKEN)["draw"]["seconds"] == 20
    clock.t += 3600
    assert g.presence(TOKEN, SESSION)["draw"]["seconds"] == 20
    clock.t += 20
    assert g.presence(TOKEN, SESSION)["draw"]["seconds"] == 40


def test_tickets_have_no_inventory_cap_and_persist_after_restart(tmp_path):
    path = tmp_path / "draw.sqlite"
    g, clock = game(path=path)
    pid = player_id_for(TOKEN)
    g.store.update_player(pid, draw_tickets=10000, draw_seconds=290, draw_pity=399)
    g.presence(TOKEN, SESSION)
    clock.t += 20
    assert g.presence(TOKEN, SESSION)["draw"]["tickets"] == 10001
    g.store.close()
    reopened = Game(Store(str(path)), Manifest.load(), now=clock)
    assert reopened.status(TOKEN)["draw"] == {
        "tickets": 10001, "seconds": 10, "secondsPerDraw": 300,
        "pity": 399, "hardPity": 400, "total": 0}


@pytest.mark.parametrize("roll,tier", [(0, "big"), (.00499, "big"), (.005, "small"), (.04999, "small"), (.05, "normal")])
def test_rarity_probability_boundaries(roll, tier):
    g, _ = game(SeqRng(roll, .5))
    g.store.update_player(player_id_for(TOKEN), draw_tickets=1)
    result = g.draw_cards(TOKEN, "bloom")
    assert result["drops"][0]["tier"] == tier
    assert result["draw"]["tickets"] == 0
    assert result["drops"][0]["shards"] == 0


def test_pity_is_shared_across_pools_and_resets_on_big_hidden():
    g, _ = game()
    g.store.update_player(player_id_for(TOKEN), draw_tickets=3, draw_pity=398)
    first = g.draw_cards(TOKEN, "moon")
    assert first["drops"][0]["tier"] == "normal" and first["draw"]["pity"] == 399
    second = g.draw_cards(TOKEN, "symphony")
    assert second["drops"][0]["item"] == "card:c1748345610010"
    assert second["draw"]["pity"] == 0
    assert g.draw_cards(TOKEN, "tavern")["draw"]["pity"] == 1


def test_concurrent_draws_spend_each_ticket_once():
    g, _ = game()
    g.store.update_player(player_id_for(TOKEN), draw_tickets=7)
    def draw(_):
        try:
            return len(g.draw_cards(TOKEN, "bloom", 100)["drops"])
        except GameError as e:
            assert e.code == "no_ticket"
            return 0
    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(draw, range(4))) == 7
    assert g.status(TOKEN)["draw"]["tickets"] == 0
    assert sum(g.collection(TOKEN)["owned"].values()) == 7


def test_presence_draw_api_and_emote_only_boxes(monkeypatch):
    g, clock = game()
    monkeypatch.setattr(main, "game", g)
    headers = {"X-Player-Token": TOKEN}
    with TestClient(main.app) as client:
        assert client.post("/api/presence", json={"session": SESSION}).status_code == 401
        assert client.post("/api/presence", json={"session": SESSION}, headers=headers).status_code == 200
        assert client.post("/api/cards/draw", json={"pool": "bloom"}, headers=headers).status_code == 409
        g.store.update_player(player_id_for(TOKEN), draw_tickets=2, boxes=10)
        result = client.post("/api/cards/draw", json={"pool": "tavern", "count": 2}, headers=headers).json()
        assert len(result["drops"]) == 2
        assert all(g.manifest.cards[d["item"][5:]]["series"] == "tavern" for d in result["drops"])
        opened = client.post("/api/boxes/open", json={"count": 10}, headers=headers).json()
        assert all(d["item"].startswith("emote:") for d in opened["drops"])
        assert client.post("/api/craft", json={"item": result["drops"][0]["item"]}, headers=headers).status_code == 400
        assert client.post("/api/cards/draw", json={"pool": "bloom", "count": 101}, headers=headers).status_code == 422
