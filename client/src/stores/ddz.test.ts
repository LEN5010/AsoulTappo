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
  send(data: string) {
    const msg = JSON.parse(data);
    this.sent.push(msg);
    // The server's keepalive answer.
    if (msg.type === "ping") queueMicrotask(() => this.recv({ type: "pong" }));
  }
  open() { this.readyState = 1; this.onopen?.({}); }
  close() { this.readyState = 3; this.onclose?.({}); }
  recv(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
}
let room: typeof import("./room") | undefined;
beforeEach(() => {
  vi.resetModules(); vi.useFakeTimers(); Socket.all = [];
  const agreed = JSON.stringify({ termsAgreed: TERMS_VERSION, statementSeen: APP_VERSION });
  vi.stubGlobal("localStorage", { getItem: withEconomy((k: string) => (k === "asoultappo.settings.v1" ? agreed : null)), setItem: () => {} });
  vi.stubGlobal("WebSocket", Socket);
});
afterEach(() => { room?.leaveRoom(); room = undefined; vi.useRealTimers(); vi.unstubAllGlobals(); });

const ME = { id: "me", uid: "u-me", nick: "我", character: "嘉然", taps: 0, ddz: true };
const A = { id: "a", uid: "u-a", nick: "贝", character: "贝拉", taps: 0, ddz: true };
const B = { id: "b", uid: "u-b", nick: "琳", character: "乃琳", taps: 0, ddz: true };
const OLD = { id: "old", uid: "u-old", nick: "旧", character: "心宜", taps: 0 };

function playerStatus(over: Record<string, unknown> = {}) {
  return {
    player: "p", shards: 20000, income: { multiplier: 1, perMinute: 0 },
    resonance: { pity: { legendary: 0, skin: 0 }, hardPity: { legendary: 400, skin: 200 }, total: 0 },
    totals: { taps: 10000, activeMinutes: 0, owned: 0, items: 0 }, duel: { net: 0 }, ddz: { net: 0 }, ...over,
  };
}

async function setup(over: Record<string, unknown> = {}) {
  const { settings } = await import("./settings");
  room = await import("./room");
  const d = await import("./ddz");
  const player = await import("./player");
  const { ui, ddzFrame: frame } = await import("./ui");
  player.status.value = playerStatus(over) as typeof player.status.value;
  const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => playerStatus(over) }));
  vi.stubGlobal("fetch", fetchMock);
  room.joinRoom("r");
  const socket = Socket.all[0]!;
  socket.open();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A, B, OLD] });
  return { settings, socket, r: room, d, player, fetchMock, ui, frame };
}

const SEATS = [A, ME, B].map(({ id, nick, character }) => ({ id, nick, character, auto: false, away: false }));
/** The own hand of the deals below: 3 3 4 5 6 7 8 9 and nine more, as card ids. */
const HAND = [0, 1, 4, 8, 12, 16, 20, 24, 28, 29, 32, 36, 40, 44, 48, 49, 52];

it("joins saying it plays, and offers a game only when the save looks able to start one", async () => {
  const { socket, d, r, player } = await setup();
  expect(socket.sent[0]).toMatchObject({ type: "join", ddz: true });
  expect(d.ddzOn.value).toBe(true);
  expect(d.ddzCanStart.value).toBe(true);
  expect([50, 250, 500].map(d.ddzDeposit)).toEqual([2400, 12000, 24000]);
  expect([50, 250, 500, 100].map(d.ddzStakeOpen)).toEqual([true, true, false, false]);
  expect(d.ddzCanInvite(r.members.get("a")!)).toBe(true);
  expect(d.ddzCanInvite(r.members.get("me")!)).toBe(false);
  expect(d.ddzCanInvite(r.members.get("old")!)).toBe(false); // a client from before the game
  expect(d.ddzCanInvite({ ...A, uid: null })).toBe(false);
  expect(d.ddzCanInvite({ ...A, id: "me-too", uid: "u-me" })).toBe(false);
  player.status.value = playerStatus({ ddz: { net: 50000 } }) as typeof player.status.value;
  expect(d.ddzCanStart.value).toBe(false); // today's cap
  player.status.value = playerStatus({ totals: { taps: 9999, activeMinutes: 0, owned: 0, items: 0 } }) as typeof player.status.value;
  expect(d.ddzCanStart.value).toBe(false);
  player.status.value = playerStatus({ ddz: undefined }) as typeof player.status.value;
  expect(d.ddzOn.value).toBe(false); // a server without the game
});

it("sends an invite only for two other members, and tracks who accepted", async () => {
  const { socket, d } = await setup();
  const sent = socket.sent.length;
  d.inviteDdz(["a"], 50);
  d.inviteDdz(["a", "a"], 50);
  d.inviteDdz(["a", "old"], 50);
  d.inviteDdz(["a", "b"], 500); // cannot pay the deposit
  d.inviteDdz(["a", "b"], 100); // not a stake
  d.inviteDdz(["a", "b"], 250);
  expect(socket.sent.slice(sent)).toEqual([{ type: "ddz_invite", ids: ["a", "b"], base: 250 }]);
  socket.recv({ type: "ddz_invite", table: "t1", from: "me", ids: ["me", "a", "b"], base: 250, deposit: 12000, sec: 15 });
  expect(d.ddz.value).toMatchObject({ id: "t1", phase: "invite", you: 0, sent: true, accepted: ["me"], base: 250, deposit: 12000 });
  expect(d.ddz.value!.seats.map((s) => s.nick)).toEqual(["我", "贝", "琳"]);
  expect(d.ddzBusy.value).toBe(true);
  expect(d.ddzCanStart.value).toBe(false);
  d.answerDdz(true); // the inviter has nothing to answer
  expect(socket.sent).toHaveLength(sent + 1);
  socket.recv({ type: "ddz_answer", table: "t1", id: "a" });
  expect(d.ddz.value!.accepted).toEqual(["me", "a"]);
  socket.recv({ type: "ddz_over", table: "t1", reason: "declined", by: "b" });
  expect(d.ddz.value).toMatchObject({ phase: "over", reason: "declined", by: "琳" });
  expect(d.ddzBusy.value).toBe(false);
  await vi.advanceTimersByTimeAsync(d.DDZ_END_MS);
  expect(d.ddz.value).toBeNull();
});

it("answers an invite, and a refusal closes it at once", async () => {
  const { socket, d } = await setup();
  socket.recv({ type: "ddz_invite", table: "t2", from: "a", ids: ["a", "me", "b"], base: 10, deposit: 480, sec: 15 });
  expect(d.ddz.value).toMatchObject({ you: 1, sent: false, answered: false });
  const sent = socket.sent.length;
  d.answerDdz(true);
  d.answerDdz(true);
  expect(socket.sent.slice(sent)).toEqual([{ type: "ddz_answer", table: "t2", accept: true }]);
  expect(d.ddz.value!.answered).toBe(true);
  socket.recv({ type: "ddz_invite", table: "t3", from: "a", ids: ["a", "me", "b"], base: 10, deposit: 480, sec: 15 });
  d.answerDdz(false);
  expect(socket.sent.at(-1)).toEqual({ type: "ddz_answer", table: "t3", accept: false });
  expect(d.ddz.value).toBeNull();
  socket.recv({ type: "ddz_invite", table: "t4", from: "a", ids: ["a", "old", "b"], base: 10, deposit: 480, sec: 15 });
  expect(d.ddz.value).toBeNull(); // somebody else's table
});

