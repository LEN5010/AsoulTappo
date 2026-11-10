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
    onRoomInfo: vi.fn(),
    onMemberJoined: vi.fn(),
    onMemberLeft: vi.fn(),
    onTap: vi.fn(),
    onMotion: vi.fn(),
    onEmote: vi.fn(),
    onScratch: vi.fn(),
    onState: vi.fn(),
    onDuel: vi.fn(),
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

  it("drops a dead connection at once instead of waiting for its close handshake", () => {
    const { c, ev } = setup();
    c.join("http://h:1", INFO);
    const dead = FakeWs.all[0];
    let closeCalled = false;
    dead.close = () => { closeCalled = true; }; // a dead peer never answers the close frame
    dead.open();
    vi.advanceTimersByTime(1000); // ping #1
    vi.advanceTimersByTime(1000); // no pong
    expect(closeCalled).toBe(true);
    expect(ev.onConnState).toHaveBeenLastCalledWith("reconnecting");
    vi.advanceTimersByTime(400);
    expect(FakeWs.all).toHaveLength(2);
    FakeWs.all[1].open();
    expect(ev.onConnState).toHaveBeenLastCalledWith("open");
    dead.readyState = 3;
    dead.onclose?.({}); // the late close of the abandoned socket
    expect(ev.onConnState).toHaveBeenLastCalledWith("open");
    vi.advanceTimersByTime(900); // past any backoff, before the new socket's first ping
    expect(FakeWs.all).toHaveLength(2);
  });

  it("a join rejected as invalid is final: no reconnect, error surfaced", () => {
    const { c, ev } = setup();
    c.join("http://h:1", INFO);
    const ws = FakeWs.all[0];
    ws.open();
    ws.recv({ type: "error", code: "bad_message", message: "invalid message" });
    expect(ev.onError).toHaveBeenCalledWith("bad_message", "invalid message");
    expect(ev.onConnState).toHaveBeenLastCalledWith("idle");
    vi.advanceTimersByTime(60000);
    expect(FakeWs.all).toHaveLength(1);
  });

  it("a bad message after joining keeps the connection", () => {
    const { c, ev } = setup();
    c.join("http://h:1", INFO);
    const ws = FakeWs.all[0];
    ws.open();
    ws.recv({ type: "joined", room: "r", you: "me", members: [] });
    ws.recv({ type: "error", code: "bad_message", message: "invalid message" });
    expect(ev.onError).toHaveBeenCalledWith("bad_message", "invalid message");
    expect(ev.onConnState).toHaveBeenLastCalledWith("open");
    expect(ws.readyState).toBe(1);
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

  it("reports the host and public flag from joined and room_info, and null from older servers", () => {
    const { c, ev } = setup();
    c.join("http://h:1", INFO);
    const ws = FakeWs.all[0];
    ws.open();
    ws.recv({ type: "joined", room: "r", you: "me", members: [] });
    expect(ev.onRoomInfo).toHaveBeenLastCalledWith(null);
    ws.recv({ type: "joined", room: "r", you: "me", members: [], info: { host: "me", public: false } });
    expect(ev.onRoomInfo).toHaveBeenLastCalledWith({ host: "me", public: false });
    ws.recv({ type: "room_info", host: "x", public: true });
    expect(ev.onRoomInfo).toHaveBeenLastCalledWith({ host: "x", public: true });
    c.sendSetPublic(true);
    c.sendKick("x");
    expect(ws.sent.slice(1)).toEqual([{ type: "set_public", public: true }, { type: "kick", id: "x" }]);
  });

  it.each(["kicked", "banned", "need_save"])("a room_full with reason %s is final and reported as that reason", (reason) => {
    const { c, ev } = setup();
    c.join("http://h:1", INFO);
    const ws = FakeWs.all[0];
    ws.open();
    ws.recv({ type: "joined", room: "r", you: "me", members: [], info: { host: "x", public: false } });
    ws.recv({ type: "error", code: "room_full", message: "你已被移出这个房间", reason });
    expect(ev.onError).toHaveBeenCalledWith(reason, "你已被移出这个房间");
    expect(ev.onConnState).toHaveBeenLastCalledWith("idle");
    expect(ws.sent.at(-1)).toEqual({ type: "leave" });
    // the server closing the socket afterwards does not bring the client back
    ws.onclose?.({});
    vi.advanceTimersByTime(60000);
    expect(FakeWs.all).toHaveLength(1);
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

  it("a plate put on or taken off is remembered for re-join", () => {
    const { c } = setup();
    c.join("http://h:1", { ...INFO });
    FakeWs.all[0].open();
    c.sendState({ plate: "c1" });
    expect(FakeWs.all[0].sent.at(-1)).toEqual({ type: "state", plate: "c1" });
    FakeWs.all[0].close();
    vi.advanceTimersByTime(400);
    FakeWs.all[1].open();
    expect(FakeWs.all[1].sent[0]).toMatchObject({ type: "join", plate: "c1" });
    c.sendState({ plate: "" });
    FakeWs.all[1].close();
    vi.advanceTimersByTime(400);
    FakeWs.all[2].open();
    expect(FakeWs.all[2].sent[0]).not.toHaveProperty("plate");
  });

  it("hands duel messages over and sends the duel messages", () => {
    const { c, ev } = setup();
    c.join("http://h:1", INFO);
    const ws = FakeWs.all[0];
    ws.open();
    ws.recv({ type: "joined", room: "r", you: "me", members: [] });
    const invite = { type: "duel_invite", duel: "d1", from: "x", to: "me", bet: 150, prize: 250, sec: 15 };
    const result = { type: "duel_result", duel: "d1", winner: "me", loser: "x", prize: 250, hands: { me: "rock", x: null } };
    for (const m of [invite, { type: "duel_start", duel: "d1", round: 1, sec: 10 },
      { type: "duel_round", duel: "d1", round: 2, sec: 10, hands: { me: "rock", x: "rock" } }, result,
      { type: "duel_over", duel: "d2", reason: "declined" }]) ws.recv(m);
    expect(ev.onDuel.mock.calls.map(([m]) => m.type)).toEqual(["duel_invite", "duel_start", "duel_round", "duel_result", "duel_over"]);
    expect(ev.onDuel).toHaveBeenCalledWith(invite);
    const sent = ws.sent.length;
    c.sendDuelInvite("x", 1500);
    c.sendDuelAnswer("d1", true);
    c.sendDuelThrow("d1", "paper");
    expect(ws.sent.slice(sent)).toEqual([
      { type: "duel_invite", id: "x", bet: 1500 }, { type: "duel_answer", duel: "d1", accept: true },
      { type: "duel_throw", duel: "d1", hand: "paper" },
    ]);
    expect(ev.onError).not.toHaveBeenCalled();
  });

  it("keeps do-not-disturb for every rejoin and sends it only when told to", () => {
    const { c } = setup();
    c.join("http://h:1", { ...INFO });
    FakeWs.all[0].open();
    expect(FakeWs.all[0].sent[0]).not.toHaveProperty("dnd");
    c.setDnd(true, false);
    expect(FakeWs.all[0].sent).toHaveLength(1);
    FakeWs.all[0].close();
    vi.advanceTimersByTime(400);
    FakeWs.all[1].open();
    expect(FakeWs.all[1].sent[0]).toMatchObject({ type: "join", dnd: true });
    c.setDnd(false, true);
    expect(FakeWs.all[1].sent.at(-1)).toEqual({ type: "dnd", dnd: false });
    FakeWs.all[1].close();
    vi.advanceTimersByTime(400);
    FakeWs.all[2].open();
    expect(FakeWs.all[2].sent[0]).not.toHaveProperty("dnd");
  });
});
