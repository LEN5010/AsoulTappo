// Tap income (protocol/PROTOCOL.md): shards follow a curve over the taps a China day counts that nears
// the daily cap and never passes it. The server pays; the client only shows it.
import { manifest } from "./manifest";
import type { PlayerStatus } from "./net/api";

/** Shards `taps` counted taps earn over one day. */
export function tapShards(taps: number): number {
  const { dailyCap, curve: [a, b, c] } = manifest.economy.income;
  const m = taps / 1000;
  return -dailyCap * Math.expm1(-(a * m + b * m * m + c * m * m * m));
}

export interface TodayIncome { today: number; cap: number; perTap: number }

/** Today's tap income; null on servers without tap income. */
export function todayIncome(status: PlayerStatus | null | undefined): TodayIncome | null {
  const inc = status?.income;
  if (!inc || typeof inc.today !== "number" || typeof inc.cap !== "number") return null;
  return { today: inc.today, cap: inc.cap, perTap: inc.perTap ?? 0 };
}

const count = new Intl.NumberFormat("en-US");
export const formatCount = (n: number): string => count.format(n);

/** What the next tap pays, or that today is full. */
export function nextTapText(income: TodayIncome): string {
  const p = income.perTap;
  return p > 0 ? `敲一下 +${p.toFixed(p >= 1 ? 1 : 2)}` : "今日已满";
}

/** One line for a tooltip; undefined on servers without tap income. */
export function incomeTip(status: PlayerStatus | null | undefined): string | undefined {
  const income = todayIncome(status);
  return income ? `今日已获得 ${formatCount(income.today)} · ${nextTapText(income)}` : undefined;
}
