"""A save's own drops, a page at a time (Game.drop_history, GET /api/resonance/history)."""
import sqlite3

from fastapi.testclient import TestClient

import app.main as main
from app.game import HISTORY_PAGE, Game, player_id_for
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock, SeqRng

TOKEN = "history-player-token-01"
NEW = "9.9.9"
DAY = 86400.0
SKINS = ["char:嘉然然龙", "char:乃琳法师"]


def game(*rolls, banner=False, holo=None):
    m = Manifest.load()
    clock = Clock()
    if banner:
        m.resonance["banners"] = [{"id": "forms", "name": "双形态", "start": clock.t, "end": clock.t + 7 * DAY,
                                   "items": SKINS, "rate": 5}]
        m.__dict__.pop("banners", None)
    if holo is not None:
        m.resonance["holoChance"] = holo
    g = Game(Store(":memory:"), m, rng=SeqRng(*rolls) if rolls else None, now=clock)
    g.status(TOKEN)
    g.store.update_player(player_id_for(TOKEN), shards=10_000_000)
    return g, clock


def test_the_pages_run_from_the_newest_back_to_the_first_drop():
    g, clock = game()
    drawn = []
    for _ in range(12):
        clock.t += 60
        drawn += [d["item"] for d in g.resonate(TOKEN, 10, NEW)["drops"]]
    pages, before = [], None
    while True:
        page = g.drop_history(TOKEN, before, NEW)
        pages.append(page["drops"])
        before = page["next"]
        if before is None:
            break
    assert [len(p) for p in pages] == [HISTORY_PAGE, HISTORY_PAGE, 20]
    rows = [d for p in pages for d in p]
    # Holo versions are logged as themselves, so compare the cards they are of.
    card = {holo: c for c, holo in g.manifest.holos.items()}
    assert [card.get(d["item"], d["item"]) for d in rows] == drawn[::-1]
    assert all(d["source"] == "draw" and "pool" not in d for d in rows)
    assert [d["id"] for d in rows] == sorted((d["id"] for d in rows), reverse=True)
    assert rows[0]["ts"] == clock.t


def test_a_save_with_exactly_a_page_is_told_there_is_no_more():
    g, _ = game()
    for _ in range(HISTORY_PAGE // 10):
        g.resonate(TOKEN, 10, NEW)
    page = g.drop_history(TOKEN, None, NEW)
    assert len(page["drops"]) == HISTORY_PAGE and page["next"] is None
    assert g.drop_history("another-players-token-1", None, NEW) == {"drops": [], "next": None}


def test_a_draw_from_a_limited_pool_names_it():
    # .95 is the first roll inside the pool's own 5%; the second picks among the featured skins.
    g, clock = game(.95, 0, .5, banner=True)
    g.resonate(TOKEN, 1, NEW, "forms")
    drop = g.drop_history(TOKEN, None, NEW)["drops"][0]
    assert (drop["item"], drop["source"], drop["pool"], drop["poolName"]) == (SKINS[0], "draw", "forms", "双形态")
    # The economy no longer lists the pool: the row keeps its id, without a name.
    g.manifest.resonance["banners"] = []
    g.manifest.__dict__.pop("banners", None)
    drop = g.drop_history(TOKEN, None, NEW)["drops"][0]
    assert drop["pool"] == "forms" and "poolName" not in drop


def test_a_crafted_item_and_a_scratch_cards_item_say_where_they_came_from():
    g, _ = game()
    pid = player_id_for(TOKEN)
    item = next(i for i in g.manifest.resonance_pool["common"] if i["kind"] == "emote")
    g.craft(TOKEN, item["id"])
    g.store.log_drop(pid, "card:whatever", "rare", True, g.now(), "scratch")
    scratch, craft = g.drop_history(TOKEN, None, NEW)["drops"]
    assert (craft["item"], craft["source"], craft["new"]) == (item["id"], "craft", True)
    assert (scratch["item"], scratch["source"]) == ("card:whatever", "scratch")


def test_a_client_older_than_the_holo_versions_is_not_shown_them():
    g, _ = game()
    pid = player_id_for(TOKEN)
    card, holo = next(iter(g.manifest.holos.items()))
    g.store.log_drops(pid, [{"item": card, "rarity": "common", "new": True}], 1)
    g.store.log_drops(pid, [{"item": holo, "rarity": "common", "new": True}], 2)
    assert [d["item"] for d in g.drop_history(TOKEN, None, NEW)["drops"]] == [holo, card]
    assert [d["item"] for d in g.drop_history(TOKEN, None, "1.2.3")["drops"]] == [card]


def test_rows_from_before_the_columns_carry_neither_source_nor_pool(tmp_path):
    path = str(tmp_path / "old.db")
    Store(path)
    pid = player_id_for(TOKEN)
    with sqlite3.connect(path) as db:
        db.executescript("""
            DROP TABLE drops;
            CREATE TABLE drops (id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT NOT NULL, item_id TEXT NOT NULL,
                                rarity TEXT NOT NULL, is_new INTEGER NOT NULL, ts REAL NOT NULL);
        """)
        db.execute("INSERT INTO drops (player_id, item_id, rarity, is_new, ts) VALUES (?, 'card:old', 'rare', 1, 5)",
                   (pid,))
    g = Game(Store(path), Manifest.load(), now=Clock())
    assert g.drop_history(TOKEN, None, NEW)["drops"] == [
        {"id": 1, "item": "card:old", "rarity": "rare", "new": True, "ts": 5}]
    g.store.update_player(pid, shards=10_000)
    g.resonate(TOKEN, 1, NEW)
    assert g.drop_history(TOKEN, None, NEW)["drops"][0]["source"] == "draw"


def test_the_endpoint_pages_with_before(monkeypatch):
    g, _ = game()
    monkeypatch.setattr(main, "game", g)
    H = {"X-Player-Token": TOKEN, "X-Client-Version": NEW}
    with TestClient(main.app) as c:
        for _ in range(6):
            c.post("/api/resonance/draw", json={"count": 10}, headers=H)
        first = c.get("/api/resonance/history", headers=H).json()
        assert len(first["drops"]) == HISTORY_PAGE and first["next"] == first["drops"][-1]["id"]
        rest = c.get("/api/resonance/history", params={"before": first["next"]}, headers=H).json()
        assert len(rest["drops"]) == 10 and rest["next"] is None
        assert c.get("/api/resonance/history", params={"before": 0}, headers=H).status_code == 422
        assert c.get("/api/resonance/history").status_code == 401
