// Dou dizhu (斗地主) at a table of the room: the invite, the game as this seat sees it, and how it ended; the
// server's queue, where a save waits at one stake for two others from any room; and open tables, opened in the room
// for its members to sit down at. The desk window hears the server and
// keeps the state; the panel and the table's own window mirror it (desktop/bridge.ts), the panel for the invite and
// the queue, the table's window (DdzApp.vue) for the game. The server decides everything (server/app/ddz.py); the
// rules here (src/ddz/rules.ts) only light the keys.
import { computed, ref, watch } from "vue";
import { isBomb, playable, sortHand } from "../ddz/rules";
import type { DdzMessage, DdzOpenSeat, DdzOpenTable, Member } from "../net/protocol";
import { isMirrorWindow, isTauri } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import { windowVisible } from "./activity";
import { economy } from "./economy";
import { reloadStatus, status } from "./player";
import { settings } from "./settings";
import {
  ddzHooks, ddzMatchOn, duelBusy, duelDnd, inRoom, me, members, sendDdz, showRoomError, showWin, shownNick, youId,
} from "./room";
import { closeDdzWindow, ddzFrame, openDdzWindow, ui } from "./ui";

export interface DdzSeat {
  /** Member id, kept while the member is away. */
  id: string;
  nick: string;
  character: string;
  /** Cards in hand. */
  left: number;
  /** This deal's bid: 0 passed, null not yet. */
  bid: number | null;
  /** Played for by the server. */
  auto: boolean;
  /** Out of the room, or left the table. */
  away: boolean;
  /** Asked for another game. */
  again: boolean;
  /** At an open table: offered to a save of the queue, not taken yet (`id` is ""; an empty seat is "" without it). */
  pending?: boolean;
}

/** What just happened at the table, for the panel to animate; `seq` only grows. */
type DdzEventBody =
  | { kind: "deal" }
  | { kind: "bid"; seat: number; bid: number }
  | { kind: "landlord"; seat: number }
  | { kind: "play"; seat: number; cards: number[]; bomb: boolean }
  | { kind: "result" }
  /** The whole state arrived at once (a seat taken again): nothing to animate. */
  | { kind: "sync" };
export type DdzEvent = DdzEventBody & { seq: number };

export interface DdzResult {
  winner: "landlord" | "farmers";
  landlord: number;
  bid: number;
  bombs: number;
  /** 0 none, 1 spring, 2 counter-spring. */
  spring: number;
  mult: number;
  base: number;
  /** Shards won or lost by seat. */
  deltas: number[];
  /** Cards left in each seat. */
  hands: number[][];
}

export interface DdzState {
  id: string;
  /** "open": seated at an open table that waits for its seats; `until` is when it is put away. */
  phase: "open" | "invite" | "bid" | "play" | "result" | "over";
  /** The queue made the table: nobody invited, all three answer, the others may be in other rooms. */
  match: boolean;
  /** An open table with its three seats taken, while the deposits are taken. */
  starting: boolean;
  /** The own seat. */
  you: number;
  seats: DdzSeat[];
  /** The invite: this client sent it, this client answered it, and the member ids that accepted. */
  sent: boolean;
  answered: boolean;
  accepted: string[];
  base: number;
  deposit: number;
  /** The most the multiplier reaches. */
  cap: number;
  deal: number;
  /** The own cards, as held (src/ddz/rules.ts sortHand). */
  hand: number[];
  /** The highest bid so far. */
  bid: number;
  landlord: number | null;
  /** The three cards the landlord took; empty until there is one. */
  bottom: number[];
  mult: number;
  bombs: number;
  /** This deal's bombs in the order they were played (a seat taken again knows only how many, as bombs). */
  boosts: ("bomb" | "rocket")[];
  /** The cards are dealt out until then (local ms); the bids wait for it. */
  dealUntil: number;
  /** The seat to move, null between moves. */
  turn: number | null;
  /** The seat to move leads: nothing to beat. */
  lead: boolean;
  /** Each seat's last move on the table: cards, [] for a pass, null for none. A lead clears the others. */
  trick: (number[] | null)[];
  /** The current countdown: its length and its end in local ms. */
  sec: number;
  until: number;
  /** A move was sent and the server has not answered yet. */
  acted: boolean;
  result: DdzResult | null;
  /** After the result: the table is gone, so there is no other game to ask for. */
  closed: boolean;
  /** Why it ended with nothing won (ddz_over), and the member who caused it. */
  reason: string;
  by: string;
  log: DdzEvent[];
}

