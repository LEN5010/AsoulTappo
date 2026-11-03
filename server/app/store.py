"""SQLite persistence for players, their card collection and the drop log (stdlib only)."""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any

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
  badge TEXT
);
CREATE TABLE IF NOT EXISTS cards (
  player_id TEXT NOT NULL,
  card_id TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  first_ts REAL NOT NULL,
  PRIMARY KEY (player_id, card_id)
);
CREATE TABLE IF NOT EXISTS drops (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT NOT NULL,
  card_id TEXT NOT NULL,
  rarity TEXT NOT NULL,
  is_new INTEGER NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS drops_player ON drops (player_id, id);
"""

PLAYER_FIELDS = (
    "id created taps_total active_minutes progress_taps progress_minutes boxes boxes_day boxes_today "
    "last_activity minute_bucket minute_taps minute_counted since_epic since_legend opened_total frame badge"
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
                self._db.execute("INSERT INTO players (id, created) VALUES (?, ?)", (pid, now))
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

    # --- cards
    def owned(self, pid: str) -> dict[str, int]:
        with self._lock:
            rows = self._db.execute("SELECT card_id, count FROM cards WHERE player_id=?", (pid,)).fetchall()
        return {r["card_id"]: r["count"] for r in rows}

    def add_card(self, pid: str, card_id: str, now: float) -> int:
        """Increment the owned count; returns the new count."""
        with self._lock:
            self._db.execute(
                "INSERT INTO cards (player_id, card_id, count, first_ts) VALUES (?,?,1,?) "
                "ON CONFLICT(player_id, card_id) DO UPDATE SET count = count + 1",
                (pid, card_id, now))
            row = self._db.execute(
                "SELECT count FROM cards WHERE player_id=? AND card_id=?", (pid, card_id)).fetchone()
            self._commit()
            return row["count"]

    def log_drop(self, pid: str, card_id: str, rarity: str, is_new: bool, now: float) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO drops (player_id, card_id, rarity, is_new, ts) VALUES (?,?,?,?,?)",
                (pid, card_id, rarity, int(is_new), now))
            self._commit()

    def recent_drops(self, pid: str, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT card_id, rarity, is_new, ts FROM drops WHERE player_id=? ORDER BY id DESC LIMIT ?",
                (pid, limit)).fetchall()
        return [dict(r) for r in rows]

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
