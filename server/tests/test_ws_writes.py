"""Coalesced websocket writes (app/ws_writes.py): the transport stand-in, and a real uvicorn connection through it."""
import asyncio
import json
import socket

import pytest
import uvicorn
import websockets
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute

from app import ws_writes
from app.main import app as server_app
from app.ws_writes import CoalesceWebSocketWrites, CoalescingTransport


class Transport:
    def __init__(self):
        self.writes = []
        self.closed = False
        self.aborted = False

    def write(self, data):
        assert not self.closed
        self.writes.append(data)

    def is_closing(self):
        return self.closed

    def close(self):
        self.closed = True

    def abort(self):
        self.aborted = self.closed = True

    def get_write_buffer_size(self):
        return 0

    def get_extra_info(self, name, default=None):
        return {"peername": ("127.0.0.1", 1)}.get(name, default)


def test_writes_within_one_pass_leave_as_one_in_order():
    async def run():
        real = Transport()
        t = CoalescingTransport(real, asyncio.get_running_loop())
        t.write(b"a")
        t.write(memoryview(b"bc"))
        t.write(b"")
        assert real.writes == []
        assert t.get_write_buffer_size() == 3
        await asyncio.sleep(0)
        assert real.writes == [b"abc"]
        t.write(b"d")
        await asyncio.sleep(0)
        assert real.writes == [b"abc", b"d"]
        # Everything else is the real transport's.
        assert t.get_extra_info("peername") == ("127.0.0.1", 1)
        assert t.wrapped is real
    asyncio.run(run())


def test_close_sends_what_was_held_and_abort_drops_it():
    async def run():
        loop = asyncio.get_running_loop()
        real = Transport()
        t = CoalescingTransport(real, loop)
        t.write(b"close frame")
        t.close()
        assert real.writes == [b"close frame"] and real.closed
        await asyncio.sleep(0)  # the scheduled flush finds nothing left
        assert real.writes == [b"close frame"]

        other = Transport()
        t = CoalescingTransport(other, loop)
        t.write(b"lost")
        t.abort()
        await asyncio.sleep(0)
        assert other.writes == [] and other.aborted
    asyncio.run(run())


def test_writes_held_when_the_connection_closed_underneath_are_dropped():
    async def run():
        real = Transport()
        t = CoalescingTransport(real, asyncio.get_running_loop())
        t.write(b"late")
        real.closed = True
        await asyncio.sleep(0)
        assert real.writes == []
    asyncio.run(run())


def test_only_uvicorns_sansio_protocol_is_wrapped(monkeypatch):
    class WebSocketsSansIOProtocol:
        def __init__(self):
            self.transport = Transport()

        async def send(self, message):
            pass

    class Other(WebSocketsSansIOProtocol):
        pass

    Other.__name__ = "WebSocketProtocol"

    async def run():
        protocol = WebSocketsSansIOProtocol()
        assert ws_writes.coalesce(protocol.send)
        assert isinstance(protocol.transport, CoalescingTransport)
        assert not ws_writes.coalesce(protocol.send)  # once only
        other = Other()
        assert not ws_writes.coalesce(other.send)
        assert not ws_writes.coalesce(lambda message: None)
        monkeypatch.setattr(ws_writes, "ENABLED", False)
        fresh = WebSocketsSansIOProtocol()
        assert not ws_writes.coalesce(fresh.send)
    asyncio.run(run())


def test_the_server_app_puts_the_coalescing_outside_every_other_middleware():
    assert server_app.user_middleware[0].cls is CoalesceWebSocketWrites


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("ws_impl", ["websockets-sansio"])
def test_a_real_uvicorn_connection_gets_every_frame_in_order_from_fewer_writes(monkeypatch, ws_impl):
    flushed = []
    original = CoalescingTransport.flush

    def counting(self):
        if self._pending:
            flushed.append(len(self._pending))
        original(self)

    monkeypatch.setattr(CoalescingTransport, "flush", counting)

    async def endpoint(ws):
        await ws.accept()
        await ws.receive_text()
        for i in range(5):
            await ws.send_text(json.dumps({"n": i}))
        await ws.close()

    inner = Starlette(routes=[WebSocketRoute("/ws", endpoint)])
    port = _free_port()

    async def run():
        config = uvicorn.Config(CoalesceWebSocketWrites(inner), host="127.0.0.1", port=port, ws=ws_impl,
                                log_level="warning", lifespan="off")
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(.01)
        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as client:
                await client.send("go")
                got = [json.loads(await client.recv()) for _ in range(5)]
                assert got == [{"n": i} for i in range(5)]
        finally:
            server.should_exit = True
            await task

    asyncio.run(run())
    # The five frames sent back to back left in one write (handshake and close come on their own).
    assert 5 in flushed or any(n >= 5 for n in flushed)


def test_the_server_apps_websockets_reach_the_coalescing_with_uvicorns_own_send(monkeypatch):
    """Through the whole middleware stack of the real app: a wrapper that changed `send` would turn coalescing off."""
    results = []
    original = ws_writes.coalesce

    def spy(send):
        results.append(original(send))
        return results[-1]

    monkeypatch.setattr(ws_writes, "coalesce", spy)
    port = _free_port()

    async def run():
        config = uvicorn.Config(server_app, host="127.0.0.1", port=port, ws="websockets-sansio",
                                log_level="warning", lifespan="off")
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(.01)
        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as client:
                await client.send(json.dumps({"type": "ping"}))
                assert json.loads(await client.recv()) == {"type": "pong"}
        finally:
            server.should_exit = True
            await task

    asyncio.run(run())
    assert results == [True]
