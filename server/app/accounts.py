"""Main-site (len5010.top) account lookup: a Bearer token from the desk pet becomes a main user."""
from __future__ import annotations

import hashlib
import json
import random
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .game import GameError

CACHE_SECONDS = 300
# Each answer is reused for CACHE_SECONDS less up to this much, drawn per answer, so the accounts that all signed in
# again after a restart do not all go back to the main site in the same minute.
CACHE_SPREAD = 120
# A token's last good answer keeps being served this long while the main site fails.
STALE_SECONDS = 3600
# After a failure the main site is not asked again for this long, so a hanging main site does not
# hold a worker thread for every account request.
RETRY_SECONDS = 15
CACHE_LIMIT = 10_000

Fetch = Callable[[str, str], tuple[int, dict[str, Any] | None]]


def http_me(url: str, token: str, key: str = "") -> tuple[int, dict[str, Any] | None]:
    """GET <main>/auth/me with the token; returns (status, json). [key]: the admin key this server shares with the
    main site, sent as X-Game-Key so the main site does not count these lookups against one address's rate limit."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "AsoulTappoServer"}
    if key:
        headers["X-Game-Key"] = key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, None


class MainAccounts:
    """Resolves tokens through the main site's /auth/me, caching each answer for three to five minutes and
    falling back to it for an hour while the main site fails."""

    def __init__(self, base_url: str, fetch: Fetch = http_me, now: Callable[[], float] = time.monotonic,
                 spread: Callable[[], float] = lambda: random.uniform(0, CACHE_SPREAD)) -> None:
        self.base_url = base_url.rstrip("/")
        self.fetch = fetch
        self.now = now
        self.spread = spread
        # token hash -> (when the main site answered, user, until when the answer is reused without asking)
        self._cache: dict[str, tuple[float, dict[str, Any], float]] = {}
        self._retry_at = float("-inf")
        # The last request to the main site failed; cleared by its next answer.
        self._down = False
        self._lock = threading.Lock()

    def user_for(self, token: str) -> dict[str, Any]:
        if not token or len(token) > 512:
            raise GameError("account_expired", "请重新登录主站账号")
        key = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            now = self.now()
            hit = self._cache.get(key)
            if hit and now < hit[2]:
                return hit[1]
            if now < self._retry_at:
                return self._stale(hit, now)
            if self._down:
                # One request tries a failing main site again; the rest keep the fallback until it
                # has an answer, instead of each holding a thread for the timeout.
                self._retry_at = now + RETRY_SECONDS
        try:
            status, body = self.fetch(f"{self.base_url}/auth/me", token)
        except Exception:
            # Any transport failure counts, http.client.HTTPException included (not an OSError).
            status, body = 0, None
        user = (body or {}).get("user") if status == 200 else None
        with self._lock:
            done = self.now()
            self._down = status not in (200, 401)
            if not self._down:
                self._retry_at = float("-inf")
            if status == 401 or (status == 200 and not user):
                self._cache.pop(key, None)
                raise GameError("account_expired", "主站登录已过期，请重新登录")
            if status != 200:
                self._retry_at = done + RETRY_SECONDS
                return self._stale(self._cache.get(key), done)
            if len(self._cache) >= CACHE_LIMIT:
                self._cache.clear()
            self._cache[key] = (done, user, done + CACHE_SECONDS - self.spread())
        return user

    def _stale(self, hit: tuple[float, dict[str, Any], float] | None, now: float) -> dict[str, Any]:
        if hit and now - hit[0] <= STALE_SECONDS:
            return hit[1]
        raise GameError("account_unavailable", "暂时连不上主站，请稍后再试")
