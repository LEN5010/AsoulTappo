// The daily lottery (protocol/PROTOCOL.md 每日夺宝): the shape of GET /api/park/lottery, and the small rules the
// section shows: which digits of a ticket matched, the countdown, and the check of a drawn number against the hash
// published before the day's sales.

export type LotteryTier = "top" | "second" | "third";

export interface LotteryTiers<T> { top: T; second: T; third: T }

export interface LotteryDraw {
  day: string;
  number: string;
  salt: string;
  hash: string;
  drawnAt: number;
  sales: number;
  /** Winning tickets per tier, and shards per winning ticket. */
  winners: LotteryTiers<number>;
  each: LotteryTiers<number>;
  mine: { number: string; tier: LotteryTier | null; prize: number }[];
  won: number;
}

export interface LotteryState {
  day: string;
  hash: string;
  /** Unix seconds of today's close and draw; once `drawn`, the next draw is a day later. */
  closeAt: number;
  drawAt: number;
  open: boolean;
  drawn: boolean;
  sales: number;
  /** The next draw's prizes: today's until it is drawn, then what has rolled into tomorrow. */
  prize: LotteryTiers<number>;
  daily: number;
  left: number;
  tickets: string[];
  last: LotteryDraw | null;
  /** The save's latest drawn days with tickets, newest first. */
  history: { day: string; number: string; won: number }[];
  /** The server's latest drawn days, newest first, with who won the top prize and what each top ticket was paid. */
  draws: LotteryDrawLine[];
}

/** A drawn day in the list of top prize winners: `top` has a save once (collection board id and nick). */
export interface LotteryDrawLine {
  day: string;
  number: string;
  top: { id: string; nick: string }[];
  each: number;
}

export interface LotteryBuy { lottery: LotteryState; bought: string[] }

/** How many trailing digits of a ticket of [tier] match the drawn number. */
export function matchedDigits(tier: LotteryTier | null): number {
  return tier === "top" ? 3 : tier === "second" ? 2 : tier === "third" ? 1 : 0;
}

/**
 * After [stopped] trailing digits of a draw have come to rest (0 to 3): which digits of a ticket of [tier] are lit,
 * and whether the ticket is out, i.e. cannot win anything any more.
 */
export function revealDigits(tier: LotteryTier | null, stopped: number): { lit: boolean[]; out: boolean } {
  const matched = matchedDigits(tier);
  const k = Math.min(stopped, matched);
  return { lit: [0, 1, 2].map((j) => j >= 3 - k), out: stopped > 0 && matched === 0 };
}

/** Whether tickets can be bought at [now] (Unix seconds): the server says so and the local clock is before the close. */
export function salesOpen(s: Pick<LotteryState, "open" | "closeAt">, now: number): boolean {
  return s.open && now < s.closeAt;
}

/** The digit on cell [k] (k >= 1) of key [key]'s spinning reel: every digit once in ten cells, never twice in a row. */
export function reelDigit(k: number, key: number): string {
  return String((((k * 7 + key * 3) % 10) + 10) % 10);
}

/** A draw's top prize winners in a line: up to [most] nicks, then how many in all; 无人 without one. */
export function winnersLine(top: readonly { nick: string }[], most = 3): string {
  if (!top.length) return "无人";
  const names = top.slice(0, most).map((t) => t.nick).join("、");
  return top.length > most ? `${names} 等 ${top.length} 人` : names;
}

/** The next draw time in Unix seconds. */
export function nextDraw(s: Pick<LotteryState, "drawAt" | "drawn">): number {
  return s.drawn ? s.drawAt + 86400 : s.drawAt;
}

/** h:mm:ss (or m:ss under an hour) until [target] seconds from [now] seconds; 0:00 once past. */
export function countdown(target: number, now: number): string {
  const left = Math.max(0, Math.floor(target - now));
  const h = Math.floor(left / 3600);
  const m = Math.floor((left % 3600) / 60);
  const s = left % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/** 2026-11-12 as 11月12日. */
export function shortDay(day: string): string {
  const [, m, d] = day.split("-").map(Number);
  return m && d ? `${m}月${d}日` : day;
}

/** Whether SHA-256(number + salt) is [hash]; null where the browser cannot hash. */
export async function verifyDraw(number: string, salt: string, hash: string): Promise<boolean | null> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return null;
  try {
    const digest = await subtle.digest("SHA-256", new TextEncoder().encode(number + salt));
    const hex = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
    return hex === hash.toLowerCase();
  } catch {
    return null;
  }
}

/** A three-digit number from what was typed: digits only, at most three; complete when it has three. */
export function cleanNumber(typed: string): string {
  return typed.replace(/[^0-9]/g, "").slice(0, 3);
}

// ---- the three number keys: a digit or "" each, and the key picked to change (null: the next empty one)

export type Picks = readonly [string, string, string];
export const NO_PICKS: Picks = ["", "", ""];

/** The key the next digit goes to: [at] when one is picked, else the first empty key; null when all are set. */
export function pickTarget(picks: Picks, at: number | null): number | null {
  if (at !== null) return at;
  const i = picks.indexOf("");
  return i < 0 ? null : i;
}

/** [picks] with digit [d] put on the target key, and that key; unchanged with null when there is no target. */
export function putDigit(picks: Picks, at: number | null, d: string): { picks: Picks; key: number | null } {
  const key = pickTarget(picks, at);
  if (key === null) return { picks, key };
  const next: [string, string, string] = [...picks];
  next[key] = d;
  return { picks: next, key };
}

/** [picks] with the picked key cleared, or else the rightmost one set. */
export function dropDigit(picks: Picks, at: number | null): Picks {
  let key = at ?? -1;
  if (at === null) for (let i = 2; i >= 0 && key < 0; i--) if (picks[i]) key = i;
  if (key < 0) return picks;
  const next: [string, string, string] = [...picks];
  next[key] = "";
  return next;
}

/** One digit up or down, round from 9 to 0; an empty key starts at 0 going up and at 9 going down. */
export function stepDigit(d: string, by: 1 | -1): string {
  if (!d) return by > 0 ? "0" : "9";
  return String((Number(d) + by + 10) % 10);
}

/** The number on the pick key: the digits picked, "_" for each key still blank. */
export function pickLabel(picks: Picks): string[] {
  return picks.map((d) => d || "_");
}

/** The number on the keys once all three are set. */
export function pickedNumber(picks: Picks): string | null {
  return picks.every((d) => d !== "") ? picks.join("") : null;
}

/** The day before [day] (YYYY-MM-DD). */
export function dayBefore(day: string): string {
  const t = Date.parse(`${day}T00:00:00Z`);
  return Number.isNaN(t) ? "" : new Date(t - 86400000).toISOString().slice(0, 10);
}

// ---- the draw revealed once: the day of the last draw whose reveal has played, kept on this machine

const SEEN_KEY = "asoultappo.lotterySeen.v1";

export function seenDraw(): string {
  try {
    return localStorage.getItem(SEEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function markDrawSeen(day: string): void {
  try {
    localStorage.setItem(SEEN_KEY, day);
  } catch {
    // Storage blocked: the reveal plays again next time.
  }
}
