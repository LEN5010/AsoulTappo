"""SQLite persistence for players, their item collection, presets and the drop log (stdlib only)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
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
-- Shards each save gained (amount > 0) or spent (amount < 0) per China day and source, and how many times.
-- Written in the same transaction as the change; there is no history from before the table existed.
CREATE TABLE IF NOT EXISTS shard_ledger (
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  source TEXT NOT NULL,
  amount INTEGER NOT NULL DEFAULT 0,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, player_id, source)
);
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
-- Shards the operator gives once to every save that runs `version` or newer, until the reward is ended.
CREATE TABLE IF NOT EXISTS update_rewards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version TEXT NOT NULL,
  shards INTEGER NOT NULL,
  created REAL NOT NULL,
  ended REAL
);
CREATE TABLE IF NOT EXISTS update_reward_claims (
  reward_id INTEGER NOT NULL,
  player_id TEXT NOT NULL,
  at REAL NOT NULL,
  PRIMARY KEY (reward_id, player_id)
);
-- Rooms once a minute (ts: the minute's start): rooms with members, members, distinct saves among them, the largest
-- room and the listed public rooms. Counts only.
CREATE TABLE IF NOT EXISTS room_samples (
  ts INTEGER PRIMARY KEY,
  rooms INTEGER NOT NULL,
  members INTEGER NOT NULL,
  saves INTEGER NOT NULL,
  largest INTEGER NOT NULL,
  public INTEGER NOT NULL
);
-- Rooms as the server left them when it stopped (see RoomManager.snapshot); read back and emptied at the next start.
-- host: the host's save; banned: JSON list of the saves the host removed.
CREATE TABLE IF NOT EXISTS room_restore (
  room TEXT PRIMARY KEY,
  public INTEGER NOT NULL,
  host TEXT,
  banned TEXT NOT NULL,
  saved REAL NOT NULL
);
-- Server-wide counts per China day (room joins, pokes, profile views, emotes, duel invites, cheer rounds).
CREATE TABLE IF NOT EXISTS daily_counts (
  day TEXT NOT NULL,
  key TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, key)
);
-- Per save and China day: reported taps that were not credited, cooldowns the server started for input too fast
-- for a hand, cooldowns the client's own guard started, and cooldowns the server started for input at one steady
-- rate for too long.
CREATE TABLE IF NOT EXISTS tap_flags (
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  dropped INTEGER NOT NULL DEFAULT 0,
  server_cooldowns INTEGER NOT NULL DEFAULT 0,
  client_cooldowns INTEGER NOT NULL DEFAULT 0,
  steady INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, player_id)
);
-- What the operator changed through /admin: who (the main site's admin), on which save, what (JSON) and why.
CREATE TABLE IF NOT EXISTS admin_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  actor TEXT NOT NULL DEFAULT '',
  action TEXT NOT NULL,
  player_id TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS admin_log_player ON admin_log (player_id, id);
-- Park coins each save gained (amount > 0) or spent (amount < 0) per China day and source, like shard_ledger.
CREATE TABLE IF NOT EXISTS coin_ledger (
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  source TEXT NOT NULL,
  amount INTEGER NOT NULL DEFAULT 0,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, player_id, source)
);
-- Shared park amounts, such as the scratch jackpot and the lottery rollovers, written in the caller's transaction.
CREATE TABLE IF NOT EXISTS park_counters (
  key TEXT PRIMARY KEY,
  value INTEGER NOT NULL DEFAULT 0
);
-- Park wins every running pet hears of (status `park.news`); kept PARK_NEWS_DAYS.
CREATE TABLE IF NOT EXISTS park_news (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  player_id TEXT NOT NULL DEFAULT '',
  nick TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '{}'
);
-- park: scratch tables
-- Coin scratch cards (park_scratch.py), decided when bought and paid when revealed (revealed = 0 until then). tier:
-- again, shards, emote, skin, big, jackpot or miss; shards, coins and item are what the reveal pays.
CREATE TABLE IF NOT EXISTS park_scratch_cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT NOT NULL,
  day TEXT NOT NULL,
  kind TEXT NOT NULL,
  cells TEXT NOT NULL,
  tier TEXT NOT NULL,
  shards INTEGER NOT NULL DEFAULT 0,
  coins INTEGER NOT NULL DEFAULT 0,
  item TEXT NOT NULL DEFAULT '',
  ts REAL NOT NULL,
  revealed REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS park_scratch_cards_player ON park_scratch_cards (player_id, revealed);
-- park: race tables
-- Dumpling races (park_race.py), id = when its bets open (unix seconds). seed (hex), ranking and result stay
-- server-side until status 'running'; result ({start, moves}) is cleared after RESULT_KEEP_DAYS (the seed and
-- setup reproduce it). status: open (prepared or taking bets), running, settled, void (called off, bets refunded).
CREATE TABLE IF NOT EXISTS park_races (
  id INTEGER PRIMARY KEY,
  starts_at REAL NOT NULL,
  ends_at REAL NOT NULL,
  step_ms INTEGER NOT NULL,
  seed TEXT NOT NULL,
  hash TEXT NOT NULL,
  setup TEXT NOT NULL,
  odds TEXT NOT NULL,
  ranking TEXT NOT NULL,
  result TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open'
);
CREATE INDEX IF NOT EXISTS park_races_status ON park_races (status, id);
-- Bets on a race, one row per save and selection; odds in tenths; prize in shards once settled.
CREATE TABLE IF NOT EXISTS park_race_bets (
  race_id INTEGER NOT NULL,
  player_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  member TEXT NOT NULL,
  coins INTEGER NOT NULL,
  odds INTEGER NOT NULL,
  prize INTEGER NOT NULL DEFAULT 0,
  ts REAL NOT NULL,
  PRIMARY KEY (race_id, player_id, kind, member)
);
-- park: lottery tables
-- The daily lottery (lottery.py): one row per China day, made before the day's first ticket. `hash` is SHA-256 of
-- number + salt and is public all day; number and salt go public once `drawn` is set. `result` is the draw's JSON.
CREATE TABLE IF NOT EXISTS lottery_days (
  day TEXT PRIMARY KEY,
  number TEXT NOT NULL,
  salt TEXT NOT NULL,
  hash TEXT NOT NULL,
  created REAL NOT NULL,
  drawn REAL,
  result TEXT NOT NULL DEFAULT '{}'
);
-- One row per ticket; `tier` (1 top, 2 second, 3 third, 0 none) and `prize` are set by the draw.
CREATE TABLE IF NOT EXISTS lottery_tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT NOT NULL,
  player_id TEXT NOT NULL,
  number TEXT NOT NULL,
  ts REAL NOT NULL,
  tier INTEGER NOT NULL DEFAULT 0,
  prize INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS lottery_tickets_day ON lottery_tickets (day, player_id);
-- park: redeem tables
-- Redeem codes made through /admin/codes (see redeem.py). code: normalized (upper case, no dashes or spaces); custom: an
-- admin wrote it rather than the generator; uses: claims allowed, used: claims so far; expires: Unix seconds, 0 never.
CREATE TABLE IF NOT EXISTS redeem_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  custom INTEGER NOT NULL DEFAULT 0,
  shards INTEGER NOT NULL DEFAULT 0,
  coins INTEGER NOT NULL DEFAULT 0,
  uses INTEGER NOT NULL DEFAULT 1,
  used INTEGER NOT NULL DEFAULT 0,
  expires REAL NOT NULL DEFAULT 0,
  disabled REAL,
  note TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL DEFAULT '',
  created REAL NOT NULL
);
-- One row per code a save redeemed; a save redeems each code once.
CREATE TABLE IF NOT EXISTS redeem_claims (
  code_id INTEGER NOT NULL,
  player_id TEXT NOT NULL,
  ts REAL NOT NULL,
  PRIMARY KEY (code_id, player_id)
);
CREATE INDEX IF NOT EXISTS redeem_claims_player ON redeem_claims (player_id);
-- Wrong codes a save entered lately (older rows go when it enters the next), and the save's lockout: locked until
-- [until], [locks] lockouts so far, the last at [last].
CREATE TABLE IF NOT EXISTS redeem_tries (
  player_id TEXT NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS redeem_tries_player ON redeem_tries (player_id, ts);
CREATE TABLE IF NOT EXISTS redeem_locks (
  player_id TEXT PRIMARY KEY,
  until REAL NOT NULL,
  locks INTEGER NOT NULL DEFAULT 0,
  last REAL NOT NULL
);
"""

