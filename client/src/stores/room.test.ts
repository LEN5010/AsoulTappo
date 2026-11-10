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

it("shows a scratch card win over the winner's pet, with 阿草's face for that prize", async () => {
  const { socket, r } = await setup();
  socket.recv({ type: "member_joined", member: { id: "friend", nick: "朋友", character: "乃琳", taps: 0 } });
  socket.recv({ type: "scratch", id: "friend", shards: 2500 });
  expect(r.members.get("friend")!.win).toMatchObject({ count: 2500 });
  expect(r.members.get("friend")!.emote).toMatchObject({ key: "achao.05" });
  // taps keep their own counter
  socket.recv({ type: "tap", id: "friend", count: 3, total: 3 });
  expect(r.members.get("friend")!.combo).toMatchObject({ count: 3 });
  expect(r.members.get("friend")!.win).toMatchObject({ count: 2500 });
  socket.recv({ type: "scratch", id: "me", shards: 30000 });
  expect(r.localPet.win).toMatchObject({ count: 30000 });
  expect(r.localPet.emote).toMatchObject({ key: "achao.15" });
  await vi.advanceTimersByTimeAsync(3600);
  expect(r.members.get("friend")!.win).toBeNull();
  expect(r.localPet.win).toBeNull();
  // a member who is not in the room is ignored
  socket.recv({ type: "scratch", id: "gone", shards: 2500 });
});

it("knows the host from joined and room_info, and sends host actions only as host", async () => {
  const { socket, r } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [
    { id: "me", nick: "old", character: "嘉然", taps: 0 }, { id: "friend", nick: "朋友", character: "乃琳", taps: 0 },
  ], info: { host: "me", public: false } });
  expect(r.isHost.value).toBe(true);
  const sent = socket.sent.length;
  r.setRoomPublic(true);
  r.kickMember("me"); // never the host itself
  r.kickMember("friend");
  expect(socket.sent.slice(sent)).toEqual([{ type: "set_public", public: true }, { type: "kick", id: "friend" }]);
  socket.recv({ type: "room_info", host: "friend", public: true });
  expect(r.roomInfo.value).toEqual({ host: "friend", public: true });
  expect(r.isHost.value).toBe(false);
  r.setRoomPublic(false);
  r.kickMember("friend");
  expect(socket.sent).toHaveLength(sent + 2);
  socket.close();
  expect(r.roomInfo.value).toBeNull();
});

it("sends no host actions to a server without room info", async () => {
  const { socket, r } = await setup();
  socket.recv({ type: "member_joined", member: { id: "friend", nick: "朋友", character: "乃琳", taps: 0 } });
  expect(r.roomInfo.value).toBeNull();
  expect(r.isHost.value).toBe(false);
  const sent = socket.sent.length;
  r.setRoomPublic(true);
  r.kickMember("friend");
  expect(socket.sent).toHaveLength(sent);
});

it("treats being removed as leaving for good: no reconnect, no rejoin, a short notice", async () => {
  const { settings, socket, r } = await setup();
  expect(settings.lastRoom).toBe("r");
  socket.recv({ type: "error", code: "room_full", message: "你已被移出这个房间", reason: "kicked" });
  expect(r.lastError.value).toBe("你已被移出这个房间");
  expect(r.conn.value).toBe("idle");
  expect(r.roomId.value).toBe("");
  expect(settings.lastRoom).toBe("");
  socket.close();
  await vi.advanceTimersByTimeAsync(60000);
  expect(Socket.all).toHaveLength(1);
});

