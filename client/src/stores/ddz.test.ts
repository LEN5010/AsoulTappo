import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { WsLike } from "../net/RoomClient";
import { TERMS_VERSION } from "../legal";
import { APP_VERSION } from "../version";
import { withEconomy } from "../test/economy";

// The cue when a game starts at a table the save waited at: a call is enough here (no audio in tests).
const tableCue = vi.hoisted(() => vi.fn());
vi.mock("../audio/sfx", async (original) => ({ ...(await original<typeof import("../audio/sfx")>()), tableCue }));

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
  vi.resetModules(); vi.useFakeTimers(); Socket.all = []; tableCue.mockClear();
  const agreed = JSON.stringify({ termsAgreed: TERMS_VERSION, statementSeen: APP_VERSION });
  vi.stubGlobal("localStorage", { getItem: withEconomy((k: string) => (k === "asoultappo.settings.v1" ? agreed : null)), setItem: () => {} });
  vi.stubGlobal("WebSocket", Socket);
});
afterEach(async () => {
  room?.leaveRoom(); room = undefined;
  // Reads still on their way end on this test's stubs: past the test they would go out, and count in the next one.
  await vi.advanceTimersByTimeAsync(0);
  vi.useRealTimers(); vi.unstubAllGlobals();
});

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
  expect(socket.sent[0]).toMatchObject({ type: "join", ddz: true, ddzWatch: true });
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
  expect(frame.open).toBe(false); // the table is put away: its window goes too
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
  deal(1); // 再来一局: the server counts each game's deals from 1 again
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

