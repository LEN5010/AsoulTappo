"""Store methods of dou dizhu (斗地主): the games whose deposits were taken, and what each seat won or lost."""
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


class DdzStore(_StoreState):
    def add_ddz_game(self, players: list[str], base: int, deposit: int, day: str, ts: float) -> int:
        with self._lock:
            cur = self._db.execute("INSERT INTO ddz_games (base, deposit, day, ts) VALUES (?, ?, ?, ?)",
                                   (base, deposit, day, ts))
            self._db.executemany("INSERT INTO ddz_seats (game_id, seat, player_id, day) VALUES (?, ?, ?, ?)",
                                 [(cur.lastrowid, i, pid, day) for i, pid in enumerate(players)])
            self._commit()
            return cur.lastrowid

    def ddz_game(self, game_id: int) -> dict[str, Any] | None:
        """The game with its seats' saves in seat order as `players`."""
        with self._lock:
            row = self._db.execute("SELECT * FROM ddz_games WHERE id=?", (game_id,)).fetchone()
            seats = self._db.execute("SELECT player_id FROM ddz_seats WHERE game_id=? ORDER BY seat",
                                     (game_id,)).fetchall()
        return {**dict(row), "players": [s["player_id"] for s in seats]} if row else None

    def close_ddz_game(self, game_id: int, state: str, landlord: int, mult: int, burnt: int, ts: float) -> bool:
        """Moves an open game to [state]; False when it was closed already, so it is paid at most once."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE ddz_games SET state=?, landlord=?, mult=?, burnt=?, settled=? WHERE id=? AND state='open'",
                (state, landlord, mult, burnt, ts, game_id))
            self._commit()
            return cur.rowcount == 1

    def set_ddz_deltas(self, game_id: int, deltas: list[int]) -> None:
        with self._lock:
            self._db.executemany("UPDATE ddz_seats SET delta=? WHERE game_id=? AND seat=?",
                                 [(d, game_id, i) for i, d in enumerate(deltas)])
            self._commit()

    def open_ddz_games(self) -> list[int]:
        with self._lock:
            rows = self._db.execute("SELECT id FROM ddz_games WHERE state='open' ORDER BY id").fetchall()
        return [r["id"] for r in rows]

    def ddz_net(self, pid: str, day: str) -> int:
        """What the save won minus what it lost in the games settled with a winner that started on [day]; open and
        refunded games count nothing (their seats' deltas stay 0)."""
        with self._lock:
            return self._db.execute("SELECT COALESCE(SUM(delta), 0) FROM ddz_seats WHERE player_id=? AND day=?",
                                    (pid, day)).fetchone()[0]

    def ddz_winnings(self, starts_at: float, ends_at: float) -> list[dict[str, Any]]:
        """Each save's winnings from games settled in the period, after rake."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT s.player_id, l.main_user_id, SUM(s.delta) AS amount, 'ddz_win' AS source "
                "FROM ddz_games g JOIN ddz_seats s ON s.game_id = g.id "
                "LEFT JOIN account_links l ON l.player_id = s.player_id "
                "WHERE g.state = 'settled' AND g.settled >= ? AND g.settled < ? AND s.delta > 0 "
                "GROUP BY s.player_id", (starts_at, ends_at)).fetchall()
        return [dict(row) for row in rows]