it("loads the public room list and hides it on servers without one", async () => {
  const { r } = await setup();
  const list = [{ room: "pub", host: { nick: "房主", character: "贝拉" }, members: 3, max: 20 }];
  const fetchMock = vi.fn(async (): Promise<unknown> => ({ ok: true, status: 200, json: async () => ({ rooms: list }) }));
  vi.stubGlobal("fetch", fetchMock);
  await r.loadPublicRooms();
  expect(fetchMock).toHaveBeenCalledWith("https://len5010.top/tappo/rooms", undefined);
  expect(r.publicRooms.value).toEqual(list);
  // a failed request keeps the list, so it can be refreshed
  fetchMock.mockImplementation(async () => { throw new TypeError("offline"); });
  await r.loadPublicRooms();
  expect(r.publicRooms.value).toEqual(list);
  fetchMock.mockImplementation(async () => ({ ok: false, status: 502, json: async () => ({}) }));
  await r.loadPublicRooms();
  expect(r.publicRooms.value).toEqual(list);
  // an older server only has POST /rooms
  fetchMock.mockImplementation(async () => ({ ok: false, status: 405, json: async () => ({ detail: "Method Not Allowed" }) }));
  await r.loadPublicRooms();
  expect(r.publicRooms.value).toBeNull();
  fetchMock.mockImplementation(async () => ({ ok: false, status: 404, json: async () => ({}) }));
  await r.loadPublicRooms();
  expect(r.publicRooms.value).toBeNull();
  // a server that answers neither starts from an empty list
  r.publicRooms.value = null;
  fetchMock.mockImplementation(async () => { throw new TypeError("offline"); });
  await r.loadPublicRooms();
  expect(r.publicRooms.value).toEqual([]);
});

// ---------------------------------------------------------------- public rooms on a server with accounts
const ROOMS_URL = "https://len5010.top/tappo/rooms";
const INFO_URL = "https://len5010.top/tappo/api/info";
const LISTED = [{ room: "pub", host: { nick: "房主", character: "贝拉" }, members: 3, max: 20 }];
const reply = (status: number, body: unknown) => ({ ok: status < 400, status, json: async () => body });

it("asks a server with accounts for the list only while an account is signed in", async () => {
  const { r } = await setup();
  const fetchMock = vi.fn(async (url: string): Promise<unknown> =>
    url === INFO_URL ? reply(200, { accountLogin: true, mainApi: "https://len5010.top/api/" }) : reply(200, { rooms: LISTED }));
  vi.stubGlobal("fetch", fetchMock);
  await r.loadPublicRooms();
  expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([INFO_URL]);
  expect(r.publicRooms.value).toBe("signin");

  const player = await import("./player");
  await player.setAccount({ server: "https://len5010.top/tappo", token: "acct", user: { id: "u", username: "a", email: null } });
  fetchMock.mockClear();
  await r.loadPublicRooms();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith(ROOMS_URL, { headers: { Authorization: "Bearer acct" } });
  expect(r.publicRooms.value).toEqual(LISTED);
  // signing out drops the rooms at once; a refresh that cannot reach the server keeps the sign-in key
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {} });
  await player.setAccount(null);
  expect(r.publicRooms.value).toBeNull();
  await r.loadPublicRooms();
  expect(r.publicRooms.value).toBe("signin");
  fetchMock.mockImplementation(async () => { throw new TypeError("offline"); });
  await r.loadPublicRooms();
  expect(r.publicRooms.value).toBe("signin");
});

it("never sends an account token to a server it was not signed in on", async () => {
  const { r, settings } = await setup();
  const player = await import("./player");
  await player.setAccount({ server: "https://len5010.top/tappo", token: "acct", user: { id: "u", username: "a", email: null } });
  settings.serverUrl = "http://127.0.0.1:8012";
  const fetchMock = vi.fn(async (url: string): Promise<unknown> =>
    url.endsWith("/api/info") ? reply(200, { accountLogin: false, mainApi: null }) : reply(200, { rooms: [] }));
  vi.stubGlobal("fetch", fetchMock);
  await r.loadPublicRooms();
  expect(fetchMock).toHaveBeenLastCalledWith("http://127.0.0.1:8012/rooms", undefined);
  expect(JSON.stringify(fetchMock.mock.calls)).not.toContain("acct");
  expect(r.publicRooms.value).toEqual([]);
});

