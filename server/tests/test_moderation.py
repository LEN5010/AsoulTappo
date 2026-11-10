"""Nickname blocklist: folding, masking, the admin routes and masked nicks in rooms."""
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.game import Game
from app.manifest import Manifest
from app.moderation import Blocklist, fold, folded
from app.store import Store

KEY = {"X-Admin-Key": "admin-secret"}
TOKEN = "moderation-player-token-01"

# Same word list and rows as the table in protocol/PROTOCOL.md (昵称屏蔽); the main site checks its port against it.
WORDS = ["坏词", "BadWord", "café", "wordy", "!!"]
VECTORS = [
    ("[坏词]", "坏词", "[**]"),
    ("ＢＡＤＷＯＲＤ", "badword", "*******"),
    ("Bad Word!", "badword", "********!"),
    ("坏​词abc", "坏词abc", "***abc"),
    ("CAFÉ", "cafe", "****"),
    ("café", "cafe", "****́"),
    ("坏词x坏词", "坏词x坏词", "**x**"),
    ("badwordy", "badwordy", "********"),
    ("坏😀词", "坏词", "***"),
    ("好词", "好词", "好词"),
]


@pytest.mark.parametrize("text, fold_result, masked", VECTORS)
def test_vectors(text, fold_result, masked):
    b = Blocklist(WORDS)
    assert folded(text) == fold_result
    assert b.mask(text) == masked
    assert len(b.mask(text)) == len(text)
    assert b.hits(text) == (masked != text)


def _unescape(cell: str) -> str:
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), cell.strip().strip("`"))


