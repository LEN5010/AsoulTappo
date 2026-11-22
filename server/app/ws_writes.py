"""Coalesced writes for websocket connections under uvicorn.

uvicorn writes every websocket frame to the socket on its own. Room messages are a few dozen bytes each and a member
gets several within one room tick (app/rooms.py), so each became its own write on the loopback, its own TLS record at
the proxy and its own packet to the player, with packet headers outweighing the message. CoalescingTransport holds the
frames a connection writes within one pass of the event loop and hands them to the real transport as one write at the
start of the next pass; the frames and their order stay the same, so clients see no difference.

Only uvicorn's websockets-sansio protocol is wrapped: it writes through its `transport` attribute alone. With any
other server or protocol (the tests' TestClient among them) connections are left as they are.
ASOULTAPPO_WS_COALESCE=0 turns it off.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

ENABLED = os.environ.get("ASOULTAPPO_WS_COALESCE", "1") != "0"
# The uvicorn protocol class known to write only through `self.transport`.
PROTOCOLS = frozenset({"WebSocketsSansIOProtocol"})


class CoalescingTransport:
    """Stands in for a transport: write() collects, and the collected bytes go out in one write on the next loop pass.
    close() and write_eof() send what was collected first; abort() drops it. Everything else is the real transport's."""

    def __init__(self, transport: asyncio.Transport, loop: asyncio.AbstractEventLoop) -> None:
        self._transport = transport
        self._loop = loop
        self._pending: list[bytes] = []
        self._scheduled = False

    @property
    def wrapped(self) -> asyncio.Transport:
        return self._transport

    def write(self, data: bytes | bytearray | memoryview) -> None:
        if not data:
            return
        self._pending.append(bytes(data))
        if not self._scheduled:
            self._scheduled = True
            self._loop.call_soon(self.flush)

    def writelines(self, chunks) -> None:
        for chunk in chunks:
            self.write(chunk)

    def flush(self) -> None:
        self._scheduled = False
        if not self._pending:
            return
        data = self._pending[0] if len(self._pending) == 1 else b"".join(self._pending)
        self._pending.clear()
        if not self._transport.is_closing():
            self._transport.write(data)

    def close(self) -> None:
        self.flush()
        self._transport.close()

    def write_eof(self) -> None:
        self.flush()
        self._transport.write_eof()

    def abort(self) -> None:
        self._pending.clear()
        self._transport.abort()

    def get_write_buffer_size(self) -> int:
        return self._transport.get_write_buffer_size() + sum(len(chunk) for chunk in self._pending)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._transport, name)


def coalesce(send: Any) -> bool:
    """Wraps the transport of the uvicorn websocket connection whose ASGI `send` this is; whether it did."""
    protocol = getattr(send, "__self__", None)
    if not ENABLED or protocol is None or type(protocol).__name__ not in PROTOCOLS:
        return False
    transport = getattr(protocol, "transport", None)
    if transport is None or isinstance(transport, CoalescingTransport):
        return False
    protocol.transport = CoalescingTransport(transport, asyncio.get_running_loop())
    return True


class CoalesceWebSocketWrites:
    """ASGI middleware: coalesces the writes of each websocket connection (see the module docstring). It has to sit
    where `send` is still uvicorn's own: outside every middleware that wraps it for websockets."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket":
            coalesce(send)
        await self.app(scope, receive, send)
