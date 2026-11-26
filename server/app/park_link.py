"""连连看 in the park (economy park.link): one player clears a board of emote tiles against the clock.

A game costs `entry` shards, burnt when it starts; a save starts at most len(levels) games a China day, counted by the
day a game starts, abandoned ones too, and the n-th of the day is played on levels[n-1]. The board and its rules are
link.py; the client holds the whole board and reports each pair it clears, in order (`seq`). The server checks every
pair against its own board, keeps the time (moves after deadline + grace are not taken) and shuffles a board left with
no pair. A game pays max × counted² // total² shards once, when it is cleared, finished, or found past its time by
the next call (lazy settlement); counted leaves out the pairs claimed sooner than antiCheat link_min_pair_ms after the
one before (`fast`), and is at most the pairs that time could have held by the last pair's arrival. Per-move answers are kept minimal; full answers come with start, finish, settlement
and GET."""
from __future__ import annotations

import json
from typing import Any, Callable

from .game import SCRATCH_DAYS, GameError, player_id_for
from .link import EMPTY, connect, find_pair, generate, remove_pair, shuffle
from .park import LINK_FEE, LINK_PRIZE, Park
from .store import Store, day_of

# Tries of start: the board is laid outside the store's lock, and laid again when the level changed in between (a
# concurrent start or the day turning); the last try lays it inside.
START_TRIES = 3
# How far past its arrival a move may claim to have been played (ms): the client's clock estimate and the time the
# report spent on the way. A later claim is cut to this.
LINK_CLAIM_SLACK_MS = 1500
# _view's default: the game in play is read there.
_UNREAD: Any = object()


