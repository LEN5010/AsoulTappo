"""Feedback players send from the settings page: a text, an optional contact, the client's version and system, and,
when the player ticks it, the latest part of the client's log. There are no replies; the main site's admin pages read
it (/admin/feedback).

A save sends PER_SAVE a China day and an address PER_ADDRESS; the server keeps PER_SERVER a day in all, so a script
with many saves and addresses still cannot make it store more than about PER_SERVER x LOG_MAX a day."""
from __future__ import annotations

import threading
from typing import Any

from .game import GameError
from .store import day_of

TEXT_MAX = 1000
CONTACT_MAX = 100
SYSTEM_MAX = 200
VERSION_MAX = 32
LOG_MAX = 128 * 1024
PER_SAVE = 5
PER_ADDRESS = 20
PER_SERVER = 500
ADDRESSES_MAX = 50000

# Feedback per address on a China day: {address: count}, kept for that day only.
_addresses: dict[str, int] = {}
_addresses_day = ""
_addresses_lock = threading.Lock()


def _clip(s: str, n: int) -> str:
    return s.strip()[:n]


def send(store: Any, now: float, pid: str, address: str | None, version: str, system: str, text: str, contact: str,
         log: str) -> dict[str, Any]:
    """Keeps one feedback of the save [pid] (an existing save) sent from [address] (None: not counted). Returns its
    id and how many more the save may send today."""
    global _addresses_day
    text = text.strip()
    if not text:
        raise GameError("bad_feedback", "反馈内容是空的")
    if not store.has_player(pid):
        raise GameError("no_save", "存档还没有建好，请稍后再试")
    day = day_of(now)
    if store.feedback_count(day, pid) >= PER_SAVE:
        raise GameError("feedback_limit", "今天的反馈次数用完了，明天再来吧")
    with _addresses_lock:
        # Counted again under the lock: two feedbacks of a save sent at once both saw the count before either was kept.
        sent = store.feedback_count(day, pid)
        if sent >= PER_SAVE:
            raise GameError("feedback_limit", "今天的反馈次数用完了，明天再来吧")
        if _addresses_day != day or len(_addresses) > ADDRESSES_MAX:
            _addresses.clear()
            _addresses_day = day
        if address is not None and _addresses.get(address, 0) >= PER_ADDRESS:
            raise GameError("feedback_limit", "今天的反馈次数用完了，明天再来吧")
        if store.feedback_count(day) >= PER_SERVER:
            raise GameError("feedback_full", "今天收到的反馈太多了，明天再试吧")
        fid = store.add_feedback(pid, now, day, _clip(version, VERSION_MAX), _clip(system, SYSTEM_MAX),
                                 text[:TEXT_MAX], _clip(contact, CONTACT_MAX), log[-LOG_MAX:])
        if address is not None:
            _addresses[address] = _addresses.get(address, 0) + 1
    return {"id": fid, "left": PER_SAVE - sent - 1}


def admin_view(row: dict[str, Any]) -> dict[str, Any]:
    """A row as the admin pages read it."""
    out = {"id": row["id"], "player": row["player_id"], "mainUserId": row["main_user_id"], "ts": row["ts"],
           "version": row["version"], "system": row["system"], "text": row["text"], "contact": row["contact"],
           "logSize": row["log_size"]}
    if "log" in row:
        out["log"] = row["log"]
    return out
