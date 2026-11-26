"""SQLite persistence for players, their item collection, presets and the drop log (stdlib only)."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator

from .store_admin import AdminStore
from .store_ddz import DdzStore
from .store_feedback import FeedbackStore
from .store_park import ParkStore
from .store_photo import PhotoStore

from .store_schema import SCHEMA  # noqa: F401 (tests import it from here)

STARTER_SHARDS = 1600
# Statistics count days in China Standard Time.
DAY_OFFSET = 8 * 3600
# Saves whose collectible count is remembered (see Store.count_items); the cache starts over when full.
COUNT_CACHE_LIMIT = 20000

PLAYER_FIELDS = (
    "id created taps_total active_minutes last_activity minute_bucket minute_taps minute_counted frame badge "
    "shards loadout draw_pity drawn_total presence_last skin_pity last_minute_taps shard_remainder "
    "boost_day boost_used tap_cooldown_until tap_day day_taps day_taps_total scratch_pity "
    "auto_until auto_strike_day auto_strikes coins gift_day stamps_total ddz_counter"
).split()


def day_of(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts + DAY_OFFSET))


class Store(AdminStore, ParkStore, DdzStore, FeedbackStore, PhotoStore):
    """Thread-safe wrapper around one sqlite3 connection (":memory:" for tests)."""

    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            d = os.path.dirname(os.path.abspath(path))
            os.makedirs(d, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        # Saves marked active on `_active_day`, and collectible counts per save: both are read on every
        # status call and change rarely. Every write goes through this class, which keeps them current;
        # a rollback drops them (see _Tx).
        self._active_day = ""
        self._active: set[str] = set()
        self._counts: dict[str, tuple[frozenset[str], int]] = {}
        with self._lock:
            if path != ":memory:":
                # WAL: a commit appends to the log without rewriting and syncing the database file, and
                # readers of other connections (backups, sqlite3 on the host) do not block the writer.
                # NORMAL syncs at checkpoints only: after a power cut the last commits may be missing,
                # the database stays consistent. The mode is stored in the file; older builds keep using it.
                self._db.execute("PRAGMA journal_mode=WAL")
                self._db.execute("PRAGMA synchronous=NORMAL")
            self._drop_old_races()
            self._db.executescript(SCHEMA)
            self._migrate()
        # The admin pages' whole-table reads run on a connection of their own: in WAL mode a reader neither waits
        # for the writer nor holds it up, so a slow statistic no longer stalls every player request behind _lock.
        # It sees committed data only. ":memory:" databases are private to their connection and keep using _db.
        self._reader: sqlite3.Connection | None = None
        self._read_lock = threading.Lock()
        if path != ":memory:":
            self._reader = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            self._reader.row_factory = sqlite3.Row
            self._reader.execute("PRAGMA query_only=ON")

    @contextmanager
    def _reading(self) -> Iterator[sqlite3.Connection]:
        """The connection for the admin pages' statistics. Each use is one read transaction, so a method that runs
        several queries reads one snapshot, as it did under _lock."""
        if self._reader is None:
            with self._lock:
                yield self._db
            return
        with self._read_lock:
            self._reader.execute("BEGIN")
            try:
                yield self._reader
            finally:
                self._reader.execute("COMMIT")

    def _columns(self, table: str) -> set[str]:
        return {r[1] for r in self._db.execute(f"PRAGMA table_info({table})")}

    def _drop_old_races(self) -> None:
        """Drops the race tables of the park's test builds (odds from sims, one bet row per selection); the park was
        never deployed with them. SCHEMA then makes them anew."""
        races = self._columns("park_races")
        bets = self._columns("park_race_bets")
        if (races and "slow_ms" not in races) or (bets and "id" not in bets):
            self._db.execute("DROP TABLE IF EXISTS park_race_bets")
            self._db.execute("DROP TABLE IF EXISTS park_races")
            self._db.commit()

    def _migrate(self) -> None:
        """Bring databases created by older versions up to the current schema."""
        with self._db:
            # Keep schema additions and their initial values in the same transaction.
            self._db.execute("BEGIN")
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
            # Daily tap statistics include every credited tap, including those beyond the income cap.
            if "day_taps_total" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN day_taps_total INTEGER NOT NULL DEFAULT 0")
                self._db.execute("UPDATE players SET day_taps_total = day_taps")
            # Scratch cards bought since the last one that gave an emote.
            if "scratch_pity" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN scratch_pity INTEGER NOT NULL DEFAULT 0")
            # The nick the save last used in a room ("" for the default one): the board's nick for clients
            # before 1.2.0, which do not send one with the loadout.
            if "room_nick" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN room_nick TEXT NOT NULL DEFAULT ''")
            # The client version the save last ran ("other" when not a version).
            if "client_version" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN client_version TEXT NOT NULL DEFAULT ''")
            # Until when the save's input counts as automatic (app/guard.py). The steady_* columns of older
            # databases belonged to a rule the guard replaced and are no longer read.
            if "auto_until" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN auto_until REAL NOT NULL DEFAULT 0")
            # Cooldowns the guard gave on one China day for keeping automatic input on.
            for field, kind in (("auto_strike_day", "TEXT NOT NULL DEFAULT ''"),
                                ("auto_strikes", "INTEGER NOT NULL DEFAULT 0")):
                if field not in players:
                    self._db.execute(f"ALTER TABLE players ADD COLUMN {field} {kind}")
            # Park coins: held, the day of the last free one, and stamps ever earned.
            for field, kind in (("coins", "INTEGER NOT NULL DEFAULT 0"), ("gift_day", "TEXT NOT NULL DEFAULT ''"),
                                ("stamps_total", "INTEGER NOT NULL DEFAULT 0")):
                if field not in players:
                    self._db.execute(f"ALTER TABLE players ADD COLUMN {field} {kind}")
            # Dou dizhu: games of the card counter the save has left.
            if "ddz_counter" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN ddz_counter INTEGER NOT NULL DEFAULT 0")
            flags = self._columns("tap_flags")
            for field in ("steady", "auto", "injected"):
                if field not in flags:
                    self._db.execute(f"ALTER TABLE tap_flags ADD COLUMN {field} INTEGER NOT NULL DEFAULT 0")
            sessions = self._columns("activity_sessions")
            for field in ("last_at", "fast_since"):
                if field not in sessions:
                    self._db.execute(f"ALTER TABLE activity_sessions ADD COLUMN {field} REAL NOT NULL DEFAULT 0")
            # The guard's notes on the session, JSON. The rate, steady, odd and near columns of older databases
            # belonged to a rule the guard replaced and are no longer read.
            if "guard" not in sessions:
                self._db.execute("ALTER TABLE activity_sessions ADD COLUMN guard TEXT NOT NULL DEFAULT ''")
            # The names of rooms, which the table left out before: each restart brought its rooms back unnamed.
            if "name" not in self._columns("room_restore"):
                self._db.execute("ALTER TABLE room_restore ADD COLUMN name TEXT NOT NULL DEFAULT ''")
            # v1 stored bare card ids in `cards`; items are namespaced (card:<id>)
            if self._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cards'").fetchone():
                self._db.execute(
                    "INSERT OR IGNORE INTO items (player_id, item_id, count, first_ts) "
                    "SELECT player_id, 'card:' || card_id, count, first_ts FROM cards")
                self._db.execute("DROP TABLE cards")
            if "card_id" in self._columns("drops"):
                self._db.execute("ALTER TABLE drops RENAME COLUMN card_id TO item_id")
                self._db.execute("UPDATE drops SET item_id = 'card:' || item_id WHERE instr(item_id, ':') = 0")
            for field in ("source", "pool"):
                if field not in self._columns("drops"):
                    self._db.execute(f"ALTER TABLE drops ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
            # Filled from the drop log once (fill_banner_guarantees), since the game knows the featured items.
            if "guaranteed" not in self._columns("banner_draws"):
                self._db.execute("ALTER TABLE banner_draws ADD COLUMN guaranteed TEXT NOT NULL DEFAULT ''")

    def _commit(self) -> None:
        if not getattr(self, "_in_tx", False):
            self._db.commit()

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def probe(self) -> float:
        """Time the lock wait and a quick read to detect stalls in player requests."""
        started = time.monotonic()
        with self._lock:
            self._db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        return round(time.monotonic() - started, 3)

    def transaction(self):
        """Context manager: holds the lock and commits/rolls back."""
        return _Tx(self)

    # --- players
    def get_player(self, pid: str, now: float) -> dict[str, Any]:
        with self._lock:
            row = self._db.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
            if row is None:
                self._db.execute("INSERT INTO players (id, created, shards) VALUES (?, ?, ?)", (pid, now, STARTER_SHARDS))
                self.add_ledger(pid, day_of(now), "starter", STARTER_SHARDS)
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

    def activity_session(self, pid: str, session: str) -> dict[str, Any]:
        """The session's last batch: its sequence, when it came, since when it has been too fast, and the guard's
        notes (JSON, "" for none)."""
        with self._lock:
            row = self._db.execute(
                "SELECT sequence, last_at, fast_since, guard FROM activity_sessions "
                "WHERE player_id=? AND session=?", (pid, session)).fetchone()
            return dict(row) if row else {"sequence": 0, "last_at": 0.0, "fast_since": 0.0, "guard": ""}

    def save_activity_sequence(self, pid: str, session: str, sequence: int, last_at: float = 0.0,
                               fast_since: float = 0.0, guard: str = "") -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO activity_sessions (player_id, session, sequence, last_at, fast_since, guard) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(player_id, session) DO UPDATE SET "
                "sequence=excluded.sequence, last_at=excluded.last_at, fast_since=excluded.fast_since, "
                "guard=excluded.guard",
                (pid, session, sequence, last_at, fast_since, guard))
            self._commit()

    def guard_day(self, pid: str, day: str) -> str:
        with self._lock:
            row = self._db.execute("SELECT notes FROM guard_days WHERE day=? AND player_id=?", (day, pid)).fetchone()
            return row[0] if row else "{}"

    def save_guard_day(self, pid: str, day: str, notes: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO guard_days (day,player_id,notes) VALUES (?,?,?) "
                             "ON CONFLICT(day,player_id) DO UPDATE SET notes=excluded.notes", (day, pid, notes))
            self._commit()

    def prune_activity_sessions(self, before: float) -> int:
        """Delete sessions last seen before [before]; rows from before last_at existed hold 0 and go too."""
        with self._lock:
            self._db.execute("DELETE FROM guard_days WHERE day < ?", (day_of(before),))
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

    # --- update rewards
    def open_update_rewards(self, pid: str) -> list[dict[str, Any]]:
        """Rewards not ended that [pid] has not claimed, oldest first. A reward is for the saves that were there
        when it opened; a save made later has no earlier version to update from and is offered none."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, version, shards FROM update_rewards r WHERE ended IS NULL "
                "AND created >= (SELECT created FROM players WHERE id = ?) AND NOT EXISTS "
                "(SELECT 1 FROM update_reward_claims c WHERE c.reward_id = r.id AND c.player_id = ?) ORDER BY id",
                (pid, pid)).fetchall()
        return [dict(r) for r in rows]

    def add_update_claim(self, reward_id: int, pid: str, ts: float) -> None:
        with self._lock:
            self._db.execute("INSERT INTO update_reward_claims (reward_id, player_id, at) VALUES (?, ?, ?)",
                             (reward_id, pid, ts))
            self._commit()

    def update_rewards(self) -> list[dict[str, Any]]:
        """Every reward, newest first, with how many saves claimed it."""
        with self._lock:
            rows = self._db.execute(
                "SELECT r.id, r.version, r.shards, r.created, r.ended, COUNT(c.player_id) AS claims "
                "FROM update_rewards r LEFT JOIN update_reward_claims c ON c.reward_id = r.id "
                "GROUP BY r.id ORDER BY r.id DESC").fetchall()
        return [dict(r) for r in rows]

    def add_update_reward(self, version: str, shards: int, ts: float) -> int:
        with self._lock:
            cur = self._db.execute("INSERT INTO update_rewards (version, shards, created) VALUES (?, ?, ?)",
                                   (version, shards, ts))
            self._commit()
            return int(cur.lastrowid)

    def end_update_reward(self, reward_id: int, ts: float) -> bool:
        """Ends a reward still open; False when there is none by that id or it has ended."""
        with self._lock:
            cur = self._db.execute("UPDATE update_rewards SET ended = ? WHERE id = ? AND ended IS NULL", (ts, reward_id))
            self._commit()
            return cur.rowcount > 0

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
            # `+state` keeps the planner off duels_state, which would walk every duel ever won; the two
            # day indexes (duels_a, duels_b) find this save's few rows of the day.
            return self._db.execute(
                "SELECT COALESCE(SUM(CASE WHEN winner=? THEN prize - bet ELSE -bet END), 0) FROM duels "
                "WHERE ((a=? AND day=?) OR (b=? AND day=?)) AND +state='won'", (pid, pid, day, pid, day)).fetchone()[0]

    # --- daily statistics (days are China Standard Time dates, YYYY-MM-DD)
    def mark_active(self, pid: str, day: str) -> None:
        with self._lock:
            if day != self._active_day:
                self._active_day, self._active = day, set()
            elif pid in self._active:
                # Heartbeats and activity reports repeat this all day; the row is there after the first.
                return
            self._db.execute("INSERT OR IGNORE INTO daily_active (day, player_id) VALUES (?, ?)", (day, pid))
            self._commit()
            self._active.add(pid)

    def totals(self, today: str) -> dict[str, int]:
        with self._reading() as db:
            one = lambda sql, *a: db.execute(sql, a).fetchone()[0]  # noqa: E731
            return {"saves": one("SELECT COUNT(*) FROM players"),
                    "linked": one("SELECT COUNT(*) FROM account_links"),
                    "activeToday": one("SELECT COUNT(*) FROM daily_active WHERE day=?", today)}

    def daily(self, since: str, offset_seconds: int) -> dict[str, dict[str, int]]:
        """Per day since [since]: active saves, new saves and items obtained."""
        shift = f"{offset_seconds} seconds"
        out: dict[str, dict[str, int]] = {}
        with self._reading() as db:
            queries = {
                "active": ("SELECT day, COUNT(*) FROM daily_active WHERE day >= ? GROUP BY day", (since,)),
                "newSaves": ("SELECT date(created, 'unixepoch', ?) d, COUNT(*) FROM players GROUP BY d HAVING d >= ?", (shift, since)),
                "items": ("SELECT date(ts, 'unixepoch', ?) d, COUNT(*) FROM drops GROUP BY d HAVING d >= ?", (shift, since)),
            }
            for key, (sql, args) in queries.items():
                for day, n in db.execute(sql, args).fetchall():
                    out.setdefault(day, {})[key] = n
        return out

    # --- shard ledger (days are China Standard Time dates, YYYY-MM-DD)
    def add_ledger(self, pid: str, day: str, source: str, amount: int, count: int = 1) -> None:
        """Adds to the save's [source] row of [day]; the caller's transaction, if any, keeps it with the change."""
        with self._lock:
            self._db.execute(
                "INSERT INTO shard_ledger (day, player_id, source, amount, count) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(day, player_id, source) DO UPDATE SET "
                "amount = amount + excluded.amount, count = count + excluded.count",
                (day, pid, source, amount, count))
            self._commit()

    # --- boards
    def card_counts(self, cards: list[str], big: list[str]) -> list[dict[str, Any]]:
        """Per save holding any of [cards] (item ids): how many, how many of [big], and when the last came."""
        if not cards:
            return []
        marks = ",".join("?" * len(cards))
        big_marks = ",".join("?" * len(big)) or "''"
        with self._reading() as db:
            rows = db.execute(
                f"SELECT player_id, COUNT(*) AS cards, SUM(item_id IN ({big_marks})) AS big, MAX(first_ts) AS last "
                f"FROM items WHERE count > 0 AND item_id IN ({marks}) GROUP BY player_id", (*big, *cards)).fetchall()
        return [dict(r) for r in rows]

    def held_items(self, linked: bool = False) -> list[tuple[str, str, float]]:
        """(player id, item id, when it first came) of every item a save holds; with [linked], only of the saves
        bound to a main-site account, so the read does not grow with saves that are never listed. The collection
        board's scan: it reads committed rows on the statistics connection (_reading), so player requests do not
        wait for it, and Game.board calls it outside any transaction."""
        only = " AND player_id IN (SELECT player_id FROM account_links)" if linked else ""
        with self._reading() as db:
            rows = db.execute(f"SELECT player_id, item_id, first_ts FROM items WHERE count > 0{only}").fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def set_room_nick(self, pid: str, nick: str) -> None:
        """Remember the nick an existing save uses in rooms; nothing happens for a token without a save."""
        with self._lock:
            self._db.execute("UPDATE players SET room_nick=? WHERE id=? AND room_nick != ?", (nick, pid, nick))
            self._commit()

    def room_nicks(self, pids: list[str]) -> dict[str, str]:
        """The non-empty room nick of each save among [pids]."""
        out: dict[str, str] = {}
        with self._lock:
            for i in range(0, len(pids), 500):
                chunk = pids[i:i + 500]
                rows = self._db.execute(f"SELECT id, room_nick FROM players WHERE room_nick != '' AND id IN "
                                        f"({','.join('?' * len(chunk))})", chunk).fetchall()
                out.update({r["id"]: r["room_nick"] for r in rows})
        return out

    def loadouts(self, pids: list[str]) -> dict[str, str]:
        """The stored loadout text of each existing save among [pids]."""
        out: dict[str, str] = {}
        with self._lock:
            for i in range(0, len(pids), 500):
                chunk = pids[i:i + 500]
                rows = self._db.execute(
                    f"SELECT id, loadout FROM players WHERE id IN ({','.join('?' * len(chunk))})", chunk).fetchall()
                out.update({r["id"]: r["loadout"] for r in rows})
        return out

    def linked_players(self) -> set[str]:
        with self._lock:
            return {r["player_id"] for r in self._db.execute("SELECT player_id FROM account_links")}

    def ledger_amount(self, pid: str, day: str, source: str) -> int:
        """The save's ledger amount from [source] on [day]; 0 without a row."""
        with self._lock:
            row = self._db.execute("SELECT amount FROM shard_ledger WHERE day=? AND player_id=? AND source=?",
                                   (day, pid, source)).fetchone()
        return row["amount"] if row else 0

    def ledger_since(self, since: str) -> list[dict[str, Any]]:
        """Every ledger row from [since] on, with the save's creation time (None when the save is gone)."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT g.day, g.player_id, g.source, g.amount, g.count, p.created FROM shard_ledger g "
                "LEFT JOIN players p ON p.id = g.player_id WHERE g.day >= ?", (since,)).fetchall()
        return [dict(r) for r in rows]

    def ledger_of(self, pid: str, days: list[str]) -> list[dict[str, Any]]:
        """One save's ledger rows on [days]; the day list keeps the lookup on the primary key."""
        if not days:
            return []
        with self._lock:
            rows = self._db.execute(
                f"SELECT day, source, amount, count FROM shard_ledger "
                f"WHERE day IN ({','.join('?' for _ in days)}) AND player_id=?", (*days, pid)).fetchall()
        return [dict(r) for r in rows]

    def find_saves(self, prefix: str | None, main_user_id: str, limit: int) -> list[dict[str, Any]]:
        """Saves whose id starts with [prefix] (lowercase hex) or that are linked to [main_user_id], most
        recently active first. Rows are player rows plus `main_user_id` (None for guest saves)."""
        clauses, args = ["p.id IN (SELECT player_id FROM account_links WHERE main_user_id=?)"], [main_user_id]
        if prefix:
            # A range on the primary key; '~' sorts after every hex digit.
            clauses.append("(p.id >= ? AND p.id < ?)")
            args += [prefix, prefix + "~"]
        with self._lock:
            rows = self._db.execute(
                f"SELECT p.*, l.main_user_id FROM players p LEFT JOIN account_links l ON l.player_id = p.id "
                f"WHERE {' OR '.join(clauses)} "
                f"ORDER BY COALESCE(NULLIF(p.last_activity, 0), p.created) DESC LIMIT ?", (*args, limit)).fetchall()
        return [dict(r) for r in rows]

    def owned(self, pid: str) -> dict[str, int]:
        with self._lock:
            rows = self._db.execute("SELECT item_id, count FROM items WHERE player_id=?", (pid,)).fetchall()
        return {r["item_id"]: r["count"] for r in rows}

    def count_items(self, pid: str, item_ids: frozenset[str]) -> int:
        if not item_ids:
            return 0
        with self._lock:
            hit = self._counts.get(pid)
            if hit is not None and hit[0] is item_ids:
                return hit[1]
            # Walk this player's covering index once. A large IN list probes the index once per
            # collectible, including the hundreds a new player has yet to collect.
            rows = self._db.execute("SELECT item_id FROM items WHERE player_id=?", (pid,))
            count = sum(row[0] in item_ids for row in rows)
            if len(self._counts) >= COUNT_CACHE_LIMIT:
                self._counts.clear()
            self._counts[pid] = (item_ids, count)
            return count

    def has_item(self, pid: str, item_id: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM items WHERE player_id=? AND item_id=?",
                                    (pid, item_id)).fetchone() is not None

    def add_item(self, pid: str, item_id: str, now: float) -> int:
        """Increment the owned count; returns the new count."""
        with self._lock:
            self._db.execute(
                "INSERT INTO items (player_id, item_id, count, first_ts) VALUES (?,?,1,?) "
                "ON CONFLICT(player_id, item_id) DO UPDATE SET count = count + 1",
                (pid, item_id, now))
            self._counts.pop(pid, None)
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
            self._counts.pop(pid, None)
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

    def banner_draws(self, pid: str) -> dict[str, dict[str, Any]]:
        """banner id -> {pity, drawn, guaranteed} for every limited pool the save drew from; `guaranteed` is a sorted
        list of tiers."""
        with self._lock:
            rows = self._db.execute(
                "SELECT banner, pity, drawn, guaranteed FROM banner_draws WHERE player_id=?", (pid,)).fetchall()
        return {r["banner"]: {"pity": r["pity"], "drawn": r["drawn"],
                              "guaranteed": sorted(t for t in r["guaranteed"].split(",") if t)} for r in rows}

    def save_banner_draws(self, pid: str, banner: str, pity: int, drawn: int, guaranteed: Iterable[str] = ()) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO banner_draws (player_id, banner, pity, drawn, guaranteed) VALUES (?,?,?,?,?) "
                "ON CONFLICT(player_id, banner) DO UPDATE SET pity=excluded.pity, drawn=excluded.drawn, "
                "guaranteed=excluded.guaranteed",
                (pid, banner, pity, drawn, ",".join(sorted(set(guaranteed)))))
            self._commit()

    def fill_banner_guarantees(self, name: str, featured: dict[str, dict[str, frozenset[str]]], now: float) -> int:
        """Once per database (recorded as `name`): marks the shared tiers each save's next draw in a limited pool
        guarantees, for draws made before the guarantee was kept. [featured]: banner id -> tier -> the featured items
        of that tier. A tier is marked when the save's last drop of it from the pool was not featured and the save
        still lacks a featured item of it. Returns the saves marked."""
        with self._lock:
            if self._db.execute("SELECT 1 FROM migrations WHERE name=?", (name,)).fetchone():
                return 0
            marked: dict[tuple[str, str], set[str]] = {}
            for banner, tiers in featured.items():
                if not tiers:
                    continue
                marks = ",".join("?" * len(tiers))
                rows = self._db.execute(
                    f"SELECT d.player_id, d.rarity, d.item_id FROM drops d JOIN (SELECT MAX(id) AS id FROM drops "
                    f"WHERE pool=? AND rarity IN ({marks}) GROUP BY player_id, rarity) last "
                    f"ON d.id = last.id", (banner, *tiers)).fetchall()
                for r in rows:
                    items = tiers[r["rarity"]]
                    if r["item_id"] in items:
                        continue
                    have = self._db.execute(
                        f"SELECT COUNT(*) FROM items WHERE player_id=? AND item_id IN ({','.join('?' * len(items))})",
                        (r["player_id"], *items)).fetchone()[0]
                    if have < len(items):
                        marked.setdefault((r["player_id"], banner), set()).add(r["rarity"])
            with self._db:
                self._db.executemany(
                    "INSERT INTO banner_draws (player_id, banner, guaranteed) VALUES (?,?,?) "
                    "ON CONFLICT(player_id, banner) DO UPDATE SET guaranteed=excluded.guaranteed",
                    [(pid, banner, ",".join(sorted(t))) for (pid, banner), t in marked.items()])
                self._db.execute("INSERT INTO migrations (name, at) VALUES (?, ?)", (name, now))
            return len(marked)

    def log_drops(self, pid: str, drops: list[dict], now: float, pool: str = "") -> None:
        """The drops of one draw request, in the order drawn; [pool] is the limited pool they are from."""
        with self._lock:
            self._db.executemany(
                "INSERT INTO drops (player_id, item_id, rarity, is_new, ts, source, pool) VALUES (?,?,?,?,?,'draw',?)",
                [(pid, d["item"], d["rarity"], int(d["new"]), now, pool) for d in drops])
            self._commit()

    def log_drop(self, pid: str, item_id: str, rarity: str, is_new: bool, now: float, source: str) -> None:
        """An item that came some other way than a draw: [source] is 'craft' or 'scratch'."""
        with self._lock:
            self._db.execute(
                "INSERT INTO drops (player_id, item_id, rarity, is_new, ts, source) VALUES (?,?,?,?,?,?)",
                (pid, item_id, rarity, int(is_new), now, source))
            self._commit()

    def drops_page(self, pid: str, before: int | None, limit: int) -> list[dict]:
        """A save's drops from the newest back, [limit] of them older than the row [before] (None: from the newest)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, item_id, rarity, is_new, ts, source, pool FROM drops "
                "WHERE player_id=? AND id < ? ORDER BY id DESC LIMIT ?",
                (pid, before if before is not None else 1 << 62, limit)).fetchall()
        return [{"id": r["id"], "item": r["item_id"], "rarity": r["rarity"], "new": bool(r["is_new"]), "ts": r["ts"],
                 "source": r["source"], "pool": r["pool"]} for r in rows]

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
        if self._reader is not None:
            with self._read_lock:
                self._reader.close()


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
                try:
                    self.store._db.commit()
                except BaseException:
                    # SQLite can refuse the COMMIT and keep the transaction open: undo it here, or the next caller
                    # on this connection would commit it with its own.
                    self._undo()
                    raise
            else:
                self._undo()
        finally:
            self.store._in_tx = False
            self.store._lock.release()

    def _undo(self) -> None:
        try:
            if self.store._db.in_transaction:
                self.store._db.rollback()
        finally:
            # Rows the caches answered for may be gone again.
            self.store._active.clear()
            self.store._counts.clear()