/** How long the ending of an invite stays up. */
export const DDZ_END_MS = 4000;
const LOG_MAX = 12;

/** Dou dizhu numbers from the server's economy; null without the game. */
export const ddzConfig = computed(() => economy.value?.doudizhu ?? null);
export const ddz = ref<DdzState | null>(null);
/** Games under way in the room: the three member ids by table. */
export const ddzLive = ref<Record<string, string[]>>({});
/** This connection waits in the server's queue: at which stake, and since when (local ms); null when it does not. */
export const ddzQueue = ref<{ base: number; since: number } | null>(null);
/** How many saves wait at each stake, this one included, as the server last counted. */
export const ddzWaiting = ref<Record<number, number>>({});
/** The save declined a table of the queue, left it or let it lapse: the server keeps it out of the queue for a while. */
export const ddzRetry = ref(false);
/** The open tables of the room, oldest first, as the server last listed them. */
export const ddzTables = ref<DdzOpenTable[]>([]);
/** The opener of an open table called this save to it: shown over the own pet until `until` (local ms). */
export interface DdzCall { table: string; from: string; base: number; deposit: number; seats: DdzOpenSeat[]; until: number }
export const ddzCall = ref<DdzCall | null>(null);
/** How long an open table that opens again after a game shows over the own pet. */
export const REOPEN_CUE_MS = 8000;
/** The open table this save sits at opened again after a game: shown over the own pet until `until` (local ms). */
export const ddzReopened = ref<{ table: string; until: number } | null>(null);

/** The server has the game (its status says so) and this client is in a room. */
export const ddzOn = computed(() => inRoom.value && !!ddzConfig.value && !!status.value?.ddz);
/** Member ids playing in the room right now. */
export const ddzPlaying = computed(() => new Set(Object.values(ddzLive.value).flat()));
/** The table is up: a game or its result. */
export const ddzAtTable = computed(() => !!ddz.value && (ddz.value.phase === "bid" || ddz.value.phase === "play" || ddz.value.phase === "result"));
/** An invite or a game holds this save. */
export const ddzBusy = computed(() => !!ddz.value && ddz.value.phase !== "over" && !(ddz.value.phase === "result" && ddz.value.closed));

/** What each seat pays when a game at [base] starts: the most a landlord can lose. */
export const ddzDeposit = (base: number): number => base * (ddzConfig.value?.capMult ?? 0) * 2;

/** A base stake this save can pay the deposit of, while today's net win is under the cap. */
export function ddzStakeOpen(base: number): boolean {
  const cfg = ddzConfig.value;
  const s = status.value;
  return !!cfg && !!s?.ddz && cfg.stakes.includes(base) && s.shards >= ddzDeposit(base) && s.ddz.net < cfg.dailyWinCap;
}

/** Whether this save looks able to start a game; the server checks again, the other saves included. */
export const ddzCanStart = computed(() => {
  const cfg = ddzConfig.value;
  const s = status.value;
  return ddzOn.value && !!cfg && !!s && !!me.value?.uid && !ddzBusy.value && !duelBusy.value &&
    s.totals.taps >= cfg.minTaps && cfg.stakes.some(ddzStakeOpen);
});

/** The server has the queue, and this client is in a room of a server with the game. */
export const ddzMatchable = computed(() => ddzOn.value && ddzMatchOn.value);

/** Whether this save looks able to wait for a table: as for starting a game, and not turning invites down. */
export const ddzCanQueue = computed(() => ddzMatchable.value && ddzCanStart.value && !duelDnd() && !ddzRetry.value);

/** Whether this save looks able to open a table, or sit down at one at [base]: as for waiting in the queue. */
export const ddzCanOpen = computed(() => ddzMatchable.value && ddzCanStart.value && !duelDnd());
export const ddzCanSit = (base: number): boolean => ddzCanOpen.value && ddzStakeOpen(base);

