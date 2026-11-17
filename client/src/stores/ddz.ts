// Dou dizhu (斗地主) at a table of the room: the invite, the game as this seat sees it, and how it ended. The desk
// window hears the server and keeps the state; the panel mirrors it (desktop/bridge.ts) and draws the table. The
// server decides everything (server/app/ddz.py); the rules here (src/ddz/rules.ts) only light the keys.
import { computed, ref, watch } from "vue";
import { isBomb, playable, sortHand } from "../ddz/rules";
import type { DdzMessage, Member } from "../net/protocol";
import { isPanelWindow, isTauri } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";
import { economy } from "./economy";
import { reloadStatus, status } from "./player";
import { ddzHooks, duelBusy, inRoom, me, members, sendDdz, showWin, shownNick, youId } from "./room";
import { openPanel, ui } from "./ui";

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
  phase: "invite" | "bid" | "play" | "result" | "over";
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
  timeout: "没有等到回应", gone: "有人离开了", nobid: "三次都没人叫分，押金已退还", no_shards: "有人的碎片不够押金",
  ddz_cap: "有人今天赢到上限了", ddz_locked: "有人还不能斗地主", error: "没能开局",
};
/** Why a table ended with nothing won, in words. */
export const ddzReason = (t: DdzState): string =>
  (t.reason === "declined" ? `${t.by || "有人"}没有接受` : REASONS[t.reason] ?? "已取消");

/** The panel shows the room page, where the table is drawn (the desk window is told by the panel). */
export const ddzTableSeen = computed(() => (isTauri && !isPanelWindow ? ui.roomSeen : ui.panelOpen && ui.page === "room"));

/**
 * What the bubble over the own pet shows: an invite, how one ended, or that a game goes on while the table is out
 * of sight ("turn" when it waits for this seat); null for nothing.
 */
export const ddzBubble = computed<"invite" | "over" | "turn" | "table" | null>(() => {
  const t = ddz.value;
  if (!t) return null;
  if (t.phase === "invite" || t.phase === "over") return t.phase;
  if ((t.phase === "bid" || t.phase === "play") && !ddzTableSeen.value) return t.turn === t.you && !t.seats[t.you]?.auto ? "turn" : "table";
  return null;
});

// ------------------------------------------------------------------ messages (desk window)
let endTimer: ReturnType<typeof setTimeout> | undefined;
let seq = 0;

const countdown = (sec: number) => ({ sec, until: Date.now() + sec * 1000 });

function blank(id: string): DdzState {
  return {
    id, phase: "invite", you: 0, seats: [], sent: false, answered: false, accepted: [], base: 0, deposit: 0, cap: 0, deal: 0,
    hand: [], bid: 0, landlord: null, bottom: [], mult: 1, bombs: 0, boosts: [], dealUntil: 0, turn: null, lead: false,
    trick: [null, null, null],
    sec: 0, until: 0, acted: false, result: null, closed: false, reason: "", by: "", log: [],
  };
}

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
    for (const [id, gain] of Object.entries(msg.gains ?? {})) showWin(id, gain);
    return;
  }
  if (msg.type === "ddz_invite") {
    const at = msg.ids.indexOf(you);
    if (at < 0) return;
    clearTimeout(endTimer);
    ddz.value = {
      ...blank(msg.table), you: at, sent: msg.from === you, accepted: [msg.from], base: msg.base, deposit: msg.deposit,
      seats: msg.ids.map((id) => {
        const m = members.get(id);
        return { id, nick: m?.nick ?? "", character: m?.character ?? "", left: 0, bid: null, auto: false, away: false, again: false };
      }),
      ...countdown(msg.sec),
    };
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
    // The deposit is paid with a table's first deal; the table opens on the panel's room page.
    if (msg.type === "ddz_state" || msg.deal === 1) {
      void reloadStatus();
      openPanel("room");
    }
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

if (!isPanelWindow) {
  ddzHooks.message = onDdzMessage;
  // A move the server would not take: the keys come back.
  ddzHooks.refused = () => { if (ddz.value) ddz.value.acted = false; };
  // The room connection carries the table: without it nothing of the game is known here any more. The seat is kept
  // by the server and comes back, whole, with the room (ddz_state).
  watch(inRoom, (on) => {
    if (on) return;
    ddzLive.value = {};
    const t = ddz.value;
    if (t?.phase === "result") t.closed = true;
    else close();
  }, { flush: "sync" });
}

// ------------------------------------------------------------------ actions (panel or desk)
export type DdzOp = "invite" | "answer" | "bid" | "play" | "auto" | "again" | "leave";

/** The panel's actions run in the desk window, which holds the room connection. */
export function ddzRequest(op: DdzOp, ...args: unknown[]): void {
  switch (op) {
    case "invite": inviteDdz(args[0] as string[], args[1] as number); break;
    case "answer": answerDdz(args[0] as boolean); break;
    case "bid": bidDdz(args[0] as number); break;
    case "play": playDdz(args[0] as number[]); break;
    case "auto": autoDdz(args[0] as boolean); break;
    case "again": againDdz(); break;
    case "leave": leaveDdz(); break;
  }
}
const viaDesk = (op: DdzOp, ...args: unknown[]): boolean => {
  if (isPanelWindow) void requestDesktop("ddz", op, ...args).catch(() => {});
  return isPanelWindow;
};

/** Invite the two members [ids] to a game at [base]. */
export function inviteDdz(ids: string[], base: number): void {
  if (viaDesk("invite", ids, base)) return;
  const picked = ids.map((id) => members.get(id));
  if (ids.length === 2 && ids[0] !== ids[1] && ddzCanStart.value && ddzStakeOpen(base) && picked.every((m) => m && ddzCanInvite(m))) {
    sendDdz({ type: "ddz_invite", ids, base });
  }
}

/** Answer the invite on screen. Turning it down closes it at once. */
export function answerDdz(accept: boolean): void {
  if (viaDesk("answer", accept)) return;
  const t = ddz.value;
  if (!t || t.phase !== "invite" || t.sent || t.answered) return;
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
 * Leave the table: drops an invite, puts the receipt away, and walks out of a game under way, which the server
 * then plays to its end for this seat.
 */
export function leaveDdz(): void {
  if (viaDesk("leave")) return;
  const t = ddz.value;
  if (!t) return;
  if (t.phase !== "over" && !t.closed) sendDdz({ type: "ddz_leave", table: t.id });
  close();
}
