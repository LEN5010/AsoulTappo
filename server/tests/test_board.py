"""The 应援 page's collection board."""
import calendar

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import BOARD_DEFAULT_NICK, BOARD_SECONDS, BOARD_SIZE, Game, GameError, board_id, player_id_for
from app.manifest import Manifest
from app.store import Store
from fixtures import Clock

M = Manifest.load()
CARDS = list(M.cards)
BIG = [c["id"] for c in M.cards.values() if c.get("tier") == "big"]
NORMAL = [c for c in CARDS if c not in BIG]
# Wednesday 2026-11-11, 12:00 in China
NOW = calendar.timegm((2026, 11, 11, 4, 0, 0))


def tok(n):
    return f"board-player-token-{n:04d}"


def game():
    return Game(Store(":memory:"), M, now=Clock(NOW))


def save(g, n, cards=(), character="嘉然", **loadout):
    t = tok(n)
    pid = player_id_for(t)
    g.status(t)
    for i, cid in enumerate(cards):
        g.store.add_item(pid, f"card:{cid}", NOW - 1000 + n * 10 + i)
    if character in M.skins:
        g.store.add_item(pid, f"char:{character}", NOW)
    g.set_loadout(t, {"character": character, **loadout})
    return t, pid


def test_the_collection_board_ranks_by_cards_then_hidden_cards_then_who_got_there_first():
    g = game()
    t, _ = save(g, 1, NORMAL[:3], nick="三张")
    save(g, 2, NORMAL[:2] + BIG[:1], nick="有大隐藏")
    save(g, 3, NORMAL[3:6], nick="后到")
    save(g, 4, NORMAL[:5], nick="", board=False)
    save(g, 5, NORMAL[:1])
    rows = g.board(t, False)["cards"]
    assert [(r["rank"], r["nick"], r["cards"]) for r in rows] == [
        (1, "有大隐藏", 3), (2, "三张", 3), (3, "后到", 3), (4, BOARD_DEFAULT_NICK, 1)]
    assert rows[0]["id"] == board_id(player_id_for(tok(2))) and rows[0]["big"] == 1


def test_a_plate_shows_on_the_board_only_with_its_set():
    g = game()
    t, pid = save(g, 1, NORMAL[:1])
    g.store.update_player(pid, loadout='{"character": "嘉然", "plate": "%s"}' % BIG[0])
    assert g.board(t, False)["cards"][0]["plate"] is None
    for item in g.plate_needs(BIG[0]):
        g.store.add_item(pid, item, NOW)
    g.now.t += BOARD_SECONDS
    assert g.board(t, False)["cards"][0]["plate"] == BIG[0]


def test_where_the_asking_save_stands():
    g = game()
    save(g, 1, NORMAL[:4])
    t, _ = save(g, 2, NORMAL[:2] + BIG[:1], character="乃琳")
    me = g.board(t, False)["me"]
    assert me == {"rank": 2, "cards": 3, "big": 1, "off": None}
    hidden, _ = save(g, 3, NORMAL[:1], board=False)
    assert g.board(hidden, False)["me"]["off"] == "hidden"


def test_with_main_site_accounts_only_linked_saves_are_ranked():
    g = game()
    t, pid = save(g, 1, NORMAL[:2])
    other, _ = save(g, 2, NORMAL[:3])
    g.store.link_account("user-1", pid, NOW)
    board = g.board(other, True)
    assert [r["cards"] for r in board["cards"]] == [2]
    assert board["me"]["off"] == "account" and board["me"]["rank"] is None
    assert g.board(t, True)["me"]["rank"] == 1


def test_the_board_is_worked_out_again_only_after_a_while():
    g = game()
    t, _ = save(g, 1, NORMAL[:1])
    assert len(g.board(t, False)["cards"]) == 1
    save(g, 2, NORMAL[:2])
    assert len(g.board(t, False)["cards"]) == 1
    g.now.t += BOARD_SECONDS
    assert [r["cards"] for r in g.board(t, False)["cards"]] == [2, 1]


def test_the_top_rows_only():
    g = game()
    for n in range(BOARD_SIZE + 2):
        save(g, n, NORMAL[:1 + n % 3])
    # one card, and the last to get it
    board = g.board(tok(BOARD_SIZE + 1 - (BOARD_SIZE + 1) % 3), False)
    assert len(board["cards"]) == BOARD_SIZE
    assert board["me"]["rank"] == BOARD_SIZE + 2


def test_profiles_of_saves_on_the_board():
    g = game()
    t, _ = save(g, 1, NORMAL[:2], showcase=[NORMAL[1]])
    row = g.board(t, False)["cards"][0]
    assert g.board_profile(row["id"], False) == {"showcase": [NORMAL[1]], "progress": g.collection_progress(
        g.store.owned(player_id_for(t)))}
    with pytest.raises(GameError) as e:
        g.board_profile("nobody", False)
    assert e.value.code == "no_member"


def test_the_board_over_http_masks_nicks(monkeypatch):
    g = game()
    t, _ = save(g, 1, NORMAL[:1], nick="好朋友")
    monkeypatch.setattr(main, "game", g)
    monkeypatch.setattr(main.blocklist, "mask", lambda s: s.replace("朋友", "**"))
    with TestClient(main.app) as c:
        h = {"X-Player-Token": t}
        board = c.get("/api/board", headers=h).json()
        assert board["cards"][0]["nick"] == "好**"
        assert c.get(f"/api/board/profile/{board['cards'][0]['id']}", headers=h).status_code == 200
        assert c.get("/api/board/profile/nobody", headers=h).status_code == 404
        assert c.post("/api/loadout", json={"nick": "x" * 30}, headers=h).status_code == 400


def test_a_save_without_a_board_nick_shows_its_room_nick():
    g = game()
    t1, p1 = save(g, 1, NORMAL[:3])
    t2, _ = save(g, 2, NORMAL[:2], nick="设的昵称")
    save(g, 3, NORMAL[:1])
    g.note_room_nick(t1, " 联机昵称 ")
    g.note_room_nick(t2, "别的联机昵称")
    g.note_room_nick(tok(3), BOARD_DEFAULT_NICK)
    # A token that never made a save leaves nothing behind.
    g.note_room_nick(tok(9), "路人")
    g.note_room_nick(None, "无存档")
    assert not g.store.has_player(player_id_for(tok(9)))
    clock = g.now
    clock.t += BOARD_SECONDS + 1
    assert [r["nick"] for r in g.board(t1, False)["cards"]] == ["联机昵称", "设的昵称", BOARD_DEFAULT_NICK]
    # Going back to the default nick in a room clears it again.
    g.note_room_nick(t1, BOARD_DEFAULT_NICK)
    clock.t += BOARD_SECONDS + 1
    assert g.board(t1, False)["cards"][0]["nick"] == BOARD_DEFAULT_NICK


def test_joining_and_renaming_in_a_room_keep_the_room_nick(monkeypatch):
    g = game()
    t, pid = save(g, 1, NORMAL[:1])
    monkeypatch.setattr(main, "game", g)
    main.manager.rooms.clear()
    with TestClient(main.app) as c, c.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "room": "nicks", "nick": "进房", "token": t, "motionVersion": 2})
        ws.receive_json()
        assert g.store.room_nicks([pid]) == {pid: "进房"}
        ws.send_json({"type": "state", "nick": "改名"})
        ws.receive_json()
        assert g.store.room_nicks([pid]) == {pid: "改名"}
