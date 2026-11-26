"""Local status/presence/activity timings and room-motion traffic.

Run from the repository root: server/.venv/bin/python scripts/benchmark_server.py
Uses a temporary SQLite database and in-process socket sinks.

`--root <checkout>` measures another checkout with the same room-tick protocol.

Room traffic is what the server writes to one member's connection, counted three ways:
- JSON: the message text as Starlette serializes it.
- wire: the same messages through permessage-deflate as the server negotiates it (one zlib stream per
  connection, 4 KiB window, sync flush per message) plus the WebSocket frame header. TLS is not counted.
- binary: an estimate for the packed motion portion in a fixed binary layout (see `binary_size`),
  uncompressed, with the same frame header.
Members move the mouse layer along smooth two-axis curves; "typing" adds key presses and taps.
The server flushes every 100ms. Versions 1 and 2 send button edges immediately, version 3 batches
them with positions, and version 4 sends those batches and taps together as `room_tick`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
import zlib

TICK_MS = 50
ROOM_TICK_MS = 100
SECONDS = 20


def timings(fn, iterations: int) -> dict:
    for _ in range(20):
        fn()
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {"median_ms": round(statistics.median(samples), 3),
            "p95_ms": round(samples[math.ceil(len(samples) * .95) - 1], 3)}


def database(root: Path, iterations: int) -> dict:
    from app.game import Game, player_id_for
    from app.manifest import Manifest
    from app.store import Store

    manifest = Manifest.load(root / "assets-packs" / "manifest.json", economy=root / "server" / "economy.example.json")
    rows = []
    with tempfile.TemporaryDirectory(prefix="tappo-bench-") as directory:
        store = Store(str(Path(directory) / "bench.db"))
        # Each call is two seconds after the last, so activity reports are credited rather than rate-limited.
        clock = [1_800_000_000.0]

        def now() -> float:
            clock[0] += 2
            return clock[0]

        game = Game(store, manifest, now=now)
        ids = sorted(game.collectible_ids)
        mode = store._db.execute("PRAGMA journal_mode").fetchone()[0]
        for count in (0, 50, len(ids)):
            token = f"benchmark-player-{count:04d}"
            pid = player_id_for(token)
            game.status(token)
            with store.transaction():
                store.add_items(pid, dict.fromkeys(ids[:count], 1), time.time())
            sequence = [0]

            def activity() -> None:
                sequence[0] += 1
                game.report_activity(token, 1, "benchmark-session-0001", sequence[0])

            rows.append({"owned": count,
                         "status": timings(lambda: game.status(token), iterations),
                         "presence": timings(lambda: game.presence(token, "benchmark-session-0001"), iterations),
                         "activity": timings(activity, iterations)})
        store.close()
    return {"journal_mode": mode, "rows": rows}


def binary_size(data: dict) -> int:
    """Bytes of a fixed layout for packed motion: a type byte, then per member a room slot byte, a byte
    naming the fields that follow, and one signed byte per field (quarter pixels fit -80..80)."""
    motions = data.get("motions") or data.get("edges") or [data]
    return 2 + 1 + sum(2 + sum(key in motion for key in ("x", "y", "b")) for motion in motions)


class Socket:
    def __init__(self):
        self.deflate = zlib.compressobj(6, zlib.DEFLATED, -12)
        self.reset_counts()

    def reset_counts(self):
        self.messages = self.json = self.wire = self.binary = 0
        self.taps = self.tap_messages = self.room_ticks = 0

    async def send_json(self, data):
        kind = data["type"]
        if kind == "benchmark_marker":
            return
        text = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
        self.messages += 1
        self.json += len(text)
        # permessage-deflate drops the four bytes that end a sync flush.
        payload = len(self.deflate.compress(text) + self.deflate.flush(zlib.Z_SYNC_FLUSH)) - 4
        self.wire += payload + (2 if payload < 126 else 4)
        if kind in ("motion_delta", "motion_edge", "motion_edges", "motion_snapshot"):
            self.binary += binary_size(data)
        elif kind == "tap":
            self.tap_messages += 1
            self.taps += data["count"]
        elif kind == "room_tick":
            self.room_ticks += 1
            self.taps += sum(tap["count"] for tap in data["taps"])
            if data["motions"]:
                self.binary += binary_size(data)

    async def close(self, code=1000):
        pass


def curve(member: int, tick: int) -> tuple[float, float]:
    t = tick * TICK_MS / 1000
    return (20 * math.sin(t * 4.4 + member * 1.7), 20 * math.sin(t * 3.1 + member * .9))


async def room(manager_type, size: int, moving: int, shown: int | None, typing: bool, version: int) -> dict:
    """[shown]: how many other members the watched client displays (packed motion only; older clients
    hear everyone). The watched client is the last member and sits still."""
    packed = version >= 2
    send_every = 2 if packed else 1  # client: 100ms with packed motion, 50ms before
    flush_every = ROOM_TICK_MS // TICK_MS
    step = 4 if packed else 10  # quarter pixels, tenths before
    # Flushed by hand below, one simulated tick at a time.
    manager = manager_type(motion_interval=60)
    peers = [manager.join("benchmark", str(i), "嘉然", Socket()) for i in range(size)]
    current = manager.rooms["benchmark"]
    for peer in peers:
        peer.motion_version = version
    resting = {"dx": 0.0, "dy": 0.0, "keyDown": False, "left": False, "right": False}
    sent: list[dict | None] = [None] * size
    uplink = [0] * size
    tap_uplink = [0] * size
    if packed:
        watcher = peers[-1]
        others = [p.id for p in peers[:-1]]
        manager.subscribe_motion("benchmark", watcher, others if shown is None else others[:shown])
        # Everyone else shows the whole room.
        for peer in peers[:-1]:
            manager.subscribe_motion("benchmark", peer, [p.id for p in peers])

    async def move(i: int, pose: dict) -> None:
        if not packed:
            uplink[i] += len(json.dumps({"type": "motion", **pose}, separators=(",", ":")))
            await manager.motion("benchmark", peers[i], pose)
            return
        now = {"x": round(pose["dx"] * 4), "y": round(pose["dy"] * 4),
               "b": int(pose["keyDown"]) | int(pose["left"]) << 1 | int(pose["right"]) << 2}
        patch = {k: v for k, v in now.items() if sent[i] is None or sent[i][k] != v}
        sent[i] = now
        if patch:
            uplink[i] += len(json.dumps({"type": "pose", **patch}, separators=(",", ":")))
            await manager.pose("benchmark", peers[i], patch)

    async def flush() -> None:
        manager._flush_tick(current)
        # An ordered marker waits for the tick to reach every sink without adding to its traffic.
        await asyncio.gather(*(peer.send({"type": "benchmark_marker"}, 2) for peer in peers))

    ticks = SECONDS * 1000 // TICK_MS
    for i in range(size):
        await move(i, resting)
    await flush()
    for peer in peers:
        peer.ws.reset_counts()
    uplink = [0] * size
    held = [False] * size
    for tick in range(ticks):
        for i in range(moving):
            x, y = curve(i, tick)
            pose = {**resting, "dx": round(x * step) / step, "dy": round(y * step) / step, "keyDown": held[i]}
            # A press every 150ms, held for 50ms, with one tap per press.
            if typing and (tick + i) % 3 == 0:
                held[i] = True
                await move(i, {**pose, "keyDown": True})
                peers[i].taps += 1
                manager.tap("benchmark", peers[i], 1)
                tap_uplink[i] += len('{"type":"tap","count":1}')
            elif held[i]:
                held[i] = False
                await move(i, {**pose, "keyDown": False})
            elif tick % send_every == 0:
                await move(i, pose)
        if tick % flush_every == flush_every - 1:
            await flush()
    watched = peers[-1].ws
    kib = lambda n: round(n / SECONDS / 1024, 2)  # noqa: E731
    result = {"members": size, "moving": moving, "typing": typing, "motion_version": version,
              "edges_batched": version >= 3,
              "shown": size - 1 if shown is None or not packed else shown,
              "client_messages_per_s": round(watched.messages / SECONDS, 1),
              "client_json_KiB_per_s": kib(watched.json), "client_wire_KiB_per_s": kib(watched.wire),
              "client_taps_per_s": round(watched.taps / SECONDS, 1),
              "client_tap_messages_per_s": round(watched.tap_messages / SECONDS, 1),
              "client_room_ticks_per_s": round(watched.room_ticks / SECONDS, 1),
              "room_messages_per_s": round(sum(p.ws.messages for p in peers) / SECONDS, 1),
              "room_wire_KiB_per_s": kib(sum(p.ws.wire for p in peers)),
              "mover_uplink_json_KiB_per_s": kib(uplink[0] + tap_uplink[0]),
              "mover_tap_uplink_json_KiB_per_s": kib(tap_uplink[0])}
    if packed:
        result["client_binary_KiB_per_s"] = kib(watched.binary)
    for peer in peers:
        manager.leave("benchmark", peer.id)
    return result


async def motion() -> dict:
    from app.rooms import RoomManager

    scenarios = [(2, 1, None, False), (6, 5, None, False), (20, 1, None, False), (20, 19, None, False),
                 (20, 19, None, True)]
    subscriptions = [(20, 19, 5, False), (20, 19, 5, True), (20, 19, 0, True)]
    rows = [await room(RoomManager, *scenario, version) for version in (1, 2, 3, 4)
            for scenario in (scenarios if version == 1 else scenarios + subscriptions)]
    return {"room_tick_ms": ROOM_TICK_MS, "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="checkout to measure (default: the one this script is in)")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    root = args.root.resolve()
    sys.path.insert(0, str(root / "server"))
    print(json.dumps({"python": platform.python_version(), "platform": platform.platform(), "root": str(root),
                      "iterations": args.iterations, "database": database(root, args.iterations),
                      "motion": asyncio.run(motion())}, ensure_ascii=False, indent=2))
