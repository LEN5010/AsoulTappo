"""Telling automatic input (an auto-clicker, a macro) from a hand, kept out of the public repository.

The server hands every batch of a session's taps to a guard and takes back how long the save's input counts as
automatic. While it does, the save's status says so (``autoInput``, see protocol/PROTOCOL.md); nothing is taken from
its income.

Rooms count hands only. A client that tells which presses other software sent keeps those out of its rooms, so the
server asks a second time about the rest of each batch (``taps - injected``, with notes of its own) and rooms stop
showing the save's taps and motion while that answer holds. From a client that cannot tell, the first answer hides it.

The rules live in a Python file named by ``ASOULTAPPO_GUARD``, next to the economy file on the server. It defines
``judge(batch, notes)`` with the meaning of ``Guard.judge`` below. Without the variable nothing is judged.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ENV = "ASOULTAPPO_GUARD"


@dataclass(frozen=True)
class Batch:
    """One report of a session, as sent: before the rate limit and the cooldown take anything from it."""
    taps: int
    # Of those, how many other software sent; None from a client that cannot tell.
    injected: int | None
    # Seconds since the session's batch before this one; 0 for its first.
    elapsed: float
    now: float


class Guard:
    """Judges nothing: every batch is a hand's."""

    def judge(self, batch: Batch, notes: dict[str, Any]) -> float:
        """Seconds from ``batch.now`` for which the save's input counts as automatic; 0 for a hand's. ``notes`` is
        what this session's earlier calls left in it (JSON values only, empty at first) and is kept for the next."""
        return 0.0


class FileGuard(Guard):
    def __init__(self, judge: Callable[[Batch, dict[str, Any]], float]) -> None:
        self._judge = judge

    def judge(self, batch: Batch, notes: dict[str, Any]) -> float:
        return max(0.0, float(self._judge(batch, notes)))


def load(path: Path | str | None = None) -> Guard:
    """The guard of the file at [path], else of the file ``ASOULTAPPO_GUARD`` names, else the one judging nothing."""
    path = path or os.environ.get(ENV)
    if not path:
        return Guard()
    spec = importlib.util.spec_from_file_location("asoultappo_guard", Path(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{ENV}: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    judge = getattr(module, "judge", None)
    if not callable(judge):
        raise RuntimeError(f"{ENV}: {path} defines no judge(batch, notes)")
    return FileGuard(judge)