it("asks for the card counter where it is sold, one asking at a time, and leaves it free elsewhere", async () => {
  const { socket, d, fetchMock } = await setup();
  const deal = { type: "ddz_deal", table: "t", seats: SEATS, you: 1, hand: HAND, base: 100, cap: 24, turn: 1, sec: 15, dealSec: 0 };
  socket.recv({ ...deal, deal: 1 });
  const t = () => d.ddz.value!;
  // A server that does not sell it says nothing of it: the counter is free, and there is nothing to ask for.
  expect(t().counter).toBeNull();
  const sent = socket.sent.length;
  d.counterDdz();
  expect(socket.sent).toHaveLength(sent);

  socket.recv({ ...deal, deal: 2, counter: { on: false, left: 0 } });
  expect(t()).toMatchObject({ counter: { on: false, left: 0 }, counterAsked: false, counterError: "" });
  d.counterDdz();
  d.counterDdz();
  expect(socket.sent.slice(sent)).toEqual([{ type: "ddz_counter", table: "t" }]);
  expect(t().counterAsked).toBe(true);
  await vi.advanceTimersByTimeAsync(0);
  const reads = fetchMock.mock.calls.length;
  // Nothing bought: the reason shows, the balance is not read again, and asking again clears it.
  socket.recv({ type: "ddz_counter", table: "t", on: false, left: 0, error: "no_shards" });
  expect(t()).toMatchObject({ counter: { on: false, left: 0 }, counterAsked: false, counterError: "no_shards" });
  await vi.advanceTimersByTimeAsync(0);
  expect(fetchMock.mock.calls.length).toBe(reads);
  d.counterDdz();
  expect(t()).toMatchObject({ counterAsked: true, counterError: "" });
  socket.recv({ type: "ddz_counter", table: "t", on: false, left: 10 });
  expect(t()).toMatchObject({ counter: { on: false, left: 10 }, counterAsked: false });
  await vi.advanceTimersByTimeAsync(0);
  expect(fetchMock.mock.calls.length).toBe(reads + 1); // the coins and shards changed

  // The landlord is known: the server says a game of it was used, before the play shows.
  socket.recv({ type: "ddz_bid", table: "t", seat: 1, bid: 3 });
  socket.recv({ type: "ddz_counter", table: "t", on: true, left: 9 });
  socket.recv({ type: "ddz_landlord", table: "t", seat: 1, bid: 3, bottom: [5, 9, 53], mult: 3, turn: 1, sec: 30 });
  expect(t()).toMatchObject({ phase: "play", counter: { on: true, left: 9 } });
  const before = socket.sent.length;
  d.counterDdz(); // on already
  expect(socket.sent).toHaveLength(before);

  // A seat taken again hears it with the whole state; a move the server refuses gives the key back.
  socket.recv({
    type: "ddz_state", table: "t", phase: "play", you: 1, hand: [0, 4, 53],
    seats: SEATS.map((x) => ({ ...x, left: 5, bid: 0 })), base: 100, cap: 24, deal: 2, bid: 3, landlord: 1, bottom: [1, 2, 3], mult: 3,
    bombs: 0, turn: 1, lead: true, trick: [null, null, null], sec: 20, of: 30, played: [], counter: { on: false, left: 0 },
  });
  expect(t().counter).toEqual({ on: false, left: 0 });
  d.counterDdz();
  expect(t().counterAsked).toBe(true);
  socket.recv({ type: "error", code: "ddz_gone", message: "" });
  expect(t().counterAsked).toBe(false);
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
  expect(lk.sent).toEqual([{ type: "ddz_hello", nick: settings.nick.trim() || "匿名小面包", character: settings.character, token: expect.any(String), ddzWatch: true }]);
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
  // Put back at the front of the line, still counting from when it started waiting; why the table fell through stays
  // up for its moment first.
  lk.recv({ type: "ddz_queue", base: 50, waited: 20 });
  expect(d.ddzQueue.value).toEqual({ base: 50, since: Date.now() - 20000 });
  expect([d.ddzBubble.value, d.ddzReason(d.ddz.value!)]).toEqual(["over", "天边没有接受"]);
  await vi.advanceTimersByTimeAsync(d.DDZ_END_MS - 1);
  expect(d.ddzBubble.value).toBe("over");
  await vi.advanceTimersByTimeAsync(1);
  expect([d.ddz.value, d.ddzBubble.value, d.ddzQueue.value?.base]).toEqual([null, null, 50]);
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

/** An invite of the queue's to the save (member [you]) and two others. */
const matchInvite = (table: string, you: string, more: Record<string, unknown> = {}) => ({
  type: "ddz_invite", table, ids: ["x", you, "y"], base: 50, deposit: 2400, sec: 15, match: true,
  seats: [X, { ...ME, id: you }, Y], ...more,
});

it("gives an answer that did not arrive again when the next connection is asked the same", async () => {
  const { d } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv(matchInvite("m1", "L"));
  expect(d.ddzCut.value).toBe(false);
  // The connection goes before the answer arrives: nothing is accepted yet, and the keys give way.
  lk.close();
  expect(d.ddzCut.value).toBe(true);
  const sent = lk.sent.length;
  d.answerDdz(true);
  expect(lk.sent).toHaveLength(sent);
  expect(d.ddz.value).toMatchObject({ id: "m1", phase: "invite", answered: false });
  await vi.advanceTimersByTimeAsync(1000);
  const lk2 = linkUp({ you: "L2", table: "m1" });
  expect(sentOf(lk2, "ddz_answer")).toEqual([]); // not before it is asked
  lk2.recv(matchInvite("m1", "L2", { accepted: ["x"], sec: 13 }));
  expect(sentOf(lk2, "ddz_answer")).toEqual([{ type: "ddz_answer", table: "m1", accept: true }]);
  expect(d.ddzCut.value).toBe(false);
  expect(d.ddz.value).toMatchObject({ id: "m1", answered: true, accepted: ["x"] });
  lk2.recv({ type: "ddz_answer", table: "m1", id: "L2" });
  // Arrived: asked once more on another connection, it is not given again.
  lk2.close();
  await vi.advanceTimersByTimeAsync(2000);
  const lk3 = linkUp({ you: "L3", table: "m1" });
  lk3.recv(matchInvite("m1", "L3", { accepted: ["x", "L3"], sec: 9 }));
  expect(sentOf(lk3, "ddz_answer")).toEqual([]);
  expect(d.ddz.value).toMatchObject({ answered: true });
});

it("gives an answer again that went out on a connection already dead, and a refusal too", async () => {
  const { d } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv(matchInvite("m1", "L"));
  d.answerDdz(true); // out, but the server never had it
  expect(d.ddz.value!.answered).toBe(true);
  lk.close();
  await vi.advanceTimersByTimeAsync(1000);
  const lk2 = linkUp({ you: "L2", table: "m1" });
  lk2.recv(matchInvite("m1", "L2"));
  expect(sentOf(lk2, "ddz_answer")).toEqual([{ type: "ddz_answer", table: "m1", accept: true }]);
  lk2.recv({ type: "ddz_over", table: "m1", reason: "declined", by: "y" });
  await vi.advanceTimersByTimeAsync(d.DDZ_END_MS);
  // Turned down on a dead connection: told again, and not shown again.
  lk2.recv(matchInvite("m2", "L2"));
  d.answerDdz(false);
  lk2.close();
  await vi.advanceTimersByTimeAsync(3000);
  const lk3 = linkUp({ you: "L3", table: "m2" });
  lk3.recv(matchInvite("m2", "L3"));
  expect(sentOf(lk3, "ddz_answer")).toEqual([{ type: "ddz_answer", table: "m2", accept: false }]);
  expect([d.ddz.value, d.ddzBubble.value]).toEqual([null, null]);
});

it("never answers an asking with an answer given to an earlier one", async () => {
  const { d, settings } = await setup();
  d.queueDdz(50);
  let lk = linkUp();
  const offer = (you: string) => matchInvite("o1", you, { ids: ["x", you, ""], seats: [X, { ...ME, id: you }, null], accepted: ["x"] });
  const again = async (ready: Record<string, unknown>) => {
    lk.close();
    await vi.advanceTimersByTimeAsync(20_000);
    lk = linkUp(ready);
  };
  // Accepted and seated, left, and offered the same table later: asked as if for the first time.
  lk.recv(offer("L"));
  d.answerDdz(true);
  lk.recv({ type: "ddz_open", table: "o1", base: 50, deposit: 2400, you: 1, seats: [X, { ...ME, id: "L" }, null], sec: 540 });
  d.leaveDdz("o1", "open");
  lk.recv({ type: "ddz_closed", table: "o1" });
  d.queueDdz(50);
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  lk.recv(offer("L"));
  expect(d.ddz.value).toMatchObject({ id: "o1", answered: false });
  expect(sentOf(lk, "ddz_answer")).toHaveLength(1);
  // Turned down, and the server says the seat is gone: a new connection asked for it later is not answered for.
  d.answerDdz(false);
  lk.recv({ type: "ddz_over", table: "o1", reason: "declined" });
  lk.recv({ type: "ddz_queue", base: null, reason: "ddz_match_cooldown", retry: 1 });
  await vi.advanceTimersByTimeAsync(1000);
  d.queueDdz(50);
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  await again({ base: 50, table: null });
  lk.recv(offer("L"));
  expect(sentOf(lk, "ddz_answer")).toEqual([]);
  expect(d.ddz.value).toMatchObject({ id: "o1", answered: false });
  // Accepted on a dead connection, the table gone from the next one: the same table offered there asks anew.
  d.answerDdz(true);
  await again({ table: null });
  lk.recv(offer("L"));
  expect(sentOf(lk, "ddz_answer")).toEqual([]);
  expect(d.ddz.value).toMatchObject({ id: "o1", answered: false });
  // Accepted on a dead connection, then invites turned down for good: not given again.
  d.answerDdz(true);
  settings.duelDnd = true;
  await again({ you: "L9", table: "o1" });
  lk.recv(offer("L9"));
  expect(sentOf(lk, "ddz_answer")).toEqual([]);
  settings.duelDnd = false;
});

it("says the connection was lost when an invite or a seat went with it", async () => {
  const { d } = await setup();
  d.queueDdz(50);
  let lk = linkUp();
  lk.recv(matchInvite("m1", "L"));
  d.answerDdz(true);
  lk.close();
  await vi.advanceTimersByTimeAsync(1000);
  lk = linkUp();
  expect(d.ddzBubble.value).toBe("over");
  expect(d.ddzReason(d.ddz.value!)).toBe("掉线了");
  await vi.advanceTimersByTimeAsync(d.DDZ_END_MS);
  expect([d.ddz.value, d.ddzBubble.value]).toEqual([null, null]);
  // The same for a seat at an open table.
  lk.recv({ type: "ddz_open", table: "o1", base: 50, deposit: 2400, you: 1, seats: [X, { ...ME, id: "L" }, null], sec: 540 });
  lk.close();
  await vi.advanceTimersByTimeAsync(1000);
  linkUp();
  expect([d.ddzBubble.value, d.ddzReason(d.ddz.value!)]).toEqual(["over", "掉线了"]);
});

it("shows the seat the queue gave at an open table until the game or the table goes", async () => {
  const { socket, d, frame } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A], features: ["ddz_match"] });
  // A seat taken in the room is the room's: the sign of the queue does not show for it.
  socket.recv({ type: "ddz_open", table: "r1", base: 50, deposit: 2400, you: 0, seats: [{ ...ME }, null, null], sec: 600 });
  expect(d.ddzQueueSeat.value).toBeNull();
  socket.recv({ type: "ddz_closed", table: "r1" });
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  lk.recv({ type: "ddz_queue", base: null });
  lk.recv(matchInvite("o1", "L", { ids: ["x", "L", ""], seats: [X, { ...ME, id: "L" }, null], accepted: ["x"] }));
  expect(d.ddzQueueSeat.value).toBeNull();
  d.answerDdz(true);
  const seats = [X, { ...ME, id: "L" }];
  lk.recv({ type: "ddz_open", table: "o1", base: 50, deposit: 2400, you: 1, seats: [...seats, null], sec: 540 });
  expect([d.ddzQueueSeat.value?.id, d.ddzBubble.value, d.ddzQueue.value]).toEqual(["o1", null, null]);
  // Put away before its game: the reason shows, then the wait the server gave back.
  lk.recv({ type: "ddz_over", table: "o1", reason: "disband", by: "x" });
  lk.recv({ type: "ddz_queue", base: 50, waited: 90 });
  expect([d.ddzQueueSeat.value, d.ddzBubble.value, d.ddzReason(d.ddz.value!)]).toEqual([null, "over", "已散桌"]);
  await vi.advanceTimersByTimeAsync(d.DDZ_END_MS);
  expect([d.ddz.value, d.ddzQueue.value?.base]).toEqual([null, 50]);
  // Filled and dealt: the table's window comes up.
  lk.recv({ type: "ddz_queue", base: null });
  lk.recv({ type: "ddz_open", table: "o2", base: 50, deposit: 2400, you: 1, seats: [...seats, Y], sec: 500, starting: true });
  expect(d.ddzQueueSeat.value).toMatchObject({ id: "o2", starting: true });
  lk.recv({
    type: "ddz_deal", table: "o2", seats: [...seats, Y].map((s) => ({ auto: false, away: false, ...s })), you: 1, hand: HAND,
    base: 50, cap: 24, deal: 1, turn: 0, sec: 15, dealSec: 0,
  });
  expect([d.ddzQueueSeat.value, frame.open]).toEqual([null, true]);
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

it("sends back the tag of the hall's list it holds, and a list still the same keeps the hall on", async () => {
  const { fetchMock, player } = await setup();
  await vi.advanceTimersByTimeAsync(0);
  const head = { net: 0, cap: 50000, left: 50000, taps: 10000, minTaps: 10000, account: true, seated: false };
  const stake = { base: 50, deposit: 2400, afford: true, waiting: 1 };
  fetchMock.mockImplementation((async (url: string) => (String(url).includes("/api/ddz/lobby")
    ? {
      ok: true, status: 200, json: async () => (String(url).endsWith("/api/ddz/lobby?hall=ab0")
        ? { ...head, tiers: [stake], hallTag: "ab0", hallSame: true }
        : { ...head, tiers: [{ ...stake, tables: [] }], hallTag: "ab0" }),
    }
    : { ok: true, status: 200, json: async () => playerStatus() })) as never);
  expect(await player.loadDdzLobby()).toMatchObject({ hallTag: "ab0" });
  expect(player.ddzHallOn.value).toBe(true);
  expect(await player.loadDdzLobby("ab0")).toMatchObject({ hallSame: true });
  expect(player.ddzHallOn.value).toBe(true);
  const urls = fetchMock.mock.calls.map((c) => String((c as unknown[])[0]));
  expect(urls.filter((u) => u.endsWith("/api/ddz/lobby?hall=ab0"))).toHaveLength(1);
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

const LINK_WAIT = 12_000;

it("keeps a stop of the wait sent on a ready connection until the server says so", async () => {
  const { d } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_queue", base: 50, waited: 0 });
  d.unqueueDdz();
  expect(sentOf(lk, "ddz_queue").at(-1)).toEqual({ type: "ddz_queue", base: 0 });
  expect(d.ddzQueue.value).toBeNull();
  // Dropped before the answer: the new hello took the wait over, and it is stopped there.
  lk.close();
  await vi.advanceTimersByTimeAsync(12_000);
  expect(d.ddzLink.value).not.toBe("idle");
  const lk2 = linkUp({ base: 50, waited: 3 });
  expect(sentOf(lk2, "ddz_queue")).toEqual([{ type: "ddz_queue", base: 0 }]);
  expect(d.ddzQueue.value).toBeNull();
  // A hello that finds no wait does not join again.
  lk2.close();
  await vi.advanceTimersByTimeAsync(1000);
  const lk3 = linkUp();
  await vi.advanceTimersByTimeAsync(2000);
  expect(sentOf(lk3, "ddz_queue")).toEqual([]);
  expect(d.ddzQueue.value).toBeNull();
});

it("goes on with a game put aside behind a late room invite and brings it back as it stands", async () => {
  const { socket, d } = await setup();
  socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A, B], features: ["ddz_match", "ddz_emote"] });
  d.queueDdz(50);
  const lk = linkUp();
  const seats = [{ ...ME, id: "L" }, X, Y].map((s) => ({ auto: false, away: false, ...s }));
  lk.recv({ type: "ddz_deal", table: "m1", seats, you: 0, hand: HAND, base: 50, cap: 24, deal: 1, turn: 1, sec: 15, dealSec: 0 });
  // A room invite of before arrives late and takes the screen; the game goes on behind it.
  socket.recv({ type: "ddz_invite", table: "r1", from: "a", ids: ["a", "me", "b"], base: 50, deposit: 2400, sec: 15 });
  expect(d.ddz.value).toMatchObject({ id: "r1" });
  lk.recv({ type: "ddz_bid", table: "m1", seat: 1, bid: 2, turn: 2, sec: 15 });
  // Its connection stays up meanwhile.
  await vi.advanceTimersByTimeAsync(LINK_WAIT);
  expect(lk.readyState).toBe(1);
  socket.recv({ type: "ddz_over", table: "r1", reason: "declined", by: "b" });
  expect(d.ddz.value).toMatchObject({ id: "m1", phase: "bid", bid: 2, turn: 2 });
  expect(d.ddz.value!.seats[1]!.bid).toBe(2);
});

