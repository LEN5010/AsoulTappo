// The save's own coin ledger and redeem history (protocol/PROTOCOL.md 驼币, GET /api/park/ledger): the answer's
// shape, the words for each ledger source, and the sums and dates the sheet shows.
import { parkTry } from "../../stores/park";

export interface LedgerItem { source: string; amount: number; count: number }
export interface LedgerDay { day: string; items: LedgerItem[] }
export interface RedeemEntry { code: string; ts: number; shards: number; coins: number }
export interface Ledger { days: LedgerDay[]; redeems: RedeemEntry[] }

/** Each source in the coin ledger, in the park's own words. */
const SOURCES: Record<string, string> = {
  buy: "购买",
  gift: "每日赠送",
  redeem: "兑换码",
  stamp: "集章",
  scratch_again: "再来一张",
  race_prize: "赛跑奖金",
  race_refund: "赛跑退回",
  admin: "调整",
  scratch: "刮刮乐",
  race: "赛跑",
  lottery: "夺宝",
};

/** A source's words; a source newer than this client gets a generic one. */
export function sourceLabel(source: string): string {
  return SOURCES[source] ?? "其他";
}

/** Gains first, largest first, then spending, largest first. */
export function sortItems(items: readonly LedgerItem[]): LedgerItem[] {
  return [...items].sort((a, b) => (a.amount > 0) === (b.amount > 0) ? Math.abs(b.amount) - Math.abs(a.amount) : b.amount - a.amount);
}

export function dayNet(day: LedgerDay): number {
  return day.items.reduce((sum, i) => sum + i.amount, 0);
}

/** +12, −12 (a true minus), 0. */
export function signed(n: number): string {
  const f = (v: number) => v.toLocaleString("en-US");
  return n > 0 ? `+${f(n)}` : n < 0 ? `−${f(-n)}` : "0";
}

/** China time (UTC+8), as the server's days. */
const CHINA = 8 * 3600;

/** The China day (YYYY-MM-DD) of [ts] Unix seconds. */
export function chinaDay(ts: number): string {
  return new Date((ts + CHINA) * 1000).toISOString().slice(0, 10);
}

/** The answer, or the line saying why it did not come. */
export async function loadLedger(): Promise<{ ok: true; data: Ledger } | { ok: false; message: string }> {
  const r = await parkTry<Ledger>("GET", "/api/park/ledger");
  if (r.ok) return { ok: true, data: { days: r.data.days ?? [], redeems: r.data.redeems ?? [] } };
  return { ok: false, message: (r.error.status && r.error.message) || "无法连接服务器" };
}
