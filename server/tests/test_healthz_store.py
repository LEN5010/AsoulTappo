import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pytest

from app import main, store as store_module
from app.store import Store


@pytest.fixture
def store(monkeypatch):
    db = Store()
    monkeypatch.setattr(main.game, "store", db)
    yield db
    db.close()


def test_store_probe_is_public_and_read_only(store):
    store._db.execute("PRAGMA query_only=ON")
    statements = []
    store._db.set_trace_callback(statements.append)
    response = TestClient(main.app).get("/healthz/store")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["waited"] >= 0
    assert len(statements) == 1 and statements[0].startswith("SELECT ")
    assert store._db.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0


def test_store_probe_waits_for_lock_in_threadpool(store, monkeypatch):
    ticks = iter([100, 103.1256])
    monkeypatch.setattr(store_module, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    lock = store.lock

    async def run():
        entered = asyncio.Event()
        loop = asyncio.get_running_loop()

        class SignaledLock:
            def __enter__(self):
                loop.call_soon_threadsafe(entered.set)
                lock.acquire()

            def __exit__(self, *exc):
                lock.release()

        with monkeypatch.context() as patch:
            patch.setattr(store, "_lock", SignaledLock())
            async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
                with lock:
                    pending = asyncio.create_task(client.get("/healthz/store"))
                    await asyncio.wait_for(entered.wait(), timeout=2)
                    assert not pending.done()
                    assert (await client.get("/healthz")).json()["status"] == "ok"
                response = await asyncio.wait_for(pending, timeout=2)
                assert response.json() == {"status": "ok", "waited": 3.126}

    asyncio.run(run())
