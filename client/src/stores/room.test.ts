import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { WsLike } from "../net/RoomClient";

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
beforeEach(() => {
  vi.resetModules(); vi.useFakeTimers(); Socket.all = [];
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {} });
  vi.stubGlobal("WebSocket", Socket);
});
afterEach(() => { room?.leaveRoom(); room = undefined; vi.useRealTimers(); vi.unstubAllGlobals(); });

async function setup() {
  const { settings } = await import("./settings");
  room = await import("./room");
  settings.nick = "old";
  room.joinRoom("r");
  const socket = Socket.all[0];
  socket.open();
  socket.recv({ type: "joined", room: "r", you: "me", members: [] });
  return { settings, socket, r: room };
}

it("rejoins with edits made while reconnecting, including a cleared nickname", async () => {
  const { settings, socket } = await setup();
  socket.close();
  settings.character = "贝拉";
  settings.nick = "";
  await vi.advanceTimersByTimeAsync(800);
  const next = Socket.all[1];
  next.open();
  expect(next.sent[0]).toMatchObject({ type: "join", character: "贝拉", nick: "匿名小面包" });
});

it("syncs clearing a nickname while connected and closes the old room on server change", async () => {
  const { settings, socket, r } = await setup();
  settings.nick = "";
  expect(socket.sent.at(-1)).toEqual({ type: "state", nick: "匿名小面包" });
  settings.serverUrl = "http://new-server";
  expect(socket.readyState).toBe(3);
  expect(r.roomId.value).toBe("");
  expect(r.inRoom.value).toBe(false);
  await vi.advanceTimersByTimeAsync(60000);
  expect(Socket.all).toHaveLength(1);
});

it("receives a remote pet's movement and button release without changing its tap count", async () => {
  const { socket, r } = await setup();
  socket.recv({ type: 'member_joined', member: { id: 'friend', nick: '朋友', character: '乃琳', taps: 12 } });
  socket.recv({ type: 'motion', id: 'friend', dx: 15.2, dy: -3, keyDown: true, left: true, right: false });
  expect(r.members.get('friend')!.motion).toEqual({ dx: 15.2, dy: -3, keyDown: true, left: true, right: false });
  expect(r.members.get('friend')!.taps).toBe(12);
  socket.recv({ type: 'motion', id: 'friend', dx: 0, dy: 0, keyDown: false, left: false, right: false });
  expect(r.members.get('friend')!.motion.left).toBe(true);
  await vi.advanceTimersByTimeAsync(70);
  expect(r.members.get('friend')!.motion.left).toBe(false);
  r.leaveRoom();
  expect(r.members.size).toBe(0);
});
