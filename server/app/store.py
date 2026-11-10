"""SQLite persistence for players, their item collection, presets and the drop log (stdlib only)."""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Callable, Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY,
  created REAL NOT NULL,
  taps_total INTEGER NOT NULL DEFAULT 0,
  active_minutes INTEGER NOT NULL DEFAULT 0,
  progress_taps INTEGER NOT NULL DEFAULT 0,
  progress_minutes INTEGER NOT NULL DEFAULT 0,
  boxes INTEGER NOT NULL DEFAULT 0,
  boxes_day TEXT NOT NULL DEFAULT '',
  boxes_today INTEGER NOT NULL DEFAULT 0,
  last_activity REAL NOT NULL DEFAULT 0,
  minute_bucket INTEGER NOT NULL DEFAULT 0,
  minute_taps INTEGER NOT NULL DEFAULT 0,
  minute_counted INTEGER NOT NULL DEFAULT 0,
  since_epic INTEGER NOT NULL DEFAULT 0,
  since_legend INTEGER NOT NULL DEFAULT 0,
  opened_total INTEGER NOT NULL DEFAULT 0,
  frame TEXT,
  badge TEXT,
  shards INTEGER NOT NULL DEFAULT 0,
  loadout TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS items (
  player_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  first_ts REAL NOT NULL,
  PRIMARY KEY (player_id, item_id)
);
CREATE TABLE IF NOT EXISTS drops (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  rarity TEXT NOT NULL,
  is_new INTEGER NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS drops_player ON drops (player_id, id);
CREATE TABLE IF NOT EXISTS activity_budget (
  player_id TEXT PRIMARY KEY,
  balance REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS activity_sessions (
  player_id TEXT NOT NULL,
  session TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  PRIMARY KEY (player_id, session)
);
CREATE TABLE IF NOT EXISTS presets (
  player_id TEXT NOT NULL,
  slot INTEGER NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY (player_id, slot)
);
CREATE TABLE IF NOT EXISTS account_links (
  main_user_id TEXT PRIMARY KEY,
  player_id TEXT NOT NULL UNIQUE,
  linked_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_active (
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  PRIMARY KEY (day, player_id)
);
CREATE TABLE IF NOT EXISTS presence_sessions (
  player_id TEXT NOT NULL,
  session TEXT NOT NULL,
  last_seen REAL NOT NULL,
  PRIMARY KEY (player_id, session)
);
CREATE TABLE IF NOT EXISTS checkins (
  player_id TEXT NOT NULL,
  day TEXT NOT NULL,
  prize INTEGER NOT NULL,
  shards INTEGER NOT NULL,
  ts REAL NOT NULL,
  PRIMARY KEY (player_id, day)
);
-- Scratch cards: the prize is decided when a card is bought and paid when it is revealed (revealed = 0 until then).
CREATE TABLE IF NOT EXISTS scratch_cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT NOT NULL,
  day TEXT NOT NULL,
  cells TEXT NOT NULL,
  shards INTEGER NOT NULL,
  item TEXT NOT NULL DEFAULT '',
  ts REAL NOT NULL,
  revealed REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS scratch_cards_player ON scratch_cards (player_id, day);
-- Rock-paper-scissors between saves a (inviter) and b. A row is written when both bets are taken; state goes from
-- 'open' to 'won' (winner holds the save paid `prize`) or 'refunded' exactly once. day: China date of the stakes.
CREATE TABLE IF NOT EXISTS duels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  a TEXT NOT NULL,
  b TEXT NOT NULL,
  bet INTEGER NOT NULL,
  prize INTEGER NOT NULL,
  day TEXT NOT NULL,
  ts REAL NOT NULL,
  state TEXT NOT NULL DEFAULT 'open',
  winner TEXT NOT NULL DEFAULT '',
  settled REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS duels_a ON duels (a, day);
CREATE INDEX IF NOT EXISTS duels_b ON duels (b, day);
CREATE INDEX IF NOT EXISTS duels_state ON duels (state);
-- One-time data changes already applied to this database.
CREATE TABLE IF NOT EXISTS migrations (
  name TEXT PRIMARY KEY,
  at REAL NOT NULL
);
-- Nickname blocklist as the main site's admin backend sent it (trimmed, not folded).
CREATE TABLE IF NOT EXISTS blocked_words (
  word TEXT PRIMARY KEY
);
-- Single values the operator sets through /admin, as JSON (the notice: minimum version and announcements).
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

STARTER_SHARDS = 1600

PLAYER_FIELDS = (
    "id created taps_total active_minutes last_activity minute_bucket minute_taps minute_counted frame badge "
    "shards loadout draw_pity drawn_total presence_last skin_pity last_minute_taps shard_remainder "
    "boost_day boost_used tap_cooldown_until tap_day day_taps scratch_pity"
).split()


class Store:
    """Thread-safe wrapper around one sqlite3 connection (":memory:" for tests)."""

    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            d = os.path.dirname(os.path.abspath(path))
            os.makedirs(d, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._migrate()

    def _columns(self, table: str) -> set[str]:
        return {r[1] for r in self._db.execute(f"PRAGMA table_info({table})")}

    def _migrate(self) -> None:
        """Bring databases created by older versions up to the current schema."""
        with self._db:
            players = self._columns("players")
            if "shards" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN shards INTEGER NOT NULL DEFAULT 0")
            if "loadout" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN loadout TEXT NOT NULL DEFAULT ''")
            for field, kind in (("draw_tickets", "INTEGER"), ("draw_seconds", "REAL"),
                                ("draw_pity", "INTEGER"), ("drawn_total", "INTEGER"),
                                ("presence_last", "REAL")):
                if field not in players:
                    self._db.execute(f"ALTER TABLE players ADD COLUMN {field} {kind} NOT NULL DEFAULT 0")
            if "skin_pity" not in players:
                for field, kind in (("skin_pity", "INTEGER"), ("last_minute_taps", "INTEGER"),
                                    ("shard_remainder", "REAL")):
                    self._db.execute(f"ALTER TABLE players ADD COLUMN {field} {kind} NOT NULL DEFAULT 0")
                self._db.execute("UPDATE players SET shards = shards * 16 + (draw_tickets + boxes) * 160, "
                                 "draw_tickets = 0, boxes = 0")
            # Boosted income spent on one China day, and the cooldown after input too fast for a hand.
            if "boost_day" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN boost_day TEXT NOT NULL DEFAULT ''")
            for field in ("boost_used", "tap_cooldown_until"):
                if field not in players:
                    self._db.execute(f"ALTER TABLE players ADD COLUMN {field} REAL NOT NULL DEFAULT 0")
            # Taps that paid shards on one China day (tap income since 1.1; boost_* is no longer used).
            if "tap_day" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN tap_day TEXT NOT NULL DEFAULT ''")
            if "day_taps" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN day_taps INTEGER NOT NULL DEFAULT 0")
            # Scratch cards bought since the last one that gave an emote.
            if "scratch_pity" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN scratch_pity INTEGER NOT NULL DEFAULT 0")
            sessions = self._columns("activity_sessions")
            for field in ("last_at", "fast_since"):
                if field not in sessions:
                    self._db.execute(f"ALTER TABLE activity_sessions ADD COLUMN {field} REAL NOT NULL DEFAULT 0")
            # v1 stored bare card ids in `cards`; items are namespaced (card:<id>)
            if self._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cards'").fetchone():
                self._db.execute(
                    "INSERT OR IGNORE INTO items (player_id, item_id, count, first_ts) "
                    "SELECT player_id, 'card:' || card_id, count, first_ts FROM cards")
                self._db.execute("DROP TABLE cards")
            if "card_id" in self._columns("drops"):
                self._db.execute("ALTER TABLE drops RENAME COLUMN card_id TO item_id")
                self._db.execute("UPDATE drops SET item_id = 'card:' || item_id WHERE instr(item_id, ':') = 0")

    def _commit(self) -> None:
        if not getattr(self, "_in_tx", False):
            self._db.commit()

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def transaction(self):
        """Context manager: holds the lock and commits/rolls back."""
        return _Tx(self)

    # --- players
    def get_player(self, pid: str, now: float) -> dict[str, Any]:
        with self._lock:
            row = self._db.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
            if row is None:
                self._db.execute("INSERT INTO players (id, created, shards) VALUES (?, ?, ?)", (pid, now, STARTER_SHARDS))
                self._commit()
                row = self._db.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
            return dict(row)

    def update_player(self, pid: str, **fields: Any) -> None:
        bad = set(fields) - set(PLAYER_FIELDS)
        if bad:
            raise ValueError(f"unknown player fields: {bad}")
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._db.execute(f"UPDATE players SET {cols} WHERE id=?", (*fields.values(), pid))
            self._commit()

    # --- activity (updated in the same transaction as player progress)
    def activity_budget(self, pid: str) -> float:
        with self._lock:
            row = self._db.execute("SELECT balance FROM activity_budget WHERE player_id=?", (pid,)).fetchone()
            return row["balance"] if row else 0.0

    def save_activity_budget(self, pid: str, balance: float) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO activity_budget VALUES (?, ?) "
                "ON CONFLICT(player_id) DO UPDATE SET balance=excluded.balance", (pid, balance))
            self._commit()

    def activity_session(self, pid: str, session: str) -> dict[str, float]:
        """The session's last batch: its sequence, when it came, and since when it has been too fast."""
        with self._lock:
            row = self._db.execute(
                "SELECT sequence, last_at, fast_since FROM activity_sessions WHERE player_id=? AND session=?",
                (pid, session)).fetchone()
            return dict(row) if row else {"sequence": 0, "last_at": 0.0, "fast_since": 0.0}

    def save_activity_sequence(self, pid: str, session: str, sequence: int,
                               last_at: float = 0.0, fast_since: float = 0.0) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO activity_sessions (player_id, session, sequence, last_at, fast_since) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(player_id, session) DO UPDATE SET "
                "sequence=excluded.sequence, last_at=excluded.last_at, fast_since=excluded.fast_since",
                (pid, session, sequence, last_at, fast_since))
            self._commit()

    def prune_activity_sessions(self, before: float) -> int:
        """Delete sessions last seen before [before]; rows from before last_at existed hold 0 and go too."""
        with self._lock:
            cur = self._db.execute("DELETE FROM activity_sessions WHERE last_at < ?", (before,))
            self._commit()
            return cur.rowcount

    # --- main-site accounts: one save per account, one account per save
    def has_player(self, pid: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM players WHERE id=?", (pid,)).fetchone() is not None

    def linked_player(self, main_user_id: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT player_id FROM account_links WHERE main_user_id=?", (main_user_id,)).fetchone()
        return row["player_id"] if row else None

    def account_for_player(self, pid: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT main_user_id FROM account_links WHERE player_id=?", (pid,)).fetchone()
        return row["main_user_id"] if row else None

    def link_account(self, main_user_id: str, pid: str, now: float) -> None:
        with self._lock:
            self._db.execute("INSERT INTO account_links (main_user_id, player_id, linked_at) VALUES (?, ?, ?)",
                             (main_user_id, pid, now))
            self._commit()

    def unlink_account(self, main_user_id: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM account_links WHERE main_user_id=?", (main_user_id,))
            self._commit()
            return cur.rowcount > 0

    def account_links(self, user_ids: list[str] | None, offset: int, limit: int) -> tuple[list[dict], int]:
        """Linked saves, most recently active first; [user_ids] narrows to those accounts."""
        where, args = "", ()
        if user_ids is not None:
            where = f"WHERE l.main_user_id IN ({','.join('?' for _ in user_ids)})" if user_ids else "WHERE 0"
            args = tuple(user_ids)
        with self._lock:
            total = self._db.execute(f"SELECT COUNT(*) FROM account_links l {where}", args).fetchone()[0]
            rows = self._db.execute(
                f"SELECT l.main_user_id, l.player_id, l.linked_at FROM account_links l "
                f"LEFT JOIN players p ON p.id = l.player_id {where} "
                f"ORDER BY COALESCE(NULLIF(p.last_activity, 0), p.created, l.linked_at) DESC LIMIT ? OFFSET ?",
                (*args, limit, offset)).fetchall()
        return [dict(r) for r in rows], total

    # --- daily check-in (days are China Standard Time dates, YYYY-MM-DD)
    def checked_in(self, pid: str, day: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM checkins WHERE player_id=? AND day=?", (pid, day)).fetchone() is not None

    def add_checkin(self, pid: str, day: str, prize: int, shards: int, ts: float) -> None:
        with self._lock:
            self._db.execute("INSERT INTO checkins (player_id, day, prize, shards, ts) VALUES (?, ?, ?, ?, ?)",
                             (pid, day, prize, shards, ts))
            self._commit()

    def checkins_since(self, pid: str, first_day: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT day, prize, shards FROM checkins WHERE player_id=? AND day >= ? ORDER BY day",
                                    (pid, first_day)).fetchall()
        return [dict(r) for r in rows]

    # --- scratch cards (days are China Standard Time dates, YYYY-MM-DD)
    def scratch_count(self, pid: str, day: str) -> int:
        """Cards bought on [day]."""
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM scratch_cards WHERE player_id=? AND day=?", (pid, day)).fetchone()[0]

    def add_scratch(self, pid: str, day: str, cells: str, shards: int, item: str, ts: float) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO scratch_cards (player_id, day, cells, shards, item, ts) VALUES (?, ?, ?, ?, ?, ?)",
                (pid, day, cells, shards, item, ts))
            self._commit()
            return cur.lastrowid

    def pending_scratch(self, pid: str) -> dict[str, Any] | None:
        """The card bought and not revealed yet; a save holds one at most."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM scratch_cards WHERE player_id=? AND revealed=0 ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
        return dict(row) if row else None

    def scratch_card(self, pid: str, card_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM scratch_cards WHERE id=? AND player_id=?", (card_id, pid)).fetchone()
        return dict(row) if row else None

    def reveal_scratch(self, card_id: int, ts: float) -> None:
        with self._lock:
            self._db.execute("UPDATE scratch_cards SET revealed=? WHERE id=?", (ts, card_id))
            self._commit()

    def prune_scratch_cards(self, before: float) -> int:
        """Delete revealed cards bought before [before]; a card still to be revealed is kept however old."""
        with self._lock:
            cur = self._db.execute("DELETE FROM scratch_cards WHERE revealed > 0 AND ts < ?", (before,))
            self._commit()
            return cur.rowcount

    # --- rock-paper-scissors (days are China Standard Time dates, YYYY-MM-DD)
    def player_taps(self, pid: str) -> int | None:
        """All-time taps of a save, None when there is no such save (never creates one)."""
        with self._lock:
            row = self._db.execute("SELECT taps_total FROM players WHERE id=?", (pid,)).fetchone()
        return row["taps_total"] if row else None

    def add_duel(self, a: str, b: str, bet: int, prize: int, day: str, ts: float) -> int:
        with self._lock:
            cur = self._db.execute("INSERT INTO duels (a, b, bet, prize, day, ts) VALUES (?, ?, ?, ?, ?, ?)",
                                   (a, b, bet, prize, day, ts))
            self._commit()
            return cur.lastrowid

    def duel(self, duel_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM duels WHERE id=?", (duel_id,)).fetchone()
        return dict(row) if row else None

    def close_duel(self, duel_id: int, state: str, winner: str, ts: float) -> bool:
        """Moves an open duel to [state]; False when it was closed already, so it is paid at most once."""
        with self._lock:
            cur = self._db.execute("UPDATE duels SET state=?, winner=?, settled=? WHERE id=? AND state='open'",
                                   (state, winner, ts, duel_id))
            self._commit()
            return cur.rowcount == 1

    def open_duels(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM duels WHERE state='open' ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def duel_net(self, pid: str, day: str) -> int:
        """Prizes minus bets of the save's duels won or lost on [day]; refunded and open duels count nothing."""
        with self._lock:
            return self._db.execute(
                "SELECT COALESCE(SUM(CASE WHEN winner=? THEN prize - bet ELSE -bet END), 0) FROM duels "
                "WHERE state='won' AND (a=? OR b=?) AND day=?", (pid, pid, pid, day)).fetchone()[0]

    # --- daily statistics (days are China Standard Time dates, YYYY-MM-DD)
    def mark_active(self, pid: str, day: str) -> None:
        with self._lock:
            self._db.execute("INSERT OR IGNORE INTO daily_active (day, player_id) VALUES (?, ?)", (day, pid))
            self._commit()

    def totals(self, today: str) -> dict[str, int]:
        with self._lock:
            one = lambda sql, *a: self._db.execute(sql, a).fetchone()[0]  # noqa: E731
            return {"saves": one("SELECT COUNT(*) FROM players"),
                    "linked": one("SELECT COUNT(*) FROM account_links"),
                    "activeToday": one("SELECT COUNT(*) FROM daily_active WHERE day=?", today)}

    def daily(self, since: str, offset_seconds: int) -> dict[str, dict[str, int]]:
        """Per day since [since]: active saves, new saves and items obtained."""
        shift = f"{offset_seconds} seconds"
        out: dict[str, dict[str, int]] = {}
        with self._lock:
            queries = {
                "active": ("SELECT day, COUNT(*) FROM daily_active WHERE day >= ? GROUP BY day", (since,)),
                "newSaves": ("SELECT date(created, 'unixepoch', ?) d, COUNT(*) FROM players GROUP BY d HAVING d >= ?", (shift, since)),
                "items": ("SELECT date(ts, 'unixepoch', ?) d, COUNT(*) FROM drops GROUP BY d HAVING d >= ?", (shift, since)),
            }
            for key, (sql, args) in queries.items():
                for day, n in self._db.execute(sql, args).fetchall():
                    out.setdefault(day, {})[key] = n
        return out

    def owned(self, pid: str) -> dict[str, int]:
        with self._lock:
            rows = self._db.execute("SELECT item_id, count FROM items WHERE player_id=?", (pid,)).fetchall()
        return {r["item_id"]: r["count"] for r in rows}

    def count_items(self, pid: str, item_ids: tuple[str, ...]) -> int:
        if not item_ids:
            return 0
        placeholders = ",".join("?" for _ in item_ids)
        with self._lock:
            return self._db.execute(
                f"SELECT COUNT(*) FROM items WHERE player_id=? AND item_id IN ({placeholders})",
                (pid, *item_ids)).fetchone()[0]

    def add_item(self, pid: str, item_id: str, now: float) -> int:
        """Increment the owned count; returns the new count."""
        with self._lock:
            self._db.execute(
                "INSERT INTO items (player_id, item_id, count, first_ts) VALUES (?,?,1,?) "
                "ON CONFLICT(player_id, item_id) DO UPDATE SET count = count + 1",
                (pid, item_id, now))
            row = self._db.execute(
                "SELECT count FROM items WHERE player_id=? AND item_id=?", (pid, item_id)).fetchone()
            self._commit()
            return row["count"]

    def add_items(self, pid: str, counts: dict[str, int], now: float) -> None:
        """Apply one draw batch's increments; the caller owns the transaction."""
        with self._lock:
            self._db.executemany(
                "INSERT INTO items (player_id, item_id, count, first_ts) VALUES (?,?,?,?) "
                "ON CONFLICT(player_id, item_id) DO UPDATE SET count = count + excluded.count",
                [(pid, item, count, now) for item, count in counts.items()])
            self._commit()

    def refund_duplicates(self, name: str, prefix: str, shards_for: Callable[[str], int], now: float) -> tuple[int, int]:
        """Once per database (recorded as `name`): every item under `prefix` held more than once goes back to
        one copy, and each extra copy pays `shards_for(item)`. Items that pay nothing keep their copies.
        Returns (players paid, shards paid)."""
        with self._lock:
            if self._db.execute("SELECT 1 FROM migrations WHERE name=?", (name,)).fetchone():
                return 0, 0
            rows = self._db.execute(
                "SELECT player_id, item_id, count FROM items WHERE item_id LIKE ? AND count > 1", (prefix + "%",)).fetchall()
            paid: dict[str, int] = {}
            exchanged: list[tuple[str, str]] = []
            for r in rows:
                each = shards_for(r["item_id"])
                if each > 0:
                    paid[r["player_id"]] = paid.get(r["player_id"], 0) + (r["count"] - 1) * each
                    exchanged.append((r["player_id"], r["item_id"]))
            with self._db:
                self._db.executemany("UPDATE players SET shards = shards + ? WHERE id=?",
                                     [(n, pid) for pid, n in paid.items()])
                self._db.executemany("UPDATE items SET count = 1 WHERE player_id=? AND item_id=?", exchanged)
                self._db.execute("INSERT INTO migrations (name, at) VALUES (?, ?)", (name, now))
            return sum(1 for n in paid.values() if n), sum(paid.values())

    def log_drops(self, pid: str, drops: list[dict], now: float) -> None:
        with self._lock:
            self._db.executemany(
                "INSERT INTO drops (player_id, item_id, rarity, is_new, ts) VALUES (?,?,?,?,?)",
                [(pid, d["item"], d["rarity"], int(d["new"]), now) for d in drops])
            self._commit()

    def log_drop(self, pid: str, item_id: str, rarity: str, is_new: bool, now: float) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO drops (player_id, item_id, rarity, is_new, ts) VALUES (?,?,?,?,?)",
                (pid, item_id, rarity, int(is_new), now))
            self._commit()

    def recent_drops(self, pid: str, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT item_id, rarity, is_new, ts FROM drops WHERE player_id=? ORDER BY id DESC LIMIT ?",
                (pid, limit)).fetchall()
        return [{"item": r["item_id"], "rarity": r["rarity"], "new": bool(r["is_new"]), "ts": r["ts"]}
                for r in rows]

    # --- presets (JSON text per slot)
    def presets(self, pid: str) -> dict[int, str]:
        with self._lock:
            rows = self._db.execute("SELECT slot, data FROM presets WHERE player_id=?", (pid,)).fetchall()
        return {r["slot"]: r["data"] for r in rows}

    def save_preset(self, pid: str, slot: int, data: str | None) -> None:
        with self._lock:
            if data is None:
                self._db.execute("DELETE FROM presets WHERE player_id=? AND slot=?", (pid, slot))
            else:
                self._db.execute(
                    "INSERT INTO presets VALUES (?, ?, ?) "
                    "ON CONFLICT(player_id, slot) DO UPDATE SET data=excluded.data", (pid, slot, data))
            self._commit()

    # --- nickname blocklist
    def blocked_words(self) -> list[str]:
        with self._lock:
            rows = self._db.execute("SELECT word FROM blocked_words ORDER BY rowid").fetchall()
        return [r["word"] for r in rows]

    def replace_blocked_words(self, words: list[str]) -> None:
        """Replace the whole list in one transaction; [words] must be distinct."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM blocked_words")
            self._db.executemany("INSERT INTO blocked_words (word) VALUES (?)", [(w,) for w in words])

    def setting(self, key: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def close(self) -> None:
        with self._lock:
            self._db.close()


class _Tx:
    def __init__(self, store: Store) -> None:
        self.store = store

    def __enter__(self) -> Store:
        self.store._lock.acquire()
        self.store._in_tx = True
        return self.store

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.store._db.commit()
            else:
                self.store._db.rollback()
        finally:
            self.store._in_tx = False
            self.store._lock.release()
