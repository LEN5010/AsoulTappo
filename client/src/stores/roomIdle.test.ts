// The desk's idle clock (stores/activity.ts) and the room: what partners do is drawn, but only what concerns this desk
// keeps its looping decoration (name plate videos, sweeps) running.
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { WsLike } from "../net/RoomClient";
import { TERMS_VERSION } from "../legal";
import { APP_VERSION } from "../version";
import { withEconomy } from "../test/economy";

class Socket implements WsLike {
  static all: Socket[] = [];
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: WsLike["onopen"] = null;
  onmessage: WsLike["onmessage"] = null;
  onclose: WsLike["onclose"] = null;
  onerror: WsLike["onerror"] = null;
  constructor(public url: string) { Socket.all.push(this); }
  send(data: string) { this.sent.push(JSON.parse(data)); }
  open() { this.readyState = 1; this.onopen?.({}); }
  close() { this.readyState = 3; this.onclose?.({}); }
  recv(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
}

let room: typeof import("./room") | undefined;
let stopActivity: (() => void) | undefined;
beforeEach(() => {
  vi.resetModules(); vi.useFakeTimers(); Socket.all = [];
  const agreed = JSON.stringify({ termsAgreed: TERMS_VERSION, statementSeen: APP_VERSION });
  vi.stubGlobal("localStorage", { getItem: withEconomy((k: string) => (k === "asoultappo.settings.v1" ? agreed : null)), setItem: () => {} });
  vi.stubGlobal("WebSocket", Socket);
  // The desk window of the app: the only one whose decoration goes idle.
  vi.stubGlobal("window", { __TAURI_INTERNALS__: {}, location: { search: "" }, addEventListener: () => {}, removeEventListener: () => {} });
  vi.stubGlobal("document", {
    hidden: false, getAnimations: () => [], createElement: () => ({}), addEventListener: () => {}, removeEventListener: () => {},
  });
  vi.doMock("@tauri-apps/api/event", () => ({ listen: vi.fn(async () => () => {}) }));
  vi.doMock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({ isVisible: async () => true }) }));
});
afterEach(() => {
  stopActivity?.(); stopActivity = undefined;
  room?.leaveRoom(); room = undefined;
  vi.doUnmock("@tauri-apps/api/event"); vi.doUnmock("@tauri-apps/api/window");
  vi.useRealTimers(); vi.unstubAllGlobals();
});

async function setup() {
  const activity = await import("./activity");
  stopActivity = await activity.startActivity();
  room = await import("./room");
  room.joinRoom("r");
  const socket = Socket.all[0];
  socket.open();
  socket.recv({ type: "joined", room: "r", you: "me", members: [] });
  socket.recv({ type: "member_joined", member: { id: "friend", nick: "朋友", character: "乃琳", taps: 0 } });
  socket.recv({ type: "member_joined", member: { id: "other", nick: "路人", character: "贝拉", taps: 0 } });
  return { activity, socket, r: room };
}

it("goes idle while partners keep moving and tapping, and still draws what they do", async () => {
  const { activity, socket, r } = await setup();
  expect(activity.renderActive.value).toBe(true);
  for (let i = 1; i <= 35; i++) {
    await vi.advanceTimersByTimeAsync(1000);
    socket.recv({ type: "motion", id: "friend", dx: i, dy: 0, keyDown: i % 2 === 0, left: false, right: false });
    socket.recv({ type: "tap", id: "friend", count: 1, total: i });
  }
  expect(activity.renderActive.value).toBe(false);
  expect(r.members.get("friend")!.motion.dx).toBe(35);
  expect(r.members.get("friend")!.taps).toBe(35);
  expect(r.members.get("friend")!.pulse).toBe(35);
});

it("stays idle for what partners do among themselves and wakes for what reaches this desk", async () => {
  const { activity, socket, r } = await setup();
  await vi.advanceTimersByTimeAsync(31_000);
  expect(activity.renderActive.value).toBe(false);
  socket.recv({ type: "poke", from: "friend", to: "other", quiet: false });
  socket.recv({ type: "drink", id: "friend" });
  expect(r.members.get("other")!.pulse).toBe(1);
  expect(r.members.get("friend")!.sip).toBe(1);
  expect(activity.renderActive.value).toBe(false);
  socket.recv({ type: "poke", from: "friend", to: "me", quiet: false });
  expect(activity.renderActive.value).toBe(true);
});

it("keeps a partner's own loops playing while the partner keeps tapping, however long this desk is idle", async () => {
  const { effectScope, ref } = await import("vue");
  /** An endless animation, as a second form's loop frames run (pet/PetView.vue `.loop img`). */
  const endless = () => ({
    playState: "running" as AnimationPlayState,
    effect: { getComputedTiming: () => ({ iterations: Infinity }) },
    pause() { this.playState = "paused"; },
    play() { this.playState = "running"; },
  });
  const partnerLoop = endless();
  const ownDecoration = endless();
  // The desk's idle clock pauses every endless animation on the page (stores/activity.ts).
  vi.stubGlobal("document", {
    hidden: false, getAnimations: () => [partnerLoop, ownDecoration], createElement: () => ({}),
    addEventListener: () => {}, removeEventListener: () => {},
  });
  const { activity, socket, r } = await setup();
  const { usePartnerLoops } = await import("../pet/partnerLoops");
  const pet = ref({ getAnimations: () => [partnerLoop] });
  const scope = effectScope();
  scope.run(() => usePartnerLoops(pet, () => true, () => r.members.get("friend")!.pulse));

  for (let i = 1; i <= 40; i++) {
    await vi.advanceTimersByTimeAsync(1000);
    socket.recv({ type: "tap", id: "friend", count: 1, total: i });
    socket.recv({ type: "pong" });
  }
  await vi.advanceTimersByTimeAsync(0);
  expect(activity.renderActive.value).toBe(false);
  expect(ownDecoration.playState).toBe("paused");
  expect(partnerLoop.playState).toBe("running");

  // Quiet as long as the desk: it rests too. The room stays connected meanwhile.
  for (let i = 0; i < 31; i++) {
    await vi.advanceTimersByTimeAsync(1000);
    socket.recv({ type: "pong" });
  }
  expect(partnerLoop.playState).toBe("paused");
  // Taps again: it plays again, the desk's own decoration still resting.
  socket.recv({ type: "tap", id: "friend", count: 1, total: 41 });
  await vi.advanceTimersByTimeAsync(0);
  expect(partnerLoop.playState).toBe("running");
  expect(ownDecoration.playState).toBe("paused");
  // Input on this desk wakes everything.
  activity.noteActivity();
  await vi.advanceTimersByTimeAsync(0);
  expect(ownDecoration.playState).toBe("running");
  expect(partnerLoop.playState).toBe("running");
  scope.stop();
});