/** Whether the opener can call member [m] to its table: another save in the room, on a client with open tables, free. */
export function ddzCanCall(m: Member): boolean {
  const t = ddz.value;
  const mine = me.value;
  return !!t && t.phase === "open" && t.you === 0 && !t.starting && t.seats.some((s) => !s.id && !s.pending) &&
    !!mine && m.id !== mine.id && !!m.ddzMatch && !!m.uid && m.uid !== mine.uid && !ddzPlaying.value.has(m.id) &&
    !t.seats.some((s) => s.id === m.id) && !ddzTables.value.some((x) => x.seats.some((s) => !!s && "id" in s && s.id === m.id));
}

/** Saves other than this one waiting at [base]. */
export function ddzOthersWaiting(base: number): number {
  return Math.max(0, (ddzWaiting.value[base] ?? 0) - (ddzQueue.value?.base === base ? 1 : 0));
}

/** Whether member [m] can be asked to a game: another save, on a client that plays, not at a table already. */
export function ddzCanInvite(m: Member): boolean {
  const mine = me.value;
  return !!mine && m.id !== mine.id && !!m.ddz && !!m.uid && m.uid !== mine.uid && !ddzPlaying.value.has(m.id);
}

/** The cards the seat to move has to beat and who played them; null when it leads. */
export function ddzLast(t: DdzState): { seat: number; cards: number[] } | null {
  if (t.phase !== "play" || t.turn === null || t.lead) return null;
  for (let back = 1; back <= 2; back++) {
    const seat = (t.turn + 3 - back) % 3;
    const cards = t.trick[seat];
    if (cards?.length) return { seat, cards };
  }
  return null;
}

const REASONS: Record<string, string> = {
  timeout: "没有等到回应", gone: "有人离开了", disband: "已散桌", expired: "已散桌", nobid: "三次都没人叫分，押金已退还", no_shards: "有人的碎片不够押金",
  ddz_cap: "有人今天赢到上限了", ddz_locked: "有人还不能斗地主", ddz_account: "有人还没有登录 Asasfans 账号",
  error: "没能开局",
};
/** Why a table ended with nothing won, in words. */
export const ddzReason = (t: DdzState): string =>
  (t.reason === "declined" ? `${t.by || "有人"}没有接受` : REASONS[t.reason] ?? "已取消");

/** The table is on screen: its window is open and not minimized (the desk is told by that window), or the browser preview's frame is up. */
export const ddzTableSeen = computed(() => (isTauri ? ui.ddzSeen : ddzFrame.open));

/**
 * What the bubble over the own pet shows: an invite, how one ended, that a game goes on while the table is out of
 * sight ("turn" when it waits for this seat), a call to an open table, or for a moment the open table this save sits
 * at once it opened again after a game; null for nothing.
 */
export const ddzBubble = computed<"invite" | "over" | "turn" | "table" | "call" | "open" | null>(() => {
  const t = ddz.value;
  if (!t) return ddzCall.value ? "call" : null;
  if (t.phase === "open") return !t.starting && ddzReopened.value?.table === t.id ? "open" : null;
  if (t.phase === "invite" || t.phase === "over") return t.phase;
  if ((t.phase === "bid" || t.phase === "play") && !ddzTableSeen.value) return t.turn === t.you && !t.seats[t.you]?.auto ? "turn" : "table";
  return null;
});

// ------------------------------------------------------------------ messages (desk window)
let endTimer: ReturnType<typeof setTimeout> | undefined;
let retryTimer: ReturnType<typeof setTimeout> | undefined;
let callTimer: ReturnType<typeof setTimeout> | undefined;
let reopenTimer: ReturnType<typeof setTimeout> | undefined;
let seq = 0;

/** The server takes a join of the queue, or a move in it, once a second at most (QUEUE_INTERVAL); joins go this far apart. */
const QUEUE_GAP_MS = 1100;
let queueSentAt = -Infinity;
/** The stake of a join waiting for its time to be sent, and its timer. */
let queueNext: number | null = null;
let queueTimer: ReturnType<typeof setTimeout> | undefined;
/** The stake of a join sent and not answered yet; whether it was sent once more after the server held it back. */
let queueAsked: number | null = null;
let queueRetried = false;

function dropQueueJoin(): void {
  clearTimeout(queueTimer);
  queueTimer = undefined;
  queueNext = null;
  queueAsked = null;
}