it("plays a game from the deal to the result", async () => {
  const { socket, d, r, fetchMock, ui, frame } = await setup();
  socket.recv({ type: "ddz_invite", table: "t", from: "a", ids: ["a", "me", "b"], base: 100, deposit: 4800, sec: 15 });
  d.answerDdz(true);
  socket.recv({ type: "ddz_live", table: "t", ids: ["a", "me", "b"], on: true });
  expect([...d.ddzPlaying.value]).toEqual(["a", "me", "b"]);
  socket.recv({ type: "ddz_deal", table: "t", seats: SEATS, you: 1, hand: HAND, base: 100, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 1.8 });
  const t = () => d.ddz.value!;
  expect(t()).toMatchObject({ phase: "bid", you: 1, turn: 0, base: 100, cap: 24, deposit: 4800, sec: 15 });
  // The cards are dealt out first; the first bid's time starts after that.
  expect([t().dealUntil - Date.now(), t().until - Date.now()]).toEqual([1800, 16800]);
  expect(t().hand[0]).toBe(52); // held highest first
  expect(t().seats.map((s) => s.left)).toEqual([17, 17, 17]);
  expect(d.ddzAtTable.value).toBe(true);
  expect(frame.open).toBe(true); // the table's window comes up (here the browser preview's frame)
  expect(ui.panelOpen).toBe(false); // the panel stays as it was
  await vi.advanceTimersByTimeAsync(0);
  expect(fetchMock).toHaveBeenCalled(); // the deposit is paid

  const sent = socket.sent.length;
  d.bidDdz(1); // not this seat's turn
  expect(socket.sent).toHaveLength(sent);
  socket.recv({ type: "ddz_bid", table: "t", seat: 0, bid: 1, turn: 1, sec: 15 });
  d.bidDdz(2); // the cards are still being dealt out
  expect(socket.sent).toHaveLength(sent);
  await vi.advanceTimersByTimeAsync(1800);
  d.bidDdz(1); // not above the bid
  d.bidDdz(2);
  d.bidDdz(3); // one move a turn
  expect(socket.sent.slice(sent)).toEqual([{ type: "ddz_bid", table: "t", bid: 2 }]);
  socket.recv({ type: "ddz_bid", table: "t", seat: 1, bid: 2, turn: 2, sec: 15 });
  socket.recv({ type: "ddz_bid", table: "t", seat: 2, bid: 0 });
  expect(t().seats.map((s) => s.bid)).toEqual([1, 2, 0]);
  socket.recv({ type: "ddz_landlord", table: "t", seat: 1, bid: 2, bottom: [5, 9, 53], mult: 2, turn: 1, sec: 30 });
  expect(t()).toMatchObject({ phase: "play", landlord: 1, lead: true, mult: 2, turn: 1 });
  expect(t().hand).toHaveLength(20);
  expect(t().seats[1]!.left).toBe(20);
  expect(d.ddzLast(t())).toBeNull();

  const before = socket.sent.length;
  d.playDdz([]); // a lead cannot pass
  d.playDdz([0, 4]); // not a hand
  d.playDdz([2]); // not held
  d.playDdz([0, 1]);
  expect(socket.sent.slice(before)).toEqual([{ type: "ddz_play", table: "t", cards: [0, 1] }]);
  socket.recv({ type: "error", code: "ddz_bad", message: "" });
  expect(t().acted).toBe(false); // refused: the keys are back
  expect(r.lastError.value).toBe("");
  d.playDdz([0, 1]);
  socket.recv({ type: "ddz_play", table: "t", seat: 1, cards: [0, 1], left: 18, mult: 2, bombs: 0, turn: 2, sec: 30, lead: false });
  expect(t().hand).toHaveLength(18);
  expect(t().trick).toEqual([null, [0, 1], null]);
  socket.recv({ type: "ddz_play", table: "t", seat: 2, cards: [], left: 17, mult: 2, bombs: 0, turn: 0, sec: 30, lead: false });
  socket.recv({ type: "ddz_play", table: "t", seat: 0, cards: [6, 7], left: 15, mult: 2, bombs: 0, turn: 1, sec: 30, lead: false });
  expect(d.ddzLast(t())).toEqual({ seat: 0, cards: [6, 7] });
  const at = socket.sent.length;
  d.playDdz([4, 5]); // 4 4 does not beat 4 4
  d.playDdz([28, 29]);
  expect(socket.sent.slice(at)).toEqual([{ type: "ddz_play", table: "t", cards: [28, 29] }]);
  socket.recv({ type: "ddz_play", table: "t", seat: 1, cards: [28, 29], left: 16, mult: 2, bombs: 0, turn: 2, sec: 30, lead: false });
  socket.recv({ type: "ddz_play", table: "t", seat: 2, cards: [], left: 17, mult: 2, bombs: 0, turn: 0, sec: 30, lead: false });
  socket.recv({ type: "ddz_play", table: "t", seat: 0, cards: [], left: 15, mult: 2, bombs: 0, turn: 1, sec: 30, lead: true });
  // Both passed: the trick stays on the table until the lead is played.
  expect(t().trick).toEqual([[], [28, 29], []]);
  expect(d.ddzLast(t())).toBeNull();
  d.playDdz([52, 53]);
  socket.recv({ type: "ddz_play", table: "t", seat: 1, cards: [52, 53], left: 14, mult: 4, bombs: 1, turn: 2, sec: 30, lead: false });
  expect(t().trick).toEqual([null, [52, 53], null]);
  expect(t()).toMatchObject({ mult: 4, bombs: 1, boosts: ["rocket"] });
  expect(t().log.at(-1)).toMatchObject({ kind: "play", seat: 1, bomb: true });
  expect(t().log.map((e) => e.seq)).toEqual([...t().log.map((e) => e.seq)].sort((a, b) => a - b));

  socket.recv({ type: "ddz_seat", table: "t", seat: 2, id: "b", away: true, auto: false, turn: 2, sec: 1.2 });
  expect(t().seats[2]).toMatchObject({ away: true });
  socket.recv({
    type: "ddz_result", table: "t", winner: "landlord", landlord: 1, bid: 2, bombs: 1, spring: 0, mult: 4, base: 100,
    deltas: [-400, 720, -400], hands: [[6], [], [10, 11]], sec: 30,
  });
  expect(t()).toMatchObject({ phase: "result", turn: null, result: { winner: "landlord", deltas: [-400, 720, -400] } });
  socket.recv({ type: "ddz_live", table: "t", ids: ["a", "me", "b"], on: false, gains: { me: 720 } });
  expect(r.localPet.win).toMatchObject({ count: 720 });
  expect(d.ddzPlaying.value.size).toBe(0);
  const end = socket.sent.length;
  d.againDdz();
  socket.recv({ type: "ddz_again", table: "t", seat: 1 });
  d.againDdz();
  expect(socket.sent.slice(end)).toEqual([{ type: "ddz_again", table: "t" }]);
  socket.recv({ type: "ddz_closed", table: "t" });
  expect(t()).toMatchObject({ phase: "result", closed: true }); // the receipt stays
  expect(d.ddzBusy.value).toBe(false);
  expect(frame.open).toBe(true);
  d.leaveDdz();
  expect(socket.sent).toHaveLength(end + 1); // nothing left to leave
  expect(d.ddz.value).toBeNull();
  expect(frame.open).toBe(true); // the table is put away: its window stays, on the lobby
});

it("leaves the table's window shut for a deal while the pet is hidden, and opens it with the next deal once shown", async () => {
  const { socket, d, frame } = await setup();
  const { windowVisible } = await import("./activity");
  const deal = (n: number) => socket.recv({
    type: "ddz_deal", table: "t", seats: SEATS, you: 1, hand: HAND, base: 100, cap: 24, deal: n, turn: 1, sec: 15, dealSec: 0,
  });
  windowVisible.value = false; // the hide key
  deal(1);
  expect(frame.open).toBe(false);
  windowVisible.value = true;
  expect(frame.open).toBe(false); // shown again: the table stays shut, as if closed
  expect(d.ddzBubble.value).toBe("turn");
  socket.recv({ type: "ddz_bid", table: "t", seat: 1, bid: 3, turn: 2, sec: 15 });
  expect(frame.open).toBe(false);
  expect(d.ddzBubble.value).toBe("table");
  socket.recv({
    type: "ddz_result", table: "t", winner: "farmers", landlord: 1, bid: 3, bombs: 0, spring: 0, mult: 3, base: 100,
    deltas: [300, -600, 300], hands: [[0], [], []], sec: 30,
  });
  deal(2);
  expect(frame.open).toBe(true);
  // The player's own key opens it whenever.
  frame.open = false;
  d.noteDdzWindowClosed();
  const { openDdzWindow } = await import("./ui");
  await openDdzWindow();
  expect(frame.open).toBe(true);
});

