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


def test_daily_tap_statistics_migrate_atomically_and_keep_existing_progress(tmp_path):
    from app.store import SCHEMA
    path = str(tmp_path / "legacy-taps.db")
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.execute("ALTER TABLE players ADD COLUMN tap_day TEXT NOT NULL DEFAULT ''")
        db.execute("ALTER TABLE players ADD COLUMN day_taps INTEGER NOT NULL DEFAULT 0")
        db.execute("INSERT INTO players (id, created, taps_total, tap_day, day_taps) VALUES (?, ?, ?, ?, ?)",
                   ("p1", 0, 200, "2026-11-10", 120))
        db.execute("CREATE TRIGGER interrupt_tap_migration BEFORE UPDATE OF day_taps_total ON players "
                   "BEGIN SELECT RAISE(ABORT, 'interrupted migration'); END")
    with pytest.raises(sqlite3.IntegrityError, match="interrupted migration"):
        Store(path)
    with sqlite3.connect(path) as db:
        assert "day_taps_total" not in {row[1] for row in db.execute("PRAGMA table_info(players)")}
        db.execute("DROP TRIGGER interrupt_tap_migration")
    store = Store(path)
    player = store.get_player("p1", 0)
    assert player["taps_total"] == 200
    assert player["tap_day"] == "2026-11-10"
    assert player["day_taps"] == player["day_taps_total"] == 120
    store.update_player("p1", day_taps_total=170)
    store.close()
    reopened = Store(path)
    assert reopened.get_player("p1", 0)["day_taps_total"] == 170
    reopened.close()


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


def test_collectible_count_uses_distinct_known_items_for_one_player():
    s = Store()
    collectible = frozenset({"card:c1", "emote:e1", "char:skin"})
    s.add_items("p1", {"card:c1": 5, "emote:e1": 1, "emote:starter": 1, "card:removed": 2}, 0)
    s.add_items("p2", {"char:skin": 1}, 0)
    assert s.count_items("p1", collectible) == 2
    assert s.count_items("p2", collectible) == 1
    assert s.count_items("new", collectible) == 0
    assert s.count_items("p1", frozenset()) == 0
    s.close()


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
        assert store.activity_session("old", "session-1") == {"sequence": 5, "last_at": 0, "fast_since": 0,
                                                              "rate": 0, "steady": 0, "odd": 0, "near": 0}
        assert store.owned("old") == {"emote:e.02": 2}
        store.close()


def test_a_database_file_uses_the_write_ahead_log(tmp_path):
    s = Store(str(tmp_path / "wal.db"))
    assert s._db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert s._db.execute("PRAGMA synchronous").fetchone()[0] == 1
    s.close()


def test_collectible_count_follows_new_items_and_rollbacks():
    s = Store()
    collectible = frozenset({"card:c1", "emote:e1"})
    assert s.count_items("p1", collectible) == 0
    s.add_item("p1", "card:c1", 0)
    assert s.count_items("p1", collectible) == 1
    s.add_items("p1", {"emote:e1": 2}, 0)
    assert s.count_items("p1", collectible) == 2
    with pytest.raises(RuntimeError):
        with s.transaction():
            s.add_items("p2", {"card:c1": 1}, 0)
            assert s.count_items("p2", collectible) == 1
            raise RuntimeError("undo")
    assert s.count_items("p2", collectible) == 0
    # Another set of collectibles (another manifest) is counted afresh.
    assert s.count_items("p1", frozenset({"card:c1"})) == 1
    assert s.has_item("p1", "emote:e1") and not s.has_item("p1", "emote:e2") and not s.has_item("p2", "card:c1")
    s.close()


def test_marking_a_save_active_writes_once_a_day_and_survives_a_rollback():
    s = Store()
    statements = []
    s.mark_active("p1", "2026-11-10")
    s._db.set_trace_callback(statements.append)
    s.mark_active("p1", "2026-11-10")
    assert statements == []
    s.mark_active("p1", "2026-11-11")
    s.mark_active("p2", "2026-11-11")
    s._db.set_trace_callback(None)
    assert s.totals("2026-11-10")["activeToday"] == 1 and s.totals("2026-11-11")["activeToday"] == 2
    with pytest.raises(RuntimeError):
        with s.transaction():
            s.mark_active("p3", "2026-11-11")
            raise RuntimeError("undo")
    s.mark_active("p3", "2026-11-11")
    assert s.totals("2026-11-11")["activeToday"] == 3
    s.close()


def test_duel_net_counts_won_duels_of_the_day_through_the_day_indexes():
    s = Store()
    won = s.add_duel("p1", "p2", 100, 190, "2026-11-10", 0)
    lost = s.add_duel("p3", "p1", 50, 95, "2026-11-10", 0)
    s.add_duel("p1", "p2", 70, 133, "2026-11-10", 0)  # still open
    other_day = s.add_duel("p1", "p2", 30, 57, "2026-11-09", 0)
    refunded = s.add_duel("p1", "p2", 20, 38, "2026-11-10", 0)
    s.close_duel(won, "won", "p1", 1)
    s.close_duel(lost, "won", "p3", 1)
    s.close_duel(other_day, "won", "p1", 1)
    s.close_duel(refunded, "refunded", "", 1)
    assert s.duel_net("p1", "2026-11-10") == 90 - 50
    assert s.duel_net("p2", "2026-11-10") == -100
    assert s.duel_net("p3", "2026-11-10") == 45
    plan = " ".join(r[3] for r in s._db.execute(
        "EXPLAIN QUERY PLAN SELECT SUM(bet) FROM duels WHERE ((a=? AND day=?) OR (b=? AND day=?)) AND +state='won'",
        ("p1", "d", "p1", "d")))
    assert "duels_a" in plan and "duels_b" in plan and "duels_state" not in plan
    s.close()


def test_databases_from_before_the_shard_ledger_gain_it(tmp_path):
    path = str(tmp_path / "pre-ledger.db")
    s = Store(path)
    s.get_player("p1", 0)
    s.close()
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE shard_ledger")
    s = Store(path)
    assert s.get_player("p1", 0)["shards"] == 1600
    assert s.ledger_of("p1", ["1970-01-01"]) == []
    s.add_ledger("p1", "1970-01-01", "admin", 5)
    s.add_ledger("p1", "1970-01-01", "admin", -2)
    assert s.ledger_of("p1", ["1970-01-01"]) == [{"day": "1970-01-01", "source": "admin", "amount": 3, "count": 2}]
    s.close()


def test_tap_flags_and_steady_fields_are_added_to_older_databases(tmp_path):
    from app.store import SCHEMA
    path = str(tmp_path / "before-steady.db")
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.executescript("""
        DROP TABLE tap_flags;
        CREATE TABLE tap_flags (day TEXT NOT NULL, player_id TEXT NOT NULL, dropped INTEGER NOT NULL DEFAULT 0,
          server_cooldowns INTEGER NOT NULL DEFAULT 0, client_cooldowns INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (day, player_id));
        INSERT INTO tap_flags VALUES ('2026-11-13', 'old', 7, 1, 0);
    """)
    db.close()
    store = Store(path)
    store.add_tap_flags("2026-11-13", "old", steady=1)
    row = store._db.execute("SELECT dropped, server_cooldowns, steady FROM tap_flags").fetchone()
    assert tuple(row) == (7, 1, 1)
    p = store.get_player("old", 0)
    assert p["steady_day"] == "" and p["steady_hits"] == 0 and p["steady_rate"] == 0
    store.close()
