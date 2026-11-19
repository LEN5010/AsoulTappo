"""Store methods of the park (乐园): coins, shared counters and news, park scratch cards, races, lottery and redeem
codes."""
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


class ParkStore(_StoreState):
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
        with self._reading() as db:
            rows = db.execute(
                "SELECT day, source, SUM(amount) AS amount, SUM(count) AS count, COUNT(*) AS saves FROM coin_ledger "
                "WHERE day >= ? GROUP BY day, source ORDER BY day, source", (since,)).fetchall()
        return [dict(r) for r in rows]

    def coin_ledger_of(self, pid: str, days: int) -> list[dict[str, Any]]:
        """The save's nonzero coin rows on its latest [days] China days with any, newest day first, then by source."""
        with self._lock:
            picked = self._db.execute(
                "SELECT DISTINCT day FROM coin_ledger WHERE player_id = ? AND amount != 0 ORDER BY day DESC LIMIT ?",
                (pid, days)).fetchall()
            if not picked:
                return []
            rows = self._db.execute(
                "SELECT day, source, amount, count FROM coin_ledger WHERE player_id = ? AND day >= ? AND amount != 0 "
                "ORDER BY day DESC, source", (pid, picked[-1]["day"])).fetchall()
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

    def grant_park_gift(self, pid: str, day: str, coins: int, min_taps: int) -> bool:
        """Gives the save [coins] and marks [day]'s gift given, when it has [min_taps] taps and no gift that day.
        One conditional update and its coin_ledger row, committed together (or in the caller's transaction)."""
        with self._lock:
            done = self._db.execute(
                "UPDATE players SET coins = coins + ?, gift_day = ? WHERE id = ? AND gift_day != ? AND taps_total >= ?",
                (coins, day, pid, day, min_taps)).rowcount
            if done:
                self._db.execute(
                    "INSERT INTO coin_ledger (day, player_id, source, amount, count) VALUES (?, ?, 'gift', ?, 1) "
                    "ON CONFLICT(day, player_id, source) DO UPDATE SET "
                    "amount = amount + excluded.amount, count = count + excluded.count", (day, pid, coins))
                self._commit()
            return bool(done)

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

    def has_park_scratch(self, pid: str, kind: str) -> bool:
        """Whether the save has ever bought a card of [kind] (prune keeps each save's first one)."""
        with self._lock:
            row = self._db.execute("SELECT 1 FROM park_scratch_cards WHERE player_id=? AND kind=? LIMIT 1",
                                   (pid, kind)).fetchone()
        return row is not None

    def park_scratch_history(self, pid: str, days: int, after: str) -> dict[str, list[dict[str, Any]]]:
        """The save's coin cards on its latest [days] China days with any after [after], newest day first. `sums`: per
        day and kind the cards bought, and the shards and coins the revealed ones paid. `items`: the items revealed
        cards paid, in the order bought. `spent`: per day the coins spent on cards (coin_ledger)."""
        with self._lock:
            picked = self._db.execute(
                "SELECT DISTINCT day FROM park_scratch_cards WHERE player_id = ? AND day > ? ORDER BY day DESC LIMIT ?",
                (pid, after, days)).fetchall()
            if not picked:
                return {"sums": [], "items": [], "spent": []}
            first = picked[-1]["day"]
            sums = self._db.execute(
                "SELECT day, kind, COUNT(*) AS cards, "
                "COALESCE(SUM(CASE WHEN revealed > 0 THEN shards END), 0) AS shards, "
                "COALESCE(SUM(CASE WHEN revealed > 0 THEN coins END), 0) AS coins "
                "FROM park_scratch_cards WHERE player_id = ? AND day >= ? GROUP BY day, kind ORDER BY day DESC, kind",
                (pid, first)).fetchall()
            items = self._db.execute(
                "SELECT day, kind, item FROM park_scratch_cards WHERE player_id = ? AND day >= ? AND revealed > 0 "
                "AND item != '' ORDER BY id", (pid, first)).fetchall()
            spent = self._db.execute(
                "SELECT day, -SUM(amount) AS coins FROM coin_ledger WHERE player_id = ? AND day >= ? "
                "AND source = 'scratch' GROUP BY day", (pid, first)).fetchall()
        return {"sums": [dict(r) for r in sums], "items": [dict(r) for r in items], "spent": [dict(r) for r in spent]}

    def prune_park_scratch(self, before: float) -> int:
        """Deletes revealed cards bought before [before]. A card still to be revealed is kept however old, and so is
        each save's first card of each kind."""
        with self._lock:
            n = self._db.execute(
                "DELETE FROM park_scratch_cards WHERE revealed > 0 AND ts < ? AND id NOT IN "
                "(SELECT MIN(id) FROM park_scratch_cards GROUP BY player_id, kind)", (before,)).rowcount
            self._commit()
            return n

    # --- park: race
    def race_get(self, race_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM park_races WHERE id = ?", (race_id,)).fetchone()
        return dict(row) if row else None

    def race_insert(self, row: dict[str, Any]) -> bool:
        """Adds a prepared race unless one with its id exists; True when added."""
        cols = ("id", "starts_at", "ends_at", "step_ms", "slow_ms", "seed", "hash", "setup", "ranking", "result")
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

    def race_shown(self, now: float, schedule: bool = False) -> dict[str, Any] | None:
        """The newest race whose bets have opened by [now]."""
        columns = "id, status, starts_at, ends_at" if schedule else "*"
        with self._lock:
            row = self._db.execute(f"SELECT {columns} FROM park_races WHERE id <= ? ORDER BY id DESC LIMIT 1",
                                   (now,)).fetchone()
        return dict(row) if row else None

    def races_settled(self, before: int, limit: int) -> list[dict[str, Any]]:
        """The newest settled races with an id below [before], newest first."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM park_races WHERE status = 'settled' AND id < ? "
                                    "ORDER BY id DESC LIMIT ?", (before, limit)).fetchall()
        return [dict(r) for r in rows]

    def races_past(self, limit: int) -> list[dict[str, Any]]:
        """The newest finished races (settled or called off), newest first."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM park_races WHERE status IN ('settled', 'void') "
                                    "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def race_bets_in(self, race_ids: list[int], pid: str) -> list[dict[str, Any]]:
        """[pid]'s bets on any of [race_ids], in the order they were placed."""
        if not race_ids:
            return []
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM park_race_bets WHERE player_id = ? AND race_id IN ({', '.join('?' * len(race_ids))}) "
                "ORDER BY id", (pid, *race_ids)).fetchall()
        return [dict(r) for r in rows]

    def race_bets(self, race_id: int, pid: str | None = None) -> list[dict[str, Any]]:
        """The race's bets (of [pid] only, when given), in the order they were placed."""
        sql = "SELECT * FROM park_race_bets WHERE race_id = ?"
        args: tuple = (race_id,)
        if pid is not None:
            sql += " AND player_id = ?"
            args += (pid,)
        with self._lock:
            rows = self._db.execute(sql + " ORDER BY id", args).fetchall()
        return [dict(r) for r in rows]

    def race_add_bet(self, race_id: int, pid: str, kind: str, member: str, coins: int, odds: int,
                     ts: float) -> int:
        """Places one bet at [odds] (tenths); in the caller's transaction. Returns its id."""
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO park_race_bets (race_id, player_id, kind, member, coins, odds, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (race_id, pid, kind, member, coins, odds, ts))
            self._commit()
            return int(cur.lastrowid)

    def race_set_prize(self, bet_id: int, prize: int) -> None:
        with self._lock:
            self._db.execute("UPDATE park_race_bets SET prize = ? WHERE id = ?", (prize, bet_id))
            self._commit()

    def race_stakes(self, race_id: int) -> dict[str, dict[str, int]]:
        """Coins staked on the race: {kind: {member: coins}}, only what was bet on."""
        with self._lock:
            rows = self._db.execute(
                "SELECT kind, member, SUM(coins) AS coins FROM park_race_bets WHERE race_id = ? "
                "GROUP BY kind, member", (race_id,)).fetchall()
        out: dict[str, dict[str, int]] = {}
        for r in rows:
            out.setdefault(r["kind"], {})[r["member"]] = int(r["coins"])
        return out

    def race_bettors(self, race_id: int) -> int:
        """How many saves bet on the race."""
        with self._lock:
            row = self._db.execute("SELECT COUNT(DISTINCT player_id) FROM park_race_bets WHERE race_id = ?",
                                   (race_id,)).fetchone()
        return int(row[0])

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

    def lottery_draws(self, limit: int) -> list[dict[str, Any]]:
        """The [limit] latest drawn days, newest first: {day, number, result, top}, `top` being the saves holding a
        top prize ticket of the day, each once, by their earliest such ticket. Two queries whatever the limit."""
        with self._lock:
            rows = self._db.execute("SELECT day, number, result FROM lottery_days WHERE drawn IS NOT NULL "
                                    "ORDER BY day DESC LIMIT ?", (limit,)).fetchall()
            days = [r["day"] for r in rows]
            won = self._db.execute(
                f"SELECT day, player_id, MIN(id) AS first FROM lottery_tickets WHERE tier = 1 AND day IN "
                f"({','.join('?' * len(days))}) GROUP BY day, player_id ORDER BY day, first", days).fetchall() \
                if days else []
        top: dict[str, list[str]] = {}
        for r in won:
            top.setdefault(r["day"], []).append(r["player_id"])
        return [{"day": r["day"], "number": r["number"], "result": r["result"], "top": top.get(r["day"], [])}
                for r in rows]

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

    def redeem_history(self, pid: str, limit: int) -> list[dict[str, Any]]:
        """The codes the save redeemed, newest first, with what each gave."""
        with self._lock:
            rows = self._db.execute(
                "SELECT r.code, r.custom, r.shards, r.coins, c.ts FROM redeem_claims c "
                "JOIN redeem_codes r ON r.id = c.code_id WHERE c.player_id = ? "
                "ORDER BY c.ts DESC, c.code_id DESC LIMIT ?", (pid, limit)).fetchall()
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