/** Sends the join waiting for its time once the gap since the last one has passed, if the save can still wait there. */
function sendQueueJoin(): void {
  clearTimeout(queueTimer);
  queueTimer = undefined;
  const base = queueNext;
  if (base === null) return;
  const wait = queueSentAt + QUEUE_GAP_MS - Date.now();
  if (wait > 0) {
    queueTimer = setTimeout(sendQueueJoin, wait);
    return;
  }
  queueNext = null;
  if (!ddzCanQueue.value || !ddzStakeOpen(base) || ddzQueue.value?.base === base) return;
  queueSentAt = Date.now();
  queueAsked = base;
  sendDdz({ type: "ddz_queue", base });
}

/** `rate_limited` from the server: when a join waits for its answer it may be the one held back, sent once more. */
function queueHeldBack(): void {
  if (queueAsked === null || queueRetried) return;
  queueRetried = true;
  queueNext = queueAsked;
  queueAsked = null;
  queueSentAt = Date.now();
  sendQueueJoin();
}

/** The deal at the table as "table:deal"; "" while the table is not up. */
const dealKey = computed(() => (ddzAtTable.value && ddz.value ? `${ddz.value.id}:${ddz.value.deal}` : ""));
/** The deal the table's window was opened for, and the one it was closed during. */
let opened = "";
let dismissed = "";

/** Desk window: the table's window was closed (by the player, or because the table was put away). */
export function noteDdzWindowClosed(): void {
  ui.ddzSeen = false;
  if (dealKey.value) dismissed = dealKey.value;
}

const countdown = (sec: number) => ({ sec, until: Date.now() + sec * 1000 });

function blank(id: string): DdzState {
  return {
    id, phase: "invite", match: false, starting: false, you: 0, seats: [], sent: false, answered: false, accepted: [], base: 0, deposit: 0, cap: 0, deal: 0,
    hand: [], bid: 0, landlord: null, bottom: [], mult: 1, bombs: 0, boosts: [], dealUntil: 0, turn: null, lead: false,
    trick: [null, null, null],
    sec: 0, until: 0, acted: false, result: null, closed: false, reason: "", by: "", log: [],
  };
}

const seatOf = (s: { id: string; nick: string; character: string } | null | undefined, pending = false): DdzSeat => ({
  id: s?.id ?? "", nick: s?.nick ?? "", character: s?.character ?? "", left: 0, bid: null, auto: false, away: false,
  again: false, ...(pending ? { pending } : {}),
});
const openSeat = (s: DdzOpenSeat): DdzSeat => (s && "id" in s ? seatOf(s) : seatOf(null, !!s));

function note(t: DdzState, event: DdzEventBody): void {
  t.log.push({ ...event, seq: ++seq });
  if (t.log.length > LOG_MAX) t.log.splice(0, t.log.length - LOG_MAX);
}

function close(): void {
  clearTimeout(endTimer);
  ddz.value = null;
}

/** Leaves the ending up for a moment, then clears it (unless another table took its place). */
function closeLater(): void {
  clearTimeout(endTimer);
  const shown = ddz.value;
  endTimer = setTimeout(() => { if (ddz.value?.id === shown?.id) ddz.value = null; }, DDZ_END_MS);
}

function setTurn(t: DdzState, turn: number | undefined, sec: number | undefined): void {
  t.acted = false;
  if (turn === undefined) { t.turn = null; return; }
  t.turn = turn;
  Object.assign(t, countdown(sec ?? 0));
}