it("keeps the table's window closed for the deal it was closed during, and opens it with the next deal", async () => {
  const { socket, d, frame } = await setup();
  const deal = (n: number) => socket.recv({
    type: "ddz_deal", table: "t", seats: SEATS, you: 1, hand: HAND, base: 100, cap: 24, deal: n, turn: 0, sec: 15, dealSec: 1.8,
  });
  deal(1);
  expect(frame.open).toBe(true);
  expect(d.ddzBubble.value).toBeNull(); // the table is in sight
  frame.open = false;
  d.noteDdzWindowClosed();
  expect(d.ddzBubble.value).toBe("table"); // the pet's bubble brings it back
  socket.recv({ type: "ddz_bid", table: "t", seat: 0, bid: 1, turn: 1, sec: 15 });
  expect(frame.open).toBe(false);
  expect(d.ddzBubble.value).toBe("turn");
  socket.recv({
    type: "ddz_state", table: "t", phase: "bid", you: 1, hand: HAND, seats: SEATS.map((s) => ({ ...s, left: 17, bid: null })),
    base: 100, cap: 24, deal: 1, bid: 1, landlord: null, bottom: [], mult: 1, bombs: 0, turn: 1, lead: false,
    trick: [null, null, null], sec: 10, of: 15,
  });
  expect(frame.open).toBe(false); // the same deal, taken again: still closed
  socket.recv({
    type: "ddz_result", table: "t", winner: "farmers", landlord: 0, bid: 1, bombs: 0, spring: 0, mult: 1, base: 100,
    deltas: [-200, 100, 100], hands: [[0], [], []], sec: 30,
  });
  expect(frame.open).toBe(false);
  deal(2); // 再来一局
  expect(frame.open).toBe(true);
});

it("takes its seat again from the whole state, and walks away from a game", async () => {
  const { socket, d, fetchMock } = await setup();
  socket.recv({
    type: "ddz_state", table: "t9", phase: "play", you: 2, hand: [0, 4, 53],
    seats: SEATS.map((s, i) => ({ ...s, left: [5, 9, 3][i], bid: [1, 0, 3][i] })), base: 10, cap: 24, deal: 1, bid: 3,
    landlord: 2, bottom: [1, 2, 3], mult: 6, bombs: 1, turn: 2, lead: false, trick: [[8], [], null], sec: 12.5, of: 30,
  });
  const t = d.ddz.value!;
  expect(t).toMatchObject({ phase: "play", you: 2, landlord: 2, mult: 6, turn: 2, sec: 30, deposit: 480, boosts: ["bomb"], dealUntil: 0 });
  expect(t.hand).toEqual([53, 4, 0]);
  expect(t.seats.map((s) => s.left)).toEqual([5, 9, 3]);
  expect(d.ddzLast(t)).toEqual({ seat: 0, cards: [8] });
  expect(Math.round((t.until - Date.now()) / 100)).toBe(125);
  d.autoDdz(true);
  expect(socket.sent.at(-1)).toEqual({ type: "ddz_auto", table: "t9", on: true });
  d.leaveDdz();
  expect(socket.sent.at(-1)).toEqual({ type: "ddz_leave", table: "t9" });
  expect(d.ddz.value).toBeNull();
  // The game is played to its end without this client: only the balance is read again.
  await vi.advanceTimersByTimeAsync(0);
  const reads = fetchMock.mock.calls.length;
  socket.recv({ type: "ddz_result", table: "t9", winner: "farmers", landlord: 2, bid: 3, bombs: 1, spring: 0, mult: 6, base: 10, deltas: [54, 54, -120], hands: [[], [], []], sec: 30 });
  expect(d.ddz.value).toBeNull();
  await vi.advanceTimersByTimeAsync(0);
  expect(fetchMock.mock.calls.length).toBe(reads + 1);
});

it("drops the table with the room connection", async () => {
  const { socket, d } = await setup();
  socket.recv({ type: "ddz_live", table: "x", ids: ["a", "b", "old"], on: true });
  socket.recv({ type: "ddz_invite", table: "t", from: "a", ids: ["a", "me", "b"], base: 10, deposit: 480, sec: 15 });
  socket.recv({ type: "ddz_deal", table: "t", seats: SEATS, you: 1, hand: HAND, base: 10, cap: 24, deal: 1, turn: 1, sec: 15 });
  expect(d.ddzCanInvite({ ...OLD, ddz: true })).toBe(false); // at a table
  socket.close();
  expect(d.ddz.value).toBeNull();
  expect(d.ddzLive.value).toEqual({});
});

it("says a game ended because a seat's save has no account", async () => {
  const { ddzReason } = await import("./ddz");
  expect(ddzReason({ reason: "ddz_account" } as Parameters<typeof ddzReason>[0])).toBe("有人还没有登录 Asasfans 账号");
});

// ------------------------------------------------------------------ the queue
const X = { id: "x", nick: "远方", character: "贝拉" };
const Y = { id: "y", nick: "天边", character: "乃琳" };

/** The dou dizhu connection the store opened last: opens it and answers its hello as [ready]. */
function linkUp(ready: Record<string, unknown> = {}) {
  const lk = Socket.all.at(-1)!;
  lk.open();
  lk.recv({ type: "ddz_ready", you: "L", base: null, table: null, ...ready });
  return lk;
}
const sentOf = (s: Socket, type: string) => s.sent.filter((m) => m.type === type);

