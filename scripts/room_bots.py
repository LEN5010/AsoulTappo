"""Five room members who keep moving the mouse, typing and counting taps, for measuring a client that shows them.

Run from the repository root against a local server:
  server/.venv/bin/python scripts/room_bots.py new <room> <seconds> [mouse,keys,taps] [ws://127.0.0.1:8010/ws]
`old`: full poses at 20 Hz (clients up to 1.1.3); `new`: packed poses at 10 Hz, subscribed to the whole room
like a client showing everyone. The fourth argument picks what they do (default: all three).
"""
import asyncio, json, math, sys
import websockets

MODE, ROOM, SECONDS = sys.argv[1], sys.argv[2], float(sys.argv[3])
WHAT = sys.argv[4] if len(sys.argv) > 4 else "mouse,keys,taps"
URL = sys.argv[5] if len(sys.argv) > 5 else "ws://127.0.0.1:8010/ws"

async def member(i):
    async with websockets.connect(f"{URL}?v=1.1.3") as ws:
        join = {"type": "join", "room": ROOM, "nick": f"bot{i}", "character": ["嘉然", "乃琳", "贝拉", "心宜", "思诺"][i % 5]}
        if MODE == "new":
            join["motionVersion"] = 2
        await ws.send(json.dumps(join))
        ids = set()
        async def listen():
            async for raw in ws:
                m = json.loads(raw)
                if MODE != "new":
                    continue
                before = len(ids)
                if m["type"] == "joined":
                    ids.update(x["id"] for x in m["members"] if x["id"] != m["you"])
                elif m["type"] == "member_joined":
                    ids.add(m["member"]["id"])
                elif m["type"] == "member_left":
                    ids.discard(m["id"])
                if len(ids) != before:
                    await ws.send(json.dumps({"type": "motion_subscribe", "ids": sorted(ids)}))
        task = asyncio.create_task(listen())
        step = .1 if MODE == "new" else .05
        sent = None
        t = 0.0
        while t < SECONDS:
            x, y = (20 * math.sin(t * 4.4 + i * 1.7), 20 * math.sin(t * 3.1 + i * .9)) if "mouse" in WHAT else (0, 0)
            key = "keys" in WHAT and int(t * 3 + i * .2) % 2 == 0 and (t * 3 + i * .2) % 1 < .3
            if MODE == "new":
                now = {"x": round(x * 4), "y": round(y * 4), "b": int(key)}
                patch = {k: v for k, v in now.items() if sent is None or sent[k] != v}
                sent = now
                if patch:
                    await ws.send(json.dumps({"type": "pose", **patch}))
            else:
                now = {"type": "motion", "dx": round(x, 1), "dy": round(y, 1), "keyDown": key, "left": False, "right": False}
                if now != sent:  # like the real sender: nothing goes out while the pose stays the same
                    sent = now
                    await ws.send(json.dumps(now))
            if "taps" in WHAT and int(t / step) % 10 == 0:
                await ws.send(json.dumps({"type": "tap", "count": 2}))
            await asyncio.sleep(step)
            t += step
        task.cancel()

async def main():
    await asyncio.gather(*(member(i) for i in range(5)))
asyncio.run(main())