export function onDdzMessage(msg: DdzMessage): void {
  const you = youId.value;
  if (msg.type === "ddz_live") {
    const live = { ...ddzLive.value };
    if (msg.on) live[msg.table] = [...msg.ids];
    else delete live[msg.table];
    ddzLive.value = live;
    // The whole room sees the winners' shards go up over their pets.
    if (!msg.on) for (const [id, gain] of Object.entries(msg.gains ?? {})) showWin(id, gain);
    return;
  }
  if (msg.type === "ddz_queue") {
    queueAsked = null;
    ddzQueue.value = msg.base ? { base: msg.base, since: Date.now() - (msg.waited ?? 0) * 1000 } : null;
    // Back in the line after a table of the queue fell through: the wait takes the ending's place at once.
    if (msg.base && ddz.value?.match && ddz.value.phase === "over") close();
    if (msg.reason === "ddz_match_cooldown") {
      // Said on the banner while it lasts.
      ddzRetry.value = true;
      clearTimeout(retryTimer);
      retryTimer = setTimeout(() => { ddzRetry.value = false; }, (msg.retry ?? 0) * 1000);
    } else if (msg.reason && msg.reason !== "error") {
      showRoomError(msg.reason);
    }
    return;
  }
  if (msg.type === "ddz_waiting") {
    ddzWaiting.value = Object.fromEntries(msg.counts);
    return;
  }
  if (msg.type === "ddz_tables") {
    ddzTables.value = msg.tables;
    return;
  }
  if (msg.type === "ddz_call") {
    clearTimeout(callTimer);
    ddzCall.value = { table: msg.table, from: msg.from, base: msg.base, deposit: msg.deposit, seats: msg.seats, until: Date.now() + msg.sec * 1000 };
    callTimer = setTimeout(() => { if (ddzCall.value?.table === msg.table) ddzCall.value = null; }, msg.sec * 1000);
    return;
  }
  if (msg.type === "ddz_open") {
    // Seated at an open table (after a game too, when it opens again): the call to it is answered.
    clearTimeout(endTimer);
    const before = ddz.value?.id === msg.table ? ddz.value : null;
    ddz.value = {
      ...blank(msg.table), log: before?.log ?? [], phase: "open", you: msg.you, base: msg.base, deposit: msg.deposit,
      starting: !!msg.starting, seats: msg.seats.map(openSeat), ...countdown(msg.sec),
    };
    if (ddzCall.value) ddzCall.value = null;
    // Back from a game: the table window goes, and the pet says for a moment that the table waits again.
    if (before && (before.phase === "result" || before.phase === "bid" || before.phase === "play")) {
      const table = msg.table;
      ddzReopened.value = { table, until: Date.now() + REOPEN_CUE_MS };
      clearTimeout(reopenTimer);
      reopenTimer = setTimeout(() => { if (ddzReopened.value?.table === table) ddzReopened.value = null; }, REOPEN_CUE_MS);
    }
    return;
  }
  if (msg.type === "ddz_invite") {
    const at = msg.ids.indexOf(you);
    if (at < 0) return;
    clearTimeout(endTimer);
    ddz.value = {
      ...blank(msg.table), you: at, match: !!msg.match, sent: !!msg.from && msg.from === you,
      accepted: msg.accepted ?? (msg.from ? [msg.from] : []), base: msg.base, deposit: msg.deposit,
      // A table of the queue names its members, who may be in other rooms; an invite's are in this one. An open
      // table's empty seat has no id.
      seats: msg.ids.map((id) => (id ? seatOf(msg.seats?.find((s) => s?.id === id) ?? members.get(id) ?? { id, nick: "", character: "" }) : seatOf(null))),
      ...countdown(msg.sec),
    };
    if (ddzCall.value) ddzCall.value = null;
    return;
  }
  if (msg.type === "ddz_deal" || msg.type === "ddz_state") {
    // A deal of a table this client holds no invite of: the seat was taken again after the client restarted.
    clearTimeout(endTimer);
    const before = ddz.value?.id === msg.table ? ddz.value : null;
    const t: DdzState = {
      ...blank(msg.table), log: before?.log ?? [], deposit: before?.deposit ?? ddzDeposit(msg.base),
      phase: msg.type === "ddz_state" ? msg.phase : "bid", you: msg.you, base: msg.base, cap: msg.cap, deal: msg.deal,
      hand: sortHand(msg.hand),
      seats: msg.seats.map((s) => ({
        id: s.id, nick: s.nick, character: s.character, auto: s.auto, away: s.away, again: false,
        left: "left" in s ? s.left : 17, bid: "bid" in s ? s.bid : null,
      })),
    };
    if (msg.type === "ddz_state") {
      Object.assign(t, {
        bid: msg.bid, landlord: msg.landlord, bottom: msg.bottom, mult: msg.mult, bombs: msg.bombs, turn: msg.turn,
        lead: msg.lead, trick: msg.trick, sec: msg.of, until: Date.now() + msg.sec * 1000,
        boosts: Array<"bomb">(msg.bombs).fill("bomb"),
      });
      note(t, { kind: "sync" });
    } else {
      // The first bid's time starts once the cards are dealt out.
      const wait = (msg.dealSec ?? 0) * 1000;
      setTurn(t, msg.turn, msg.sec);
      t.dealUntil = Date.now() + wait;
      t.until += wait;
      note(t, { kind: "deal" });
    }
    ddz.value = t;
    // The deposit is paid with a table's first deal. The table's window opens with each deal (watch below).
    if (msg.type === "ddz_state" || msg.deal === 1) void reloadStatus();
    return;
  }
  const t = ddz.value;
  if (t?.id !== msg.table) {
    // A game this client walked away from was played to its end: the shards changed.
    if (msg.type === "ddz_result" || msg.type === "ddz_over") void reloadStatus();
    return;
  }
  switch (msg.type) {
    case "ddz_answer":
      if (!t.accepted.includes(msg.id)) t.accepted.push(msg.id);
      return;
    case "ddz_over": {
      const by = msg.by ? t.seats.find((s) => s.id === msg.by) : undefined;
      Object.assign(t, { phase: "over", reason: msg.reason, by: by ? shownNick(by) : "", turn: null });
      closeLater();
      void reloadStatus(); // deposits taken went back
      return;
    }
    case "ddz_bid":
      t.seats[msg.seat]!.bid = msg.bid;
      t.bid = Math.max(t.bid, msg.bid);
      setTurn(t, msg.turn, msg.sec);
      note(t, { kind: "bid", seat: msg.seat, bid: msg.bid });
      return;
    case "ddz_landlord":
      Object.assign(t, { phase: "play", landlord: msg.seat, bid: msg.bid, bottom: msg.bottom, mult: msg.mult, lead: true, trick: [null, null, null] });
      t.seats[msg.seat]!.left = 20;
      if (msg.seat === t.you) t.hand = sortHand([...t.hand, ...msg.bottom]);
      setTurn(t, msg.turn, msg.sec);
      note(t, { kind: "landlord", seat: msg.seat });
      return;
    case "ddz_play":
      // The seat that leads sweeps the table: the last trick stayed up until now.
      if (t.lead) t.trick = [null, null, null];
      t.trick[msg.seat] = msg.cards;
      t.seats[msg.seat]!.left = msg.left;
      if (msg.seat === t.you && msg.cards.length) t.hand = t.hand.filter((c) => !msg.cards.includes(c));
      t.mult = msg.mult;
      t.bombs = msg.bombs;
      if (isBomb(msg.cards)) t.boosts.push(msg.cards.length === 2 ? "rocket" : "bomb");
      t.lead = !!msg.lead;
      setTurn(t, msg.turn, msg.sec);
      note(t, { kind: "play", seat: msg.seat, cards: msg.cards, bomb: isBomb(msg.cards) });
      return;
    case "ddz_seat": {
      const s = t.seats[msg.seat]!;
      Object.assign(s, { id: msg.id, away: msg.away, auto: msg.auto });
      if (msg.turn !== undefined) setTurn(t, msg.turn, msg.sec);
      return;
    }
    case "ddz_result":
      t.phase = "result";
      t.result = {
        winner: msg.winner, landlord: msg.landlord, bid: msg.bid, bombs: msg.bombs, spring: msg.spring, mult: msg.mult,
        base: msg.base, deltas: msg.deltas, hands: msg.hands,
      };
      t.mult = msg.mult;
      t.seats.forEach((s, i) => { s.again = false; s.left = msg.hands[i]?.length ?? 0; });
      t.turn = null;
      t.acted = false;
      Object.assign(t, countdown(msg.sec));
      note(t, { kind: "result" });
      void reloadStatus();
      return;
    case "ddz_again":
      t.seats[msg.seat]!.again = true;
      return;
    case "ddz_closed":
      // The receipt stays until the player puts it away.
      if (t.phase === "result") t.closed = true;
      else close();
      return;
  }
}

