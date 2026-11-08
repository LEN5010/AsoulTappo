import sqlite3

import pytest

from app.store import Store


def test_player_defaults_and_update():
    s = Store(":memory:")
    p = s.get_player("p1", 5.0)
    assert p["created"] == 5.0 and p["shards"] == 1600 and p["frame"] is None
    s.update_player("p1", shards=3, frame="f")
    assert s.get_player("p1", 9.0)["shards"] == 3
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
        CREATE TABLE players (id TEXT PRIMARY KEY, created REAL NOT NULL, frame TEXT, badge TEXT, boxes INTEGER NOT NULL DEFAULT 0);
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
            st.update_player("p1", shards=9)
            raise RuntimeError("boom")
    assert s.get_player("p1", 0)["shards"] == 1600


def test_persists_on_disk(tmp_path):
    path = str(tmp_path / "sub" / "t.db")
    s = Store(path)
    s.get_player("p1", 0)
    s.add_item("p1", "card:c9", 0)
    s.close()
    s2 = Store(path)
    assert s2.owned("p1") == {"card:c9": 1}
    assert sqlite3.connect(path).execute("select count(*) from players").fetchone()[0] == 1


def test_resonance_migration_converts_once_and_preserves_items_and_pity(tmp_path):
    from app.store import SCHEMA
    path = str(tmp_path / "legacy.db")
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.executescript("""
        ALTER TABLE players ADD COLUMN draw_tickets INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE players ADD COLUMN draw_seconds REAL NOT NULL DEFAULT 0;
        ALTER TABLE players ADD COLUMN draw_pity INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE players ADD COLUMN drawn_total INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE players ADD COLUMN presence_last REAL NOT NULL DEFAULT 0;
        INSERT INTO players (id, created, shards, boxes, draw_tickets, draw_pity, drawn_total)
        VALUES ('old', 1, 23, 4, 7, 321, 456);
        INSERT INTO items VALUES ('old', 'emote:e.02', 2, 1);
        INSERT INTO activity_sessions VALUES ('old', 'session-1', 5);
    """)
    db.close()
    for _ in range(2):
        store = Store(path)
        p = store.get_player("old", 0)
        assert p["shards"] == 23 * 16 + 11 * 160
        assert p["boxes"] == p["draw_tickets"] == 0
        assert p["draw_pity"] == 321 and p["drawn_total"] == 456
        assert p["skin_pity"] == p["last_minute_taps"] == p["shard_remainder"] == 0
        assert p["boost_day"] == "" and p["boost_used"] == p["tap_cooldown_until"] == 0
        assert store.activity_session("old", "session-1") == {"sequence": 5, "last_at": 0, "fast_since": 0}
        assert store.owned("old") == {"emote:e.02": 2}
        store.close()
