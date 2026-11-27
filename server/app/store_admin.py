"""Store methods for the admin pages: what tracking.py writes and what analytics.py reads back."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import AbstractContextManager
from typing import Any


class _StoreState:
    """What the mixins use of Store; Store sets them in __init__."""
    _db: sqlite3.Connection
    _lock: threading.RLock

    def _invalidate_count(self, pid: str) -> None: ...

    def _commit(self) -> None: ...

    def _reading(self) -> AbstractContextManager[sqlite3.Connection]: ...


# Saves never used: no taps, no activity report, no main-site account, no nick and no loadout. A save made by a script
# that only spent its starter shards on draws looks like this (see AdminStore.unused_saves).
_UNUSED = ("created >= ? AND created < ? AND taps_total = 0 AND last_activity = 0 AND room_nick = '' AND loadout = '' "
           "AND NOT EXISTS (SELECT 1 FROM account_links l WHERE l.player_id = players.id)")
# A list of save ids passed as one JSON parameter, so its length is not bound by SQLite's parameter limit.
_IDS = "(SELECT value FROM json_each(?))"


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
        """Replace the saved rooms with [rooms] (RoomManager.snapshot entries), saved at [ts], or [age] seconds
        before it for an entry made before (carried over from the run before, or of a room that emptied), with how
        long it lasts ([keep])."""
        with self._lock:
            self._db.execute("DELETE FROM room_restore")
            self._db.executemany(
                "INSERT INTO room_restore (room, public, host, banned, saved, name, keep) VALUES (?,?,?,?,?,?,?)",
                [(r["room"], int(r["public"]), r["host"], json.dumps(r["banned"]), ts - r.get("age", 0.0), r["name"],
                  r.get("keep")) for r in rooms])
            self._commit()

    def take_rooms(self) -> list[dict[str, Any]]:
        """The saved rooms, which are removed: each start reads them once. "keep" only for a room saved with one."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM room_restore").fetchall()
            self._db.execute("DELETE FROM room_restore")
            self._commit()
        return [{"room": r["room"], "public": bool(r["public"]), "host": r["host"], "banned": json.loads(r["banned"]),
                 "saved": r["saved"], "name": r["name"], **({"keep": r["keep"]} if r["keep"] is not None else {})}
                for r in rows]

    def add_tap_flags(self, day: str, pid: str, dropped: int = 0, server: int = 0, client: int = 0,
                      auto: int = 0, injected: int = 0) -> None:
        """Adds to the save's flags of [day]; the caller's transaction, if any, keeps it with the change."""
        if not (dropped or server or client or auto or injected):
            return
        with self._lock:
            self._db.execute(
                "INSERT INTO tap_flags (day, player_id, dropped, server_cooldowns, client_cooldowns, auto, injected) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(day, player_id) DO UPDATE SET dropped = dropped + excluded.dropped, "
                "server_cooldowns = server_cooldowns + excluded.server_cooldowns, "
                "client_cooldowns = client_cooldowns + excluded.client_cooldowns, auto = auto + excluded.auto, "
                "injected = injected + excluded.injected",
                (day, pid, dropped, server, client, auto, injected))
            self._commit()

    def has_tap_hold(self, pid: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM tap_holds WHERE player_id=?", (pid,)).fetchone() is not None

    def set_tap_hold(self, pid: str, since: float, actor: str, reason: str) -> bool:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO tap_holds (player_id, since, actor, reason) VALUES (?,?,?,?) "
                "ON CONFLICT(player_id) DO NOTHING", (pid, since, actor, reason))
            self._commit()
            return cur.rowcount > 0

    def remove_tap_hold(self, pid: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM tap_holds WHERE player_id=?", (pid,))
            self._commit()
            return cur.rowcount > 0

    def tap_holds(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT player_id AS player, since, actor, reason FROM tap_holds ORDER BY since DESC, player_id"
            ).fetchall()
        return [dict(r) for r in rows]

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

    # --- admin repairs (Game.admin_reset_save, admin_grant_all, admin_empty_saves); each runs in the caller's
    # transaction, so the change and its admin log entry land together.
    def reset_collection(self, pid: str) -> tuple[int, int]:
        """Deletes the save's items and limited pool draws and zeroes its pity, the photocards' included; a photocard
        box not opened yet counts as opened. Returns the rows deleted from items and from banner_draws."""
        with self._lock:
            items = self._db.execute("DELETE FROM items WHERE player_id=?", (pid,)).rowcount
            pools = self._db.execute("DELETE FROM banner_draws WHERE player_id=?", (pid,)).rowcount
            self._db.execute("UPDATE players SET draw_pity=0, skin_pity=0 WHERE id=?", (pid,))
            self._db.execute("DELETE FROM photo_saves WHERE player_id=?", (pid,))
            self._db.execute("UPDATE photo_boxes SET opened=ts WHERE player_id=? AND opened=0", (pid,))
            self._invalidate_count(pid)
            self._commit()
        return items, pools

    def grant_all(self, day: str, shards: int, exclude: list[str], min_taps: int, name: str, ts: float,
                  dry_run: bool = False) -> tuple[int, int] | None:
        """Adds [shards] to every save with at least [min_taps] taps that is not in [exclude], each with an 'admin'
        ledger row of [day], and records [name] in migrations so the same grant is never given twice. None when [name]
        was given before. Returns the saves given to and how many of [exclude] are existing saves; [dry_run] counts
        them and writes nothing, [name] included."""
        excluded = json.dumps(sorted(set(exclude)))
        given = f"id NOT IN {_IDS} AND taps_total >= ?"
        with self._lock:
            if self._db.execute("SELECT 1 FROM migrations WHERE name=?", (name,)).fetchone():
                return None
            skipped = self._db.execute(f"SELECT COUNT(*) FROM players WHERE id IN {_IDS}", (excluded,)).fetchone()[0]
            if dry_run:
                saves = self._db.execute(f"SELECT COUNT(*) FROM players WHERE {given}",
                                         (excluded, min_taps)).fetchone()[0]
                return saves, skipped
            saves = self._db.execute(f"UPDATE players SET shards = shards + ? WHERE {given}",
                                     (shards, excluded, min_taps)).rowcount
            # The WHERE keeps SQLite from reading ON CONFLICT as part of the SELECT's join.
            self._db.execute(
                f"INSERT INTO shard_ledger (day, player_id, source, amount, count) "
                f"SELECT ?, id, 'admin', ?, 1 FROM players WHERE {given} "
                f"ON CONFLICT(day, player_id, source) DO UPDATE SET "
                f"amount = amount + excluded.amount, count = count + excluded.count", (day, shards, excluded, min_taps))
            self._db.execute("INSERT INTO migrations (name, at) VALUES (?, ?)", (name, ts))
            self._commit()
        return saves, skipped

    @staticmethod
    def _unused_where(created_from: float, created_to: float, shards: int | None,
                      drawn: int | None) -> tuple[str, tuple[Any, ...]]:
        """_UNUSED narrowed to exactly [shards] held and [drawn] draws made, where given."""
        where, args = _UNUSED, (created_from, created_to)
        if shards is not None:
            where, args = f"{where} AND shards = ?", (*args, shards)
        if drawn is not None:
            where, args = f"{where} AND drawn_total = ?", (*args, drawn)
        return where, args

    def unused_saves(self, created_from: float, created_to: float, shards: int | None = None,
                     drawn: int | None = None) -> list[str]:
        """Saves created in [created_from, created_to) that were never used (see _UNUSED), holding exactly [shards]
        and having drawn exactly [drawn] times where those are given."""
        where, args = self._unused_where(created_from, created_to, shards, drawn)
        with self._lock:
            rows = self._db.execute(f"SELECT id FROM players WHERE {where} ORDER BY id", args).fetchall()
        return [r[0] for r in rows]

    def unused_groups(self, created_from: float, created_to: float, shards: int | None = None,
                      drawn: int | None = None, limit: int = 10) -> list[dict[str, int]]:
        """The most common (shards, draws made) pairs among the saves unused_saves picks, with how many saves each:
        one batch made by a script shows as one large group, real players as many small ones."""
        where, args = self._unused_where(created_from, created_to, shards, drawn)
        with self._lock:
            rows = self._db.execute(
                f"SELECT shards, drawn_total, COUNT(*) AS n FROM players WHERE {where} "
                f"GROUP BY shards, drawn_total ORDER BY n DESC, shards, drawn_total LIMIT ?", (*args, limit)).fetchall()
        return [{"shards": r[0], "drawn": r[1], "saves": r[2]} for r in rows]

    def ledger_totals(self, pids: list[str]) -> dict[str, dict[str, int]]:
        """The shard ledger of the saves [pids] summed per source: {source: {amount, count}}."""
        with self._lock:
            rows = self._db.execute(
                f"SELECT source, SUM(amount), SUM(count) FROM shard_ledger WHERE player_id IN {_IDS} "
                f"GROUP BY source ORDER BY source", (json.dumps(pids),)).fetchall()
        return {r[0]: {"amount": r[1], "count": r[2]} for r in rows}

    def empty_saves(self, pids: list[str]) -> dict[str, Any]:
        """Deletes the items, drops, limited pool draws, photocard boxes and ledger rows of the saves [pids] and zeroes
        their shards and pity. The save rows stay, and so do their update reward claims, so a token cannot claim a
        reward again. Returns the shards zeroed (shardsZeroed) and the rows deleted per table."""
        ids = json.dumps(pids)
        with self._lock:
            shards = self._db.execute(f"SELECT COALESCE(SUM(shards), 0) FROM players WHERE id IN {_IDS}",
                                      (ids,)).fetchone()[0]
            deleted = {key: self._db.execute(f"DELETE FROM {table} WHERE player_id IN {_IDS}", (ids,)).rowcount
                       for key, table in (("items", "items"), ("drops", "drops"), ("bannerDraws", "banner_draws"),
                                          ("photoBoxes", "photo_boxes"), ("photoSaves", "photo_saves"),
                                          ("shardLedger", "shard_ledger"))}
            self._db.execute(f"UPDATE players SET shards=0, draw_pity=0, skin_pity=0 WHERE id IN {_IDS}", (ids,))
            for pid in pids:
                self._invalidate_count(pid)
            self._commit()
        return {"shardsZeroed": shards, "deleted": deleted}

    # --- admin analysis (days are China Standard Time dates)
    def retention(self, since: str, offset_seconds: int, after: tuple[int, ...]) -> list[dict[str, Any]]:
        """Per creation day from [since]: new saves, and how many were active again [n] days later for n in [after]."""
        shift = f"{offset_seconds} seconds"
        back = ", ".join(
            f"SUM(EXISTS(SELECT 1 FROM daily_active a WHERE a.day = date(c.d, '+{n} day') AND a.player_id = c.id)) AS d{n}"
            for n in after)
        with self._reading() as db:
            rows = db.execute(
                f"WITH c AS (SELECT id, date(created, 'unixepoch', ?) AS d FROM players) "
                f"SELECT d AS day, COUNT(*) AS size{', ' + back if back else ''} FROM c WHERE d >= ? GROUP BY d ORDER BY d",
                (shift, since)).fetchall()
        return [dict(r) for r in rows]

    def active_saves(self, since: str) -> list[dict[str, Any]]:
        """Saves active on a day from [since] on, with their client version."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT id, client_version FROM players "
                "WHERE id IN (SELECT DISTINCT player_id FROM daily_active WHERE day >= ?)", (since,)).fetchall()
        return [dict(r) for r in rows]

    def drops_by_day(self, since_ts: float, offset_seconds: int) -> list[dict[str, Any]]:
        """Per day and rarity: items drawn and how many of them were new."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT date(ts, 'unixepoch', ?) AS day, rarity, COUNT(*) AS count, SUM(is_new) AS new FROM drops "
                "WHERE ts >= ? GROUP BY day, rarity", (f"{offset_seconds} seconds", since_ts)).fetchall()
        return [dict(r) for r in rows]

    def room_samples(self, since_ts: int) -> list[dict[str, Any]]:
        with self._reading() as db:
            rows = db.execute("SELECT * FROM room_samples WHERE ts >= ? ORDER BY ts", (since_ts,)).fetchall()
        return [dict(r) for r in rows]

    def daily_counts(self, since: str) -> list[dict[str, Any]]:
        with self._reading() as db:
            rows = db.execute("SELECT day, key, count FROM daily_counts WHERE day >= ?", (since,)).fetchall()
        return [dict(r) for r in rows]

    def duels_by_day(self, since_ts: float, offset_seconds: int) -> list[dict[str, Any]]:
        """Duels closed from [since_ts], per day they closed, bet and outcome ('won', 'refunded'): how many."""
        with self._reading() as db:
            rows = db.execute(
                # Aliased apart from the duels.day column (the day it opened), which GROUP BY would pick first.
                "SELECT date(settled, 'unixepoch', ?) AS ended, bet, state, COUNT(*) AS count FROM duels "
                "WHERE state != 'open' AND settled >= ? GROUP BY ended, bet, state",
                (f"{offset_seconds} seconds", since_ts)).fetchall()
        return [{"day": r["ended"], "bet": r["bet"], "state": r["state"], "count": r["count"]} for r in rows]

    def ledger_by_day(self, since: str, source: str) -> list[dict[str, Any]]:
        """Per day from [since]: the amount from [source] and how many saves it went to."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT day, SUM(amount) AS amount, SUM(count) AS count, COUNT(*) AS saves FROM shard_ledger "
                "WHERE day >= ? AND source = ? GROUP BY day", (since, source)).fetchall()
        return [dict(r) for r in rows]

    def tap_flags_of(self, day: str, limit: int) -> list[dict[str, Any]]:
        """The day's flagged saves, most often judged automatic (or, before the guard, cooled down for a steady rate)
        then fast-input cooldowns first, with their credited taps and tap shards."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT f.player_id, f.dropped, f.server_cooldowns, f.client_cooldowns, f.steady, f.auto, f.injected, "
                "COALESCE(g.count, 0) AS credited, COALESCE(g.amount, 0) AS shards, l.main_user_id "
                "FROM tap_flags f LEFT JOIN shard_ledger g ON g.day = f.day AND g.player_id = f.player_id "
                "AND g.source = 'tap' LEFT JOIN account_links l ON l.player_id = f.player_id WHERE f.day = ? "
                "ORDER BY f.auto + f.steady DESC, f.server_cooldowns DESC, f.dropped DESC LIMIT ?", (day, limit)).fetchall()
        return [dict(r) for r in rows]

    def top_tappers(self, day: str, limit: int) -> list[dict[str, Any]]:
        """The day's saves with the most credited taps, with their flags and tap shards."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT g.player_id, g.count AS credited, g.amount AS shards, l.main_user_id, "
                "COALESCE(f.dropped, 0) AS dropped, COALESCE(f.server_cooldowns, 0) AS server_cooldowns, "
                "COALESCE(f.client_cooldowns, 0) AS client_cooldowns, COALESCE(f.steady, 0) AS steady, "
                "COALESCE(f.auto, 0) AS auto, COALESCE(f.injected, 0) AS injected FROM shard_ledger g "
                "LEFT JOIN tap_flags f ON f.day = g.day AND f.player_id = g.player_id "
                "LEFT JOIN account_links l ON l.player_id = g.player_id "
                "WHERE g.day = ? AND g.source = 'tap' ORDER BY g.count DESC LIMIT ?", (day, limit)).fetchall()
        return [dict(r) for r in rows]

    def ledger_day(self, day: str) -> list[dict[str, Any]]:
        """Every ledger row of [day], with the save's linked main-site user (None for a guest save)."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT g.player_id, g.source, g.amount, g.count, l.main_user_id FROM shard_ledger g "
                "LEFT JOIN account_links l ON l.player_id = g.player_id WHERE g.day = ?", (day,)).fetchall()
        return [dict(r) for r in rows]