it("treats a 401 from the list as signed out", async () => {
  const { r } = await setup();
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {} });
  const player = await import("./player");
  const session = { server: "https://len5010.top/tappo", token: "acct", user: { id: "u", username: "a", email: null } };
  await player.setAccount(session);
  r.publicRooms.value = LISTED;
  const fetchMock = vi.fn(async (): Promise<unknown> => reply(401, { detail: { code: "account_expired", message: "登录已过期" } }));
  vi.stubGlobal("fetch", fetchMock);
  await r.loadPublicRooms();
  expect(r.publicRooms.value).toBe("signin");
  expect(player.account.value).toBeNull();
  // a 401 for a missing token (an older client state) shows the sign-in key without touching the session
  await player.setAccount(session);
  fetchMock.mockImplementation(async () => reply(401, { detail: { code: "account_required", message: "" } }));
  await r.loadPublicRooms();
  expect(r.publicRooms.value).toBe("signin");
  expect(player.account.value?.token).toBe("acct");
});

it("keeps only well-formed public rooms from the list", async () => {
  const { r } = await setup();
  const good = { room: "pub", host: { nick: "房主", character: "贝拉" }, members: 3, max: 20 };
  const rooms = [good, null, "pub", { ...good, room: 5 }, { ...good, host: null }, { ...good, host: { nick: "x" } },
    { ...good, host: { nick: 1, character: "贝拉" } }, { ...good, members: "3" }, { ...good, max: null }, { room: "bare" }];
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ rooms }) })));
  await r.loadPublicRooms();
  expect(r.publicRooms.value).toEqual([good]);
});

// ---------------------------------------------------------------- rock-paper-scissors
const ME = { id: "me", uid: "u-me", nick: "old", character: "嘉然", taps: 0 };
const FRIEND = { id: "friend", uid: "u-friend", nick: "朋友", character: "乃琳", taps: 0 };

function playerStatus(over: Record<string, unknown> = {}) {
  return {
    player: "p", shards: 20000, income: { multiplier: 1, perMinute: 0 },
    resonance: { pity: { legendary: 0, skin: 0 }, hardPity: { legendary: 400, skin: 200 }, total: 0 },
    totals: { taps: 10000, activeMinutes: 0, owned: 0, items: 0 }, duel: { net: 0 }, ...over,
  };
}

async function duelSetup(over: Record<string, unknown> = {}) {
  const s = await setup();
  const player = await import("./player");
  player.status.value = playerStatus(over) as typeof player.status.value;
  const reloaded = playerStatus({ ...over, shards: 19850 });
  const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => reloaded }));
  vi.stubGlobal("fetch", fetchMock);
  s.socket.recv({ type: "joined", room: "r", you: "me", members: [ME, FRIEND] });
  return { ...s, player, fetchMock };
}

it("offers a duel only when the server has them and this save looks able to play", async () => {
  const { r, settings, player } = await duelSetup();
  const friend = r.members.get("friend")!;
  expect(r.duelOn.value).toBe(true);
  expect(r.canDuel(friend)).toBe(true);
  expect(r.canDuel(r.members.get("me")!)).toBe(false);
  expect(r.canDuel({ ...FRIEND, uid: null })).toBe(false); // no save
  expect(r.canDuel({ ...FRIEND, id: "me-too", uid: "u-me" })).toBe(false); // the same save on another connection
  expect([150, 1500, 15000].map((bet) => r.stakeOpen(bet))).toEqual([true, true, true]);
  player.status.value = playerStatus({ shards: 14999 }) as typeof player.status.value;
  expect([150, 1500, 15000].map((bet) => r.stakeOpen(bet))).toEqual([true, true, false]);
  player.status.value = playerStatus({ duel: { net: 1 } }) as typeof player.status.value;
  expect([150, 1500, 15000].map((bet) => r.stakeOpen(bet))).toEqual([true, true, false]);
  player.status.value = playerStatus({ duel: { net: 9950 } }) as typeof player.status.value;
  expect([150, 1500, 15000].map((bet) => r.stakeOpen(bet))).toEqual([false, false, false]);
  expect(r.canDuel(friend)).toBe(false);
  player.status.value = playerStatus({ totals: { taps: 9999, activeMinutes: 0, owned: 0, items: 0 } }) as typeof player.status.value;
  expect(r.canDuel(friend)).toBe(false);
  player.status.value = playerStatus() as typeof player.status.value;
  settings.clickThrough = true; // the pet could not be clicked to throw
  expect(r.canDuel(friend)).toBe(false);
});