if (!isMirrorWindow) {
  ddzHooks.message = onDdzMessage;
  // A move the server would not take: the keys come back. Requests held back are of anything (taps, emotes); only a
  // join of the queue is sent again.
  ddzHooks.refused = (code) => {
    if (code === "rate_limited") queueHeldBack();
    else if (ddz.value) ddz.value.acted = false;
  };
  // The room connection carries the table: without it nothing of the game is known here any more. The seat is kept
  // by the server and comes back, whole, with the room (ddz_state).
  watch(inRoom, (on) => {
    if (on) return;
    ddzLive.value = {};
    // The server takes a connection that left out of its queue, and off its open table.
    dropQueueJoin();
    ddzQueue.value = null;
    ddzWaiting.value = {};
    ddzTables.value = [];
    clearTimeout(callTimer);
    ddzCall.value = null;
    const t = ddz.value;
    if (t?.phase === "result") t.closed = true;
    else close();
  }, { flush: "sync" });
  // The hold on the queue (ddzRetry) is the save's on one server: it lasts through a new connection, and goes with
  // another save or server, as does anything of the queue.
  const forgetQueue = () => {
    clearTimeout(retryTimer);
    ddzRetry.value = false;
    dropQueueJoin();
    queueSentAt = -Infinity;
    ddzQueue.value = null;
    ddzWaiting.value = {};
  };
  watch(() => settings.serverUrl, forgetQueue, { flush: "sync" });
  let player = status.value?.player;
  watch(() => status.value?.player, (now) => {
    if (!now) return;
    if (player && now !== player) forgetQueue();
    player = now;
  }, { flush: "sync" });
  // The table's window comes up with each deal, the first and every one after 再来一局, and goes once the table is
  // put away. Closed during a deal, it stays closed until the next one. A deal while the hide key has the pet hidden
  // counts as closed: the pet's bubble leads back to it once the pet is shown again.
  watch(dealKey, (key) => {
    if (!key) {
      opened = "";
      closeDdzWindow();
      return;
    }
    if (key === opened || key === dismissed) return;
    if (!windowVisible.value) {
      dismissed = key;
      return;
    }
    opened = key;
    // The app checks again: the page hears of the pet being hidden a moment late.
    void openDdzWindow(true).then((shown) => { if (!shown && dealKey.value === key) dismissed = key; });
  }, { flush: "sync" });
}