it("asks again later for a seat it could not take back on a full server", async () => {
  const { d, fetchMock, player } = await setup();
  const lobbyCalls = () => fetchMock.mock.calls.filter((c) => String((c as unknown[])[0]).endsWith("/api/ddz/lobby"));
  fetchMock.mockImplementation((async (url: string) => (String(url).endsWith("/api/ddz/lobby")
    ? { ok: true, status: 200, json: async () => ({ tiers: [], seated: true }) }
    : { ok: true, status: 200, json: async () => playerStatus({ player: "q" }) })) as never);
  player.status.value = playerStatus({ player: "q" }) as typeof player.status.value;
  await vi.advanceTimersByTimeAsync(0);
  const calls = lobbyCalls().length;
  const lk = Socket.all.at(-1)!;
  lk.open();
  lk.recv({ type: "error", code: "room_full", message: "", reason: "ddz_full" });
  expect([d.ddzLink.value, d.ddzLinkOff.value]).toEqual(["idle", false]);
  await vi.advanceTimersByTimeAsync(d.PROBE_RETRY_MS);
  expect(lobbyCalls().length).toBe(calls + 1);
  expect(d.ddzLink.value).toBe("connecting");
});

it("asked again on a new connection after accepting, shows the answer as given", async () => {
  const { d } = await setup();
  d.queueDdz(50);
  const lk = linkUp();
  lk.recv({ type: "ddz_invite", table: "m1", ids: ["L", "x", "y"], base: 50, deposit: 2400, sec: 9, match: true, seats: [{ ...ME, id: "L" }, X, Y], accepted: ["x", "L"] });
  expect(d.ddz.value).toMatchObject({ id: "m1", answered: true, accepted: ["x", "L"] });
});

// ------------------------------------------------------------------ watching
async function watchSetup() {
  const ctx = await setup();
  ctx.socket.recv({ type: "joined", room: "r", you: "me", members: [ME, A, B, OLD], features: ["ddz_match", "ddz_watch"] });
  // A game of the room: two members and a save from another room.
  ctx.socket.recv({ type: "ddz_live", table: "w", ids: ["a", "x", "b"], on: true, base: 50 });
  return ctx;
}
const WSEATS = [A, { id: "x", nick: "路人", character: "心宜" }, B].map(({ id, nick, character }) => ({ id, nick, character, auto: false, away: false }));
/** The game watched as the server sends it: in play, the landlord on seat 2, seat [seat]'s hand [hand]. */
function snapshot(seat: number, hand: number[] | null, over: Record<string, unknown> = {}) {
  return {
    type: "ddz_watch", table: "w", seat, hand, phase: "play", base: 50, cap: 24, deal: 1, bid: 2, landlord: 2,
    bottom: [5, 9, 53], mult: 2, bombs: 0, turn: 0, lead: true, trick: [null, null, null], sec: 20, of: 30, result: null,
    seats: WSEATS.map((s, i) => ({ ...s, left: [3, 17, 20][i]!, bid: [0, 1, 2][i]! })), ...over,
  };
}
const watchSent = (socket: Socket) => sentOf(socket, "ddz_watch");