it("queues on a dou dizhu connection of its own, in a room or not, and closes it once nothing needs it", async () => {
  const { socket, d, r, settings } = await setup();
  expect(socket.sent[0]).toMatchObject({ type: "join", ddz: true, ddzMatch: true });
  room!.leaveRoom(); // out of any room
  expect(r.inRoom.value).toBe(false);
  expect([d.ddzServerOn.value, d.ddzQueueOn.value, d.ddzCanQueue.value]).toEqual([true, true, true]);
  const before = Socket.all.length;
  d.queueDdz(500); // cannot pay the deposit
  d.queueDdz(100); // not a stake
  expect(Socket.all).toHaveLength(before);
  d.queueDdz(250);
  // The connection comes up for it and says hello as the room would join; the join goes once it is ready.
  expect(Socket.all).toHaveLength(before + 1);
  const lk = Socket.all.at(-1)!;
  expect(lk.url).toContain("/ws?v=");
  lk.open();
  expect(lk.sent).toEqual([{ type: "ddz_hello", nick: settings.nick.trim() || "匿名小面包", character: settings.character, token: expect.any(String) }]);
  lk.recv({ type: "ddz_ready", you: "L", base: null, table: null });
  expect(d.ddzLink.value).toBe("open");
  expect(sentOf(lk, "ddz_queue")).toEqual([{ type: "ddz_queue", base: 250 }]);
  expect(d.ddzQueue.value).toBeNull(); // waiting once the server says so
  lk.recv({ type: "ddz_queue", base: 250, waited: 3 });
  expect(d.ddzQueue.value).toEqual({ base: 250, since: Date.now() - 3000 });
  d.queueDdz(250); // waiting there already
  expect(sentOf(lk, "ddz_queue")).toHaveLength(1);
  lk.recv({ type: "ddz_waiting", counts: [[50, 1], [250, 3]] });
  expect([50, 250, 500].map(d.ddzOthersWaiting)).toEqual([1, 2, 0]);
  // Joining a room and leaving it changes nothing of the wait.
  room!.joinRoom("r");
  const again = Socket.all.at(-1)!;
  again.open();
  again.recv({ type: "joined", room: "r", you: "me", members: [ME], features: ["ddz_match"] });
  room!.leaveRoom();
  expect(d.ddzQueue.value).toEqual({ base: 250, since: Date.now() - 3000 });
  // Turning invites down tells the connection.
  settings.duelDnd = true;
  expect(lk.sent.at(-1)).toEqual({ type: "dnd", dnd: true });
  settings.duelDnd = false;
  d.unqueueDdz();
  expect(lk.sent.at(-1)).toEqual({ type: "ddz_queue", base: 0 });
  lk.recv({ type: "ddz_queue", base: null });
  expect(d.ddzQueue.value).toBeNull();
  d.unqueueDdz(); // not waiting
  expect(sentOf(lk, "ddz_queue")).toHaveLength(2);
  // Nothing needs it: it goes after a while, saying leave.
  await vi.advanceTimersByTimeAsync(d.LINK_GRACE_MS - 1);
  expect(lk.readyState).toBe(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(lk.readyState).toBe(3);
  expect(lk.sent.at(-1)).toEqual({ type: "leave" });
  expect(d.ddzLink.value).toBe("idle");
  // Turning invites down keeps the save out of the queue.
  settings.duelDnd = true;
  expect(d.ddzCanQueue.value).toBe(false);
  const sockets = Socket.all.length;
  d.queueDdz(50);
  expect(Socket.all).toHaveLength(sockets);
});

it("takes a table of the queue on the connection, plays it there, and keeps the connection up for another game", async () => {
  const { socket, d, r } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A], features: ["ddz_match"] });
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  await vi.advanceTimersByTimeAsync(20000);
  lk.recv({ type: "ddz_queue", base: null });
  // The connection names this save by its own member id, L.
  lk.recv({ type: "ddz_invite", table: "m1", ids: ["x", "L", "y"], base: 50, deposit: 2400, sec: 15, match: true, seats: [X, { ...ME, id: "L" }, Y] });
  expect(d.ddzQueue.value).toBeNull();
  expect(d.ddz.value).toMatchObject({ id: "m1", via: "link", match: true, you: 1, sent: false, accepted: [], base: 50 });
  expect(d.ddz.value!.seats.map((s) => [s.nick, s.character])).toEqual([["远方", "贝拉"], ["我", "嘉然"], ["天边", "乃琳"]]);
  expect(d.ddzBubble.value).toBe("invite");
  // An invite of the room for another save means nothing here.
  socket.recv({ type: "ddz_invite", table: "z", from: "a", ids: ["a", "L", "b"], base: 50, deposit: 2400, sec: 15 });
  expect(d.ddz.value!.id).toBe("m1");
  const roomSent = socket.sent.length;
  d.answerDdz(true);
  expect(lk.sent.at(-1)).toEqual({ type: "ddz_answer", table: "m1", accept: true });
  expect(socket.sent).toHaveLength(roomSent); // not on the room's connection
  lk.recv({ type: "ddz_answer", table: "m1", id: "L" });
  lk.recv({ type: "ddz_over", table: "m1", reason: "declined", by: "y" });
  expect(d.ddz.value).toMatchObject({ phase: "over", by: "天边" });
  // Put back at the front of the line, still counting from when it started waiting.
  lk.recv({ type: "ddz_queue", base: 50, waited: 20 });
  expect(d.ddz.value).toBeNull();
  expect(d.ddzQueue.value).toEqual({ base: 50, since: Date.now() - 20000 });
  // Matched again and dealt: the moves go on the connection; a room's refusal does not touch its keys.
  lk.recv({ type: "ddz_queue", base: null });
  lk.recv({ type: "ddz_invite", table: "m2", ids: ["L", "x", "y"], base: 50, deposit: 2400, sec: 15, match: true, seats: [{ ...ME, id: "L" }, X, Y] });
  d.answerDdz(true);
  const seats = [{ ...ME, id: "L", plate: "achao" }, X, Y].map((s) => ({ auto: false, away: false, ...s }));
  lk.recv({ type: "ddz_deal", table: "m2", seats, you: 0, hand: HAND, base: 50, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 0 });
  expect(d.ddz.value).toMatchObject({ phase: "bid", via: "link", you: 0 });
  expect(d.ddz.value!.seats[0]!.plate).toBe("achao");
  expect(d.ddz.value!.seats[2]).toMatchObject({ nick: "天边", away: false });
  expect(r.members.has("y")).toBe(false);
  d.bidDdz(3);
  expect(lk.sent.at(-1)).toEqual({ type: "ddz_bid", table: "m2", bid: 3 });
  socket.recv({ type: "error", code: "ddz_bad", message: "" });
  expect(d.ddz.value!.acted).toBe(true);
  lk.recv({ type: "error", code: "ddz_bad", message: "" });
  expect(d.ddz.value!.acted).toBe(false);
  // Leaving the room leaves the game alone.
  room!.leaveRoom();
  expect(d.ddz.value).toMatchObject({ id: "m2", phase: "bid" });
  // Another seat comes back with another nick; the result keeps the connection up for 再来一局.
  lk.recv({ type: "ddz_seat", table: "m2", seat: 2, id: "y2", away: false, auto: false, nick: "新名字", character: "思诺", plate: null });
  expect(d.ddz.value!.seats[2]).toMatchObject({ id: "y2", nick: "新名字", character: "思诺" });
  lk.recv({
    type: "ddz_result", table: "m2", winner: "landlord", landlord: 0, bid: 3, bombs: 0, spring: 0, mult: 3, base: 50,
    deltas: [270, -150, -150], hands: [[], [1], [2]], sec: 30,
  });
  expect(r.localPet.win).toMatchObject({ count: 270 }); // out of any room, the own pet shows it from the result
  await vi.advanceTimersByTimeAsync(d.LINK_GRACE_MS * 2);
  expect(lk.readyState).toBe(1);
  d.againDdz();
  expect(lk.sent.at(-1)).toEqual({ type: "ddz_again", table: "m2" });
  // The receipt put away: the connection goes after a while.
  lk.recv({ type: "ddz_closed", table: "m2" });
  d.leaveDdz();
  await vi.advanceTimersByTimeAsync(d.LINK_GRACE_MS);
  expect(lk.readyState).toBe(3);
});

it("shows the table's emotes over each seat, and sends its own over the table's connection", async () => {
  const { socket, d, r, player } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A, B], features: ["ddz_match", "ddz_emote"] });
  socket.recv({ type: "ddz_deal", table: "t", seats: SEATS, you: 1, hand: HAND, base: 100, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 0 });
  socket.recv({ type: "ddz_emote", table: "t", seat: 2, emote: "thumbup" });
  socket.recv({ type: "ddz_emote", table: "other", seat: 0, emote: "thumbup" });
  expect(d.ddzEmotes.value.map((f) => f?.key ?? null)).toEqual([null, null, "thumbup"]);
  player.collection.owned = { "emote:thumbup": 1 } as typeof player.collection.owned;
  const sent = socket.sent.length;
  d.emoteDdz("thumbup");
  // On the own pet, and to the table only: the room hears no emote of it.
  expect(r.localPet.emote).toMatchObject({ key: "thumbup" });
  expect(socket.sent.slice(sent)).toEqual([{ type: "ddz_emote", table: "t", emote: "thumbup" }]);
  d.emoteDdz("thumbup"); // too soon after the last
  expect(socket.sent).toHaveLength(sent + 1);
  await vi.advanceTimersByTimeAsync(60_000);
  expect(d.ddzEmotes.value).toEqual([null, null, null]);
  // Another table starts without them.
  socket.recv({ type: "ddz_emote", table: "t", seat: 0, emote: "thumbup" });
  socket.recv({ type: "ddz_deal", table: "t2", seats: SEATS, you: 1, hand: HAND, base: 100, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 0 });
  expect(d.ddzEmotes.value).toEqual([null, null, null]);
});

