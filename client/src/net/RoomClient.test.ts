import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RoomClient, type RoomEvents, type WsLike } from "./RoomClient";

class FakeWs implements WsLike {
  static all: FakeWs[] = [];
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: WsLike["onopen"] = null;
  onmessage: WsLike["onmessage"] = null;
  onclose: WsLike["onclose"] = null;
  onerror: WsLike["onerror"] = null;
  constructor(public url: string) {
    FakeWs.all.push(this);
  }
  send(d: string) {
    this.sent.push(JSON.parse(d));
  }
  close() {
    this.readyState = 3;
    this.onclose?.({});
  }
  open() {
    this.readyState = 1;
    this.onopen?.({});
  }
  recv(m: unknown) {
    this.onmessage?.({ data: JSON.stringify(m) });
  }
}

function setup() {
  const ev = {
    onConnState: vi.fn(),
    onJoined: vi.fn(),
    onMemberJoined: vi.fn(),
    onMemberLeft: vi.fn(),
    onTap: vi.fn(),
    onMotion: vi.fn(),
    onEmote: vi.fn(),
    onState: vi.fn(),
    onError: vi.fn(),
  } satisfies RoomEvents;
  const c = new RoomClient(ev, {
    createSocket: (u) => new FakeWs(u),
    pingMs: 1000,
    baseDelayMs: 100,
    maxDelayMs: 1000,
  });
  return { c, ev };
}

const INFO = { room: "r", nick: "n", character: "嘉然" };

describe("RoomClient", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeWs.all = [];
  });
  afterEach(() => vi.useRealTimers());

  it("connects to /ws, joins on open and dispatches events", () => {
    const { c, ev } = setup();
    c.join("http://h:1", INFO);
    const ws = FakeWs.all[0];
    expect(ws.url).toBe("ws://h:1/ws");
    ws.open();
    expect(ws.sent[0]).toEqual({ type: "join", ...INFO });
    ws.recv({ type: "joined", room: "r", you: "me", members: [] });
    expect(ev.onJoined).toHaveBeenCalledWith("r", "me", []);
    ws.recv({ type: "tap", id: "x", count: 3, total: 9 });
    expect(ev.onTap).toHaveBeenCalledWith("x", 3, 9);
    ws.recv({ type: "motion_batch", motions: [
      { id: "x", dx: 3, dy: -2, keyDown: false, left: false, right: false },
      { id: "y", dx: 9, dy: 1, keyDown: true, left: true, right: false },
    ] });
    expect(ev.onMotion).toHaveBeenCalledWith("x", { dx: 3, dy: -2, keyDown: false, left: false, right: false });
    expect(ev.onMotion).toHaveBeenCalledWith("y", { dx: 9, dy: 1, keyDown: true, left: true, right: false });
    c.sendTap(2);
    c.sendEmote("thumbup");
    expect(ws.sent.slice(1)).toEqual([
      { type: "tap", count: 2 },
      { type: "emote", emote: "thumbup" },
    ]);
  });

  it("reconnects with backoff and re-joins the room", () => {
    const { c, ev } = setup();
    c.join("http://h:1", INFO);
    FakeWs.all[0].open();
    FakeWs.all[0].close(); // connection drops
    expect(ev.onConnState).toHaveBeenLastCalledWith("reconnecting");
    expect(FakeWs.all).toHaveLength(1);
    vi.advanceTimersByTime(400);
    expect(FakeWs.all).toHaveLength(2);
    FakeWs.all[1].open();
    expect(FakeWs.all[1].sent[0]).toEqual({ type: "join", ...INFO });
  });

  it("leave() stops reconnecting", () => {
    const { c, ev } = setup();
    c.join("http://h:1", INFO);
    FakeWs.all[0].open();
    c.leave();
    expect(ev.onConnState).toHaveBeenLastCalledWith("idle");
    vi.advanceTimersByTime(60000);
    expect(FakeWs.all).toHaveLength(1);
  });

  it("room_full is final: no reconnect, error surfaced", () => {
    const { c, ev } = setup();
    c.join("http://h:1", INFO);
    const ws = FakeWs.all[0];
    ws.open();
    ws.recv({ type: "error", code: "room_full", message: "" });
    expect(ev.onError).toHaveBeenCalledWith("room_full", "");
    vi.advanceTimersByTime(60000);
    expect(FakeWs.all).toHaveLength(1);
  });

  it("forces a reconnect when pongs stop arriving", () => {
    const { c } = setup();
    c.join("http://h:1", INFO);
    const ws = FakeWs.all[0];
    ws.open();
    vi.advanceTimersByTime(1000); // ping #1 sent
    expect(ws.sent.some((m) => m.type === "ping")).toBe(true);
    vi.advanceTimersByTime(1000); // no pong -> close
    expect(ws.readyState).toBe(3);
    vi.advanceTimersByTime(500);
    expect(FakeWs.all).toHaveLength(2);
  });

  it("keeps the connection when pongs arrive", () => {
    const { c } = setup();
    c.join("http://h:1", INFO);
    const ws = FakeWs.all[0];
    ws.open();
    for (let i = 0; i < 3; i++) {
      vi.advanceTimersByTime(1000);
      ws.recv({ type: "pong" });
    }
    expect(ws.readyState).toBe(1);
  });

  it("reports an invalid server URL without throwing", () => {
    const { c, ev } = setup();
    c.join("nonsense", INFO);
    expect(ev.onError).toHaveBeenCalledWith("bad_url", expect.any(String));
    expect(FakeWs.all).toHaveLength(0);
  });

  it("state updates are remembered for re-join", () => {
    const { c } = setup();
    c.join("http://h:1", { ...INFO });
    FakeWs.all[0].open();
    c.sendState({ character: "贝拉" });
    FakeWs.all[0].close();
    vi.advanceTimersByTime(400);
    FakeWs.all[1].open();
    expect(FakeWs.all[1].sent[0]).toMatchObject({ type: "join", character: "贝拉" });
  });
});