it("keeps how each game of the room stands while the game is on", async () => {
  const { socket, d } = await watchSetup();
  const stands = (table: string, over: Record<string, unknown> = {}) => ({
    type: "ddz_live_state", table, landlord: 2, seats: [{ left: 3 }, { left: 17 }, { left: 20 }], mult: 2, watching: 1, ...over,
  });
  socket.recv(stands("w"));
  expect(d.ddzLiveState.value).toEqual({ w: { landlord: 2, left: [3, 17, 20], mult: 2, watching: 1 } });
  // A game the room was not told of stays out.
  socket.recv(stands("gone"));
  expect(Object.keys(d.ddzLiveState.value)).toEqual(["w"]);
  socket.recv(stands("w", { mult: 4, watching: 0 }));
  expect(d.ddzLiveState.value.w).toMatchObject({ mult: 4, watching: 0 });
  socket.recv({ type: "ddz_live", table: "w", on: false });
  expect(d.ddzLiveState.value).toEqual({});
});

it("watches a game of the room apart from the save's own table, and follows the hand of the seat watched", async () => {
  const { socket, d, frame } = await watchSetup();
  expect(d.ddzCanWatch.value).toBe(true);
  expect([d.ddzWatchSeat("w"), d.ddzWatchSeat("w", "b"), d.ddzWatchSeat("w", "nobody")]).toEqual([0, 2, 0]);
  // The stake comes with the game where the server says it; an older server's does not.
  expect(d.ddzLiveBase.value).toEqual({ w: 50 });
  socket.recv({ type: "ddz_live", table: "old", ids: ["a", "x", "b"], on: true });
  expect(d.ddzLiveBase.value).toEqual({ w: 50 });
  socket.recv({ type: "ddz_live", table: "old", on: false });
  d.watchDdz("w");
  expect(watchSent(socket)).toEqual([{ type: "ddz_watch", table: "w", seat: 0 }]);
  socket.recv(snapshot(0, [0, 4, 8]));
  expect(d.ddzWatch.value).toMatchObject({ id: "w", you: 0, phase: "play", shown: true, switching: false, hand: [8, 4, 0], counter: null, played: null });
  expect(d.ddzWatch.value!.seats.map((s) => s.left)).toEqual([3, 17, 20]);
  expect(d.ddzScreen.value).toBe("watch");
  expect(frame.open).toBe(true);
  // The save stays free: nothing of its own is held.
  expect(d.ddz.value).toBeNull();
  expect([d.ddzBusy.value, d.ddzAtTable.value, d.ddzCanStart.value, d.ddzCanQueue.value, d.ddzCanOpen.value]).toEqual([false, false, true, true, true]);
  // A play of the seat watched leaves its hand; another seat's only its count.
  socket.recv({ type: "ddz_play", table: "w", seat: 0, cards: [0, 4], left: 1, mult: 2, bombs: 0, turn: 1, sec: 30, watch: true });
  socket.recv({ type: "ddz_play", table: "w", seat: 1, cards: [], left: 17, mult: 2, bombs: 0, turn: 2, sec: 30, watch: true });
  expect(d.ddzWatch.value).toMatchObject({ hand: [8], trick: [[0, 4], [], null], turn: 2 });
  expect(d.ddzWatch.value!.seats.map((s) => s.left)).toEqual([1, 17, 20]);
  expect(d.ddzWatch.value!.log.at(-1)).toMatchObject({ kind: "play", seat: 1 });
  // Another seat: its cards lie face down until the server sends them; plays meanwhile leave the hand alone.
  d.viewDdz(2);
  expect(d.ddzWatch.value).toMatchObject({ you: 2, hand: [], shown: false, switching: true });
  expect(watchSent(socket)).toHaveLength(1); // a second apart
  socket.recv({ type: "ddz_play", table: "w", seat: 2, cards: [5], left: 19, mult: 2, bombs: 0, turn: 0, sec: 30, watch: true });
  expect(d.ddzWatch.value).toMatchObject({ hand: [], trick: [[0, 4], [], [5]] });
  await vi.advanceTimersByTimeAsync(1100);
  expect(watchSent(socket).at(-1)).toEqual({ type: "ddz_watch", table: "w", seat: 2 });
  socket.recv(snapshot(2, [9, 53], { trick: [[0, 4], [], [5]], turn: 0, lead: false }));
  expect(d.ddzWatch.value).toMatchObject({ you: 2, hand: [53, 9], shown: true, switching: false });
  // Picked twice within the second: only the last is asked for, and the late answer for the first brings no hand.
  d.viewDdz(1);
  d.viewDdz(0);
  await vi.advanceTimersByTimeAsync(1100);
  expect(watchSent(socket).slice(2)).toEqual([{ type: "ddz_watch", table: "w", seat: 0 }]);
  socket.recv(snapshot(1, [2, 3]));
  expect(d.ddzWatch.value).toMatchObject({ you: 0, hand: [], switching: true });
  socket.recv(snapshot(0, [4]));
  expect(d.ddzWatch.value).toMatchObject({ you: 0, hand: [4], switching: false });
  // A message of another table is not this one's.
  socket.recv({ type: "ddz_play", table: "zz", seat: 0, cards: [4], left: 0, mult: 2, bombs: 0, watch: true });
  expect(d.ddzWatch.value!.hand).toEqual([4]);
});

it("keeps a hand the server does not show face down until the result, and adds the bottom cards to one it shows", async () => {
  const { socket, d } = await watchSetup();
  d.watchDdz("w", 1);
  socket.recv(snapshot(1, null, { phase: "bid", landlord: null, bottom: [], bid: 1, turn: 2 }));
  expect(d.ddzWatch.value).toMatchObject({ you: 1, phase: "bid", hand: [], shown: false });
  socket.recv({ type: "ddz_landlord", table: "w", seat: 1, bid: 3, bottom: [5, 9, 53], mult: 3, turn: 1, sec: 30, watch: true });
  expect(d.ddzWatch.value).toMatchObject({ phase: "play", landlord: 1, hand: [], bottom: [5, 9, 53] });
  expect(d.ddzWatch.value!.seats[1]!.left).toBe(20);
  socket.recv({
    type: "ddz_result", table: "w", winner: "farmers", landlord: 1, bid: 3, bombs: 0, spring: 0, mult: 3, base: 50,
    deltas: [150, -300, 150], hands: [[], [8, 12], [20]], sec: 30, watch: true,
  });
  expect(d.ddzWatch.value).toMatchObject({ phase: "result", hand: [12, 8], shown: true, result: { winner: "farmers" } });
  socket.recv({ type: "ddz_again", table: "w", seat: 0, watch: true });
  expect(d.ddzWatch.value!.seats[0]!.again).toBe(true);
  // Another game at the table: watched on from the same seat, its hand as the deal says.
  await vi.advanceTimersByTimeAsync(1100);
  d.watchDdz("w", 2);
  socket.recv(snapshot(2, [1, 2], { phase: "bid", landlord: null, bottom: [] }));
  socket.recv({ type: "ddz_deal", table: "w", seats: WSEATS, hand: HAND, base: 50, cap: 24, deal: 2, turn: 0, sec: 15, dealSec: 1.8, watch: true });
  expect(d.ddzWatch.value).toMatchObject({ you: 2, deal: 2, phase: "bid", shown: true, turn: 0 });
  expect(d.ddzWatch.value!.hand).toHaveLength(17);
  expect(d.ddzWatch.value!.dealUntil - Date.now()).toBe(1800);
  expect(d.ddzWatch.value!.log.at(-1)).toMatchObject({ kind: "deal" });
  // The landlord taking the bottom cards adds them to a hand that is shown.
  socket.recv({ type: "ddz_landlord", table: "w", seat: 2, bid: 1, bottom: [53, 52, 51], mult: 1, turn: 2, sec: 30, watch: true });
  expect(d.ddzWatch.value!.hand).toHaveLength(20);
});

