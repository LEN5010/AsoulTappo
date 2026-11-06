"""Main-site (len5010.top) account lookup: a Bearer token from the desk pet becomes a main user."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .game import GameError

CACHE_SECONDS = 300
CACHE_LIMIT = 10_000

Fetch = Callable[[str, str], tuple[int, dict[str, Any] | None]]


def http_me(url: str, token: str) -> tuple[int, dict[str, Any] | None]:
    """GET <main>/auth/me with the token; returns (status, json)."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                                               "User-Agent": "AsoulTappoServer"})
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, None


class MainAccounts:
    """Resolves tokens through the main site's /auth/me, caching each answer for five minutes."""

    def __init__(self, base_url: str, fetch: Fetch = http_me, now: Callable[[], float] = time.monotonic) -> None:
        self.base_url = base_url.rstrip("/")
        self.fetch = fetch
        self.now = now
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def user_for(self, token: str) -> dict[str, Any]:
        if not token or len(token) > 512:
            raise GameError("account_expired", "请重新登录主站账号")
        key = hashlib.sha256(token.encode()).hexdigest()
        now = self.now()
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > now:
                return hit[1]
        try:
            status, body = self.fetch(f"{self.base_url}/auth/me", token)
        except (OSError, ValueError) as e:
            raise GameError("account_unavailable", "暂时连不上主站，请稍后再试") from e
        user = (body or {}).get("user") if status == 200 else None
        if status == 401 or (status == 200 and not user):
            raise GameError("account_expired", "主站登录已过期，请重新登录")
        if status != 200:
            raise GameError("account_unavailable", "暂时连不上主站，请稍后再试")
        with self._lock:
            if len(self._cache) >= CACHE_LIMIT:
                self._cache.clear()
            self._cache[key] = (now + CACHE_SECONDS, user)
        return user