it("comes back on a new connection: the wait and the seat the server kept, or none", async () => {
  const { d } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  // Dropped: it keeps showing the wait and reconnects; the new connection took the place over.
  lk.close();
  expect(d.ddzLink.value).toBe("reconnecting");
  expect(d.ddzQueue.value).not.toBeNull();
  await vi.advanceTimersByTimeAsync(1000);
  const lk2 = linkUp({ base: 50, waited: 4 });
  expect(lk2).not.toBe(lk);
  expect(d.ddzQueue.value).toEqual({ base: 50, since: Date.now() - 4000 });
  expect(sentOf(lk2, "ddz_queue")).toEqual([]);
  // Dropped again, and the server lost the wait meanwhile: joined again.
  lk2.close();
  await vi.advanceTimersByTimeAsync(2000);
  const lk3 = linkUp();
  expect(sentOf(lk3, "ddz_queue")).toEqual([{ type: "ddz_queue", base: 50 }]);
  lk3.recv({ type: "ddz_queue", base: null });
  lk3.recv({ type: "ddz_invite", table: "m1", ids: ["L", "x", "y"], base: 50, deposit: 2400, sec: 15, match: true, seats: [{ ...ME, id: "L" }, X, Y] });
  const seats = [{ ...ME, id: "L" }, X, Y].map((s) => ({ auto: false, away: false, ...s }));
  lk3.recv({ type: "ddz_deal", table: "m1", seats, you: 0, hand: HAND, base: 50, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 0 });
  // Back with the seat: the game stays and its state follows; back without it, the game is gone.
  lk3.close();
  await vi.advanceTimersByTimeAsync(4000);
  linkUp({ you: "L2", table: "m1" });
  expect(d.ddz.value).toMatchObject({ id: "m1", phase: "bid" });
  Socket.all.at(-1)!.close();
  await vi.advanceTimersByTimeAsync(8000);
  linkUp({ you: "L3" });
  expect(d.ddz.value).toBeNull();
});

it("takes back a seat the server kept after a restart, and stops on a server without the connection", async () => {
  const { d, fetchMock } = await setup();
  const lobbyCalls = () => fetchMock.mock.calls.filter((c) => String((c as unknown[])[0]).endsWith("/api/ddz/lobby"));
  // The desk asked once whether the save holds a seat of the queue's; this one does not.
  await vi.advanceTimersByTimeAsync(0);
  expect(lobbyCalls()).toHaveLength(1);
  expect(d.ddzLink.value).toBe("idle");
  // Another save that does: the connection comes up and takes it back.
  const player = await import("./player");
  fetchMock.mockImplementation((async (url: string) => (String(url).endsWith("/api/ddz/lobby")
    ? { ok: true, status: 200, json: async () => ({ tiers: [], seated: true }) }
    : { ok: true, status: 200, json: async () => playerStatus({ player: "q" }) })) as never);
  player.status.value = playerStatus({ player: "q" }) as typeof player.status.value;
  await vi.advanceTimersByTimeAsync(0);
  expect(lobbyCalls()).toHaveLength(2);
  expect(d.ddzLink.value).toBe("connecting");
  const lk = linkUp({ table: "m9" });
  const seats = [{ ...ME, id: "L" }, X, Y].map((s) => ({ auto: false, away: false, ...s }));
  lk.recv({
    type: "ddz_state", table: "m9", phase: "play", you: 0, hand: HAND, seats: seats.map((s) => ({ ...s, left: 17, bid: null })),
    base: 50, cap: 24, deal: 1, bid: 3, landlord: 0, bottom: [], mult: 3, bombs: 0, turn: 0, lead: true,
    trick: [null, null, null], sec: 10, of: 30,
  });
  expect(d.ddz.value).toMatchObject({ id: "m9", via: "link", phase: "play" });
  // Another server: the connection goes.
  const s2 = await import("./settings");
  s2.settings.serverUrl = "https://old.example";
  expect([d.ddzLink.value, lk.readyState, d.ddz.value]).toEqual(["idle", 3, null]);
});

it("stops on a server that does not know the connection, or whose lobby is not there", async () => {
  const { d } = await setup();
  // It answers the hello as a bad message: no queue there, and nothing is tried again.
  d.queueDdz(50);
  const old = Socket.all.at(-1)!;
  old.open();
  old.recv({ type: "error", code: "bad_message", message: "invalid message" });
  expect([d.ddzLinkOff.value, d.ddzQueueOn.value, d.ddzCanQueue.value, d.ddzQueue.value]).toEqual([true, false, false, null]);
  expect(old.readyState).toBe(3);
  const sockets = Socket.all.length;
  await vi.advanceTimersByTimeAsync(30_000);
  d.queueDdz(50);
  expect(Socket.all).toHaveLength(sockets);
});

it("turns the queue off on a server whose lobby answers 404", async () => {
  const { d, fetchMock, player } = await setup();
  fetchMock.mockImplementation((async (url: string) => (String(url).endsWith("/api/ddz/lobby")
    ? { ok: false, status: 404, json: async () => ({ detail: { code: "no_ddz", message: "" } }) }
    : { ok: true, status: 200, json: async () => playerStatus({ player: "q" }) })) as never);
  player.status.value = playerStatus({ player: "q" }) as typeof player.status.value;
  await vi.advanceTimersByTimeAsync(0);
  expect([d.ddzLinkOff.value, d.ddzQueueOn.value]).toEqual([true, false]);
  expect(await player.loadDdzLobby()).toBe("off");
});

it("says why the server took the save out of the queue or refused it", async () => {
  const { d, r } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  lk.recv({ type: "ddz_queue", base: null, reason: "no_shards" });
  expect(d.ddzQueue.value).toBeNull();
  expect(r.lastError.value).toBe("碎片不足");
  // The same save waits on another device.
  await vi.advanceTimersByTimeAsync(1100);
  d.queueDdz(50);
  lk.recv({ type: "error", code: "ddz_queued", message: "" });
  expect(r.lastError.value).toBe("已在别处匹配");
});

it("answers only the invite the player saw: an answer for another table is dropped", async () => {
  const { d } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_invite", table: "m2", ids: ["x", "L", "y"], base: 50, deposit: 2400, sec: 15, match: true, seats: [X, { ...ME, id: "L" }, Y] });
  const sent = lk.sent.length;
  d.answerDdz(true, "m1"); // clicked while m1 was on screen; m2 took its place before the click arrived
  d.answerDdz(false, "m1");
  expect(lk.sent).toHaveLength(sent);
  expect(d.ddz.value).toMatchObject({ id: "m2", answered: false });
  d.answerDdz(true, "m2");
  expect(lk.sent.slice(sent)).toEqual([{ type: "ddz_answer", table: "m2", accept: true }]);
});

it("holds the queue back as long as the server says after a table of the queue was declined or let lapse", async () => {
  const { d, r } = await setup();
  expect(d.ddzCanQueue.value).toBe(true);
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: null, reason: "ddz_match_cooldown", retry: 3 });
  expect(d.ddzRetry.value).toBe(true);
  expect(d.ddzCanQueue.value).toBe(false);
  expect(r.lastError.value).toBe(""); // the lobby says it
  const sent = lk.sent.length;
  d.queueDdz(50);
  expect(lk.sent).toHaveLength(sent);
  await vi.advanceTimersByTimeAsync(2900);
  expect(d.ddzRetry.value).toBe(true);
  await vi.advanceTimersByTimeAsync(100);
  expect(d.ddzRetry.value).toBe(false);
  expect(d.ddzCanQueue.value).toBe(true);
  // Refused for it all the same (another device declined): the words show where the room's errors do.
  d.queueDdz(50);
  lk.recv({ type: "error", code: "ddz_match_cooldown", message: "" });
  expect(r.lastError.value).toBe("稍后再匹配");
});

