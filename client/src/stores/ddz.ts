// Dou dizhu (斗地主) at a table of the room: the invite, the game as this seat sees it, and how it ended; the
// server's queue, where a save waits at one stake for two others from any room; and open tables, opened in the room
// for its members to sit down at. The desk window hears the server and keeps the state; the panel and the table's own
// window mirror it (desktop/bridge.ts), the panel for the invite and the queue, the table's window (DdzApp.vue) for the
// lobby and the game. Invites and open tables go over the room connection; the queue, and the tables it makes, over
// a dou dizhu connection of their own (net/DdzLink.ts), open only while the save waits or sits at such a table. The
// server decides everything (server/app/ddz.py); the rules here (src/ddz/rules.ts) only light the keys.
import { computed, ref, watch } from "vue";
import { isBomb, playable, sortHand } from "../ddz/rules";
import type { DdzClientMessage, DdzMessage, DdzOpenSeat, DdzOpenTable, Member } from "../net/protocol";
import { DdzLink } from "../net/DdzLink";
import type { ConnState } from "../net/RoomClient";
import { EmotePlayer, type EmoteFrame } from "../pet/EmotePlayer";
import { isMirrorWindow, isTauri } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import { noteActivity, windowVisible } from "./activity";
import { economy } from "./economy";
import { account, loadDdzLobby, reloadStatus, saveCode, status } from "./player";
import { settings } from "./settings";
import {
  clearRoomError, ddzEmoteOn, ddzHooks, ddzMatchOn, duelBusy, duelDnd, helloInfo, inRoom, me, members, sendDdz, sendEmote,
  showRoomError, showWin, shownNick, youId,
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
  /** The name plate its member wears, as the table was told. */
  plate?: string | null;
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
  /** The connection the table is on: the room's, or the dou dizhu connection (the queue's tables). */
  via: "room" | "link";
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
  /** Every card played this deal, in order; null when the server did not say (a seat taken again on an old server). */
  played: number[] | null;
  /**
   * The own card counter where it is sold: on for this game, and the games of it the save has left. null where it is
   * free. `counterAsked`: turning it on was asked for and not answered yet; `counterError`: why the last asking bought
   * nothing.
   */
  counter: { on: boolean; left: number } | null;
  counterAsked: boolean;
  counterError: string;
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

/** The dou dizhu connection: how it stands, "open" once its hello went through. */
export const ddzLink = ref<ConnState>("idle");
/** The server has no dou dizhu connection or lobby (it refused the hello, or the lobby answered 404): no queue. */
export const ddzLinkOff = ref(false);
/** The emote over each seat's pet at the table, by seat (the own seat's is the own pet's, room.localPet). */
export const ddzEmotes = ref<(EmoteFrame | null)[]>([null, null, null]);

/** The server has the game (its status says so). */
export const ddzServerOn = computed(() => !!ddzConfig.value && !!status.value?.ddz);
/** The server has the game and this client is in a room. */
export const ddzOn = computed(() => inRoom.value && ddzServerOn.value);
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

/** Whether this save looks able to sit down at a game, in a room or not; the server checks again. */
const ddzSaveReady = computed(() => {
  const cfg = ddzConfig.value;
  const s = status.value;
  return ddzServerOn.value && !!cfg && !!s && !!s.player && !ddzBusy.value && !duelBusy.value &&
    s.totals.taps >= cfg.minTaps && cfg.stakes.some(ddzStakeOpen);
});

/** Whether this save looks able to start a game in its room; the server checks again, the other saves included. */
export const ddzCanStart = computed(() => ddzOn.value && !!me.value?.uid && ddzSaveReady.value);

/** The room's server opens tables (it lists "ddz_match" in `joined.features`), and this client is in that room. */
export const ddzMatchable = computed(() => ddzOn.value && ddzMatchOn.value);

/** The server has the game and its queue (on the dou dizhu connection), in a room or not. */
export const ddzQueueOn = computed(() => ddzServerOn.value && !ddzLinkOff.value);

/** Whether this save looks able to wait for a table: able to sit down, and not turning invites down. */
export const ddzCanQueue = computed(() => ddzQueueOn.value && ddzSaveReady.value && !duelDnd() && !ddzRetry.value);

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
/** The stake of a join waiting for its time (or for the dou dizhu connection) to be sent, and its timer. */
const queueNext = ref<number | null>(null);
let queueTimer: ReturnType<typeof setTimeout> | undefined;
/**
 * Waiting was stopped and the server has not said so yet: the stop is sent again on every new connection whose hello
 * took the wait over (ddz_ready `base`), and the connection stays up for it. Kept from the click until the server says
 * the save waits no more.
 */
const unqueueLater = ref(false);
/** Asks the server again whether the save holds a seat of the queue's (the desk's probe, set below). */
let reprobe: (delay: number) => void = () => {};
/** The stake of a join sent and not answered yet; whether it was sent once more after the server held it back. */
const queueAsked = ref<number | null>(null);
let queueRetried = false;

function dropQueueJoin(): void {
  clearTimeout(queueTimer);
  queueTimer = undefined;
  queueNext.value = null;
  queueAsked.value = null;
}

/**
 * Sends the join waiting for its time once the gap since the last one has passed and the dou dizhu connection is
 * ready, if the save can still wait there.
 */
function sendQueueJoin(): void {
  clearTimeout(queueTimer);
  queueTimer = undefined;
  const base = queueNext.value;
  if (base === null || !link.ready) return;
  const wait = queueSentAt + QUEUE_GAP_MS - Date.now();
  if (wait > 0) {
    queueTimer = setTimeout(sendQueueJoin, wait);
    return;
  }
  queueNext.value = null;
  if (!ddzCanQueue.value || !ddzStakeOpen(base) || ddzQueue.value?.base === base) return;
  queueSentAt = Date.now();
  queueAsked.value = base;
  clearRoomError();
  link.send({ type: "ddz_queue", base });
}

/** `rate_limited` from the server: when a join waits for its answer it may be the one held back, sent once more. */
function queueHeldBack(): void {
  if (queueAsked.value === null || queueRetried) return;
  queueRetried = true;
  queueNext.value = queueAsked.value;
  queueAsked.value = null;
  queueSentAt = Date.now();
  sendQueueJoin();
}

// ------------------------------------------------------------------ the dou dizhu connection (desk window)
/** The member id the dou dizhu connection goes by, from its last hello. */
let linkYou = "";
/** The server says the save holds a seat of the queue's (GET /api/ddz/lobby, `seated`): the connection takes it back. */
const reclaim = ref(false);
/** How long the connection stays up after nothing needs it, so a game asked for again or a quick new join reuse it. */
export const LINK_GRACE_MS = 10_000;
/** How long the desk waits to ask again whether the save holds a seat of the queue's, after the asking failed. */
export const PROBE_RETRY_MS = 30_000;
let linkTimer: ReturnType<typeof setTimeout> | undefined;

const link = new DdzLink({
  onState(s) {
    ddzLink.value = s;
  },
  onReady(you, base, waited, table) {
    linkYou = you;
    reclaim.value = false;
    // A table of this connection that the server did not give back is gone (its invite, its open seat, its game).
    if (shelf.value?.via === "link" && shelf.value.id !== table) shelf.value = null;
    const t = ddz.value;
    if (t?.via === "link" && t.id !== table) {
      if (t.phase === "result") t.closed = true;
      else close();
    }
    if (base && unqueueLater.value) {
      link.send({ type: "ddz_queue", base: 0 });
    } else if (base) {
      ddzQueue.value = { base, since: Date.now() - waited * 1000 };
    } else if (unqueueLater.value) {
      ddzQueue.value = null;
    } else if (ddzQueue.value || queueAsked.value !== null) {
      // The wait went with the last connection: joined again, at the back of the line.
      queueNext.value = queueNext.value ?? queueAsked.value ?? ddzQueue.value!.base;
      queueAsked.value = null;
      ddzQueue.value = null;
    }
    if (!base) unqueueLater.value = false;
    sendQueueJoin();
  },
  onDdz(msg) {
    noteActivity();
    onDdzMessage(msg, "link");
  },
  onError(code) {
    if (code === "rate_limited") {
      queueHeldBack();
      return;
    }
    if (code === "ddz_gone" || code === "ddz_turn" || code === "ddz_bad") {
      if (ddz.value?.via === "link") Object.assign(ddz.value, { acted: false, counterAsked: false });
      return;
    }
    queueAsked.value = null;
    if (!link.active) {
      // Refused for good. A server without the connection, or a client it no longer takes: no queue here. A save it
      // does not know, a newer connection of the save (another device), or a full server: this one stops, and the
      // next join tries again.
      if (code === "no_ddz" || code === "client_outdated" || code === "bad_message") ddzLinkOff.value = true;
      // A full server while a seat waits to be taken back: asked again later whether it still waits, and taken then.
      else if (code === "ddz_full" && reclaim.value) reprobe(PROBE_RETRY_MS);
      dropQueueJoin();
      ddzQueue.value = null;
      reclaim.value = false;
      unqueueLater.value = false;
    }
    showRoomError(code);
  },
});

/** Something needs the dou dizhu connection: a join of the queue, the wait, a seat to take back, a table on it. */
const linkWanted = computed(() => {
  if (ddzLinkOff.value) return false;
  const t = ddz.value;
  return queueNext.value !== null || queueAsked.value !== null || !!ddzQueue.value || reclaim.value ||
    // A stop of the wait the server has not confirmed, while the connection that took the wait over may come back.
    (unqueueLater.value && ddzLink.value !== "idle") ||
    (t?.via === "link" && t.phase !== "over" && !(t.phase === "result" && t.closed)) ||
    // A game of the connection put aside behind a table of the room's still goes on.
    (shelf.value?.via === "link" && going(shelf.value)) ||
    // A room's invite to this save took it out of the queue for as long as it is out: the connection stays up to get
    // the place back should no game come of it.
    (t?.via === "room" && t.phase === "invite" && !t.sent && ddzLink.value !== "idle");
});

/** Desk: sends [msg] for the table on the connection it is on. */
function sendTable(msg: DdzClientMessage): void {
  if (ddz.value?.via === "link") {
    clearRoomError();
    link.send(msg);
  } else {
    sendDdz(msg);
  }
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

function blank(id: string, via: DdzState["via"]): DdzState {
  return {
    id, via, phase: "invite", match: false, starting: false, you: 0, seats: [], sent: false, answered: false, accepted: [], base: 0, deposit: 0, cap: 0, deal: 0,
    hand: [], bid: 0, landlord: null, bottom: [], mult: 1, bombs: 0, boosts: [], dealUntil: 0, turn: null, lead: false,
    trick: [null, null, null], played: [], counter: null, counterAsked: false, counterError: "",
    sec: 0, until: 0, acted: false, result: null, closed: false, reason: "", by: "", log: [],
  };
}

const seatOf = (s: { id: string; nick: string; character: string; plate?: string | null } | null | undefined, pending = false): DdzSeat => ({
  id: s?.id ?? "", nick: s?.nick ?? "", character: s?.character ?? "", left: 0, bid: null, auto: false, away: false,
  again: false, ...(pending ? { pending } : {}), ...(s?.plate ? { plate: s.plate } : {}),
});
const openSeat = (s: DdzOpenSeat): DdzSeat => (s && "id" in s ? seatOf(s) : seatOf(null, !!s));

function note(t: DdzState, event: DdzEventBody): void {
  t.log.push({ ...event, seq: ++seq });
  if (t.log.length > LOG_MAX) t.log.splice(0, t.log.length - LOG_MAX);
}

/**
 * A table of the other connection (room or dou dizhu) still going, kept aside while a table of this one is on screen
 * (ddz). The server holds one table per save, so one of the two is out of date, its ending still on the way: both
 * hear their own connection's messages, and whichever ends first, the other comes back on screen.
 */
const shelf = ref<DdzState | null>(null);
const going = (t: DdzState) => t.phase !== "over" && !(t.phase === "result" && t.closed);

/** Table [id] of connection [via] comes up: one of the other connection still going on screen is put aside. */
function shelve(id: string, via: DdzState["via"]): void {
  const t = ddz.value;
  if (t && t.id !== id && t.via !== via && going(t)) shelf.value = t;
  else if (shelf.value?.id === id) shelf.value = null;
}

/** The table put aside, if it still goes on, taken off the shelf. */
function unshelve(): DdzState | null {
  const t = shelf.value;
  shelf.value = null;
  return t && going(t) ? t : null;
}

/** Drops the table put aside when it is of connection [via]. */
function dropShelf(via: DdzState["via"]): void {
  if (shelf.value?.via === via) shelf.value = null;
}

function close(): void {
  clearTimeout(endTimer);
  ddz.value = unshelve();
}

/** Leaves the ending up for a moment, then clears it (unless another table took its place). */
function closeLater(): void {
  clearTimeout(endTimer);
  const shown = ddz.value;
  endTimer = setTimeout(() => { if (ddz.value?.id === shown?.id) ddz.value = unshelve(); }, DDZ_END_MS);
}

function setTurn(t: DdzState, turn: number | undefined, sec: number | undefined): void {
  t.acted = false;
  if (turn === undefined) { t.turn = null; return; }
  t.turn = turn;
  Object.assign(t, countdown(sec ?? 0));
}

/**
 * A message of dou dizhu, from the room connection or ([via] "link") the dou dizhu connection: each names this save by
 * its own member id.
 */
export function onDdzMessage(msg: DdzMessage, via: DdzState["via"] = "room"): void {
  const you = via === "link" ? linkYou : youId.value;
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
    if (via === "link" && !msg.base) unqueueLater.value = false;
    // Said before the stop reached the server: the stop is on its way, and the wait is not shown again.
    else if (via === "link" && unqueueLater.value) return;
    queueAsked.value = null;
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
  // The table put aside, when the message is of it: it comes back on screen with what it knew.
  let prior: DdzState | null = null;
  if (msg.type === "ddz_open" || msg.type === "ddz_invite" || msg.type === "ddz_deal" || msg.type === "ddz_state") {
    prior = shelf.value?.id === msg.table && shelf.value.via === via ? shelf.value : null;
    shelve(msg.table, via);
  }
  if (msg.type === "ddz_open") {
    // Seated at an open table (after a game too, when it opens again): the call to it is answered.
    const before = ddz.value?.id === msg.table ? ddz.value : prior;
    // All three asked for another game and the deposits are being taken: the result stays on the table (and the table
    // up) until the deal, or until the table waits again.
    if (msg.starting && before?.phase === "result") return;
    clearTimeout(endTimer);
    ddz.value = {
      ...blank(msg.table, via), log: before?.log ?? [], phase: "open", you: msg.you, base: msg.base, deposit: msg.deposit,
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
      // Asked again on a new connection after answering on the old one (the server hands the answer over).
      ...blank(msg.table, via), you: at, match: !!msg.match, sent: !!msg.from && msg.from === you, answered: !!msg.accepted?.includes(you),
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
    const before = ddz.value?.id === msg.table ? ddz.value : prior;
    const t: DdzState = {
      ...blank(msg.table, via), log: before?.log ?? [], deposit: before?.deposit ?? ddzDeposit(msg.base),
      phase: msg.type === "ddz_state" ? msg.phase : "bid", you: msg.you, base: msg.base, cap: msg.cap, deal: msg.deal,
      hand: sortHand(msg.hand), counter: msg.counter ? { on: msg.counter.on, left: msg.counter.left } : null,
      seats: msg.seats.map((s) => ({
        id: s.id, nick: s.nick, character: s.character, auto: s.auto, away: s.away, again: false,
        left: "left" in s ? s.left : 17, bid: "bid" in s ? s.bid : null, ...(s.plate ? { plate: s.plate } : {}),
      })),
    };
    if (msg.type === "ddz_state") {
      Object.assign(t, {
        bid: msg.bid, landlord: msg.landlord, bottom: msg.bottom, mult: msg.mult, bombs: msg.bombs, turn: msg.turn,
        lead: msg.lead, trick: msg.trick, sec: msg.of, until: Date.now() + msg.sec * 1000,
        boosts: Array<"bomb">(msg.bombs).fill("bomb"),
        played: msg.played ? [...msg.played] : null,
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
  // The table on screen, or the one put aside: each goes on with its own connection's messages.
  const front = ddz.value?.id === msg.table ? ddz.value : null;
  const t = front ?? (shelf.value?.id === msg.table && shelf.value.via === via ? shelf.value : null);
  if (!t) {
    // A game this client walked away from was played to its end: the shards changed.
    if (msg.type === "ddz_result" || msg.type === "ddz_over") void reloadStatus();
    return;
  }
  if (!front) {
    // Put aside: kept up to date, but nothing of it shows; its ending drops it, the one on screen being the right one.
    if (msg.type === "ddz_over" || (msg.type === "ddz_closed" && t.phase !== "result")) {
      shelf.value = null;
      void reloadStatus();
      return;
    }
    if (msg.type === "ddz_emote") return;
  }
  switch (msg.type) {
    case "ddz_answer":
      if (!t.accepted.includes(msg.id)) t.accepted.push(msg.id);
      return;
    case "ddz_over": {
      const by = msg.by ? t.seats.find((s) => s.id === msg.by) : undefined;
      Object.assign(t, { phase: "over", reason: msg.reason, by: by ? shownNick(by) : "", turn: null });
      void reloadStatus(); // deposits taken went back
      // A table put aside goes on: it was the right one, and comes back at once.
      if (shelf.value && going(shelf.value)) close();
      else closeLater();
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
      t.played?.push(...msg.cards);
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
      if (msg.nick !== undefined) Object.assign(s, { nick: msg.nick, character: msg.character ?? s.character, plate: msg.plate ?? null });
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
      // Out of any room, nobody tells the desk of the game's end (ddz_live): the own pet shows its win from here.
      if (front && t.via === "link" && !inRoom.value && (msg.deltas[t.you] ?? 0) > 0) showWin(youId.value, msg.deltas[t.you]!);
      return;
    case "ddz_again":
      t.seats[msg.seat]!.again = true;
      return;
    case "ddz_counter":
      Object.assign(t, { counter: { on: msg.on, left: msg.left }, counterAsked: false, counterError: msg.error ?? "" });
      // Bought: the coins and shards changed.
      if (!msg.error) void reloadStatus();
      return;
    case "ddz_emote":
      if (msg.seat !== t.you) seatEmotes[msg.seat]?.play(msg.emote);
      return;
    case "ddz_closed":
      // The receipt stays until the player puts it away.
      if (t.phase === "result") t.closed = true;
      else close();
      return;
  }
}

/** Plays the table's emotes over each seat's pet (ddzEmotes). */
const seatEmotes = [0, 1, 2].map((i) => new EmotePlayer((f) => {
  const next = [...ddzEmotes.value];
  next[i] = f;
  ddzEmotes.value = next;
}, () => settings.emoteHoldMs));

if (!isMirrorWindow) {
  ddzHooks.message = (msg) => onDdzMessage(msg, "room");
  // A move the server would not take: the keys come back. Requests held back are of anything (taps, emotes); the
  // queue's are the dou dizhu connection's (link.onError).
  ddzHooks.refused = (code) => {
    if (code !== "rate_limited" && ddz.value?.via === "room") Object.assign(ddz.value, { acted: false, counterAsked: false });
  };
  // A new table starts without the last one's emotes.
  watch(() => ddz.value?.id, () => seatEmotes.forEach((p) => p.clear()), { flush: "sync" });
  // The room connection carries the room's tables: without it nothing of them is known here any more. The seat is
  // kept by the server and comes back, whole, with the room (ddz_state). The queue and its tables are not the room's.
  watch(inRoom, (on) => {
    if (on) return;
    ddzLive.value = {};
    ddzTables.value = [];
    clearTimeout(callTimer);
    ddzCall.value = null;
    dropShelf("room");
    const t = ddz.value;
    if (t?.via !== "room") return;
    if (t.phase === "result") t.closed = true;
    else close();
  }, { flush: "sync" });
  // The dou dizhu connection is up while something needs it, and goes LINK_GRACE_MS after nothing does.
  watch(linkWanted, (on) => {
    clearTimeout(linkTimer);
    if (on) {
      if (!link.active) link.open(settings.serverUrl, helloInfo());
      return;
    }
    linkTimer = setTimeout(() => { if (!linkWanted.value) link.close(); }, LINK_GRACE_MS);
  }, { flush: "sync" });
  // Down for good (closed, or a final refusal): nothing of it is known any more.
  watch(ddzLink, (state) => {
    if (state !== "idle") return;
    linkYou = "";
    if (ddzQueue.value && !link.active) ddzQueue.value = null;
    if (!link.active) dropShelf("link");
    const t = ddz.value;
    if (t?.via === "link" && !link.active) {
      if (t.phase === "result") t.closed = true;
      else if (t.phase !== "over") close();
    }
  }, { flush: "sync" });
  // What the hello says follows the settings; an open connection hears the change as a room would.
  watch(duelDnd, (dnd) => {
    link.patchHello({ dnd: dnd || undefined });
    link.send({ type: "dnd", dnd });
  }, { flush: "sync" });
  watch(() => [settings.nick, settings.character, settings.plate] as const, () => {
    const hello = helloInfo();
    link.patchHello(hello);
    link.send({ type: "state", nick: hello.nick, character: hello.character, plate: settings.plate });
  }, { flush: "sync" });
  // The hold on the queue (ddzRetry) is the save's on one server: it lasts through a new connection, and goes with
  // another save or server, as does anything of the queue and the connection.
  const forgetQueue = () => {
    clearTimeout(retryTimer);
    ddzRetry.value = false;
    dropQueueJoin();
    queueSentAt = -Infinity;
    ddzQueue.value = null;
    ddzWaiting.value = {};
    reclaim.value = false;
    link.close();
    ddzLinkOff.value = false;
    dropShelf("link");
    if (ddz.value?.via === "link") close();
  };
  watch(() => settings.serverUrl, forgetQueue, { flush: "sync" });
  let player = status.value?.player;
  watch(() => status.value?.player, (now) => {
    if (!now) return;
    if (player && now !== player) forgetQueue();
    player = now;
  }, { flush: "sync" });
  // Another guest save or account: the connection speaks for the save it said hello as, so it goes.
  watch(() => [saveCode.value, account.value?.token], () => { if (link.active) forgetQueue(); }, { flush: "sync" });
  // Once per server and save, the desk asks whether the save holds a seat of the queue's (a restart in the middle of a
  // game): the connection then comes up and takes it back.
  // A read that failed is tried again after PROBE_RETRY_MS; an answer for another server or save than the current one is
  // dropped.
  let checked = "";
  let probing = "";
  let probeTimer: ReturnType<typeof setTimeout> | undefined;
  const probeKey = () => (status.value?.player && ddzServerOn.value ? `${settings.serverUrl}|${status.value.player}` : "");
  const probe = () => {
    clearTimeout(probeTimer);
    const key = probeKey();
    if (!key || checked === key || probing === key) return;
    probing = key;
    void loadDdzLobby().then((lobby) => {
      if (probing === key) probing = "";
      if (key !== probeKey()) return;
      if (lobby === null) {
        probeTimer = setTimeout(probe, PROBE_RETRY_MS);
        return;
      }
      checked = key;
      if (lobby === "off") ddzLinkOff.value = true;
      else if (lobby.seated && !link.active) reclaim.value = true;
    });
  };
  watch(probeKey, probe, { immediate: true });
  reprobe = (delay) => {
    checked = "";
    clearTimeout(probeTimer);
    probeTimer = setTimeout(probe, delay);
  };
  // The table's window comes up with each deal, the first and every one after 再来一局, and goes once the table is
  // put away. Closed during a deal, it stays closed until the next one. A deal while the hide key has the pet
  // hidden counts as closed: the pet's bubble leads back to it once the pet is shown again.
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
  | "dismiss" | "emote" | "counter";

/**
 * The panel's and the table window's actions run in the desk window, which holds the connections. An argument left
 * out comes over the bridge as null (JSON), and is taken as left out.
 */
export function ddzRequest(op: DdzOp, ...sent: unknown[]): void {
  const args = sent.map((x) => x ?? undefined);
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
    case "emote": emoteDdz(args[0] as string); break;
    case "counter": counterDdz(); break;
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
  sendTable({ type: "ddz_answer", table: t.id, accept });
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
  sendTable({ type: "ddz_bid", table: t.id, bid });
}

/** Play [cards] from the hand, [] to pass. */
export function playDdz(cards: number[]): void {
  if (viaDesk("play", cards)) return;
  const t = ddz.value;
  if (!myTurn(t, "play")) return;
  const last = ddzLast(t);
  if (cards.length ? !cards.every((c) => t.hand.includes(c)) || !playable(cards, last?.cards ?? null) : !last) return;
  t.acted = true;
  sendTable({ type: "ddz_play", table: t.id, cards });
}

/** Hand the seat to the server's autopilot, or take it back. */
export function autoDdz(on: boolean): void {
  if (viaDesk("auto", on)) return;
  const t = ddz.value;
  if (t && (t.phase === "bid" || t.phase === "play")) sendTable({ type: "ddz_auto", table: t.id, on });
}

/**
 * Turn the own card counter on where it is sold: a save with no game of it left buys its games first (the server
 * answers with what it has then, or why it bought nothing).
 */
export function counterDdz(): void {
  if (viaDesk("counter")) return;
  const t = ddz.value;
  if (!t?.counter || t.counter.on || t.counterAsked || (t.phase !== "bid" && t.phase !== "play")) return;
  t.counterAsked = true;
  t.counterError = "";
  sendTable({ type: "ddz_counter", table: t.id });
}

/** After a result: ask for another game with the same two. */
export function againDdz(): void {
  if (viaDesk("again")) return;
  const t = ddz.value;
  if (t?.phase === "result" && !t.closed && !t.seats[t.you]?.again) sendTable({ type: "ddz_again", table: t.id });
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
  if (t.phase !== "over" && !t.closed) sendTable({ type: "ddz_leave", table: t.id });
  close();
}

/**
 * Wait in the server's queue for a table at [base] with two saves of any room; at another stake, move there. It goes
 * over the dou dizhu connection, which comes up for it; within QUEUE_GAP_MS of the last join it goes when the gap has
 * passed, the stake picked last.
 */
export function queueDdz(base: number): void {
  if (viaDesk("queue", base)) return;
  if (!ddzCanQueue.value || !ddzStakeOpen(base) || (ddzQueue.value?.base === base && queueNext.value === null)) return;
  queueNext.value = base;
  queueRetried = false;
  unqueueLater.value = false;
  sendQueueJoin();
}

/** Stop waiting in the queue, or drop a join not sent or not answered yet. */
export function unqueueDdz(): void {
  if (viaDesk("unqueue")) return;
  const asked = queueAsked.value !== null;
  dropQueueJoin();
  if (!ddzQueue.value && !asked) return;
  ddzQueue.value = null;
  if (link.ready) {
    link.send({ type: "ddz_queue", base: 0 });
    unqueueLater.value = true;
    return;
  }
  // Not connected: the server drops the wait with the connection, unless a new hello takes it over first; that one
  // then stops it (onReady).
  unqueueLater.value = link.active;
}

/** Show emote [name] to the other seats of the table (and on the own pet); the server keeps it to the table. */
export function emoteDdz(name: string): void {
  if (viaDesk("emote", name)) return;
  const t = ddz.value;
  if (!t || (t.phase !== "bid" && t.phase !== "play" && t.phase !== "result")) return;
  // A room's server without table emotes: the emote goes to the room, as before them.
  if (t.via === "room" && !ddzEmoteOn.value) {
    sendEmote(name);
    return;
  }
  if (sendEmote(name, Date.now(), false)) sendTable({ type: "ddz_emote", table: t.id, emote: name });
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