def _dump(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


class ParkLink:
    def __init__(self, park: Park, require_account: Callable[[], bool] = lambda: False) -> None:
        self.park = park
        # Whether the server has main-site accounts; then `account` in the config makes a game need a linked save.
        self.require_account = require_account

    @property
    def cfg(self) -> dict[str, Any]:
        cfg = self.park.cfg.get("link")
        if not cfg:
            raise GameError("no_park", "这个服务器没有连连看")
        return cfg

    def _level(self, level: int) -> dict[str, Any]:
        """The config of the [level]-th game of a day (from 1); the last level if the config has fewer since."""
        levels = self.cfg["levels"]
        return levels[min(level, len(levels)) - 1]

    def _emotes(self) -> list[str]:
        """Keys of the static emotes in the configured sets, in manifest order, each once."""
        sets = {s["id"]: s for s in self.park.game.manifest.data.get("emoteSets", [])}
        keys = [e["key"] for sid in self.cfg["sets"] if sid in sets for e in sets[sid]["emotes"] if not e.get("animated")]
        return list(dict.fromkeys(keys))

    def _lay(self, n: int) -> tuple[list[str], list[int]]:
        """The emote keys and the board of a game on levels[n]: `kinds` distinct static emotes picked with the game's
        rng (a partial Fisher-Yates shuffle), then link.generate."""
        level = self.cfg["levels"][n]
        rng = self.park.game.rng
        pool = self._emotes()
        count = level["kinds"]
        for i in range(count):
            j = min(i + int(rng.random() * (len(pool) - i)), len(pool) - 1)
            pool[i], pool[j] = pool[j], pool[i]
        board = generate(level["rows"], level["cols"], count, level["shift"], rng)
        return pool[:count], list(board)

    # ------------------------------------------------------------------ views
    @staticmethod
    def _result(row: dict[str, Any]) -> dict[str, Any]:
        """LinkResult of a settled game. ms: from the start to the last accepted pair; without one, to the settlement
        or the deadline, whichever came first (a game settled lazily long after its time counts to its deadline)."""
        events = json.loads(row["events"])
        if events:
            ms = events[-1]["t"]
        else:
            ms = max(0, round((min(row["settled_at"], row["deadline"]) - row["started_at"]) * 1000))
        return {"id": row["id"], "level": row["level"], "cleared": row["cleared"], "total": row["total"],
                "prize": row["prize"], "reason": row["reason"], "ms": ms}

    def _game(self, row: dict[str, Any], now: float) -> dict[str, Any]:
        """LinkGame of a game in play. Each accepted pair clears one, so seq equals cleared."""
        return {"id": row["id"], "level": row["level"], "rows": row["rows"], "cols": row["cols"],
                "shift": row["shift"], "kinds": json.loads(row["kinds"]), "board": json.loads(row["board"]),
                "seq": row["cleared"], "cleared": row["cleared"], "total": row["total"], "max": row["max"],
                "hints": self._level(row["level"])["hints"], "seconds": round(row["deadline"] - row["started_at"]),
                "start": round(row["started_at"] * 1000), "deadline": round(row["deadline"] * 1000),
                "now": round(now * 1000)}

    def _view(self, st: Store, pid: str, now: float, active: Any = _UNREAD) -> dict[str, Any]:
        """LinkState: today's settled games, today's count, the daily cap, the game in play and the last result.
        [active]: the game in play (None for none) when the caller has just read it."""
        today = st.park_link_day(pid, day_of(now))
        if active is _UNREAD:
            active = st.park_link_active(pid)
        last = st.park_link_last(pid)
        return {"today": [self._result(r) for r in today if r["settled_at"] is not None],
                "played": len(today), "levels": len(self.cfg["levels"]),
                "game": self._game(active, now) if active else None,
                "last": self._result(last) if last else None}

    def _answer(self, token: str, active: Any = _UNREAD, **extra: Any) -> dict[str, Any]:
        """The status, the park and LinkState as they are at one moment, whatever another device does meanwhile: all
        read under one hold of the store's lock, the park and LinkState at one time. The player is read after the
        status, which may grant today's free coin."""
        g = self.park.game
        pid = player_id_for(token)
        with g.store.lock:
            status = g.status(token)
            now = g.now()
            park = self.park.view(g.store, g.store.get_player(pid, now), day_of(now))
            link = self._view(g.store, pid, now, active)
        return {**status, "park": park, "link": link, **extra}

    # ------------------------------------------------------------- settlement
    def _settle(self, st: Store, row: dict[str, Any], reason: str, now: float) -> dict[str, Any]:
        """Settles the game in the caller's transaction and pays its prize, once: a game settled already is answered
        as it is. The prize uses the `max` stored when the game started, so a config change during the game leaves
        it alone, and goes on the shard ledger of the day it is settled on, as park scratch prizes do."""
        if row["settled_at"] is not None:
            return row
        counted = self._counted(row)
        prize = row["max"] * counted ** 2 // row["total"] ** 2
        if not st.settle_park_link(row["id"], prize, reason, now):
            return st.park_link_game(row["player_id"], row["id"]) or row
        if prize > 0:
            pid = row["player_id"]
            p = st.get_player(pid, now)
            st.update_player(pid, shards=p["shards"] + prize)
            st.add_ledger(pid, day_of(now), LINK_PRIZE, prize)
        return {**row, "prize": prize, "reason": reason, "settled_at": now}

    def _counted(self, row: dict[str, Any]) -> int:
        """Pairs the prize counts: the cleared ones but the `fast` ones, and no more than link_min_pair_ms fits into
        the server-measured arrival of the last pair, so a script cannot bank spaced claims within the slack."""
        events = json.loads(row["events"])
        if not events:
            return 0
        fast = sum(1 for ev in events if ev.get("fast"))
        return max(0, min(row["cleared"] - fast, events[-1]["t"] // self.park.game.cfg.link_min_pair_ms))

    def _due(self, st: Store, pid: str, now: float) -> dict[str, Any] | None:
        """The save's game in play, after settling it (reason time) when it is past deadline + grace."""
        row = st.park_link_active(pid)
        if row is not None and now > row["deadline"] + self.cfg["grace"]:
            self._settle(st, row, "time", now)
            return None
        return row

    # ------------------------------------------------------------------ calls
    def state(self, token: str) -> dict[str, Any]:
        """GET: status, park and LinkState, after settling a game past its time."""
        cfg = self.cfg
        g = self.park.game
        pid = player_id_for(token)
        with g.store.lock:
            row = g.store.park_link_active(pid)
            if row is not None and g.now() > row["deadline"] + cfg["grace"]:
                with g.store.transaction() as st:
                    row = self._due(st, pid, g.now())
            return self._answer(token, row)

    def start(self, token: str) -> dict[str, Any]:
        """Starts the day's next game: takes the entry fee and makes the game in one transaction. A game in play is
        handed back as it is, at no charge, so a save never plays two."""
        cfg = self.cfg
        g = self.park.game
        pid = player_id_for(token)
        laid: tuple[int, list[str], list[int]] | None = None
        for attempt in range(START_TRIES):
            error: GameError | None = None
            with g.store.transaction() as st:
                try:
                    need = self._start(st, pid, laid, last=attempt == START_TRIES - 1)
                except GameError as e:
                    # Raised after the transaction ends, so the settlement of an expired game is kept.
                    error, need = e, None
            if error is not None:
                raise error
            if need is None:
                break
            laid = (need, *self._lay(need))
        return self._answer(token)

    def _start(self, st: Store, pid: str, laid: tuple[int, list[str], list[int]] | None, last: bool) -> int | None:
        """In start's transaction: None once the save has a game in play, or the index of the level whose board must
        be laid (outside the lock) before the game can be made."""
        cfg = self.cfg
        now = self.park.game.now()
        day = day_of(now)
        if self._due(st, pid, now) is not None:
            return None
        p = st.get_player(pid, now)
        if p["taps_total"] < self.park.coin["minTaps"]:
            raise GameError("park_locked", "累计敲击 1 万下后开放")
        if cfg.get("account") and self.require_account() and not st.account_for_player(pid):
            raise GameError("account_required", "登录 Asasfans 账号后才能玩连连看")
        n = st.park_link_played(pid, day)
        if n >= len(cfg["levels"]):
            raise GameError("link_done", "今天的连连看已经玩完了")
        if p["shards"] < cfg["entry"]:
            raise GameError("no_shards", "碎片不足")
        if laid is None or laid[0] != n:
            if not last:
                return n
            laid = (n, *self._lay(n))
        _, kinds, board = laid
        level = cfg["levels"][n]
        st.update_player(pid, shards=p["shards"] - cfg["entry"])
        st.add_ledger(pid, day, LINK_FEE, -cfg["entry"], 1)
        st.add_park_link(pid, day, n + 1, level["rows"], level["cols"], level["shift"], _dump(kinds), _dump(board),
                         level["rows"] * level["cols"] // 2, level["max"], now, now + level["seconds"])
        return None

    def move(self, token: str, game_id: int, seq: int, a: int, b: int, t: int | None = None) -> dict[str, Any]:
        """Takes the [seq]-th pair (a, b) of the game, played [t] ms after the start as the client claims (the arrival
        when absent). Answers {seq, cleared, shuffle?}; a settled game (including one this pair clears or one past
        its time) answers in full with `settled` and `result`. The time is taken on arrival, before waiting for the
        store's lock."""
        cfg = self.cfg
        g = self.park.game
        pid = player_id_for(token)
        now = g.now()
        # The settled answer is read under the same hold of the lock as the settlement.
        with g.store.lock:
            with g.store.transaction() as st:
                row = st.park_link_game(pid, game_id)
                if row is None:
                    raise GameError("no_game", "没有这局连连看")
                if row["settled_at"] is None and now > row["deadline"] + cfg["grace"]:
                    row = self._settle(st, row, "time", now)
                reply = None
                if row["settled_at"] is None:
                    row, reply = self._move(st, row, seq, a, b, t, now)
                result = self._result(row) if reply is None else None
            if reply is not None:
                return reply
            return {"settled": True, **self._answer(token), "result": result}

    def _move(self, st: Store, row: dict[str, Any], seq: int, a: int, b: int, t: int | None,
              now: float) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """In move's transaction: the minimal reply with the row as it was read, or the settled game after the pair
        and None as the reply when the pair cleared the board."""
        events = json.loads(row["events"])
        n = len(events)
        if seq < 0 or seq > n:
            raise GameError("bad_seq", "上报顺序不对")
        if seq < n:
            # A resend: the same pair answers what it answered then, shuffle included.
            ev = events[seq]
            if {ev["a"], ev["b"]} != {a, b}:
                raise GameError("bad_seq", "上报顺序不对")
            return row, self._reply(seq + 1, ev)
        rows, cols = row["rows"], row["cols"]
        board = json.loads(row["board"])
        size = rows * cols
        if not (0 <= a < size and 0 <= b < size) or a == b or board[a] == EMPTY or board[a] != board[b] \
                or not connect(board, rows, cols, a, b):
            raise GameError("bad_move", "这两张牌连不上")
        board = list(remove_pair(board, rows, cols, row["shift"], a, b))
        arrived = round((now - row["started_at"]) * 1000)
        # The claimed time c: at most the arrival plus the slack and, from the second pair on, never before the
        # claim of the pair before; a pair claimed too soon after it is fast. The first pair is never fast, as the
        # start's answer may reach the client late; settlement caps instant play by the arrival instead.
        claimed = min(arrived if t is None else t, arrived + LINK_CLAIM_SLACK_MS)
        ev: dict[str, Any] = {"a": a, "b": b, "t": arrived, "c": claimed}
        if events:
            before = events[-1].get("c", events[-1]["t"])
            ev["c"] = claimed = max(before, claimed)
            if claimed - before < self.park.game.cfg.link_min_pair_ms:
                ev["fast"] = True
        cleared = n + 1
        if cleared < row["total"] and not find_pair(board, rows, cols):
            board = list(shuffle(board, rows, cols, self.park.game.rng))
            ev["shuffle"] = board
        events.append(ev)
        board_json, events_json = _dump(board), _dump(events)
        st.update_park_link(row["id"], board_json, events_json, cleared)
        if cleared < row["total"]:
            # move reads the row only once the game is settled.
            return row, self._reply(cleared, ev)
        row = {**row, "board": board_json, "events": events_json, "cleared": cleared}
        return self._settle(st, row, "clear", now), None

    @staticmethod
    def _reply(seq: int, ev: dict[str, Any]) -> dict[str, Any]:
        reply: dict[str, Any] = {"seq": seq, "cleared": seq}
        if "shuffle" in ev:
            reply["shuffle"] = ev["shuffle"]
        return reply

    def finish(self, token: str, game_id: int) -> dict[str, Any]:
        """Settles the game on the pairs taken so far: reason time once the deadline has passed, quit before. A game
        settled already answers its result again and pays nothing. The time is taken on arrival, as in move."""
        self.cfg
        g = self.park.game
        pid = player_id_for(token)
        now = g.now()
        with g.store.lock:
            with g.store.transaction() as st:
                row = st.park_link_game(pid, game_id)
                if row is None:
                    raise GameError("no_game", "没有这局连连看")
                row = self._settle(st, row, "time" if now >= row["deadline"] else "quit", now)
                result = self._result(row)
            return self._answer(token, result=result)

    def prune(self) -> int:
        """Forgets games settled more than SCRATCH_DAYS ago. Returns rows removed."""
        g = self.park.game
        return g.store.prune_park_link(g.now() - SCRATCH_DAYS * 86400)
