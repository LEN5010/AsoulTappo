"""Main-site (len5010.top) account lookup: a Bearer token from the desk pet becomes a main user."""
from __future__ import annotations

import hashlib
import http.client
import json
import random
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import Future
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

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
HTTP_TIMEOUT = 8
IDLE_LIMIT = 8

Fetch = Callable[[str, str], tuple[int, dict[str, Any] | None]]

_DEFAULT_URLOPEN = urllib.request.urlopen
_idle: deque[tuple[tuple[str, str], http.client.HTTPConnection]] = deque()
_pool_lock = threading.Lock()


def _urllib_me(url: str, headers: dict[str, str]) -> tuple[int, dict[str, Any] | None]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, None


# The handlers of the opener urlopen builds for itself (and keeps in urllib.request._opener after its first call).
_PLAIN_HANDLERS = tuple(type(h) for h in urllib.request.build_opener().handlers)


def _proxied(req: urllib.request.Request, proxies: dict[str, str]) -> bool:
    """Whether urllib sends [req] through one of [proxies]: there is one for its scheme and its host is not left out
    (NO_PROXY, or the system's exceptions), as urllib.request.ProxyHandler decides."""
    return bool(proxies.get(req.type)) and not urllib.request.proxy_bypass(req.host)


def _opener_does_more(req: urllib.request.Request) -> bool:
    """Whether the opener urlopen uses does more for [req] than connect to its host: one installed with install_opener
    that has a handler of its own, or one whose proxies take [req] (urlopen's own has the proxies of its first
    call)."""
    opener = getattr(urllib.request, "_opener", None)
    if opener is None:
        return False
    return any(type(h) not in _PLAIN_HANDLERS
               or (isinstance(h, urllib.request.ProxyHandler) and _proxied(req, h.proxies)) for h in opener.handlers)


def _needs_urllib(url: str) -> bool:
    """Whether a request to [url] has to go through urllib.request.urlopen rather than a kept connection to its host:
    urlopen was replaced, its opener does more (_opener_does_more), or a proxy takes the request (HTTPS_PROXY and the
    like, or the system's), so the host may not be reachable but through the proxy."""
    req = urllib.request.Request(url)
    if urllib.request.urlopen is not _DEFAULT_URLOPEN or _opener_does_more(req):
        return True
    return _proxied(req, urllib.request.getproxies())


def http_me(url: str, token: str, key: str = "") -> tuple[int, dict[str, Any] | None]:
    """GET <main>/auth/me with the token; returns (status, json). [key]: the admin key this server shares with the
    main site, sent as X-Game-Key so the main site does not count these lookups against one address's rate limit.
    A direct request reuses a connection kept from the last one to the same host (up to IDLE_LIMIT are kept)."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "AsoulTappoServer"}
    if key:
        headers["X-Game-Key"] = key
    if _needs_urllib(url):
        return _urllib_me(url, headers)

    parts = urlsplit(url)
    origin = (parts.scheme, parts.netloc)
    path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
    connect = {"http": http.client.HTTPConnection, "https": http.client.HTTPSConnection}[parts.scheme]
    with _pool_lock:
        entry = next((entry for entry in reversed(_idle) if entry[0] == origin), None)
        if entry is not None:
            _idle.remove(entry)
    conn = entry[1] if entry is not None else connect(parts.netloc, timeout=HTTP_TIMEOUT)
    while True:
        try:
            conn.request("GET", path, headers=headers)
            with conn.getresponse() as res:
                status = res.status
                redirect = status in (301, 302, 303, 307, 308) and res.getheader("Location")
                body = res.read()
        except (OSError, http.client.HTTPException) as exc:
            conn.close()
            if entry is None or isinstance(exc, TimeoutError):
                raise
            # The upstream can close an idle socket before its next request.
            entry = None
            conn = connect(parts.netloc, timeout=HTTP_TIMEOUT)
        else:
            break
    if conn.sock is not None:
        with _pool_lock:
            if len(_idle) >= IDLE_LIMIT:
                _idle.popleft()[1].close()
            _idle.append((origin, conn))
    if redirect:
        return _urllib_me(url, headers)
    return status, json.loads(body) if 200 <= status < 300 else None


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
        self._pending: dict[str, Future[dict[str, Any]]] = {}
        self._retry_at = float("-inf")
        # The last request to the main site failed; cleared by its next answer.
        self._down = False
        self._lock = threading.Lock()

    def cached_user(self, token: str) -> dict[str, Any] | None:
        """A fresh answer can be used without waiting for an upstream lookup slot."""
        if not token or len(token) > 512:
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            hit = self._cache.get(key)
            return hit[1] if hit and self.now() < hit[2] else None

    def user_for(self, token: str) -> dict[str, Any]:
        if not token or len(token) > 512:
            raise GameError("account_expired", "请重新登录主站账号")
        key = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            now = self.now()
            hit = self._cache.get(key)
            if hit and now < hit[2]:
                return hit[1]
            pending = self._pending.get(key)
            refresh = pending is None
            if pending is None:
                if now < self._retry_at:
                    return self._stale(hit, now)
                if self._down:
                    # While one request retries the main site, other tokens use their fallback.
                    self._retry_at = now + RETRY_SECONDS
                pending = self._pending[key] = Future()
        if refresh:
            try:
                pending.set_result(self._refresh(key, token))
            except Exception as exc:
                pending.set_exception(exc)
            finally:
                with self._lock:
                    del self._pending[key]
        return pending.result()

    def _refresh(self, key: str, token: str) -> dict[str, Any]:
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
            if key not in self._cache and len(self._cache) >= CACHE_LIMIT:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (done, user, done + CACHE_SECONDS - self.spread())
        return user

    def _stale(self, hit: tuple[float, dict[str, Any], float] | None, now: float) -> dict[str, Any]:
        if hit and now - hit[0] <= STALE_SECONDS:
            return hit[1]
        raise GameError("account_unavailable", "暂时连不上主站，请稍后再试")