it("ends watching when the save's own game is dealt, and keeps the save's open table as it is meanwhile", async () => {
  const { socket, d, frame } = await watchSetup();
  socket.recv({ type: "ddz_open", table: "o", base: 50, deposit: 2400, you: 1, seats: [{ ...A }, { ...ME }, null], sec: 600 });
  expect(d.ddz.value).toMatchObject({ phase: "open" });
  expect(d.ddzCanWatch.value).toBe(true); // waiting at an open table
  d.watchDdz("w");
  socket.recv(snapshot(0, [4]));
  // A deal of the table watched, and a watcher list of each table, leave the save's own table alone.
  socket.recv({ type: "ddz_deal", table: "w", seats: WSEATS, hand: null, base: 50, cap: 24, deal: 2, turn: 0, sec: 15, watch: true });
  expect(d.ddz.value).toMatchObject({ id: "o", phase: "open" });
  expect(d.ddzWatch.value).toMatchObject({ deal: 2, shown: false });
  socket.recv({ type: "ddz_watchers", table: "w", faces: [{ nick: "我", character: "嘉然", seat: null }] });
  expect(d.ddzWatchers.value).toEqual({ w: [{ nick: "我", character: "嘉然", seat: null }] });
  expect(d.ddzScreen.value).toBe("watch");
  // The open table fills and deals: its game takes the window, and the server hears that watching stopped.
  await vi.advanceTimersByTimeAsync(1100);
  socket.recv({ type: "ddz_deal", table: "o", seats: SEATS, you: 1, hand: HAND, base: 50, cap: 24, deal: 1, turn: 0, sec: 15 });
  expect(d.ddzWatch.value).toBeNull();
  expect(d.ddzScreen.value).toBe("own");
  expect(watchSent(socket).at(-1)).toEqual({ type: "ddz_watch", table: "" });
  expect(d.ddzCanWatch.value).toBe(false);
  await vi.advanceTimersByTimeAsync(0);
  expect(frame.open).toBe(true);
  expect(d.ddzWatchers.value).toEqual({}); // the table watched is gone
  socket.recv({ type: "ddz_watchers", table: "o", faces: [{ nick: "贝", character: "贝拉", seat: 1 }] });
  expect(d.ddzWatchers.value.o).toHaveLength(1);
  d.watchDdz("w"); // not while playing
  expect(watchSent(socket).at(-1)).toEqual({ type: "ddz_watch", table: "" });
});

it("ends watching as the server says: the result stays at a table that opens again, a game that falls through goes", async () => {
  const { socket, d, frame } = await watchSetup();
  const result = {
    type: "ddz_result", table: "w", winner: "landlord", landlord: 2, bid: 2, bombs: 0, spring: 0, mult: 2, base: 50,
    deltas: [-100, -100, 180], hands: [[1], [2, 3], []], sec: 30,
  };
  d.watchDdz("w");
  // Come in at the result: every hand is open.
  socket.recv(snapshot(0, null, { phase: "over", turn: null, result }));
  expect(d.ddzWatch.value).toMatchObject({ phase: "result", shown: true, hand: [1], result: { winner: "landlord" } });
  socket.recv({ type: "ddz_tables", tables: [{ table: "w", base: 50, seats: [{ ...A }, null, null] }] });
  socket.recv({ type: "ddz_watch_end", table: "w", reason: "reopen" });
  expect(d.ddzWatch.value).toMatchObject({ ended: "reopen", closed: true, phase: "result" });
  expect(d.ddzCanSit(50)).toBe(true);
  socket.recv({ type: "ddz_play", table: "w", seat: 0, cards: [1], left: 0, mult: 2, bombs: 0, watch: true });
  expect(d.ddzWatch.value!.phase).toBe("result"); // nothing more of it is heard
  d.sitDdz("w");
  expect(socket.sent.at(-1)).toEqual({ type: "ddz_sit", table: "w" });
  socket.recv({ type: "ddz_open", table: "w", base: 50, deposit: 2400, you: 1, seats: [{ ...A }, { ...ME }, null], sec: 600 });
  expect(d.ddzWatch.value).toBeNull();
  await vi.advanceTimersByTimeAsync(0);
  expect(frame.open).toBe(false);

  // A game that falls through: its ending shows for a moment, then the window goes.
  socket.recv({ type: "ddz_closed", table: "w" });
  expect(d.ddz.value).toBeNull();
  socket.recv({ type: "ddz_live", table: "w2", ids: ["a", "x", "b"], on: true });
  await vi.advanceTimersByTimeAsync(1100);
  d.watchDdz("w2");
  socket.recv({ ...snapshot(0, [4]), table: "w2" });
  expect(frame.open).toBe(true);
  socket.recv({ type: "ddz_watch_end", table: "w2", reason: "gone", over: "nobid" });
  expect(d.ddzWatch.value).toMatchObject({ ended: "gone", phase: "over", reason: "nobid" });
  expect(d.ddzReason(d.ddzWatch.value!)).toBe("三次都没人叫分，押金已退还");
  await vi.advanceTimersByTimeAsync(d.DDZ_END_MS);
  expect(d.ddzWatch.value).toBeNull();
  expect(frame.open).toBe(false);

  // The save's own game starting elsewhere: the game watched stays up until the own deal takes the window over, so
  // the window does not close in between; with no deal it goes after a while.
  await vi.advanceTimersByTimeAsync(1100);
  d.watchDdz("w2");
  socket.recv({ ...snapshot(0, [4]), table: "w2" });
  socket.recv({ type: "ddz_watch_end", table: "w2", reason: "playing" });
  expect(d.ddzWatch.value).toMatchObject({ ended: "playing" });
  expect(d.ddzScreen.value).toBe("watch");
  await vi.advanceTimersByTimeAsync(d.PLAYING_WAIT_MS - 1);
  expect(d.ddzWatch.value).not.toBeNull();
  await vi.advanceTimersByTimeAsync(1);
  expect(d.ddzWatch.value).toBeNull();
  await vi.advanceTimersByTimeAsync(0);
  expect(frame.open).toBe(false);
  await vi.advanceTimersByTimeAsync(1100);
  d.watchDdz("w2");
  socket.recv({ ...snapshot(0, [4]), table: "w2" });
  expect(frame.open).toBe(true);
  const sent = watchSent(socket).length;
  socket.recv({ type: "ddz_watch_end", table: "w2", reason: "playing" });
  socket.recv({ type: "ddz_deal", table: "o2", seats: SEATS, you: 1, hand: HAND, base: 50, cap: 24, deal: 1, turn: 0, sec: 15 });
  expect([d.ddzWatch.value, d.ddzScreen.value]).toEqual([null, "own"]);
  expect(watchSent(socket)).toHaveLength(sent); // the server ended it: no stop
  await vi.advanceTimersByTimeAsync(0);
  expect(frame.open).toBe(true);
});

