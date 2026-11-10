"""What the operator tells every client: the oldest version still served, and announcements.

Clients from 1.1.3 on send their version with every request (`X-Client-Version`, `?v=` on the room
socket) and read this through the update check. Earlier clients send none: with a minimum set they
are refused like any older version, which shows them an error instead of the update dialog.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

KEY = "notice"
OUTDATED_MESSAGE = "当前版本过旧，请更新到最新版本"
MAX_ANNOUNCEMENTS = 20
# Same forms as `client/src/semver.ts`.
VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def version_key(text: str | None) -> tuple | None:
    """Sort key of a version, a pre-release below its release; None if [text] is not a version."""
    match = VERSION.match(text.strip()) if isinstance(text, str) else None
    if not match:
        return None
    pre = match.group(4)
    # Numeric identifiers sort below alphanumeric ones, a shorter list below a longer one it starts.
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")) if pre else ()
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), 0 if pre else 1, ids)


@dataclass(frozen=True)
class Notice:
    min_version: str = ""
    announcements: list[dict[str, Any]] = field(default_factory=list)

    def outdated(self, version: str | None) -> bool:
        """Whether a client reporting [version] is below the minimum. No or an unreadable version is."""
        floor = version_key(self.min_version)
        if floor is None:
            return False
        have = version_key(version)
        return have is None or have < floor

    def current(self, now: float | None = None) -> list[dict[str, Any]]:
        """Announcements not past their `until` (unix seconds; absent or 0 = no end)."""
        now = time.time() if now is None else now
        return [a for a in self.announcements if not a.get("until") or a["until"] > now]

    def dump(self) -> str:
        return json.dumps({"minVersion": self.min_version, "announcements": self.announcements}, ensure_ascii=False)

    @staticmethod
    def load(raw: str | None) -> "Notice":
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        return Notice(str(data.get("minVersion") or ""), list(data.get("announcements") or []))
