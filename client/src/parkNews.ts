// The server-wide news of big park wins (status `park.news`): which items this device has already shown, and the
// line a pet shows for each. Every running pet shows each item once.
import { getItem } from "./items";
import type { ParkNews } from "./net/api";

/** Ids kept per server; the server sends at most 5 items of the last 15 minutes, so this is plenty. */
export const SEEN_KEEP = 40;

/** The items not shown yet, oldest first. */
export function unseenNews(news: readonly ParkNews[] | undefined, seen: ReadonlySet<number>): ParkNews[] {
  return (news ?? []).filter((n) => Number.isInteger(n?.id) && !seen.has(n.id)).sort((a, b) => a.id - b.id);
}

/** [seen] with [ids] added, at most [keep] of the newest. */
export function rememberNews(seen: readonly number[], ids: readonly number[], keep = SEEN_KEEP): number[] {
  const all = [...new Set([...seen, ...ids])].sort((a, b) => a - b);
  return all.slice(Math.max(0, all.length - keep));
}

/** What a pet says of an item: who (may be empty), what happened, and the shards when there are some. */
export interface NewsLine { nick: string; text: string; shards: number | null }

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);

function itemName(item: unknown): string {
  if (typeof item !== "string") return "大奖";
  const found = getItem(item);
  if (found) return found.name;
  if (item.startsWith("char:")) return "皮肤";
  if (item.startsWith("card:")) return "大隐藏卡";
  return "大奖";
}

/** The line for one item; null for kinds this client does not know, which are skipped. */
export function newsLine(n: ParkNews): NewsLine | null {
  const nick = typeof n.nick === "string" ? n.nick : "";
  const shards = num(n.shards);
  switch (n.kind) {
    case "jackpot":
      return { nick, text: "刮中全服奖池", shards };
    case "scratch_big":
      return { nick, text: "刮中", shards };
    case "scratch_item":
      return { nick, text: `刮出${itemName(n.item)}`, shards: null };
    case "lottery_draw": {
      const number = typeof n.number === "string" || typeof n.number === "number" ? String(n.number).padStart(3, "0") : "";
      return { nick, text: number ? `每日夺宝开奖 ${number}` : "每日夺宝开奖", shards };
    }
    default:
      return null;
  }
}