it("keeps queue requests a server interval apart, and sends a join the server held back once more", async () => {
  const { d, settings } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  const queue = () => sentOf(lk, "ddz_queue");
  expect(queue()).toEqual([{ type: "ddz_queue", base: 50 }]); // the first goes once the connection is ready
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  d.unqueueDdz(); // stopping is never held back
  expect(queue()).toHaveLength(2);
  lk.recv({ type: "ddz_queue", base: null });
  d.queueDdz(250);
  d.queueDdz(50); // the latest stake picked is the one sent
  expect(queue()).toHaveLength(2);
  await vi.advanceTimersByTimeAsync(1100);
  expect(queue().slice(2)).toEqual([{ type: "ddz_queue", base: 50 }]);
  // Held back by the server all the same (another device of the save): sent once more after the interval.
  lk.recv({ type: "error", code: "rate_limited", message: "" });
  expect(queue()).toHaveLength(3);
  await vi.advanceTimersByTimeAsync(1100);
  expect(queue().slice(3)).toEqual([{ type: "ddz_queue", base: 50 }]);
  lk.recv({ type: "error", code: "rate_limited", message: "" });
  await vi.advanceTimersByTimeAsync(3000);
  expect(queue()).toHaveLength(4); // only once
  // A join waiting for its time is checked again when it goes, and stopping drops it.
  d.queueDdz(250); // the interval has passed: at once
  expect(queue()).toHaveLength(5);
  lk.recv({ type: "ddz_queue", base: 250, waited: 0 });
  d.queueDdz(50);
  d.unqueueDdz();
  lk.recv({ type: "ddz_queue", base: null });
  d.queueDdz(50);
  settings.duelDnd = true;
  await vi.advanceTimersByTimeAsync(1100);
  expect(queue().slice(5)).toEqual([{ type: "ddz_queue", base: 0 }]);
  // Stopping before the server answered a join takes it back.
  settings.duelDnd = false;
  d.queueDdz(250);
  d.unqueueDdz();
  expect(queue().slice(6)).toEqual([{ type: "ddz_queue", base: 250 }, { type: "ddz_queue", base: 0 }]);
});

it("takes a rate_limited answer of the room as nothing of the queue", async () => {
  const { socket, d } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A, B], features: ["ddz_match"] });
  d.queueDdz(50);
  const lk = linkUp();
  socket.recv({ type: "ddz_deal", table: "t", seats: SEATS, you: 1, hand: HAND, base: 100, cap: 24, deal: 1, turn: 1, sec: 15, dealSec: 0 });
  d.bidDdz(1);
  expect(d.ddz.value!.acted).toBe(true);
  socket.recv({ type: "error", code: "rate_limited", message: "" }); // taps, say
  await vi.advanceTimersByTimeAsync(1100);
  expect(d.ddz.value!.acted).toBe(true); // the bid on its way keeps its keys down
  expect(sentOf(lk, "ddz_queue")).toHaveLength(1);
});

it("keeps the hold on the queue through a new connection, and drops it with another save or server", async () => {
  const { d, player, settings } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: null, reason: "ddz_match_cooldown", retry: 30 });
  player.status.value = playerStatus() as typeof player.status.value; // the same save, read again
  lk.close();
  expect(d.ddzRetry.value).toBe(true);
  player.status.value = playerStatus({ player: "q" }) as typeof player.status.value;
  expect(d.ddzRetry.value).toBe(false);
  expect(lk.readyState).toBe(3);
  // Another server: the hold, the wait, the counts and the connection go.
  d.queueDdz(50);
  const again = linkUp();
  again.recv({ type: "ddz_queue", base: null, reason: "ddz_match_cooldown", retry: 30 });
  again.recv({ type: "ddz_waiting", counts: [[50, 2]] });
  settings.serverUrl = "https://other.example";
  expect([d.ddzRetry.value, d.ddzQueue.value, d.ddzWaiting.value, again.readyState]).toEqual([false, null, {}, 3]);
  await vi.advanceTimersByTimeAsync(30000);
  expect(d.ddzRetry.value).toBe(false);
});

// ------------------------------------------------------------------ open tables
const NEW_A = { ...A, ddzMatch: true };
const seatOf = ({ id, nick, character }: { id: string; nick: string; character: string }) => ({ id, nick, character });

it("opens a table only where the server has open tables, and shows it as the server says", async () => {
  const { socket, d, r } = await setup();
  d.openDdz(50);
  expect(socket.sent.filter((m) => m.type === "ddz_open")).toEqual([]); // the server did not list them
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, NEW_A, B, OLD], features: ["ddz_match"] });
  expect(d.ddzCanOpen.value).toBe(true);
  d.openDdz(500); // cannot pay the deposit
  d.openDdz(50);
  expect(socket.sent.filter((m) => m.type === "ddz_open")).toEqual([{ type: "ddz_open", base: 50 }]);
  socket.recv({ type: "ddz_open", table: "o1", base: 50, deposit: 2400, you: 0, seats: [seatOf(ME), null, null], sec: 600 });
  expect(d.ddz.value).toMatchObject({ id: "o1", phase: "open", you: 0, base: 50, deposit: 2400, starting: false });
  expect(d.ddz.value!.seats.map((s) => [s.id, !!s.pending])).toEqual([["me", false], ["", false], ["", false]]);
  expect(d.ddz.value!.until).toBe(Date.now() + 600_000);
  expect([d.ddzBusy.value, d.ddzCanQueue.value, d.ddzCanOpen.value, d.ddzBubble.value]).toEqual([true, false, false, null]);
  // Members on clients with open tables are called; others stay greyed.
  expect([NEW_A, B, OLD].map((m) => d.ddzCanCall(r.members.get(m.id)!))).toEqual([true, false, false]);
  d.callDdz("b", "o1");
  d.callDdz("a", "o0"); // pressed for a table that is gone
  d.callDdz("a", "o1");
  expect(socket.sent.filter((m) => m.type === "ddz_call")).toEqual([{ type: "ddz_call", table: "o1", id: "a" }]);
  socket.recv({ type: "ddz_open", table: "o1", base: 50, deposit: 2400, you: 0, seats: [seatOf(ME), seatOf(NEW_A), { pending: true }], sec: 590 });
  expect(d.ddz.value!.seats.map((s) => [s.id, !!s.pending])).toEqual([["me", false], ["a", false], ["", true]]);
  expect(d.ddzCanCall(r.members.get("a")!)).toBe(false); // no seat empty, and a sits here
  socket.recv({ type: "ddz_open", table: "o1", base: 50, deposit: 2400, you: 0, seats: [seatOf(ME), seatOf(NEW_A), seatOf(B)], sec: 580, starting: true });
  expect(d.ddz.value!.starting).toBe(true);
  socket.recv({ type: "ddz_deal", table: "o1", seats: SEATS, you: 1, hand: HAND, base: 50, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 0 });
  expect(d.ddz.value).toMatchObject({ phase: "bid", starting: false, deposit: 2400 });
});

