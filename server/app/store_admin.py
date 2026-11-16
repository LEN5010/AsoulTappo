"""Store methods for the admin pages: what tracking.py writes and what analytics.py reads back."""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any


class _StoreState:
    """What the mixins use of Store; Store sets them in __init__."""
    _db: sqlite3.Connection
    _lock: threading.RLock

    def _commit(self) -> None: ...


class AdminStore(_StoreState):
    # --- admin tracking (see tracking.py)
    def set_client(self, pid: str, version: str) -> bool:
        """Record the client version of save [pid]; False when there is no such save."""
        with self._lock:
            cur = self._db.execute("UPDATE players SET client_version=? WHERE id=?", (version, pid))
            self._commit()
            return cur.rowcount > 0

    def add_daily_counts(self, counts: dict[tuple[str, str], int]) -> None:
        with self._lock:
            self._db.executemany(
                "INSERT INTO daily_counts (day, key, count) VALUES (?, ?, ?) "
                "ON CONFLICT(day, key) DO UPDATE SET count = count + excluded.count",
                [(day, key, n) for (day, key), n in counts.items()])
            self._commit()

    def add_room_sample(self, ts: int, n: dict[str, int]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO room_samples (ts, rooms, members, saves, largest, public) VALUES (?,?,?,?,?,?)",
                (ts, n["rooms"], n["members"], n["saves"], n["largest"], n["public"]))
            self._commit()

    def save_rooms(self, rooms: list[dict[str, Any]], ts: float) -> None:
        """Replace the saved rooms with [rooms] (RoomManager.snapshot entries)."""
        with self._lock:
            self._db.execute("DELETE FROM room_restore")
            self._db.executemany(
                "INSERT INTO room_restore (room, public, host, banned, saved) VALUES (?,?,?,?,?)",
                [(r["room"], int(r["public"]), r["host"], json.dumps(r["banned"]), ts) for r in rooms])
            self._commit()

    def take_rooms(self) -> list[dict[str, Any]]:
        """The saved rooms, which are removed: each start reads them once."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM room_restore").fetchall()
            self._db.execute("DELETE FROM room_restore")
            self._commit()
        return [{"room": r["room"], "public": bool(r["public"]), "host": r["host"], "banned": json.loads(r["banned"]),
                 "saved": r["saved"]} for r in rows]

    def add_tap_flags(self, day: str, pid: str, dropped: int = 0, server: int = 0, client: int = 0,
                      steady: int = 0) -> None:
        """Adds to the save's flags of [day]; the caller's transaction, if any, keeps it with the change."""
        if not (dropped or server or client or steady):
            return
        with self._lock:
            self._db.execute(
                "INSERT INTO tap_flags (day, player_id, dropped, server_cooldowns, client_cooldowns, steady) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(day, player_id) DO UPDATE SET dropped = dropped + excluded.dropped, "
                "server_cooldowns = server_cooldowns + excluded.server_cooldowns, "
                "client_cooldowns = client_cooldowns + excluded.client_cooldowns, steady = steady + excluded.steady",
                (day, pid, dropped, server, client, steady))
            self._commit()

    def add_admin_log(self, ts: float, actor: str, action: str, pid: str = "", detail: str = "",
                      reason: str = "") -> None:
        """The caller's transaction, if any, keeps the entry with the change."""
        with self._lock:
            self._db.execute(
                "INSERT INTO admin_log (ts, actor, action, player_id, detail, reason) VALUES (?,?,?,?,?,?)",
                (ts, actor, action, pid, detail, reason))
            self._commit()

    def admin_log(self, pid: str | None, limit: int, before: int | None = None) -> list[dict[str, Any]]:
        """Newest first; [pid] narrows to one save, [before] continues below that entry id."""
        clauses, args = [], []
        if pid is not None:
            clauses.append("player_id = ?")
            args.append(pid)
        if before is not None:
            clauses.append("id < ?")
            args.append(before)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._db.execute(f"SELECT * FROM admin_log {where} ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()
        return [dict(r) for r in rows]

    # --- admin analysis (days are China Standard Time dates)
    def retention(self, since: str, offset_seconds: int, after: tuple[int, ...]) -> list[dict[str, Any]]:
        """Per creation day from [since]: new saves, and how many were active again [n] days later for n in [after]."""
        shift = f"{offset_seconds} seconds"
        back = ", ".join(
            f"SUM(EXISTS(SELECT 1 FROM daily_active a WHERE a.day = date(c.d, '+{n} day') AND a.player_id = c.id)) AS d{n}"
            for n in after)
        with self._lock:
            rows = self._db.execute(
                f"WITH c AS (SELECT id, date(created, 'unixepoch', ?) AS d FROM players) "
                f"SELECT d AS day, COUNT(*) AS size{', ' + back if back else ''} FROM c WHERE d >= ? GROUP BY d ORDER BY d",
                (shift, since)).fetchall()
        return [dict(r) for r in rows]

    def active_saves(self, since: str) -> list[dict[str, Any]]:
        """Saves active on a day from [since] on, with their client version."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, client_version FROM players "
                "WHERE id IN (SELECT DISTINCT player_id FROM daily_active WHERE day >= ?)", (since,)).fetchall()
        return [dict(r) for r in rows]

    def drops_by_day(self, since_ts: float, offset_seconds: int) -> list[dict[str, Any]]:
        """Per day and rarity: items drawn and how many of them were new."""
        with self._lock:
            rows = self._db.execute(
                "SELECT date(ts, 'unixepoch', ?) AS day, rarity, COUNT(*) AS count, SUM(is_new) AS new FROM drops "
                "WHERE ts >= ? GROUP BY day, rarity", (f"{offset_seconds} seconds", since_ts)).fetchall()
        return [dict(r) for r in rows]

    def room_samples(self, since_ts: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM room_samples WHERE ts >= ? ORDER BY ts", (since_ts,)).fetchall()
        return [dict(r) for r in rows]

    def daily_counts(self, since: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT day, key, count FROM daily_counts WHERE day >= ?", (since,)).fetchall()
        return [dict(r) for r in rows]

    def duels_by_day(self, since_ts: float, offset_seconds: int) -> list[dict[str, Any]]:
        """Duels closed from [since_ts], per day they closed, bet and outcome ('won', 'refunded'): how many."""
        with self._lock:
            rows = self._db.execute(
                # Aliased apart from the duels.day column (the day it opened), which GROUP BY would pick first.
                "SELECT date(settled, 'unixepoch', ?) AS ended, bet, state, COUNT(*) AS count FROM duels "
                "WHERE state != 'open' AND settled >= ? GROUP BY ended, bet, state",
                (f"{offset_seconds} seconds", since_ts)).fetchall()
        return [{"day": r["ended"], "bet": r["bet"], "state": r["state"], "count": r["count"]} for r in rows]

    def ledger_by_day(self, since: str, source: str) -> list[dict[str, Any]]:
        """Per day from [since]: the amount from [source] and how many saves it went to."""
        with self._lock:
            rows = self._db.execute(
                "SELECT day, SUM(amount) AS amount, SUM(count) AS count, COUNT(*) AS saves FROM shard_ledger "
                "WHERE day >= ? AND source = ? GROUP BY day", (since, source)).fetchall()
        return [dict(r) for r in rows]

    def tap_flags_of(self, day: str, limit: int) -> list[dict[str, Any]]:
        """The day's flagged saves, most steady-rate then fast-input cooldowns first, with their credited taps and
        tap shards."""
        with self._lock:
            rows = self._db.execute(
                "SELECT f.player_id, f.dropped, f.server_cooldowns, f.client_cooldowns, f.steady, "
                "COALESCE(g.count, 0) AS credited, COALESCE(g.amount, 0) AS shards, l.main_user_id "
                "FROM tap_flags f LEFT JOIN shard_ledger g ON g.day = f.day AND g.player_id = f.player_id "
                "AND g.source = 'tap' LEFT JOIN account_links l ON l.player_id = f.player_id WHERE f.day = ? "
                "ORDER BY f.steady DESC, f.server_cooldowns DESC, f.dropped DESC LIMIT ?", (day, limit)).fetchall()
        return [dict(r) for r in rows]

    def top_tappers(self, day: str, limit: int) -> list[dict[str, Any]]:
        """The day's saves with the most credited taps, with their flags and tap shards."""
        with self._lock:
            rows = self._db.execute(
                "SELECT g.player_id, g.count AS credited, g.amount AS shards, l.main_user_id, "
                "COALESCE(f.dropped, 0) AS dropped, COALESCE(f.server_cooldowns, 0) AS server_cooldowns, "
                "COALESCE(f.client_cooldowns, 0) AS client_cooldowns, COALESCE(f.steady, 0) AS steady FROM shard_ledger g "
                "LEFT JOIN tap_flags f ON f.day = g.day AND f.player_id = g.player_id "
                "LEFT JOIN account_links l ON l.player_id = g.player_id "
                "WHERE g.day = ? AND g.source = 'tap' ORDER BY g.count DESC LIMIT ?", (day, limit)).fetchall()
        return [dict(r) for r in rows]

    def ledger_day(self, day: str) -> list[dict[str, Any]]:
        """Every ledger row of [day], with the save's linked main-site user (None for a guest save)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT g.player_id, g.source, g.amount, g.count, l.main_user_id FROM shard_ledger g "
                "LEFT JOIN account_links l ON l.player_id = g.player_id WHERE g.day = ?", (day,)).fetchall()
        return [dict(r) for r in rows]
