// The save's own drops as the resonance page's record lists them (panel/HistoryDialog.vue): each drop of
// GET /api/resonance/history as a row, and the rows by the day they came on (this machine's time).
import { getItem, RARITY_LABEL, type Item } from "./items";
import type { Rarity } from "./manifest";
import type { HistoryDrop } from "./net/api";

export interface HistoryRow {
  id: number;
  /** The item; for a holo version, the card it is of. */
  item: Item;
  holo: boolean;
  fresh: boolean;
  ts: number;
  /** The tier's name: 普通 … 大隐藏, 皮肤. */
  tier: string;
  rarity: Rarity | null;
  /** Where it came from when that is not the standing pool: a limited pool's name, 兑换, 刮刮乐. */
  from: string;
}

const SOURCES: Record<string, string> = { craft: "兑换", scratch: "刮刮乐" };

/** The rows of a page, in its order. A drop this client's catalog does not know is left out. */
export function rowsOf(drops: readonly HistoryDrop[]): HistoryRow[] {
  return drops.flatMap((d) => {
    const holo = d.item.startsWith("holo:");
    const item = getItem(holo ? `card:${d.item.slice(5)}` : d.item);
    if (!item) return [];
    const rarity = item.rarity ?? (d.rarity in RARITY_LABEL ? (d.rarity as Rarity) : null);
    return [{
      id: d.id, item, holo, fresh: d.new, ts: d.ts, rarity,
      tier: rarity ? RARITY_LABEL[rarity] : "",
      from: d.pool ? d.poolName || "限定卡池" : SOURCES[d.source ?? ""] ?? "",
    }];
  });
}

const two = (n: number) => String(n).padStart(2, "0");
/** The local day of [ts] Unix seconds: YYYY-MM-DD. */
export function dayKey(ts: number): string {
  const d = new Date(ts * 1000);
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`;
}
/** The local time of day of [ts] Unix seconds: HH:MM. */
export function clockOf(ts: number): string {
  const d = new Date(ts * 1000);
  return `${two(d.getHours())}:${two(d.getMinutes())}`;
}
/** A day as the list heads it at [now] (ms): 今日, 昨日, 11月5日, and with its year when that is not this one. */
export function dayLabel(key: string, now: number): string {
  if (key === dayKey(now / 1000)) return "今日";
  const before = new Date(now);
  before.setDate(before.getDate() - 1);
  if (key === dayKey(before.getTime() / 1000)) return "昨日";
  const [y, m, d] = key.split("-").map(Number);
  return `${y === new Date(now).getFullYear() ? "" : `${y}年`}${m}月${d}日`;
}

export interface HistoryDay { key: string; label: string; rows: HistoryRow[] }
/** [rows] (newest first) under the days they came on. */
export function byDay(rows: readonly HistoryRow[], now: number): HistoryDay[] {
  const days: HistoryDay[] = [];
  for (const row of rows) {
    const key = dayKey(row.ts);
    const last = days.at(-1);
    if (last?.key === key) last.rows.push(row);
    else days.push({ key, label: dayLabel(key, now), rows: [row] });
  }
  return days;
}