// ------------------------------------------------------------------ actions (panel or desk)
export type DdzOp =
  | "invite" | "answer" | "bid" | "play" | "auto" | "again" | "leave" | "queue" | "unqueue" | "open" | "sit" | "call"
  | "dismiss";

/** The panel's and the table window's actions run in the desk window, which holds the room connection. */
export function ddzRequest(op: DdzOp, ...args: unknown[]): void {
  switch (op) {
    case "invite": inviteDdz(args[0] as string[], args[1] as number); break;
    case "answer": answerDdz(args[0] as boolean, args[1] as string | undefined); break;
    case "bid": bidDdz(args[0] as number); break;
    case "play": playDdz(args[0] as number[]); break;
    case "auto": autoDdz(args[0] as boolean); break;
    case "again": againDdz(); break;
    case "leave": leaveDdz(args[0] as string | undefined, args[1] as DdzState["phase"] | undefined); break;
    case "queue": queueDdz(args[0] as number); break;
    case "unqueue": unqueueDdz(); break;
    case "open": openDdz(args[0] as number); break;
    case "sit": sitDdz(args[0] as string, args[1] as number | undefined); break;
    case "call": callDdz(args[0] as string, args[1] as string); break;
    case "dismiss": dismissDdzCall(); break;
  }
}
const viaDesk = (op: DdzOp, ...args: unknown[]): boolean => {
  if (isMirrorWindow) void requestDesktop("ddz", op, ...args).catch(() => {});
  return isMirrorWindow;
};

/** Invite the two members [ids] to a game at [base]. */
export function inviteDdz(ids: string[], base: number): void {
  if (viaDesk("invite", ids, base)) return;
  const picked = ids.map((id) => members.get(id));
  if (ids.length === 2 && ids[0] !== ids[1] && ddzCanStart.value && ddzStakeOpen(base) && picked.every((m) => m && ddzCanInvite(m))) {
    sendDdz({ type: "ddz_invite", ids, base });
  }
}

/**
 * Answer the invite on screen, table [table] (the one shown where the key was pressed). Turning it down closes it at
 * once. The desk drops an answer for another table: one of the queue may have taken its place meanwhile, and accepting
 * it would pay its deposit.
 */
export function answerDdz(accept: boolean, table = ddz.value?.id): void {
  if (viaDesk("answer", accept, table)) return;
  const t = ddz.value;
  if (!t || t.id !== table || t.phase !== "invite" || t.sent || t.answered) return;
  sendDdz({ type: "ddz_answer", table: t.id, accept });
  if (accept) t.answered = true;
  else close();
}

const myTurn = (t: DdzState | null, phase: DdzState["phase"]): t is DdzState =>
  !!t && t.phase === phase && t.turn === t.you && !t.acted && !t.seats[t.you]?.auto;