it("stops when the window closes, and takes a refusal of the server as the end of the request", async () => {
  const { socket, d, r, frame } = await watchSetup();
  d.watchDdz("w");
  socket.recv({ type: "error", code: "ddz_watch_full", message: "" });
  expect(r.lastError.value).toBe("观众已满");
  expect(d.ddzWatch.value).toBeNull();
  socket.recv(snapshot(0, [4])); // late, after the refusal: not shown
  expect(d.ddzWatch.value).toBeNull();
  // Held back once: asked again after the gap.
  await vi.advanceTimersByTimeAsync(1100);
  d.watchDdz("w", 2);
  socket.recv({ type: "error", code: "rate_limited", message: "" });
  expect(watchSent(socket)).toHaveLength(2);
  await vi.advanceTimersByTimeAsync(1100);
  expect(watchSent(socket)).toHaveLength(3);
  socket.recv(snapshot(2, [9]));
  expect(d.ddzWatch.value).toMatchObject({ you: 2 });
  // The window closed by the watcher: watching stops.
  frame.open = false;
  d.noteDdzWindowClosed();
  expect(d.ddzWatch.value).toBeNull();
  // A stop goes at once, and the next request's time does not count it.
  expect(watchSent(socket).at(-1)).toEqual({ type: "ddz_watch", table: "" });
  await vi.advanceTimersByTimeAsync(1100);
  d.watchDdz("w");
  expect(watchSent(socket).at(-1)).toEqual({ type: "ddz_watch", table: "w", seat: 0 });
  d.unwatchDdz();
  expect(watchSent(socket).at(-1)).toEqual({ type: "ddz_watch", table: "" });
  // The room connection going ends watching too.
  await vi.advanceTimersByTimeAsync(1100);
  d.watchDdz("w");
  socket.recv(snapshot(0, [4]));
  socket.close();
  expect(d.ddzWatch.value).toBeNull();
});

it("shows no way in on a server without watching", async () => {
  const { socket, d } = await setup();
  socket.recv({ type: "ddz_live", table: "w", ids: ["a", "x", "b"], on: true });
  expect(d.ddzCanWatch.value).toBe(false);
  const sent = socket.sent.length;
  d.watchDdz("w");
  expect(socket.sent).toHaveLength(sent);
});

it("goes on watching through a refusal, back on the seat the server still shows, and turns a hand down it stops showing", async () => {
  const { socket, d } = await watchSetup();
  d.watchDdz("w", 2);
  socket.recv(snapshot(2, [9, 53]));
  // Between two games the server turns another seat down: the seat before comes back as it was.
  d.viewDdz(0);
  expect(d.ddzWatch.value).toMatchObject({ you: 0, shown: false });
  await vi.advanceTimersByTimeAsync(1100);
  socket.recv({ type: "error", code: "ddz_gone", message: "" });
  expect(d.ddzWatch.value).toMatchObject({ you: 2, hand: [53, 9], shown: true, switching: false, ended: "" });
  // Dealt again after nobody bid: the hand starts over from the new deal.
  socket.recv({ type: "ddz_deal", table: "w", seats: WSEATS, hand: [0, 4], base: 50, cap: 24, deal: 2, turn: 0, sec: 15, watch: true });
  expect(d.ddzWatch.value).toMatchObject({ you: 2, deal: 2, hand: [4, 0], shown: true });
  // The list of watchers says this one (`you`) sees no hand any more: its cards turn face down, as many as the seat holds.
  const me = { nick: "我", character: "嘉然" };
  socket.recv({ type: "ddz_watchers", table: "w", faces: [{ nick: "别人", character: "贝拉", seat: null }, { ...me, seat: 2 }], you: 1 });
  expect(d.ddzWatch.value!.shown).toBe(true);
  socket.recv({ type: "ddz_watchers", table: "w", faces: [{ nick: "别人", character: "贝拉", seat: 2 }, { ...me, seat: null }] });
  expect(d.ddzWatch.value!.shown).toBe(true); // a list without `you` says nothing of this one
  socket.recv({ type: "ddz_watchers", table: "w", faces: [{ nick: "别人", character: "贝拉", seat: 2 }, { ...me, seat: null }], you: 1 });
  expect(d.ddzWatch.value).toMatchObject({ you: 2, hand: [], shown: false });
  socket.recv({ type: "ddz_play", table: "w", seat: 2, cards: [4], left: 16, mult: 1, bombs: 0, watch: true });
  expect(d.ddzWatch.value!.hand).toEqual([]);
});

// ------------------------------------------------------------------ the hall
/** An open table of the hall on the dou dizhu connection, seen from seat [you] ("L" is the save there). */
const hallOpen = (table: string, you: number, seats: unknown[], more: Record<string, unknown> = {}) =>
  ({ type: "ddz_open", table, base: 50, deposit: 2400, you, seats, sec: 600, ...more });
const LME = { ...seatOf(ME), id: "L" };
/** The room, joined on a server with open tables. */
const joinedOpen = () => Socket.all[0]!.recv({ type: "joined", room: "r", you: "me", members: [ME, NEW_A, B], features: ["ddz_match"] });

