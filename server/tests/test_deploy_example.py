"""The example deployment (deploy/): the server sees each visitor's own address behind Caddy, so per-address limits
count visitors, not the proxy."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import app.main as main

from test_accounts import env  # noqa: F401  (env is a fixture)

yaml = pytest.importorskip("yaml")
COMPOSE = Path(__file__).resolve().parents[2] / "deploy" / "docker-compose.yml"


def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def caddy_address(spec):
    [net] = spec["services"]["caddy"]["networks"].values()
    return net["ipv4_address"]


def option(command, name):
    return command[command.index(name) + 1]


def test_the_server_trusts_only_the_proxys_fixed_address():
    spec = compose()
    command = spec["services"]["server"]["command"]
    assert command[:2] == ["uvicorn", "app.main:app"]
    assert "--proxy-headers" in command
    assert option(command, "--forwarded-allow-ips") == caddy_address(spec)
    # As in the image's own command: app/ws_writes.py coalesces writes only for this protocol.
    assert option(command, "--ws") == "websockets-sansio"
    # Both services sit on the network that holds the proxy's address.
    [name] = spec["services"]["caddy"]["networks"]
    assert name in spec["services"]["server"]["networks"]


def test_visitors_behind_the_proxy_have_lookups_of_their_own(env, monkeypatch):
    monkeypatch.setattr(main, "ROOM_LOOKUPS", 1)
    monkeypatch.setattr(main, "_room_lookups", {})
    proxy = caddy_address(compose())
    c = TestClient(ProxyHeadersMiddleware(main.app, trusted_hosts=proxy), client=(proxy, 40000))
    one, two = {"X-Forwarded-For": "198.51.100.1"}, {"X-Forwarded-For": "198.51.100.2"}
    assert c.get("/rooms/a", headers=one).status_code == 200
    assert c.get("/rooms/a", headers=one).status_code == 429
    assert c.get("/rooms/a", headers=two).status_code == 200
    # Anyone else claiming an address is counted as itself.
    other = TestClient(ProxyHeadersMiddleware(main.app, trusted_hosts=proxy), client=("198.51.100.9", 40000))
    assert other.get("/rooms/a", headers={"X-Forwarded-For": "198.51.100.3"}).status_code == 200
    assert other.get("/rooms/a", headers={"X-Forwarded-For": "198.51.100.4"}).status_code == 429
