"""Store methods of the feedback players send from the settings page (feedback.py)."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import AbstractContextManager
from typing import Any


class _StoreState:
    """What the mixins use of Store; Store sets them in __init__."""
    _db: sqlite3.Connection
    _lock: threading.RLock

    def _commit(self) -> None: ...

    def _reading(self) -> AbstractContextManager[sqlite3.Connection]: ...


# The columns of a feedback row the admin list shows; the log is read one row at a time.
_LISTED = ("f.id, f.player_id, a.main_user_id, f.ts, f.version, f.system, f.text, f.contact, "
           "length(f.log) AS log_size")


class FeedbackStore(_StoreState):
    def add_feedback(self, pid: str, ts: float, day: str, version: str, system: str, text: str, contact: str,
                     log: str) -> int:
        """Keeps one feedback; returns its id."""
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO feedback (player_id, ts, day, version, system, text, contact, log) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (pid, ts, day, version, system, text, contact, log))
            self._commit()
            return int(cur.lastrowid or 0)

    def feedback_count(self, day: str, pid: str | None = None) -> int:
        """Feedback kept on China day [day]: the save [pid]'s, or every save's."""
        with self._lock:
            if pid is None:
                row = self._db.execute("SELECT COUNT(*) FROM feedback WHERE day = ?", (day,)).fetchone()
            else:
                row = self._db.execute("SELECT COUNT(*) FROM feedback WHERE player_id = ? AND day = ?",
                                       (pid, day)).fetchone()
        return int(row[0])

    def feedback_page(self, before: int | None, limit: int) -> list[dict[str, Any]]:
        """Feedback newest first, without the logs: below id [before] when given."""
        with self._reading() as db:
            rows = db.execute(
                f"SELECT {_LISTED} FROM feedback f LEFT JOIN account_links a ON a.player_id = f.player_id "
                "WHERE f.id < ? ORDER BY f.id DESC LIMIT ?", (before if before is not None else 2**62, limit)).fetchall()
        return [dict(r) for r in rows]

    def feedback_one(self, fid: int) -> dict[str, Any] | None:
        """One feedback with its log."""
        with self._reading() as db:
            row = db.execute(
                f"SELECT {_LISTED}, f.log FROM feedback f LEFT JOIN account_links a ON a.player_id = f.player_id "
                "WHERE f.id = ?", (fid,)).fetchone()
        return dict(row) if row else None

    def delete_feedback(self, fid: int) -> bool:
        """Deletes one feedback; False when there was none."""
        with self._lock:
            gone = self._db.execute("DELETE FROM feedback WHERE id = ?", (fid,)).rowcount
            self._commit()
        return gone > 0
