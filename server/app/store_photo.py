"""Store methods of photocard boxes (photocards.py)."""
from __future__ import annotations

import sqlite3
import threading
from typing import Any, Iterable

# Ids asked for in one statement, well under SQLite's limit of variables.
HELD_CHUNK = 500


class _StoreState:
    """What the mixins use of Store; Store sets them in __init__."""
    _db: sqlite3.Connection
    _lock: threading.RLock

    def _commit(self) -> None: ...


class PhotoStore(_StoreState):
    def photo_save(self, pid: str, series: str) -> dict[str, int]:
        """{boxes, dry, spare} of the save in [series]; zeros before its first box."""
        with self._lock:
            row = self._db.execute("SELECT boxes, dry, spare FROM photo_saves WHERE player_id = ? AND series = ?",
                                   (pid, series)).fetchone()
        return dict(row) if row else {"boxes": 0, "dry": 0, "spare": 0}

    def held_of(self, pid: str, item_ids: Iterable[str]) -> set[str]:
        """Which of [item_ids] the save holds, looked up by the items' primary key; the rest of its items are not read."""
        ids = list(dict.fromkeys(item_ids))
        held: set[str] = set()
        with self._lock:
            for at in range(0, len(ids), HELD_CHUNK):
                part = ids[at:at + HELD_CHUNK]
                rows = self._db.execute(
                    f"SELECT item_id FROM items WHERE player_id = ? AND item_id IN ({','.join('?' * len(part))})",
                    (pid, *part)).fetchall()
                held.update(r[0] for r in rows)
        return held

    def photo_played(self, pid: str) -> bool:
        """Whether the save ever bought a box, of any series."""
        with self._lock:
            return self._db.execute("SELECT 1 FROM photo_saves WHERE player_id = ? AND boxes > 0 LIMIT 1",
                                    (pid,)).fetchone() is not None

    def set_photo_save(self, pid: str, series: str, boxes: int, dry: int, spare: int) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO photo_saves (player_id, series, boxes, dry, spare) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(player_id, series) DO UPDATE SET boxes = excluded.boxes, dry = excluded.dry, "
                "spare = excluded.spare", (pid, series, boxes, dry, spare))
            self._commit()

    def photo_bought(self, pid: str, series: str, day: str) -> int:
        """Boxes of [series] the save bought on [day]."""
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) FROM photo_boxes WHERE player_id = ? AND series = ? AND day = ?",
                                   (pid, series, day)).fetchone()
        return int(row[0])

    def add_photo_box(self, pid: str, series: str, day: str, price: int, contents: str, ts: float) -> int:
        """A bought box with its [contents] (JSON); in the caller's transaction, which takes the price."""
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO photo_boxes (player_id, series, day, price, contents, ts) VALUES (?, ?, ?, ?, ?, ?)",
                (pid, series, day, price, contents, ts))
            self._commit()
            return int(cur.lastrowid)

    def photo_unopened(self, pid: str, series: str) -> dict[str, Any] | None:
        """The save's box of [series] not opened to the end yet; it has one at most."""
        with self._lock:
            row = self._db.execute("SELECT * FROM photo_boxes WHERE player_id = ? AND series = ? AND opened = 0 "
                                   "ORDER BY id LIMIT 1", (pid, series)).fetchone()
        return dict(row) if row else None

    def photo_box(self, pid: str, box_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM photo_boxes WHERE id = ? AND player_id = ?",
                                   (box_id, pid)).fetchone()
        return dict(row) if row else None

    def open_photo_box(self, box_id: int, ts: float) -> None:
        """Notes that the box was opened to the end; the first time stays."""
        with self._lock:
            self._db.execute("UPDATE photo_boxes SET opened = ? WHERE id = ? AND opened = 0", (ts, box_id))
            self._commit()

    def prune_photo_boxes(self, before: float) -> int:
        """Deletes opened boxes bought before [before]; an unopened one is kept however old."""
        with self._lock:
            n = self._db.execute("DELETE FROM photo_boxes WHERE opened > 0 AND ts < ?", (before,)).rowcount
            self._commit()
            return n