it("stands up or puts the open table away, and says why it went", async () => {
  const { socket, d } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, NEW_A], features: ["ddz_match"] });
  socket.recv({ type: "ddz_open", table: "o1", base: 50, deposit: 2400, you: 1, seats: [seatOf(NEW_A), seatOf(ME), null], sec: 600 });
  // A key pressed for another table, or for the table as it was, leaves nothing.
  const sent = socket.sent.length;
  d.leaveDdz("o0", "open");
  d.leaveDdz("o1", "invite");
  expect(socket.sent.length).toBe(sent);
  expect(d.ddz.value).toMatchObject({ id: "o1", phase: "open" });
  d.leaveDdz("o1", "open");
  expect(socket.sent.at(-1)).toEqual({ type: "ddz_leave", table: "o1" });
  expect(d.ddz.value).toBeNull();
  socket.recv({ type: "ddz_open", table: "o2", base: 50, deposit: 2400, you: 1, seats: [seatOf(NEW_A), seatOf(ME), null], sec: 600 });
  socket.recv({ type: "ddz_over", table: "o2", reason: "disband", by: "a" });
  expect(d.ddz.value).toMatchObject({ phase: "over", reason: "disband" });
  expect(d.ddzReason(d.ddz.value!)).toBe("已散桌");
  expect(d.ddzBubble.value).toBe("over");
  // After a game the table opens again for those who asked for another.
  socket.recv({ type: "ddz_open", table: "o3", base: 50, deposit: 2400, you: 0, seats: [seatOf(ME), null, null], sec: 600 });
  expect(d.ddzBubble.value).toBeNull(); // sat down just now: nothing to say
  Object.assign(d.ddz.value!, { phase: "result" });
  // All three asked for another: while the deposits are taken the result stays on the table, which stays up.
  socket.recv({ type: "ddz_open", table: "o3", base: 50, deposit: 2400, you: 0, seats: [seatOf(ME), seatOf(NEW_A), seatOf(B)], sec: 600, starting: true });
  expect(d.ddz.value).toMatchObject({ id: "o3", phase: "result" });
  expect(d.ddzAtTable.value).toBe(true);
  // One of them could not pay: the table waits again without it.
  socket.recv({ type: "ddz_open", table: "o3", base: 50, deposit: 2400, you: 0, seats: [seatOf(ME), seatOf(NEW_A), null], sec: 600 });
  expect(d.ddz.value).toMatchObject({ id: "o3", phase: "open" });
  // Back from the game, the pet shows the table waiting again for a moment.
  expect(d.ddzBubble.value).toBe("open");
  expect(d.ddzReopened.value).toEqual({ table: "o3", until: Date.now() + d.REOPEN_CUE_MS });
  socket.recv({ type: "ddz_open", table: "o3", base: 50, deposit: 2400, you: 0, seats: [seatOf(ME), seatOf(NEW_A), seatOf(B)], sec: 590, starting: true });
  expect(d.ddzBubble.value).toBeNull();
  socket.recv({ type: "ddz_open", table: "o3", base: 50, deposit: 2400, you: 0, seats: [seatOf(ME), seatOf(NEW_A), null], sec: 590 });
  expect(d.ddzBubble.value).toBe("open");
  await vi.advanceTimersByTimeAsync(d.REOPEN_CUE_MS);
  expect(d.ddzBubble.value).toBeNull();
});

it("sits down at an open table of the room or at one it was called to, and forgets both with the room", async () => {
  const { socket, d, settings } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, NEW_A], features: ["ddz_match"] });
  const tables = [{ table: "o1", base: 50, seats: [seatOf(NEW_A), null, { pending: true as const }] }, { table: "o2", base: 500, seats: [seatOf(B), null, null] }];
  socket.recv({ type: "ddz_tables", tables });
  expect(d.ddzTables.value).toEqual(tables);
  d.sitDdz("o2"); // cannot pay its deposit
  d.sitDdz("nope");
  d.sitDdz("o1", 1);
  expect(socket.sent.filter((m) => m.type === "ddz_sit")).toEqual([{ type: "ddz_sit", table: "o1", seat: 1 }]);
  // Called over the pet: the bubble shows until the time is up.
  socket.recv({ type: "ddz_call", table: "o9", from: "a", base: 50, deposit: 2400, sec: 15, seats: [seatOf(NEW_A), null, null] });
  expect(d.ddzCall.value).toMatchObject({ table: "o9", from: "a", base: 50, until: Date.now() + 15_000 });
  expect(d.ddzBubble.value).toBe("call");
  d.sitDdz("o9");
  expect(socket.sent.at(-1)).toEqual({ type: "ddz_sit", table: "o9" });
  await vi.advanceTimersByTimeAsync(15_000);
  expect(d.ddzCall.value).toBeNull();
  socket.recv({ type: "ddz_call", table: "o9", from: "a", base: 50, deposit: 2400, sec: 15, seats: [seatOf(NEW_A), null, null] });
  d.dismissDdzCall();
  expect(d.ddzBubble.value).toBeNull();
  socket.recv({ type: "ddz_call", table: "o9", from: "a", base: 50, deposit: 2400, sec: 15, seats: [seatOf(NEW_A), null, null] });
  socket.recv({ type: "ddz_open", table: "o9", base: 50, deposit: 2400, you: 1, seats: [seatOf(NEW_A), seatOf(ME), null], sec: 600 });
  expect(d.ddzCall.value).toBeNull();
  d.leaveDdz();
  // Turning invites down keeps the save from sitting down.
  settings.duelDnd = true;
  const sent = socket.sent.length;
  d.sitDdz("o1");
  expect(socket.sent.slice(sent).filter((m) => m.type === "ddz_sit")).toEqual([]);
  socket.recv({ type: "ddz_call", table: "o9", from: "a", base: 50, deposit: 2400, sec: 15, seats: [seatOf(NEW_A), null, null] });
  socket.close();
  expect([d.ddzTables.value, d.ddzCall.value]).toEqual([[], null]);
});

it("answers the seat of an open table offered from the queue, and sits there on the connection", async () => {
  const { d } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({
    type: "ddz_invite", table: "o1", ids: ["x", "", "L"], base: 50, deposit: 2400, sec: 15, match: true,
    seats: [X, null, { ...ME, id: "L" }], accepted: ["x"],
  });
  expect(d.ddz.value).toMatchObject({ id: "o1", via: "link", phase: "invite", you: 2, match: true, accepted: ["x"] });
  expect(d.ddz.value!.seats.map((s) => [s.id, s.nick])).toEqual([["x", "远方"], ["", ""], ["L", "我"]]);
  d.answerDdz(true);
  expect(lk.sent.at(-1)).toEqual({ type: "ddz_answer", table: "o1", accept: true });
  lk.recv({ type: "ddz_open", table: "o1", base: 50, deposit: 2400, you: 2, seats: [X, null, seatOf({ ...ME, id: "L" })], sec: 540 });
  expect(d.ddz.value).toMatchObject({ phase: "open", via: "link", you: 2 });
  d.leaveDdz("o1", "open");
  expect(lk.sent.at(-1)).toEqual({ type: "ddz_leave", table: "o1" });
});

it("sends a table emote to the room on a server without table emotes", async () => {
  const { socket, d, r, player } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A, B], features: ["ddz_match"] });
  socket.recv({ type: "ddz_deal", table: "t", seats: SEATS, you: 1, hand: HAND, base: 100, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 0 });
  player.collection.owned = { "emote:thumbup": 1 } as typeof player.collection.owned;
  const sent = socket.sent.length;
  d.emoteDdz("thumbup");
  expect(r.localPet.emote).toMatchObject({ key: "thumbup" });
  expect(socket.sent.slice(sent)).toEqual([{ type: "emote", emote: "thumbup" }]);
});

