import sqlite3

import pytest

from app.store import Store


def test_player_defaults_and_update():
    s = Store(":memory:")
    p = s.get_player("p1", 5.0)
    assert p["created"] == 5.0 and p["boxes"] == 0 and p["frame"] is None
    s.update_player("p1", boxes=3, frame="f")
    assert s.get_player("p1", 9.0)["boxes"] == 3
    with pytest.raises(ValueError):
        s.update_player("p1", nope=1)


def test_cards_count_and_drop_log():
    s = Store(":memory:")
    s.get_player("p1", 0)
    assert s.add_card("p1", "c1", 1.0) == 1
    assert s.add_card("p1", "c1", 2.0) == 2
    assert s.owned("p1") == {"c1": 2}
    for i in range(25):
        s.log_drop("p1", f"c{i}", "common", i == 0, float(i))
    recent = s.recent_drops("p1", 20)
    assert len(recent) == 20 and recent[0]["card_id"] == "c24"


def test_transaction_rolls_back():
    s = Store(":memory:")
    s.get_player("p1", 0)
    with pytest.raises(RuntimeError):
        with s.transaction() as st:
            st.update_player("p1", boxes=9)
            raise RuntimeError("boom")
    assert s.get_player("p1", 0)["boxes"] == 0


def test_persists_on_disk(tmp_path):
    path = str(tmp_path / "sub" / "t.db")
    s = Store(path)
    s.get_player("p1", 0)
    s.add_card("p1", "c9", 0)
    s.close()
    s2 = Store(path)
    assert s2.owned("p1") == {"c9": 1}
    assert sqlite3.connect(path).execute("select count(*) from players").fetchone()[0] == 1