it("plays a duel from the invite to the result, with the balance read again", async () => {
  const { r, socket, fetchMock, player } = await duelSetup();
  const sent = socket.sent.length;
  r.inviteDuel("friend", 151); // not a bet of the manifest
  r.inviteDuel("friend", 150);
  expect(socket.sent.slice(sent)).toEqual([{ type: "duel_invite", id: "friend", bet: 150 }]);
  socket.recv({ type: "duel_invite", duel: "d1", from: "me", to: "friend", bet: 150, prize: 250, sec: 15 });
  expect(r.duel.value).toMatchObject({ id: "d1", sent: true, phase: "invite", other: { id: "friend", nick: "朋友" } });
  expect(r.duelBusy.value).toBe(true);
  expect(r.canDuel(r.members.get("friend")!)).toBe(false);
  r.answerDuel(true); // only the invited side answers
  expect(socket.sent).toHaveLength(sent + 1);
  socket.recv({ type: "duel_start", duel: "d1", round: 1, sec: 10 });
  expect(r.duel.value).toMatchObject({ phase: "throw", round: 1, hand: null, sec: 10 });
  await vi.advanceTimersByTimeAsync(0);
  expect(fetchMock).toHaveBeenCalledWith("https://len5010.top/tappo/api/me", expect.anything());
  expect(player.status.value!.shards).toBe(19850);
  const reads = fetchMock.mock.calls.length;
  r.throwHand("rock");
  r.throwHand("paper"); // the first hand stands
  expect(socket.sent.slice(sent + 1)).toEqual([{ type: "duel_throw", duel: "d1", hand: "rock" }]);
  socket.recv({ type: "duel_round", duel: "d1", round: 2, sec: 10, hands: { me: "rock", friend: "rock" } });
  expect(r.duel.value).toMatchObject({ phase: "throw", round: 2, hand: null, shown: { mine: "rock", theirs: "rock" } });
  r.throwHand("paper");
  socket.recv({ type: "duel_result", duel: "d1", winner: "me", loser: "friend", prize: 250, hands: { me: "paper", friend: "rock" } });
  expect(r.duel.value).toMatchObject({ phase: "result", won: true, shown: { mine: "paper", theirs: "rock" } });
  expect(r.localPet.win).toMatchObject({ count: 250 });
  await vi.advanceTimersByTimeAsync(0);
  expect(fetchMock.mock.calls.length).toBe(reads + 1); // the prize is read back too
  socket.recv({ type: "sticker", id: "friend", key: "achao.07", sec: 6 });
  expect(r.members.get("friend")!.sticker).toMatchObject({ key: "achao.07" });
  await vi.advanceTimersByTimeAsync(r.DUEL_END_MS);
  expect(r.duel.value).toBeNull();
  expect(r.duelBusy.value).toBe(false);
  expect(r.members.get("friend")!.sticker).not.toBeNull();
  await vi.advanceTimersByTimeAsync(2000);
  expect(r.members.get("friend")!.sticker).toBeNull();
});