/** Bid [bid] points for the landlord's seat, 0 to pass. */
export function bidDdz(bid: number): void {
  if (viaDesk("bid", bid)) return;
  const t = ddz.value;
  if (!myTurn(t, "bid") || Date.now() < t.dealUntil || (bid !== 0 && (bid <= t.bid || bid > 3))) return;
  t.acted = true;
  sendDdz({ type: "ddz_bid", table: t.id, bid });
}

/** Play [cards] from the hand, [] to pass. */
export function playDdz(cards: number[]): void {
  if (viaDesk("play", cards)) return;
  const t = ddz.value;
  if (!myTurn(t, "play")) return;
  const last = ddzLast(t);
  if (cards.length ? !cards.every((c) => t.hand.includes(c)) || !playable(cards, last?.cards ?? null) : !last) return;
  t.acted = true;
  sendDdz({ type: "ddz_play", table: t.id, cards });
}

/** Hand the seat to the server's autopilot, or take it back. */
export function autoDdz(on: boolean): void {
  if (viaDesk("auto", on)) return;
  const t = ddz.value;
  if (t && (t.phase === "bid" || t.phase === "play")) sendDdz({ type: "ddz_auto", table: t.id, on });
}

/** After a result: ask for another game with the same two. */
export function againDdz(): void {
  if (viaDesk("again")) return;
  const t = ddz.value;
  if (t?.phase === "result" && !t.closed && !t.seats[t.you]?.again) sendDdz({ type: "ddz_again", table: t.id });
}

/**
 * Leave the table: drops an invite, puts the receipt away, stands up from an open table (the opener puts it away), and
 * walks out of a game under way, which the server then plays to its end for this seat. With [table] (and [phase]) it
 * is for the table shown where the key was pressed: the desk drops it when its table is another by then.
 */
export function leaveDdz(table?: string, phase?: DdzState["phase"]): void {
  if (viaDesk("leave", table, phase)) return;
  const t = ddz.value;
  if (!t || (table !== undefined && (t.id !== table || (phase !== undefined && t.phase !== phase)))) return;
  if (t.phase !== "over" && !t.closed) sendDdz({ type: "ddz_leave", table: t.id });
  close();
}

/**
 * Wait in the server's queue for a table at [base] with two saves of any room; at another stake, move there. Within
 * QUEUE_GAP_MS of the last join it goes when the gap has passed, the stake picked last.
 */
export function queueDdz(base: number): void {
  if (viaDesk("queue", base)) return;
  if (!ddzCanQueue.value || !ddzStakeOpen(base) || (ddzQueue.value?.base === base && queueNext === null)) return;
  queueNext = base;
  queueRetried = false;
  sendQueueJoin();
}

/** Stop waiting in the queue, or drop a join not sent or not answered yet. */
export function unqueueDdz(): void {
  if (viaDesk("unqueue")) return;
  const asked = queueAsked !== null;
  dropQueueJoin();
  if (ddzQueue.value || asked) sendDdz({ type: "ddz_queue", base: 0 });
}

/** Open a table at [base] in the room, taking its first seat. */
export function openDdz(base: number): void {
  if (viaDesk("open", base)) return;
  if (ddzCanOpen.value && ddzStakeOpen(base)) sendDdz({ type: "ddz_open", base });
}

/** Sit down at the open table [table] of the room (or the one this save was called to), at [seat] when it is empty. */
export function sitDdz(table: string, seat?: number): void {
  if (viaDesk("sit", table, seat)) return;
  const t = ddzTables.value.find((x) => x.table === table) ?? (ddzCall.value?.table === table ? ddzCall.value : null);
  if (!t || !ddzCanSit(t.base) || !t.seats.some((s) => !s)) return;
  sendDdz(seat === undefined ? { type: "ddz_sit", table } : { type: "ddz_sit", table, seat });
}

/** The opener calls member [id] to its open table [table]; the desk drops it when its table is another by then. */
export function callDdz(id: string, table: string): void {
  if (viaDesk("call", id, table)) return;
  const t = ddz.value;
  const m = members.get(id);
  if (t && t.id === table && t.phase === "open" && t.you === 0 && m && ddzCanCall(m)) sendDdz({ type: "ddz_call", table, id });
}

/** Put the call over the own pet away. */
export function dismissDdzCall(): void {
  if (viaDesk("dismiss")) return;
  clearTimeout(callTimer);
  ddzCall.value = null;
}