it("sits down in the hall on the dou dizhu connection, a queue interval apart from joins, and sends a sit held back once more", async () => {
  const { d, r, player } = await setup();
  joinedOpen();
  player.ddzHallOn.value = true;
  const before = Socket.all.length;
  d.quickSitDdz(500); // cannot pay the deposit
  d.quickSitDdz(100); // not a stake
  expect(Socket.all).toHaveLength(before);
  d.quickSitDdz(50);
  // The connection comes up for it; the sit goes once it is ready.
  const lk = linkUp();
  const opens = () => sentOf(lk, "ddz_open");
  expect(opens()).toEqual([{ type: "ddz_open", base: 50 }]);
  lk.recv({ type: "error", code: "rate_limited", message: "" });
  expect(opens()).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1100);
  expect(opens()).toEqual([{ type: "ddz_open", base: 50 }, { type: "ddz_open", base: 50 }]);
  lk.recv({ type: "error", code: "rate_limited", message: "" });
  await vi.advanceTimersByTimeAsync(3000);
  expect(opens()).toHaveLength(2); // only once
  // The server seats the save at a table of the hall: the pet's sign and the banner show it as the queue's open seat.
  lk.recv(hallOpen("h1", 0, [LME, null, null]));
  expect(d.ddzQueueSeat.value).toMatchObject({ id: "h1", via: "link", you: 0, phase: "open" });
  expect(d.ddzCanCall(r.members.get("a")!)).toBe(false); // a table of the hall has no opener to call anyone
  d.quickSitDdz(50); // seated already
  d.sitDdzAt("h2");
  await vi.advanceTimersByTimeAsync(1100);
  expect([opens().length, sentOf(lk, "ddz_sit").length]).toEqual([2, 0]);
  d.leaveDdz("h1", "open");
  expect(lk.sent.at(-1)).toEqual({ type: "ddz_leave", table: "h1" });
  // At a table of the list, at a seat; one that filled up meanwhile is said nothing of, other refusals as always.
  d.sitDdzAt("h2", 2);
  expect(sentOf(lk, "ddz_sit")).toEqual([{ type: "ddz_sit", table: "h2", seat: 2 }]);
  lk.recv({ type: "error", code: "ddz_gone", message: "" });
  expect(r.lastError.value).toBe("");
  // A join and a sit keep the interval between them, and the later one replaces the one not sent yet.
  d.queueDdz(50);
  d.sitDdzAt("h3");
  expect([sentOf(lk, "ddz_queue").length, sentOf(lk, "ddz_sit").length]).toEqual([0, 1]);
  await vi.advanceTimersByTimeAsync(1100);
  expect(sentOf(lk, "ddz_sit").slice(1)).toEqual([{ type: "ddz_sit", table: "h3" }]);
  expect(sentOf(lk, "ddz_queue")).toEqual([]);
  lk.recv({ type: "error", code: "no_shards", message: "" });
  expect(r.lastError.value).toBe("碎片不足");
  // A hold on the queue does not keep the save from sitting down; turning invites down does.
  d.ddzRetry.value = true;
  await vi.advanceTimersByTimeAsync(1100);
  d.quickSitDdz(50);
  expect(opens()).toHaveLength(3);
  lk.recv({ type: "error", code: "ddz_busy", message: "" });
  r.lastError.value = "";
  (await import("./settings")).settings.duelDnd = true;
  await vi.advanceTimersByTimeAsync(1100);
  d.quickSitDdz(50);
  d.sitDdzAt("h4");
  await vi.advanceTimersByTimeAsync(1100);
  expect([opens().length, sentOf(lk, "ddz_sit").length]).toEqual([3, 2]);
});


it("sits down at the fullest table of the stake, once, when the table picked is gone", async () => {
  const { d, r, player } = await setup();
  joinedOpen();
  player.ddzHallOn.value = true;
  d.sitDdzAt("h1", 1, 50);
  const lk = linkUp();
  // The stake stays on this side.
  expect(sentOf(lk, "ddz_sit")).toEqual([{ type: "ddz_sit", table: "h1", seat: 1 }]);
  lk.recv({ type: "error", code: "ddz_gone", message: "" });
  expect(sentOf(lk, "ddz_open")).toEqual([]); // a queue interval after the sit
  await vi.advanceTimersByTimeAsync(1100);
  expect(sentOf(lk, "ddz_open")).toEqual([{ type: "ddz_open", base: 50 }]);
  // Gone again: no second try.
  lk.recv({ type: "error", code: "ddz_gone", message: "" });
  await vi.advanceTimersByTimeAsync(3000);
  expect([sentOf(lk, "ddz_open").length, sentOf(lk, "ddz_sit").length]).toEqual([1, 1]);
  // Without the stake (a key that did not give it), nothing follows, and nothing is said.
  d.sitDdzAt("h2");
  expect(sentOf(lk, "ddz_sit").slice(1)).toEqual([{ type: "ddz_sit", table: "h2" }]);
  lk.recv({ type: "error", code: "ddz_gone", message: "" });
  await vi.advanceTimersByTimeAsync(3000);
  expect([sentOf(lk, "ddz_open").length, r.lastError.value]).toEqual([1, ""]);
});

it("takes a seat at a table of the hall that waited again after the connection dropped, at its stake", async () => {
  const { d, player } = await setup();
  joinedOpen();
  player.ddzHallOn.value = true;
  d.quickSitDdz(50);
  let lk = linkUp();
  lk.recv(hallOpen("h1", 0, [LME, X, null]));
  // Dropped and back: the server stood the seat up, and the save sits down again without a word.
  const drop = async () => {
    lk.close();
    await vi.advanceTimersByTimeAsync(1000);
    lk = linkUp();
    await vi.advanceTimersByTimeAsync(1100);
  };
  await drop();
  expect(sentOf(lk, "ddz_open")).toEqual([{ type: "ddz_open", base: 50 }]);
  expect([d.ddz.value, d.ddzBubble.value]).toEqual([null, null]);
  lk.recv(hallOpen("h2", 1, [X, LME, null]));
  expect(d.ddzQueueSeat.value).toMatchObject({ id: "h2" });
  // Not once the deposits are taken: the seat went with the connection, as always.
  lk.recv(hallOpen("h2", 1, [X, LME, Y], { starting: true }));
  await drop();
  expect(sentOf(lk, "ddz_open")).toEqual([]);
  expect([d.ddzBubble.value, d.ddzReason(d.ddz.value!)]).toEqual(["over", "掉线了"]);
  await vi.advanceTimersByTimeAsync(d.DDZ_END_MS);
  // Nor on a server without the hall.
  lk.recv(hallOpen("h3", 1, [X, LME, null]));
  player.ddzHallOn.value = false;
  await drop();
  expect(sentOf(lk, "ddz_open")).toEqual([]);
  expect([d.ddzBubble.value, d.ddzReason(d.ddz.value!)]).toEqual(["over", "掉线了"]);
  await vi.advanceTimersByTimeAsync(d.DDZ_END_MS);
  // Nor by a save shown away when the connection comes back.
  player.ddzHallOn.value = true;
  const { settings } = await import("./settings");
  settings.status = "away";
  await vi.advanceTimersByTimeAsync(0);
  lk.recv(hallOpen("h4", 1, [X, LME, null]));
  await vi.advanceTimersByTimeAsync(0);
  expect(d.ddz.value).toMatchObject({ id: "h4", phase: "open" }); // chosen away before sitting: kept
  await drop();
  expect(sentOf(lk, "ddz_open")).toEqual([]);
  expect([d.ddzBubble.value, d.ddzReason(d.ddz.value!)]).toEqual(["over", "掉线了"]);
  settings.status = "";
});

it("stands up from the seat a sit sent before turning away gets, and drops a sit not sent yet", async () => {
  const { d, player, settings } = await setup();
  joinedOpen();
  player.ddzHallOn.value = true;
  d.quickSitDdz(50);
  const lk = linkUp();
  expect(sentOf(lk, "ddz_open")).toEqual([{ type: "ddz_open", base: 50 }]);
  // Away before the seat is known: the seat the answer gives is stood up from at once.
  settings.status = "away";
  await vi.advanceTimersByTimeAsync(0);
  lk.recv(hallOpen("h1", 0, [LME, null, null]));
  await vi.advanceTimersByTimeAsync(0);
  expect(sentOf(lk, "ddz_leave")).toEqual([{ type: "ddz_leave", table: "h1" }]);
  expect(d.ddz.value).toBeNull();
  // Sitting down while shown away holds, as before.
  await vi.advanceTimersByTimeAsync(1100);
  d.quickSitDdz(50);
  expect(sentOf(lk, "ddz_open")).toHaveLength(2);
  lk.recv(hallOpen("h2", 0, [LME, null, null]));
  await vi.advanceTimersByTimeAsync(0);
  expect(d.ddz.value).toMatchObject({ id: "h2", phase: "open" });
  expect(sentOf(lk, "ddz_leave")).toHaveLength(1);
  d.leaveDdz("h2", "open");
  settings.status = "";
  await vi.advanceTimersByTimeAsync(0);
  // A sit still waiting for its time when the save turns away is not sent.
  d.quickSitDdz(50);
  settings.status = "away";
  await vi.advanceTimersByTimeAsync(3000);
  expect(sentOf(lk, "ddz_open")).toHaveLength(2);
  // Back before the answer: the seat is kept.
  settings.status = "";
  await vi.advanceTimersByTimeAsync(0);
  d.quickSitDdz(50);
  await vi.advanceTimersByTimeAsync(1100);
  expect(sentOf(lk, "ddz_open")).toHaveLength(3);
  settings.status = "away";
  await vi.advanceTimersByTimeAsync(0);
  settings.status = "";
  await vi.advanceTimersByTimeAsync(0);
  lk.recv(hallOpen("h3", 0, [LME, null, null]));
  await vi.advanceTimersByTimeAsync(0);
  expect(d.ddz.value).toMatchObject({ id: "h3", phase: "open" });
  expect(sentOf(lk, "ddz_leave")).toHaveLength(2);
}, 10_000);