it("answers an invite on the desk, and a refusal closes it at once", async () => {
  const { r, socket, fetchMock } = await duelSetup();
  socket.recv({ type: "duel_invite", duel: "d2", from: "friend", to: "me", bet: 1500, prize: 2500, sec: 15 });
  expect(r.duel.value).toMatchObject({ sent: false, bet: 1500, prize: 2500, phase: "invite" });
  const sent = socket.sent.length;
  r.answerDuel(false);
  expect(socket.sent.slice(sent)).toEqual([{ type: "duel_answer", duel: "d2", accept: false }]);
  expect(r.duel.value).toBeNull();
  socket.recv({ type: "duel_over", duel: "d2", reason: "declined" }); // already closed
  expect(r.duel.value).toBeNull();
  // an invite between two others is not this client's
  socket.recv({ type: "duel_invite", duel: "d3", from: "friend", to: "other", bet: 150, prize: 250, sec: 15 });
  expect(r.duel.value).toBeNull();
  socket.recv({ type: "duel_invite", duel: "d4", from: "friend", to: "me", bet: 150, prize: 250, sec: 15 });
  r.answerDuel(true);
  r.answerDuel(true);
  expect(socket.sent.slice(sent + 1)).toEqual([{ type: "duel_answer", duel: "d4", accept: true }]);
  const reads = fetchMock.mock.calls.length;
  socket.recv({ type: "duel_over", duel: "d4", reason: "no_shards" });
  expect(r.duel.value).toMatchObject({ phase: "over", reason: "no_shards" });
  await vi.advanceTimersByTimeAsync(0);
  expect(fetchMock.mock.calls.length).toBe(reads + 1); // refunds come back the same way
  await vi.advanceTimersByTimeAsync(r.DUEL_END_MS);
  expect(r.duel.value).toBeNull();
  // a late answer to a duel that is gone says nothing
  socket.recv({ type: "error", code: "duel_gone", message: "" });
  expect(r.lastError.value).toBe("");
});

it("shows other members' results and the loser's sticker, own sticker included", async () => {
  const { r, socket } = await duelSetup();
  socket.recv({ type: "duel_result", duel: "x", winner: "friend", loser: "me", prize: 2500, hands: { friend: "rock", me: null } });
  expect(r.members.get("friend")!.win).toMatchObject({ count: 2500 });
  expect(r.duel.value).toBeNull(); // not this client's duel as far as it knows
  socket.recv({ type: "sticker", id: "me", key: "achao.02", sec: 12 });
  expect(r.localPet.sticker).toMatchObject({ key: "achao.02" });
  expect(r.members.get("me")!.sticker).toMatchObject({ key: "achao.02" });
  socket.recv({ type: "sticker", id: "friend", key: "nonsense", sec: 12 }); // unknown emotes are ignored
  expect(r.members.get("friend")!.sticker).toBeNull();
  await vi.advanceTimersByTimeAsync(12_000);
  expect(r.localPet.sticker).toBeNull();
  // the connection going away ends a duel on screen and the sticker with it
  socket.recv({ type: "sticker", id: "me", key: "achao.02", sec: 120 });
  socket.recv({ type: "duel_invite", duel: "d5", from: "friend", to: "me", bet: 150, prize: 250, sec: 15 });
  socket.close();
  expect(r.duel.value).toBeNull();
  expect(r.localPet.sticker).toBeNull();
});

it("tells the server about do-not-disturb, counting click-through, only when it has duels", async () => {
  const { r, socket, settings, player } = await duelSetup();
  settings.duelDnd = true;
  expect(socket.sent.at(-1)).toEqual({ type: "dnd", dnd: true });
  settings.clickThrough = true; // still on: nothing new to say
  settings.duelDnd = false;
  expect(socket.sent.filter((m) => m.type === "dnd")).toEqual([{ type: "dnd", dnd: true }]);
  settings.clickThrough = false;
  expect(socket.sent.at(-1)).toEqual({ type: "dnd", dnd: false });
  settings.duelDnd = true;
  r.leaveRoom();
  r.joinRoom("r");
  const next = Socket.all.at(-1)!;
  next.open();
  expect(next.sent[0]).toMatchObject({ type: "join", dnd: true });
  // a server without duels: its status says nothing of them
  next.recv({ type: "joined", room: "r", you: "me", members: [ME, FRIEND] });
  player.status.value = playerStatus({ duel: undefined }) as typeof player.status.value;
  const sent = next.sent.length;
  settings.duelDnd = false;
  r.inviteDuel("friend", 150);
  expect(r.duelOn.value).toBe(false);
  expect(r.canDuel(r.members.get("friend")!)).toBe(false);
  expect(next.sent).toHaveLength(sent);
});
