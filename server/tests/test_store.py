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


def test_items_count_and_drop_log():
    s = Store(":memory:")
    s.get_player("p1", 0)
    assert s.add_item("p1", "card:c1", 1.0) == 1
    assert s.add_item("p1", "card:c1", 2.0) == 2
    assert s.owned("p1") == {"card:c1": 2}
    for i in range(25):
        s.log_drop("p1", f"card:c{i}", "common", i == 0, float(i))
    recent = s.recent_drops("p1", 20)
    assert len(recent) == 20 and recent[0] == {"item": "card:c24", "rarity": "common", "new": False, "ts": 24.0}


def test_presets_save_and_clear():
    s = Store(":memory:")
    s.save_preset("p1", 2, '{"a": 1}')
    s.save_preset("p1", 2, '{"a": 2}')
    assert s.presets("p1") == {2: '{"a": 2}'}
    s.save_preset("p1", 2, None)
    assert s.presets("p1") == {}


def test_migrates_v1_card_tables(tmp_path):
    path = str(tmp_path / "old.db")
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE players (id TEXT PRIMARY KEY, created REAL NOT NULL, frame TEXT, badge TEXT);
        CREATE TABLE cards (player_id TEXT NOT NULL, card_id TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0,
                            first_ts REAL NOT NULL, PRIMARY KEY (player_id, card_id));
        CREATE TABLE drops (id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT NOT NULL, card_id TEXT NOT NULL,
                            rarity TEXT NOT NULL, is_new INTEGER NOT NULL, ts REAL NOT NULL);
        INSERT INTO players (id, created) VALUES ('p1', 1);
        INSERT INTO cards VALUES ('p1', 'c7', 2, 1);
        INSERT INTO drops (player_id, card_id, rarity, is_new, ts) VALUES ('p1', 'c7', 'rare', 1, 1);
    """)
    db.commit()
    db.close()
    s = Store(path)
    assert s.owned("p1") == {"card:c7": 2}
    assert s.recent_drops("p1")[0]["item"] == "card:c7"
    assert s.get_player("p1", 0)["shards"] == 0
    s.close()
    assert Store(path).owned("p1") == {"card:c7": 2}  # migration is idempotent


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
    s.add_item("p1", "card:c9", 0)
    s.close()
    s2 = Store(path)
    assert s2.owned("p1") == {"card:c9": 1}
    assert sqlite3.connect(path).execute("select count(*) from players").fetchone()[0] == 1
