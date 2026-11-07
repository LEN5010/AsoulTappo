"""Newest desk pet release, read from the main site's release list for the panel's update check.

Many players cannot reach GitHub, and the main site's API does not answer the desk pet's webview
on this path, so the panel asks its room server. The main site lists AsoulTappo's GitHub releases
newest first, pre-releases included (`<main api>/tappo/release`).
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from typing import Any, Callable

FRESH_SECONDS = 600
RETRY_SECONDS = 60
# A last good answer keeps being served this long while the main site fails.
STALE_SECONDS = 24 * 3600
NOTES_LIMIT = 4000
VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")

Fetch = Callable[[str], Any]


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AsoulTappoServer"})
    with urllib.request.urlopen(req, timeout=8) as res:
        return json.loads(res.read())


def newest(feed: Any) -> dict[str, str] | None:
    """The first release in the main site's list as {version, notes}, or None if it has none."""
    releases = feed.get("releases") if isinstance(feed, dict) else None
    first = releases[0] if isinstance(releases, list) and releases else None
    version = first.get("version") if isinstance(first, dict) else None
    if not isinstance(version, str) or not VERSION.match(version):
        return None
    notes = first.get("notes")
    return {"version": version, "notes": notes[:NOTES_LIMIT] if isinstance(notes, str) else ""}


class ReleaseFeed:
    """Asks the main site at most every ten minutes, and a minute after a failure."""

    def __init__(self, url: str, fetch: Fetch = http_json, now: Callable[[], float] = time.monotonic) -> None:
        self.url = url
        self.fetch = fetch
        self.now = now
        self._lock = threading.Lock()
        self._latest: dict[str, str] | None = None
        self._got = float("-inf")
        self._next = float("-inf")
        self._fetching = False

    def latest(self) -> dict[str, str] | None:
        """The cached release; refreshes it when due. The main site is asked outside the lock and by
        one caller at a time, so a slow main site never holds up other requests or worker threads."""
        with self._lock:
            now = self.now()
            due = now >= self._next and not self._fetching
            if due:
                self._fetching = True
            else:
                return self._fresh(now)
        try:
            found = newest(self.fetch(self.url))
        except (OSError, ValueError):
            found = None
        with self._lock:
            self._fetching = False
            done = self.now()
            if found:
                self._latest, self._got, self._next = found, done, done + FRESH_SECONDS
            else:
                self._next = done + RETRY_SECONDS
            return self._fresh(done)

    def _fresh(self, now: float) -> dict[str, str] | None:
        return self._latest if now - self._got <= STALE_SECONDS else None