STARTER_SHARDS = 1600
# Statistics count days in China Standard Time.
DAY_OFFSET = 8 * 3600
# Saves whose collectible count is remembered (see Store.count_items); the cache starts over when full.
COUNT_CACHE_LIMIT = 20000

PLAYER_FIELDS = (
    "id created taps_total active_minutes last_activity minute_bucket minute_taps minute_counted frame badge "
    "shards loadout draw_pity drawn_total presence_last skin_pity last_minute_taps shard_remainder "
    "boost_day boost_used tap_cooldown_until tap_day day_taps day_taps_total scratch_pity "
    "steady_day steady_hits steady_rate coins coin_day coin_bought gift_day stamps_total"
).split()


def day_of(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts + DAY_OFFSET))


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
            self._db.executescript(SCHEMA)
            self._migrate()

    def _columns(self, table: str) -> set[str]:
        return {r[1] for r in self._db.execute(f"PRAGMA table_info({table})")}

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
            # The China day of the save's last steady-rate cooldown, how many it had that day, and the rate caught.
            if "steady_day" not in players:
                self._db.execute("ALTER TABLE players ADD COLUMN steady_day TEXT NOT NULL DEFAULT ''")
            for field, kind in (("steady_hits", "INTEGER"), ("steady_rate", "REAL")):
                if field not in players:
                    self._db.execute(f"ALTER TABLE players ADD COLUMN {field} {kind} NOT NULL DEFAULT 0")
            # Park coins: held, bought on `coin_day`, the day of the last free one, and stamps ever earned.
            for field, kind in (("coins", "INTEGER NOT NULL DEFAULT 0"), ("coin_day", "TEXT NOT NULL DEFAULT ''"),
                                ("coin_bought", "INTEGER NOT NULL DEFAULT 0"), ("gift_day", "TEXT NOT NULL DEFAULT ''"),
                                ("stamps_total", "INTEGER NOT NULL DEFAULT 0")):
                if field not in players:
                    self._db.execute(f"ALTER TABLE players ADD COLUMN {field} {kind}")
            if "steady" not in self._columns("tap_flags"):
                self._db.execute("ALTER TABLE tap_flags ADD COLUMN steady INTEGER NOT NULL DEFAULT 0")
            sessions = self._columns("activity_sessions")
            # The session's steady run: its mean rate, its batches, whether its last batch was an odd one left out,
            # and batches in a row at the rate caught today.
            for field, kind in (("last_at", "REAL"), ("fast_since", "REAL"), ("rate", "REAL"), ("steady", "INTEGER"),
                                ("odd", "INTEGER"), ("near", "INTEGER")):
                if field not in sessions:
                    self._db.execute(f"ALTER TABLE activity_sessions ADD COLUMN {field} {kind} NOT NULL DEFAULT 0")
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

    def activity_session(self, pid: str, session: str) -> dict[str, float]:
        """The session's last batch: its sequence, when it came, since when it has been too fast, and its steady
        run (mean rate, batches, whether the last batch was left out, batches in a row at the rate caught today)."""
        with self._lock:
            row = self._db.execute(
                "SELECT sequence, last_at, fast_since, rate, steady, odd, near FROM activity_sessions "
                "WHERE player_id=? AND session=?", (pid, session)).fetchone()
            return dict(row) if row else {"sequence": 0, "last_at": 0.0, "fast_since": 0.0, "rate": 0.0,
                                          "steady": 0, "odd": 0, "near": 0}

    def save_activity_sequence(self, pid: str, session: str, sequence: int, last_at: float = 0.0,
                               fast_since: float = 0.0, rate: float = 0.0, steady: int = 0, odd: int = 0,
                               near: int = 0) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO activity_sessions "
                "(player_id, session, sequence, last_at, fast_since, rate, steady, odd, near) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(player_id, session) DO UPDATE SET "
                "sequence=excluded.sequence, last_at=excluded.last_at, fast_since=excluded.fast_since, "
                "rate=excluded.rate, steady=excluded.steady, odd=excluded.odd, near=excluded.near",
                (pid, session, sequence, last_at, fast_since, rate, steady, odd, near))
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

    # --- update rewards
    def open_update_rewards(self, pid: str) -> list[dict[str, Any]]:
        """Rewards not ended that [pid] has not claimed, oldest first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, version, shards FROM update_rewards r WHERE ended IS NULL AND NOT EXISTS "
                "(SELECT 1 FROM update_reward_claims c WHERE c.reward_id = r.id AND c.player_id = ?) ORDER BY id",
                (pid,)).fetchall()
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
        with self._lock:
            rows = self._db.execute(
                f"SELECT player_id, COUNT(*) AS cards, SUM(item_id IN ({big_marks})) AS big, MAX(first_ts) AS last "
                f"FROM items WHERE count > 0 AND item_id IN ({marks}) GROUP BY player_id", (*big, *cards)).fetchall()
        return [dict(r) for r in rows]

    def held_items(self) -> list[tuple[str, str, float]]:
        """(player id, item id, when it first came) of every item a save holds."""
        with self._lock:
            rows = self._db.execute("SELECT player_id, item_id, first_ts FROM items WHERE count > 0").fetchall()
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
        with self._lock:
            rows = self._db.execute(
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

    # --- park (coins, shared amounts and news; see park.py)
    def add_coin_ledger(self, pid: str, day: str, source: str, amount: int, count: int = 1) -> None:
        """Adds to the save's [source] row of [day] in coin_ledger, in the caller's transaction if any."""
        with self._lock:
            self._db.execute(
                "INSERT INTO coin_ledger (day, player_id, source, amount, count) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(day, player_id, source) DO UPDATE SET "
                "amount = amount + excluded.amount, count = count + excluded.count",
                (day, pid, source, amount, count))
            self._commit()

    def coin_ledger_by_day(self, since: str) -> list[dict[str, Any]]:
        """Coins per China day and source since [since], over every save."""
        with self._lock:
            rows = self._db.execute(
                "SELECT day, source, SUM(amount) AS amount, SUM(count) AS count, COUNT(*) AS saves FROM coin_ledger "
                "WHERE day >= ? GROUP BY day, source ORDER BY day, source", (since,)).fetchall()
        return [dict(r) for r in rows]

    def ledger_sum(self, pid: str, day: str, sources: tuple[str, ...]) -> int:
        """The save's shards of [day] summed over [sources] (gains positive, spending negative)."""
        if not sources:
            return 0
        with self._lock:
            row = self._db.execute(
                f"SELECT COALESCE(SUM(amount), 0) AS n FROM shard_ledger WHERE day = ? AND player_id = ? "
                f"AND source IN ({','.join('?' * len(sources))})", (day, pid, *sources)).fetchone()
        return int(row["n"])

    def park_counter(self, key: str, default: int = 0) -> int:
        with self._lock:
            row = self._db.execute("SELECT value FROM park_counters WHERE key = ?", (key,)).fetchone()
        return int(row["value"]) if row else default

    def set_park_counter(self, key: str, value: int) -> None:
        with self._lock:
            self._db.execute("INSERT INTO park_counters (key, value) VALUES (?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
            self._commit()

    def add_park_news(self, ts: float, kind: str, pid: str, nick: str, detail: str) -> int:
        with self._lock:
            cur = self._db.execute("INSERT INTO park_news (ts, kind, player_id, nick, detail) VALUES (?, ?, ?, ?, ?)",
                                   (ts, kind, pid, nick, detail))
            self._commit()
            return int(cur.lastrowid)

    def park_news_since(self, since: float, limit: int) -> list[dict[str, Any]]:
        """The newest [limit] news items from [since] on, oldest first."""
        with self._lock:
            rows = self._db.execute("SELECT id, ts, kind, nick, detail FROM park_news WHERE ts >= ? "
                                    "ORDER BY id DESC LIMIT ?", (since, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def prune_park_news(self, before: float) -> int:
        with self._lock:
            n = self._db.execute("DELETE FROM park_news WHERE ts < ?", (before,)).rowcount
            self._commit()
            return n

    # --- park: scratch
    def add_park_scratch(self, pid: str, day: str, kind: str, cells: str, tier: str, shards: int, coins: int,
                         item: str, ts: float) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO park_scratch_cards (player_id, day, kind, cells, tier, shards, coins, item, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (pid, day, kind, cells, tier, shards, coins, item, ts))
            self._commit()
            return int(cur.lastrowid)

    def pending_park_scratch(self, pid: str) -> dict[str, Any] | None:
        """The coin scratch card bought and not revealed yet; a save holds one at most."""
        with self._lock:
            row = self._db.execute("SELECT * FROM park_scratch_cards WHERE player_id=? AND revealed=0 "
                                   "ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
        return dict(row) if row else None

    def park_scratch_card(self, pid: str, card_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM park_scratch_cards WHERE id=? AND player_id=?",
                                   (card_id, pid)).fetchone()
        return dict(row) if row else None

    def reveal_park_scratch(self, card_id: int, ts: float, **paid: Any) -> None:
        """Marks the card revealed, with what it paid when that differs from the roll (an item owned by then)."""
        cols = "".join(f", {k}=?" for k in paid)
        with self._lock:
            self._db.execute(f"UPDATE park_scratch_cards SET revealed=?{cols} WHERE id=?",
                             (ts, *paid.values(), card_id))
            self._commit()

    def prune_park_scratch(self, before: float) -> int:
        """Deletes revealed cards bought before [before]; a card still to be revealed is kept however old."""
        with self._lock:
            n = self._db.execute("DELETE FROM park_scratch_cards WHERE revealed > 0 AND ts < ?", (before,)).rowcount
            self._commit()
            return n

    # --- park: race
    def race_get(self, race_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM park_races WHERE id = ?", (race_id,)).fetchone()
        return dict(row) if row else None

    def race_insert(self, row: dict[str, Any]) -> bool:
        """Adds a prepared race unless one with its id exists; True when added."""
        cols = ("id", "starts_at", "ends_at", "step_ms", "seed", "hash", "setup", "odds", "ranking", "result")
        with self._lock:
            cur = self._db.execute(
                f"INSERT OR IGNORE INTO park_races ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                tuple(row[c] for c in cols))
            self._commit()
            return cur.rowcount > 0

    def race_set_status(self, race_id: int, status: str) -> None:
        with self._lock:
            self._db.execute("UPDATE park_races SET status = ? WHERE id = ?", (status, race_id))
            self._commit()

    def races_unsettled(self) -> list[dict[str, Any]]:
        """Races still open or running, oldest first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM park_races WHERE status IN ('open', 'running') ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def race_shown(self, now: float) -> dict[str, Any] | None:
        """The newest race whose bets have opened by [now]."""
        with self._lock:
            row = self._db.execute("SELECT * FROM park_races WHERE id <= ? ORDER BY id DESC LIMIT 1",
                                   (now,)).fetchone()
        return dict(row) if row else None

    def races_settled(self, before: int, limit: int) -> list[dict[str, Any]]:
        """The newest settled races with an id below [before], newest first."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM park_races WHERE status = 'settled' AND id < ? "
                                    "ORDER BY id DESC LIMIT ?", (before, limit)).fetchall()
        return [dict(r) for r in rows]

    def race_prune_results(self, before: int) -> int:
        with self._lock:
            n = self._db.execute("UPDATE park_races SET result = '' WHERE id < ? AND result != '' "
                                 "AND status IN ('settled', 'void')", (before,)).rowcount
            self._commit()
            return n

    def race_bets(self, race_id: int, pid: str | None = None) -> list[dict[str, Any]]:
        """The race's bets (of [pid] only, when given), in the order they were first placed."""
        sql = "SELECT * FROM park_race_bets WHERE race_id = ?"
        args: tuple = (race_id,)
        if pid is not None:
            sql += " AND player_id = ?"
            args += (pid,)
        with self._lock:
            rows = self._db.execute(sql + " ORDER BY rowid", args).fetchall()
        return [dict(r) for r in rows]

    def race_add_bet(self, race_id: int, pid: str, kind: str, member: str, coins: int, odds: int,
                     ts: float) -> None:
        """Adds [coins] to the save's bet on (kind, member), placing it if new; in the caller's transaction."""
        with self._lock:
            self._db.execute(
                "INSERT INTO park_race_bets (race_id, player_id, kind, member, coins, odds, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(race_id, player_id, kind, member) DO UPDATE SET "
                "coins = coins + excluded.coins, ts = excluded.ts", (race_id, pid, kind, member, coins, odds, ts))
            self._commit()

    def race_set_prize(self, race_id: int, pid: str, kind: str, member: str, prize: int) -> None:
        with self._lock:
            self._db.execute("UPDATE park_race_bets SET prize = ? WHERE race_id = ? AND player_id = ? AND kind = ? "
                             "AND member = ?", (prize, race_id, pid, kind, member))
            self._commit()

    def race_pool(self, race_id: int) -> dict[str, dict[str, int]]:
        """Per member bet on: coins over every kind, and how many saves bet on it."""
        with self._lock:
            rows = self._db.execute(
                "SELECT member, SUM(coins) AS coins, COUNT(DISTINCT player_id) AS bettors FROM park_race_bets "
                "WHERE race_id = ? GROUP BY member", (race_id,)).fetchall()
        return {r["member"]: {"coins": int(r["coins"]), "bettors": int(r["bettors"])} for r in rows}

    # --- park: lottery
    def lottery_day(self, day: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM lottery_days WHERE day = ?", (day,)).fetchone()
        return dict(row) if row else None

    def add_lottery_day(self, day: str, number: str, salt: str, digest: str, ts: float) -> bool:
        """Makes [day]'s row unless it exists; True when this call made it."""
        with self._lock:
            n = self._db.execute("INSERT OR IGNORE INTO lottery_days (day, number, salt, hash, created) "
                                 "VALUES (?, ?, ?, ?, ?)", (day, number, salt, digest, ts)).rowcount
            self._commit()
        return n > 0

    def lottery_undrawn(self) -> list[str]:
        """Days not drawn yet, oldest first."""
        with self._lock:
            rows = self._db.execute("SELECT day FROM lottery_days WHERE drawn IS NULL ORDER BY day").fetchall()
        return [r["day"] for r in rows]

    def lottery_last_drawn(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM lottery_days WHERE drawn IS NOT NULL ORDER BY day DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def set_lottery_drawn(self, day: str, ts: float, result: str) -> None:
        with self._lock:
            self._db.execute("UPDATE lottery_days SET drawn = ?, result = ? WHERE day = ?", (ts, result, day))
            self._commit()

    def lottery_sales(self, day: str) -> int:
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) AS n FROM lottery_tickets WHERE day = ?", (day,)).fetchone()
        return int(row["n"])

    def lottery_history(self, pid: str, limit: int) -> list[dict[str, Any]]:
        """The save's [limit] latest drawn days it had tickets in, newest first: {day, number, won}."""
        with self._lock:
            rows = self._db.execute(
                "SELECT d.day, d.number, SUM(t.prize) AS won FROM lottery_tickets t "
                "JOIN lottery_days d ON d.day = t.day WHERE t.player_id = ? AND d.drawn IS NOT NULL "
                "GROUP BY d.day ORDER BY d.day DESC LIMIT ?", (pid, limit)).fetchall()
        return [{"day": r["day"], "number": r["number"], "won": int(r["won"])} for r in rows]

    def lottery_tickets(self, day: str, pid: str | None = None) -> list[dict[str, Any]]:
        """[day]'s tickets (of [pid] only when given), in buying order."""
        with self._lock:
            if pid is None:
                rows = self._db.execute("SELECT * FROM lottery_tickets WHERE day = ? ORDER BY id", (day,)).fetchall()
            else:
                rows = self._db.execute("SELECT * FROM lottery_tickets WHERE day = ? AND player_id = ? ORDER BY id",
                                        (day, pid)).fetchall()
        return [dict(r) for r in rows]

    def add_lottery_tickets(self, day: str, pid: str, numbers: list[str], ts: float) -> None:
        with self._lock:
            self._db.executemany("INSERT INTO lottery_tickets (day, player_id, number, ts) VALUES (?, ?, ?, ?)",
                                 [(day, pid, n, ts) for n in numbers])
            self._commit()

    def set_lottery_prizes(self, rows: list[tuple[int, int, int]]) -> None:
        """(ticket id, tier, prize) of each winning ticket."""
        with self._lock:
            self._db.executemany("UPDATE lottery_tickets SET tier = ?, prize = ? WHERE id = ?",
                                 [(tier, prize, tid) for tid, tier, prize in rows])
            self._commit()

    # --- park: redeem
    _CODE_COLUMNS = "id, code, custom, shards, coins, uses, used, expires, disabled, note, created_by, created"

    def add_redeem_code(self, code: str, custom: bool, shards: int, coins: int, uses: int, expires: float, note: str,
                        actor: str, ts: float) -> int | None:
        """The new code's id, or None when the code is taken; in the caller's transaction if any."""
        with self._lock:
            try:
                cur = self._db.execute(
                    "INSERT INTO redeem_codes (code, custom, shards, coins, uses, expires, note, created_by, created) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (code, int(custom), shards, coins, uses, expires, note, actor, ts))
            except sqlite3.IntegrityError:
                return None
            self._commit()
            return int(cur.lastrowid)

    def redeem_code(self, code: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(f"SELECT {self._CODE_COLUMNS} FROM redeem_codes WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else None

    def redeem_code_by_id(self, code_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(f"SELECT {self._CODE_COLUMNS} FROM redeem_codes WHERE id = ?", (code_id,)).fetchone()
        return dict(row) if row else None

    def redeem_codes(self, q: str, limit: int, before: int | None = None) -> list[dict[str, Any]]:
        """Newest first. [q] matches part of the code or the note (empty: all); [before] continues below that id."""
        clauses, args = [], []
        if q:
            clauses.append("(instr(code, ?) > 0 OR instr(note, ?) > 0)")
            args += [q.upper().replace("-", "").replace(" ", ""), q]
        if before is not None:
            clauses.append("id < ?")
            args.append(before)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._db.execute(f"SELECT {self._CODE_COLUMNS} FROM redeem_codes {where} ORDER BY id DESC LIMIT ?",
                                    (*args, limit)).fetchall()
        return [dict(r) for r in rows]

    def disable_redeem_code(self, code_id: int, ts: float) -> None:
        with self._lock:
            self._db.execute("UPDATE redeem_codes SET disabled = ? WHERE id = ? AND disabled IS NULL", (ts, code_id))
            self._commit()

    def claim_redeem_code(self, code_id: int, pid: str, ts: float) -> bool:
        """Counts one use and notes the save's claim; False when no use is left. Run in the caller's transaction, which
        also pays the reward."""
        with self._lock:
            cur = self._db.execute("UPDATE redeem_codes SET used = used + 1 WHERE id = ? AND used < uses", (code_id,))
            if cur.rowcount == 0:
                return False
            self._db.execute("INSERT INTO redeem_claims (code_id, player_id, ts) VALUES (?, ?, ?)", (code_id, pid, ts))
            self._commit()
            return True

    def redeemed(self, code_id: int, pid: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM redeem_claims WHERE code_id = ? AND player_id = ?",
                                    (code_id, pid)).fetchone() is not None

    def redeem_claims(self, code_id: int, limit: int) -> list[dict[str, Any]]:
        """The code's claims, newest first, with the main-site account of each save (None for a guest save)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT c.player_id, a.main_user_id, c.ts FROM redeem_claims c "
                "LEFT JOIN account_links a ON a.player_id = c.player_id WHERE c.code_id = ? "
                "ORDER BY c.ts DESC, c.player_id LIMIT ?", (code_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def redeem_lock(self, pid: str) -> float:
        """Until when the save may not enter codes (0 when it never was locked)."""
        with self._lock:
            row = self._db.execute("SELECT until FROM redeem_locks WHERE player_id = ?", (pid,)).fetchone()
        return float(row["until"]) if row else 0.0

    def add_redeem_try(self, pid: str, ts: float, window: float) -> int:
        """Notes a wrong code and forgets the save's tries older than [window] seconds; returns the tries left."""
        with self._lock:
            self._db.execute("DELETE FROM redeem_tries WHERE player_id = ? AND ts <= ?", (pid, ts - window))
            self._db.execute("INSERT INTO redeem_tries (player_id, ts) VALUES (?, ?)", (pid, ts))
            n = self._db.execute("SELECT COUNT(*) FROM redeem_tries WHERE player_id = ?", (pid,)).fetchone()[0]
            self._commit()
            return int(n)

    def lock_redeem(self, pid: str, ts: float, until: float) -> None:
        """Locks the save until [until], forgets its tries and counts the lockout."""
        with self._lock:
            self._db.execute("DELETE FROM redeem_tries WHERE player_id = ?", (pid,))
            self._db.execute("INSERT INTO redeem_locks (player_id, until, locks, last) VALUES (?, ?, 1, ?) "
                             "ON CONFLICT(player_id) DO UPDATE SET until = excluded.until, locks = locks + 1, "
                             "last = excluded.last", (pid, until, ts))
            self._commit()

    def redeem_locks_since(self, since: float, limit: int) -> list[dict[str, Any]]:
        """Saves locked out at or after [since], the most recent first: for the admin anomalies page."""
        with self._lock:
            rows = self._db.execute(
                "SELECT l.player_id, a.main_user_id, l.locks, l.last FROM redeem_locks l "
                "LEFT JOIN account_links a ON a.player_id = l.player_id WHERE l.last >= ? ORDER BY l.last DESC LIMIT ?",
                (since, limit)).fetchall()
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
                # Rows the caches answered for may be gone again.
                self.store._active.clear()
                self.store._counts.clear()
        finally:
            self.store._in_tx = False
            self.store._lock.release()
