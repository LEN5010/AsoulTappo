"""Numbers kept for the admin pages: server-wide counts per day, a room sample per minute, and the client each save
last ran. Counts only; never what was said, poked or shown, and never who did it to whom."""
from __future__ import annotations

import threading
from typing import Callable, Iterable, Protocol

from .notice import version_key
from .store import Store, day_of

# Keys of the per-day counts.
COUNT_KEYS = ("room_join", "poke", "profile", "board_profile", "emote", "duel_invite", "cheer_round")
# Saves whose client is remembered; the cache starts over when full.
CLIENT_CACHE_LIMIT = 50000
MAX_VERSION = 32


def client_version(header: str) -> str:
    """The version a client named, without a leading v; "other" for something that is not a version."""
    v = header.strip().removeprefix("v")
    if not v:
        return ""
    return v[:MAX_VERSION] if version_key(v) is not None else "other"


class _Peer(Protocol):
    token: str | None


class _Room(Protocol):
    peers: dict[str, _Peer]
    public: bool
    host: str | None


class Tracker:
    """Counts collect in memory and are written with the minute's room sample, so a crash loses at most a minute
    of them. The client of a save is written when it differs from the one last written."""

    def __init__(self, store: Store, now: Callable[[], float]) -> None:
        self.store = store
        self.now = now
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str], int] = {}
        self._clients: dict[str, str] = {}

    def count(self, key: str, n: int = 1) -> None:
        if n <= 0:
            return
        day = day_of(self.now())
        with self._lock:
            self._counts[(day, key)] = self._counts.get((day, key), 0) + n

    def flush(self) -> None:
        with self._lock:
            counts, self._counts = self._counts, {}
        if counts:
            self.store.add_daily_counts(counts)

    def client(self, pid: str, version_header: str) -> None:
        """Remember the client version of an existing save; a token whose save does not exist yet is tried again
        later."""
        version = client_version(version_header)
        if not version:
            return
        with self._lock:
            if self._clients.get(pid) == version:
                return
        if self.store.set_client(pid, version):
            with self._lock:
                if len(self._clients) >= CLIENT_CACHE_LIMIT:
                    self._clients.clear()
                self._clients[pid] = version

    @staticmethod
    def room_numbers(rooms: Iterable[_Room]) -> dict[str, int]:
        """Rooms with members, members, distinct saves among them, the largest room and the listed public rooms."""
        sizes, saves, public = [], set(), 0
        for room in rooms:
            if not room.peers:
                continue
            sizes.append(len(room.peers))
            saves.update(p.token for p in room.peers.values() if p.token)
            public += bool(room.public and room.host in room.peers)
        return {"rooms": len(sizes), "members": sum(sizes), "saves": len(saves), "largest": max(sizes, default=0),
                "public": public}

    def sample(self, numbers: dict[str, int]) -> None:
        """Write this minute's room sample and the counts so far."""
        minute = int(self.now() // 60 * 60)
        self.store.add_room_sample(minute, numbers)
        self.flush()
