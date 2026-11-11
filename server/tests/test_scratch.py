import json
import random

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import scratch
from app.game import DAY_OFFSET, Game, GameError
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock, SeqRng, tiny_manifest

TOKEN = "scratch-player-token-0001"
OTHER = "scratch-player-token-0002"
M = Manifest.load()
CFG = M.scratch
AMOUNTS = [p["shards"] for p in CFG["prizes"]]


def game(*rolls, shards=100_000):
    clock = Clock()
    g = Game(Store(":memory:"), Manifest.load(), rng=SeqRng(*(rolls or (.99,))), now=clock)
    for token in (TOKEN, OTHER):
        g.status(token)
        g.store.update_player(g.status(token)["player"], shards=shards)
    return g, clock


def play(g, token=TOKEN):
    """Buys a card and reveals it; returns (cells, prize, status)."""
    card = g.scratch_buy(token)["card"]
    r = g.scratch_reveal(token, card["id"])
    return card["cells"], r["prize"], r


def next_midnight(t: float) -> float:
    return ((t + DAY_OFFSET) // 86400 + 1) * 86400 - DAY_OFFSET


def test_table_is_the_approved_one():
    assert (CFG["price"], CFG["daily"], CFG["announce"]) == (500, 20, 2500)
    assert [(p["shards"], p["weight"]) for p in CFG["prizes"]] == [(200, 25), (500, 20), (1000, 8), (2500, 3), (30000, .1)]
    assert CFG["emote"] == {"set": "achao", "weight": 5, "pity": 10}
    # the shard prizes return two thirds of the price
    assert sum(p["shards"] * p["weight"] for p in CFG["prizes"]) / 100 == pytest.approx(335)
    assert 100 - CFG["emote"]["weight"] - sum(p["weight"] for p in CFG["prizes"]) == pytest.approx(38.9)
    assert len(M.scratch_emotes) == 20 and M.scratch_emotes[0] == "achao.01"


def test_scratch_emotes_are_neither_drawn_nor_crafted():
    g, _ = game()
    pool = {i["id"] for tier in M.resonance_pool.values() for i in tier}
    assert not any(i.startswith("emote:achao.") for i in pool)
    with pytest.raises(GameError) as e:
        g.craft(TOKEN, "emote:achao.01")
    assert e.value.code == "bad_item"
    assert g.status(TOKEN)["shards"] == 100_000


@pytest.mark.parametrize("roll,shards,item", [
    (0, 0, "emote:achao.01"), (.0499, 0, "emote:achao.01"), (.05, 200, None), (.2999, 200, None), (.3, 500, None),
    (.5, 1000, None), (.58, 2500, None), (.61, 30000, None), (.6105, 30000, None), (.6115, 0, None), (.99, 0, None),
])
def test_one_draw_decides_the_prize(roll, shards, item):
    g, _ = game(roll, 0)
    cells, prize, r = play(g)
    assert prize == {"shards": shards, "item": item}
    assert r["shards"] == 100_000 - 500 + shards
    want = item[6:] if item else str(shards) if shards else None
    assert scratch.prize_of(cells) == want
    assert g.collection(TOKEN)["owned"] == ({item: 1} if item else {})


def test_a_card_shows_one_prize_or_none():
    rng = random.Random(20261109)
    emotes = M.scratch_emotes
    for win in [None, *map(str, AMOUNTS), emotes[0], emotes[19]] * 200:
        cells = scratch.layout(win, AMOUNTS, emotes, rng)
        assert len(cells) == 9
        counts = {s: cells.count(s) for s in cells}
        assert {s for s, n in counts.items() if n >= 3} == ({win} if win else set())
        assert counts.get(win, 3) == 3
        assert all(s in emotes or int(s) in AMOUNTS for s in cells)


def test_prizes_come_at_their_rates():
    rng = random.Random(7)
    n = 200_000
    seen = {}
    for _ in range(n):
        key = scratch.roll_prize(CFG, 0, rng)
        seen[key] = seen.get(key, 0) + 1
    assert seen[("emote", 0)] / n == pytest.approx(.05, abs=.003)
    assert seen[("miss", 0)] / n == pytest.approx(.389, abs=.005)
    assert sum(amount * count for (kind, amount), count in seen.items() if kind == "shards") / n == pytest.approx(335, abs=12)


def test_a_whole_set_rolls_only_the_shard_prizes():
    rng = random.Random(7)
    n = 200_000
    seen = {}
    for _ in range(n):
        # however far the pity has run, it never fires
        key = scratch.roll_prize(CFG, 99, rng, complete=True)
        seen[key] = seen.get(key, 0) + 1
    assert ("emote", 0) not in seen
    assert seen[("miss", 0)] / n == pytest.approx(.439, abs=.005)
    for prize in CFG["prizes"]:
        assert seen.get(("shards", prize["shards"]), 0) / n == pytest.approx(prize["weight"] / 100, abs=.004)
    # two thirds of the price back, as the shard prizes alone return
    assert sum(amount * count for (kind, amount), count in seen.items() if kind == "shards") / n == pytest.approx(335, abs=12)


def test_buying_charges_once_and_the_prize_waits_for_the_reveal():
    g, _ = game(.58)
    first = g.scratch_buy(TOKEN)
    assert first["shards"] == 99_500 and first["scratch"] == {"left": 19, "pity": 1}
    # the card on the table comes back as it is, at no charge
    again = g.scratch_buy(TOKEN)
    assert again["card"] == first["card"] and again["shards"] == 99_500 and again["scratch"]["left"] == 19
    state = g.scratch_state(TOKEN)
    assert state["card"] == first["card"] and state["left"] == 19 and state["pity"] == 1

    r = g.scratch_reveal(TOKEN, first["card"]["id"])
    assert r["prize"] == {"shards": 2500, "item": None} and r["shards"] == 102_000 and r["announce"] is True
    # revealing again answers the same prize and pays nothing
    r = g.scratch_reveal(TOKEN, first["card"]["id"])
    assert r["prize"] == {"shards": 2500, "item": None} and r["shards"] == 102_000 and r["announce"] is False
    assert g.scratch_state(TOKEN)["card"] is None
    assert g.scratch_buy(TOKEN)["card"]["id"] != first["card"]["id"]


def test_a_card_belongs_to_its_buyer():
    g, _ = game(.58)
    card = g.scratch_buy(TOKEN)["card"]
    for token, card_id in ((OTHER, card["id"]), (TOKEN, card["id"] + 1)):
        with pytest.raises(GameError) as e:
            g.scratch_reveal(token, card_id)
        assert e.value.code == "no_card"
    assert g.status(OTHER)["shards"] == 100_000


def test_small_prizes_and_emotes_are_not_announced_by_the_server():
    g, _ = game(.5)
    assert play(g)[2]["announce"] is False
    g, _ = game(0)
    assert play(g)[2]["announce"] is False


def test_emotes_never_repeat_and_a_whole_set_has_no_emote_tier():
    g, clock = game(0, 0)
    won = []
    for n in range(21):
        if n == 20:
            clock.t = next_midnight(clock.t)
        cells, prize, r = play(g)
        won.append(prize)
    assert [p["item"] for p in won[:20]] == [f"emote:{k}" for k in M.scratch_emotes]
    assert all(p["shards"] == 0 for p in won[:20])
    # the card after the last emote has no emote tier: the same roll of 0 is the first shard prize
    assert won[20] == {"shards": 200, "item": None} and scratch.prize_of(cells) == "200"
    assert r["totals"]["owned"] == 20


def test_emote_pity():
    g, _ = game(.99)
    for _ in range(9):
        assert play(g)[1] == {"shards": 0, "item": None}
    assert g.scratch_state(TOKEN)["pity"] == 9
    assert play(g)[1]["item"].startswith("emote:achao.")
    assert g.scratch_state(TOKEN)["pity"] == 0
    assert play(g)[1] == {"shards": 0, "item": None}
    assert g.scratch_state(TOKEN)["pity"] == 1


def test_a_whole_set_never_reaches_the_pity():
    g, _ = game(.99)
    pid = g.status(TOKEN)["player"]
    for key in M.scratch_emotes[:-1]:
        g.store.add_item(pid, f"emote:{key}", 0)
    for _ in range(4):
        play(g)
    g.store.add_item(pid, f"emote:{M.scratch_emotes[-1]}", 0)
    # the 10th card since the last emote and beyond: still the plain table, and the count stays put
    won = [play(g)[1] for _ in range(12)]
    assert won == [{"shards": 0, "item": None}] * 12
    assert g.scratch_state(TOKEN)["pity"] == 4


def test_an_older_manifest_fallback_is_ignored():
    data = json.loads(json.dumps(M.data))
    data["economy"]["scratch"]["emote"]["fallback"] = 1000
    g = Game(Store(":memory:"), Manifest(data), rng=SeqRng(.02), now=Clock())
    g.status(TOKEN)
    pid = g.status(TOKEN)["player"]
    g.store.update_player(pid, shards=100_000)
    for key in M.scratch_emotes:
        g.store.add_item(pid, f"emote:{key}", 0)
    # .02 was the emote tier; with the set whole it is the 200 prize
    assert play(g)[1] == {"shards": 200, "item": None}


def test_twenty_cards_a_china_day():
    g, clock = game(.99)
    for n in range(20):
        assert play(g)[2]["scratch"]["left"] == 19 - n
    with pytest.raises(GameError) as e:
        g.scratch_buy(TOKEN)
    assert e.value.code == "sold_out"
    assert g.status(TOKEN)["shards"] == 90_000 and g.status(OTHER)["scratch"]["left"] == 20
    midnight = next_midnight(clock.t)
    clock.t = midnight - 1
    assert g.scratch_state(TOKEN)["left"] == 0
    clock.t = midnight
    assert g.scratch_state(TOKEN)["left"] == 20
    assert g.scratch_buy(TOKEN)["scratch"]["left"] == 19


def test_yesterdays_card_can_still_be_revealed():
    g, clock = game(.35)
    card = g.scratch_buy(TOKEN)["card"]
    clock.t = next_midnight(clock.t)
    assert g.scratch_state(TOKEN) == {"day": g.scratch_state(TOKEN)["day"], "left": 20, "pity": 1, "card": card}
    assert g.scratch_reveal(TOKEN, card["id"])["prize"]["shards"] == 500


def test_not_enough_shards():
    g, _ = game(.99, shards=499)
    with pytest.raises(GameError) as e:
        g.scratch_buy(TOKEN)
    assert e.value.code == "no_shards"
    assert g.scratch_state(TOKEN) == {"day": g.scratch_state(TOKEN)["day"], "left": 20, "pity": 0, "card": None}


def test_old_revealed_cards_are_pruned():
    g, clock = game(.99)
    play(g)
    kept = g.scratch_buy(TOKEN)["card"]
    clock.t += 31 * 86400
    assert g.prune_scratch_cards() == 1
    # the unrevealed card stays however old
    assert g.scratch_state(TOKEN)["card"] == kept


def test_a_manifest_without_scratch_cards():
    g = Game(Store(":memory:"), tiny_manifest(), rng=SeqRng(0), now=Clock())
    assert "scratch" not in g.status(TOKEN)
    for call in (lambda: g.scratch_state(TOKEN), lambda: g.scratch_buy(TOKEN), lambda: g.scratch_reveal(TOKEN, 1)):
        with pytest.raises(GameError) as e:
            call()
        assert e.value.code == "no_scratch"


def test_a_database_from_before_scratch_cards_is_migrated(tmp_path):
    path = str(tmp_path / "old.db")
    store = Store(path)
    store._db.executescript("ALTER TABLE players DROP COLUMN scratch_pity; DROP TABLE scratch_cards;")
    store.close()
    g = Game(Store(path), Manifest.load(), rng=SeqRng(.99), now=Clock())
    assert g.scratch_state(TOKEN)["pity"] == 0
    assert g.scratch_buy(TOKEN)["scratch"]["left"] == 19


# ----------------------------------------------------------------------- HTTP and rooms
H = {"X-Player-Token": TOKEN}


@pytest.fixture()
def api(monkeypatch):
    g, _ = game(.58)
    monkeypatch.setattr(main, "game", g)
    main.manager.rooms.clear()
    with TestClient(main.app) as c:
        yield c, g


def test_http_flow(api):
    c, g = api
    assert c.get("/api/scratch").status_code == 401
    assert c.get("/api/scratch", headers=H).json()["card"] is None
    bought = c.post("/api/scratch", headers=H).json()
    assert bought["shards"] == 99_500 and len(bought["card"]["cells"]) == 9
    assert c.get("/api/scratch", headers=H).json()["card"] == bought["card"]
    r = c.post("/api/scratch/reveal", json={"card": bought["card"]["id"]}, headers=H)
    assert r.status_code == 200 and r.json()["prize"] == {"shards": 2500, "item": None}
    assert "announce" not in r.json() and r.json()["shards"] == 102_000
    missing = c.post("/api/scratch/reveal", json={"card": 999}, headers=H)
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "no_card"
    assert c.post("/api/scratch/reveal", json={"card": 0}, headers=H).status_code == 422
    # larger than SQLite's integers: refused as input, not an error inside the query
    assert c.post("/api/scratch/reveal", json={"card": 2**63}, headers=H).status_code == 422


def test_http_refusals(api):
    c, g = api
    g.store.update_player(g.status(TOKEN)["player"], shards=499)
    r = c.post("/api/scratch", headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_shards"
    g.store.update_player(g.status(TOKEN)["player"], shards=100_000)
    for _ in range(20):
        card = c.post("/api/scratch", headers=H).json()["card"]
        c.post("/api/scratch/reveal", json={"card": card["id"]}, headers=H)
    r = c.post("/api/scratch", headers=H)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sold_out"


def test_the_room_sees_a_big_win_once(api):
    c, g = api
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        a.send_json({"type": "join", "room": "r1", "nick": "a", "token": TOKEN})
        you = a.receive_json()["you"]
        b.send_json({"type": "join", "room": "r1", "nick": "b", "token": OTHER})
        b.receive_json()
        a.receive_json()  # member_joined(b)
        card = c.post("/api/scratch", headers=H).json()["card"]
        for _ in range(2):  # the second reveal pays nothing and says nothing
            c.post("/api/scratch/reveal", json={"card": card["id"]}, headers=H)
        expected = {"type": "scratch", "id": you, "shards": 2500}
        assert a.receive_json() == expected and b.receive_json() == expected
        # the next message either side gets is the ping's answer, not another announcement
        for ws in (a, b):
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}


def test_the_room_hears_nothing_of_a_small_prize(api):
    c, g = api
    g.rng = SeqRng(.5)
    with c.websocket_connect("/ws") as a:
        a.send_json({"type": "join", "room": "r1", "nick": "a", "token": TOKEN})
        a.receive_json()
        card = c.post("/api/scratch", headers=H).json()["card"]
        assert c.post("/api/scratch/reveal", json={"card": card["id"]}, headers=H).json()["prize"]["shards"] == 1000
        a.send_json({"type": "ping"})
        assert a.receive_json() == {"type": "pong"}


def test_a_scratch_emote_can_be_sent_once_it_is_won(api):
    c, g = api
    g.rng = SeqRng(0)
    with c.websocket_connect("/ws") as a:
        a.send_json({"type": "join", "room": "r1", "nick": "a", "token": TOKEN})
        you = a.receive_json()["you"]
        a.send_json({"type": "emote", "emote": "achao.01"})
        assert a.receive_json()["code"] == "locked"
        card = c.post("/api/scratch", headers=H).json()["card"]
        prize = c.post("/api/scratch/reveal", json={"card": card["id"]}, headers=H).json()["prize"]
        assert prize == {"shards": 0, "item": "emote:achao.01"}
        a.send_json({"type": "emote", "emote": "achao.01"})
        assert a.receive_json() == {"type": "emote", "id": you, "emote": "achao.01"}


def test_cells_are_stored_as_the_client_gets_them(api):
    c, g = api
    card = c.post("/api/scratch", headers=H).json()["card"]
    row = g.store.scratch_card(g.status(TOKEN)["player"], card["id"])
    assert json.loads(row["cells"]) == card["cells"] and row["shards"] == 2500 and row["revealed"] == 0
