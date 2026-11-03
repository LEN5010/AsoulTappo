"""WebSocket room client interface (stub).

Part of AsoulTappo (GPL-2.0). Message format: protocol/PROTOCOL.md.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Protocol


class RoomEvents(Protocol):
    """Callbacks the UI implements (must be marshalled onto the Qt thread)."""

    def on_joined(self, room: str, you: str, members: list[dict]) -> None: ...
    def on_member_joined(self, member: dict) -> None: ...
    def on_member_left(self, member_id: str) -> None: ...
    def on_tap(self, member_id: str, count: int, total: int) -> None: ...
    def on_emote(self, member_id: str, emote: str) -> None: ...
    def on_state(self, member_id: str, character: str) -> None: ...
    def on_error(self, code: str, message: str) -> None: ...


class RoomClient:
    """Interface for talking to the server. TODO: implement over WebSocket
    (e.g. ``websockets`` in a worker thread or ``QtWebSockets``)."""

    def connect(self, server_url: str, events: RoomEvents) -> None:
        raise NotImplementedError("TODO: open WebSocket to <server_url>/ws")

    def join(self, room: str, nick: str, character: str) -> None:
        raise NotImplementedError

    def leave(self) -> None:
        raise NotImplementedError

    def send_tap(self, count: int) -> None:
        raise NotImplementedError

    def send_emote(self, emote: str) -> None:
        raise NotImplementedError

    def send_state(self, character: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class NullRoomClient(RoomClient):
    """Offline no-op client so the desktop pet keeps working without a server."""

    def connect(self, server_url: str, events: RoomEvents) -> None: pass
    def join(self, room: str, nick: str, character: str) -> None: pass
    def leave(self) -> None: pass
    def send_tap(self, count: int) -> None: pass
    def send_emote(self, emote: str) -> None: pass
    def send_state(self, character: str) -> None: pass
    def close(self) -> None: pass


class TapBatcher:
    """Accumulates tap *counts* and flushes at most every ``interval`` seconds.

    Privacy: only an integer count is kept — never which key was pressed.
    Call ``add()`` from the input listener and ``poll()`` from a timer.
    """

    def __init__(self, send: Callable[[int], None], interval: float = 0.25) -> None:
        self._send = send
        self._interval = interval
        self._pending = 0
        self._last = time.monotonic()

    def add(self, n: int = 1) -> None:
        self._pending += n

    def poll(self, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        if self._pending and now - self._last >= self._interval:
            n, self._pending = self._pending, 0
            self._last = now
            self._send(n)