def test_protocol_table_matches_the_vectors():
    doc = (Path(__file__).resolve().parents[2] / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    section = doc.split("### 昵称屏蔽", 1)[1].split("\n## ", 1)[0]
    header = section.index("| 输入 |")
    rows = []
    for line in section[header:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        rows.append(tuple(_unescape(c) for c in line.strip("|").split("|")[:3]))
    assert rows == VECTORS
    listed = re.search(r"词表为 (.+?)，其中", section).group(1)
    assert re.findall(r"`([^`]+)`", listed) == WORDS


def test_fold_keeps_letters_and_digits_with_their_code_point():
    assert fold("Ａ b-1") == [("a", 0), ("b", 2), ("1", 4)]
    # one code point may fold to several characters, all pointing back at it
    assert fold("㎏") == [("k", 0), ("g", 0)]
    # each character is lowercased alone: no final-sigma form
    assert folded("ΑΣ") == "ασ"
    assert fold("‍️ 。！") == []


def test_an_empty_list_changes_nothing():
    b = Blocklist()
    assert len(b) == 0 and b.mask("坏词") == "坏词" and not b.hits("坏词")


def test_words_that_fold_to_nothing_are_ignored():
    b = Blocklist(["!!", " ", "😀", "​"])
    assert len(b) == 0
    assert b.mask("a!! 😀b") == "a!! 😀b"


def test_overlapping_and_repeated_hits_are_joined():
    b = Blocklist(["ab", "bc"])
    assert b.mask("xabcx") == "x***x"
    assert b.mask("a-b c") == "*****"
    assert b.mask("ab ab") == "** **"


def test_characters_outside_a_hit_are_kept():
    b = Blocklist(["坏词"])
    assert b.mask("  前 坏-词 后！") == "  前 *** 后！"
    assert b.mask("坏人词") == "坏人词"


def test_masking_is_fast_with_a_full_list():
    words = [f"词{i:05d}" for i in range(20000)]
    b = Blocklist(words)
    start = time.perf_counter()
    for _ in range(100):
        assert b.mask("ａｂｃ 词 0 1 2 3 4 好 人 abcdefg") == "ａｂｃ *********** 好 人 abcdefg"
    assert (time.perf_counter() - start) / 100 < 0.005


# ----------------------------------------------------------------------- HTTP and rooms
@pytest.fixture()
def api(monkeypatch, tmp_path):
    store = Store(str(tmp_path / "tappo.db"))
    monkeypatch.setattr(main, "game", Game(store, Manifest.load()))
    monkeypatch.setattr(main, "blocklist", Blocklist())
    monkeypatch.setattr(main, "raw_nicks", {})
    monkeypatch.setattr(main, "ADMIN_KEY", "admin-secret")
    monkeypatch.setattr(main, "accounts", None)
    main.manager.rooms.clear()
    with TestClient(main.app) as c:
        yield c, tmp_path / "tappo.db"
    main.manager.rooms.clear()


def put(c, words):
    return c.put("/admin/blocked-words", json={"words": words}, headers=KEY)


def join(ws, nick, room="r1", tok=None):
    msg = {"type": "join", "room": room, "nick": nick, "character": "嘉然"}
    if tok:
        msg["token"] = tok
    ws.send_json(msg)
    return ws.receive_json()


def quiet(*sockets):
    """Nothing else is waiting: the next answer is the ping's."""
    for ws in sockets:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_admin_routes_need_the_key(api):
    c, _ = api
    assert c.get("/admin/blocked-words").status_code == 404
    assert c.put("/admin/blocked-words", json={"words": ["坏词"]}).status_code == 404
    assert c.put("/admin/blocked-words", json={"words": ["坏词"]}, headers={"X-Admin-Key": "wrong"}).status_code == 404
    assert c.get("/admin/blocked-words", headers=KEY).json() == {"words": [], "count": 0}


def test_put_replaces_trims_and_dedupes(api):
    c, _ = api
    assert put(c, ["  坏词 ", "坏词", "badword", "BadWord"]).json() == {"count": 3}
    assert c.get("/admin/blocked-words", headers=KEY).json() == {"words": ["坏词", "badword", "BadWord"], "count": 3}
    assert put(c, ["新词"]).json() == {"count": 1}
    assert c.get("/admin/blocked-words", headers=KEY).json() == {"words": ["新词"], "count": 1}
    assert put(c, []).json() == {"count": 0}
    assert c.get("/admin/blocked-words", headers=KEY).json() == {"words": [], "count": 0}


def test_put_refuses_bad_lists_and_keeps_the_old_one(api):
    c, _ = api
    put(c, ["坏词"])
    for body in ({"words": [""]}, {"words": ["  "]}, {"words": ["a" * 65]}, {"words": ["ok", "x" * 65]},
                 {"words": [f"w{i}" for i in range(20001)]}, {}, {"words": "坏词"}, {"words": [1]}):
        assert c.put("/admin/blocked-words", json=body, headers=KEY).status_code == 422, body
    assert c.get("/admin/blocked-words", headers=KEY).json() == {"words": ["坏词"], "count": 1}
    assert put(c, ["a" * 64, " " + "b" * 64 + " "]).json() == {"count": 2}
    assert put(c, [f"w{i}" for i in range(20000)]).json() == {"count": 20000}
    # the cap counts words as sent, before duplicates are dropped
    assert put(c, ["w"] * 20000).json() == {"count": 1}


def test_list_survives_a_restart(api):
    c, db = api
    put(c, ["坏词", "BadWord"])
    again = Store(str(db))
    assert again.blocked_words() == ["坏词", "BadWord"]
    assert main.load_blocklist(again).mask("坏词 bad word") == "** ********"


def test_others_see_a_masked_nick_on_join(api):
    c, _ = api
    put(c, ["坏词"])
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        join(a, "a")
        jb = join(b, "b坏词!")
        assert [m["nick"] for m in jb["members"]] == ["a", "b**!"]
        assert a.receive_json()["member"]["nick"] == "b**!"
        # no block list hit: the nick goes through as sent
        with c.websocket_connect("/ws") as d:
            assert join(d, "好词")["members"][-1]["nick"] == "好词"


def test_public_list_shows_a_masked_host(api):
    c, _ = api
    put(c, ["坏词"])
    with c.websocket_connect("/ws") as a:
        join(a, "房主坏词", tok=TOKEN)
        a.send_json({"type": "set_public", "public": True})
        assert a.receive_json()["public"] is True
        assert c.get("/rooms").json()["rooms"][0]["host"]["nick"] == "房主**"


def test_a_rename_is_masked(api):
    c, _ = api
    put(c, ["坏词"])
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = join(a, "a")
        join(b, "b")
        a.receive_json()
        a.send_json({"type": "state", "nick": "坏 词"})
        for ws in (a, b):
            got = ws.receive_json()
            assert got["type"] == "state" and got["id"] == ja["you"] and got["nick"] == "***"


def test_a_new_list_masks_members_online_at_once(api):
    c, _ = api
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = join(a, "a坏词")
        join(b, "b")
        a.receive_json()
        put(c, ["坏词"])
        for ws in (a, b):
            got = ws.receive_json()
            assert got["type"] == "state" and got["id"] == ja["you"] and got["nick"] == "a**"
        quiet(a, b)  # b's nick did not change, so nothing was sent for it
        # a removed word shows the nick as sent again
        put(c, [])
        for ws in (a, b):
            assert ws.receive_json()["nick"] == "a坏词"
        quiet(a, b)


def test_a_new_list_applies_to_the_nick_as_sent_not_the_masked_one(api):
    c, _ = api
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        ja = join(a, "axb")
        join(b, "b")
        a.receive_json()
        put(c, ["x", "ab"])
        assert b.receive_json()["nick"] == "a*b"
        a.receive_json()
        # "a*b" folds to "ab", but the nick as sent does not hit it
        put(c, ["x", "ab"])
        quiet(a, b)
        assert [p.nick for p in main.manager.members("r1") if p.id == ja["you"]] == ["a*b"]


def test_nicks_of_members_who_left_are_forgotten(api):
    c, _ = api
    with c.websocket_connect("/ws") as a, c.websocket_connect("/ws") as b:
        join(a, "a")
        jb = join(b, "b")
        a.receive_json()
        assert set(main.raw_nicks) == {p.id for p in main.manager.members("r1")}
        b.send_json({"type": "leave"})
        assert a.receive_json() == {"type": "member_left", "id": jb["you"]}
        assert jb["you"] not in main.raw_nicks