it("stops the wait on the server when it was stopped while the connection was down", async () => {
  const { d } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  lk.close();
  expect(d.ddzLink.value).toBe("reconnecting");
  d.unqueueDdz();
  expect(d.ddzQueue.value).toBeNull();
  await vi.advanceTimersByTimeAsync(1000);
  // The new hello took the wait over: it is stopped there, and not shown.
  const lk2 = linkUp({ base: 50, waited: 3 });
  expect(sentOf(lk2, "ddz_queue")).toEqual([{ type: "ddz_queue", base: 0 }]);
  expect(d.ddzQueue.value).toBeNull();
  // Dropped before the server said so: the next hello stops it again.
  lk2.close();
  await vi.advanceTimersByTimeAsync(1000);
  const lk3 = linkUp({ base: 50, waited: 4 });
  expect(sentOf(lk3, "ddz_queue")).toEqual([{ type: "ddz_queue", base: 0 }]);
  lk3.recv({ type: "ddz_queue", base: null });
  // Said: a later hello that still finds a wait (another device's) shows it.
  lk3.close();
  await vi.advanceTimersByTimeAsync(1000);
  const lk4 = linkUp({ base: 50, waited: 1 });
  expect(sentOf(lk4, "ddz_queue")).toEqual([]);
  expect(d.ddzQueue.value).toMatchObject({ base: 50 });
});

it("asks again for a seat the server kept after a failed read, and drops an answer for another save", async () => {
  const { d, fetchMock, player } = await setup();
  const lobbyCalls = () => fetchMock.mock.calls.filter((c) => String((c as unknown[])[0]).endsWith("/api/ddz/lobby"));
  await vi.advanceTimersByTimeAsync(0);
  expect(lobbyCalls()).toHaveLength(1);
  // Another save whose read fails: asked again later.
  let answer: (v: unknown) => void = () => {};
  fetchMock.mockImplementation((async (url: string) => (String(url).endsWith("/api/ddz/lobby")
    ? { ok: false, status: 500, json: async () => ({ error: { code: "x", message: "" } }) }
    : { ok: true, status: 200, json: async () => playerStatus({ player: "q" }) })) as never);
  player.status.value = playerStatus({ player: "q" }) as typeof player.status.value;
  await vi.advanceTimersByTimeAsync(0);
  expect(lobbyCalls()).toHaveLength(2);
  fetchMock.mockImplementation((async (url: string) => (String(url).endsWith("/api/ddz/lobby")
    ? { ok: true, status: 200, json: async () => ({ tiers: [], seated: true }) }
    : { ok: true, status: 200, json: async () => playerStatus({ player: "q" }) })) as never);
  await vi.advanceTimersByTimeAsync(d.PROBE_RETRY_MS);
  expect(lobbyCalls()).toHaveLength(3);
  expect(d.ddzLink.value).toBe("connecting");
  // A save whose answer comes late, after another save took its place: the answer is dropped.
  fetchMock.mockImplementation(((url: string) => (String(url).endsWith("/api/ddz/lobby")
    ? new Promise((resolve) => { answer = resolve; })
    : Promise.resolve({ ok: true, status: 200, json: async () => playerStatus({ player: "s" }) }))) as never);
  player.status.value = playerStatus({ player: "s" }) as typeof player.status.value;
  await vi.advanceTimersByTimeAsync(0);
  player.status.value = playerStatus({ player: "t" }) as typeof player.status.value;
  await vi.advanceTimersByTimeAsync(0);
  answer({ ok: false, status: 404, json: async () => ({ error: { code: "no_ddz", message: "" } }) });
  await vi.advanceTimersByTimeAsync(0);
  expect(d.ddzLinkOff.value).toBe(false);
});

it("keeps a table of one connection when a late message of the other names an older one", async () => {
  const { socket, d } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A, B], features: ["ddz_match", "ddz_emote"] });
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  // A table of the queue comes up on the dou dizhu connection.
  lk.recv({ type: "ddz_invite", table: "m1", ids: ["L", "x", "y"], base: 50, deposit: 2400, sec: 15, match: true, seats: [{ ...ME, id: "L" }, X, Y] });
  expect(d.ddz.value).toMatchObject({ id: "m1", via: "link" });
  // The room's invite of before, and its ending, arrive late: the table of the queue comes back.
  socket.recv({ type: "ddz_invite", table: "r1", from: "a", ids: ["a", "me", "b"], base: 50, deposit: 2400, sec: 15 });
  expect(d.ddz.value).toMatchObject({ id: "r1", via: "room" });
  socket.recv({ type: "ddz_over", table: "r1", reason: "declined", by: "b" });
  expect(d.ddz.value).toMatchObject({ id: "m1", via: "link", phase: "invite" });
  // An ending of a table not on screen ends nothing else.
  socket.recv({ type: "ddz_over", table: "r0", reason: "timeout" });
  expect(d.ddz.value).toMatchObject({ id: "m1", phase: "invite" });
  // The other way round: the table put aside ends first, the one on screen stays.
  socket.recv({ type: "ddz_invite", table: "r2", from: "a", ids: ["a", "me", "b"], base: 50, deposit: 2400, sec: 15 });
  lk.recv({ type: "ddz_over", table: "m1", reason: "timeout" });
  expect(d.ddz.value).toMatchObject({ id: "r2", via: "room" });
  socket.recv({ type: "ddz_over", table: "r2", reason: "declined", by: "b" });
  await vi.advanceTimersByTimeAsync(d.DDZ_END_MS);
  expect(d.ddz.value).toBeNull();
});

it("backs off a server that takes the socket and drops it before the hello goes through", async () => {
  const { d } = await setup();
  d.queueDdz(50);
  const delays: number[] = [];
  for (let i = 0; i < 4; i++) {
    const lk = Socket.all.at(-1)!;
    lk.open();
    lk.close();
    const before = Socket.all.length;
    let waited = 0;
    while (Socket.all.length === before && waited < 60_000) {
      await vi.advanceTimersByTimeAsync(100);
      waited += 100;
    }
    delays.push(waited);
  }
  // Longer each time (500 ms doubling, plus up to 250 ms of jitter), not 500 ms over and over.
  expect(delays[3]).toBeGreaterThanOrEqual(4000);
});

it("stops without turning the queue off when another device took over, and joins again when asked", async () => {
  const { d, r } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  lk.recv({ type: "error", code: "room_full", message: "", reason: "ddz_queued" });
  expect([d.ddzLinkOff.value, d.ddzQueue.value, d.ddzLink.value, r.lastError.value]).toEqual([false, null, "idle", "已在别处匹配"]);
  const sockets = Socket.all.length;
  await vi.advanceTimersByTimeAsync(30_000);
  expect(Socket.all).toHaveLength(sockets);
  await vi.advanceTimersByTimeAsync(2000);
  d.queueDdz(50);
  expect(Socket.all).toHaveLength(sockets + 1);
  const lk2 = linkUp();
  await vi.advanceTimersByTimeAsync(0);
  expect(sentOf(lk2, "ddz_queue")).toEqual([{ type: "ddz_queue", base: 50 }]);
});

it("keeps the dou dizhu connection up while a room's invite holds the save, and gets the place back", async () => {
  const { socket, d } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A, B], features: ["ddz_match", "ddz_emote"] });
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  // Invited in the room: the server takes the save out of the line while the invite is out.
  socket.recv({ type: "ddz_invite", table: "r1", from: "a", ids: ["a", "me", "b"], base: 50, deposit: 2400, sec: 15 });
  lk.recv({ type: "ddz_queue", base: null });
  expect(d.ddzQueue.value).toBeNull();
  await vi.advanceTimersByTimeAsync(16_000);
  expect([lk.readyState, d.ddzLink.value]).toEqual([1, "open"]);
  // The invite came to nothing: the place comes back on the same connection.
  socket.recv({ type: "ddz_over", table: "r1", reason: "timeout" });
  lk.recv({ type: "ddz_queue", base: 50, waited: 16 });
  expect(d.ddzQueue.value).toMatchObject({ base: 50 });
  expect(lk.readyState).toBe(1);
});
