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
}

export interface LotteryBuy { lottery: LotteryState; bought: string[] }

/** How many trailing digits of a ticket of [tier] match the drawn number. */
export function matchedDigits(tier: LotteryTier | null): number {
  return tier === "top" ? 3 : tier === "second" ? 2 : tier === "third" ? 1 : 0;
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
