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
  const ui = (await import("./ui")).ui;
  player.status.value = playerStatus(over) as typeof player.status.value;
  const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => playerStatus(over) }));
  vi.stubGlobal("fetch", fetchMock);
  room.joinRoom("r");
  const socket = Socket.all[0]!;
  socket.open();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A, B, OLD] });
  return { settings, socket, r: room, d, player, fetchMock, ui };
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
  const { socket, d, r, fetchMock, ui } = await setup();
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
  expect(ui.panelOpen && ui.page === "room").toBe(true); // the table comes up
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
  d.leaveDdz();
  expect(socket.sent).toHaveLength(end + 1); // nothing left to leave
  expect(d.ddz.value).toBeNull();
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