it("waits in the queue instead of sitting down on a server without the hall", async () => {
  const { d, fetchMock, player } = await setup();
  expect(player.ddzHallOn.value).toBe(false);
  d.sitDdzAt("h1");
  expect(Socket.all).toHaveLength(1); // no connection for it
  d.quickSitDdz(50);
  const lk = linkUp();
  expect([sentOf(lk, "ddz_queue"), sentOf(lk, "ddz_open")]).toEqual([[{ type: "ddz_queue", base: 50 }], []]);
  // The lobby says whether the server has the hall: its stakes list the tables waiting there.
  const tier = { base: 50, deposit: 2400, afford: true, waiting: 0 };
  const answer = (tiers: unknown[]) => fetchMock.mockImplementation((async (url: string) => (String(url).endsWith("/api/ddz/lobby")
    ? { ok: true, status: 200, json: async () => ({ tiers, seated: false }) }
    : { ok: true, status: 200, json: async () => playerStatus() })) as never);
  answer([{ ...tier, tables: [] }]);
  await player.loadDdzLobby();
  expect(player.ddzHallOn.value).toBe(true);
  answer([tier]);
  await player.loadDdzLobby();
  expect(player.ddzHallOn.value).toBe(false);
});

it("stands up from an open table that waits when the save turns away, on the connection the table is on", async () => {
  const { socket, d, player, settings } = await setup();
  joinedOpen();
  const away = await import("./away");
  // A table of the room: left on the room connection once the status chosen turns away.
  socket.recv({ type: "ddz_open", table: "o1", base: 50, deposit: 2400, you: 0, seats: [seatOf(ME), null, null], sec: 600 });
  await vi.advanceTimersByTimeAsync(0);
  expect(sentOf(socket, "ddz_leave")).toEqual([]);
  settings.status = "away";
  await vi.advanceTimersByTimeAsync(0);
  expect(sentOf(socket, "ddz_leave")).toEqual([{ type: "ddz_leave", table: "o1" }]);
  expect(d.ddz.value).toBeNull();
  // Shown away already: a table sat down at, of the room or of the hall, is kept.
  socket.recv({ type: "ddz_open", table: "o2", base: 50, deposit: 2400, you: 0, seats: [seatOf(ME), null, null], sec: 600 });
  await vi.advanceTimersByTimeAsync(0);
  expect(d.ddz.value).toMatchObject({ id: "o2", phase: "open" });
  d.leaveDdz("o2", "open");
  player.ddzHallOn.value = true;
  d.quickSitDdz(50);
  const lk = linkUp();
  lk.recv(hallOpen("h1", 0, [LME, null, null]));
  await vi.advanceTimersByTimeAsync(0);
  expect([sentOf(lk, "ddz_leave"), sentOf(socket, "ddz_leave").length]).toEqual([[], 2]);
  expect(d.ddz.value).toMatchObject({ id: "h1", phase: "open" });
  // While the deposits are taken the seat stays.
  settings.status = "";
  await vi.advanceTimersByTimeAsync(0);
  lk.recv(hallOpen("h1", 0, [LME, X, Y], { starting: true }));
  settings.status = "away";
  await vi.advanceTimersByTimeAsync(0);
  expect(sentOf(lk, "ddz_leave")).toEqual([]);
  // Back to waiting, then ten minutes without input: left on the dou dizhu connection.
  settings.status = "";
  lk.recv(hallOpen("h1", 0, [LME, X, null]));
  const stop = away.startAway();
  await vi.advanceTimersByTimeAsync(5 * 60_000);
  expect(sentOf(lk, "ddz_leave")).toEqual([]);
  await vi.advanceTimersByTimeAsync(5 * 60_000 + 15_000);
  expect(away.shownStatus.value).toBe("away");
  expect(sentOf(lk, "ddz_leave")).toEqual([{ type: "ddz_leave", table: "h1" }]);
  expect(sentOf(socket, "ddz_leave")).toHaveLength(2);
  expect(d.ddz.value).toBeNull();
  stop();
});

it("says aloud a game starting at an open table the save waited at, while its window is out of sight", async () => {
  const { socket, d, frame, settings } = await setup();
  joinedOpen();
  const deal = (table: string, n = 1) => socket.recv({ type: "ddz_deal", table, seats: SEATS, you: 1, hand: HAND, base: 50, cap: 24, deal: n, turn: 0, sec: 15, dealSec: 0 });
  const open = (table: string, seats: unknown[], starting = false) =>
    socket.recv({ type: "ddz_open", table, base: 50, deposit: 2400, you: 1, seats, sec: 600, ...(starting ? { starting } : {}) });
  open("o1", [seatOf(NEW_A), seatOf(ME), null]);
  open("o1", [seatOf(NEW_A), seatOf(ME), seatOf(B)], true);
  deal("o1");
  expect(tableCue).toHaveBeenCalledTimes(1);
  expect(frame.open).toBe(true); // the window came up with the deal
  // A deal again after no bids is not said.
  frame.open = false;
  deal("o1", 2);
  expect(tableCue).toHaveBeenCalledTimes(1);
  // The seat that filled the table, and a table of an invite, start without it.
  socket.recv({ type: "ddz_closed", table: "o1" });
  open("o2", [seatOf(NEW_A), seatOf(ME), seatOf(B)], true);
  deal("o2");
  socket.recv({ type: "ddz_closed", table: "o2" });
  socket.recv({ type: "ddz_invite", table: "t1", from: "a", ids: ["a", "me", "b"], base: 50, deposit: 2400, sec: 15 });
  d.answerDdz(true);
  frame.open = false;
  deal("t1");
  socket.recv({ type: "ddz_closed", table: "t1" });
  expect(tableCue).toHaveBeenCalledTimes(1);
  // Nor with the table's window in sight, the interface sounds off, or the volume all the way down.
  for (const set of [() => { frame.open = true; }, () => { settings.sfx = false; }, () => { settings.volume = 0; }]) {
    frame.open = false;
    settings.sfx = true;
    settings.volume = 1;
    open("o3", [seatOf(NEW_A), seatOf(ME), null]);
    set();
    deal("o3");
    socket.recv({ type: "ddz_closed", table: "o3" });
  }
  expect(tableCue).toHaveBeenCalledTimes(1);
});
