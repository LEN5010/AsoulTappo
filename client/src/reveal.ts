// Order and pacing of a draw's results. Pure, so the scene only has to play them back.
import type { Rarity } from "./manifest";

export interface Revealed {
  rarity: Rarity;
  item: string;
  new: boolean;
}

const ORDER: Rarity[] = ["legendary", "skin", "epic", "rare", "uncommon", "common"];
const rank = (d: Revealed) => ORDER.indexOf(d.rarity);

/** Results for the summary: rarest first, then new before duplicates, otherwise in draw order. */
export function sortDrops<T extends Revealed>(drops: readonly T[]): T[] {
  return [...drops].sort((a, b) => rank(a) - rank(b) || Number(b.new) - Number(a.new));
}

/** One tile per item, so a big batch is not a wall of repeats. `got` is how many landed in this batch. */
export function groupDrops<T extends Revealed & { item: string; count: number; shards: number }>(
  drops: readonly T[],
): (T & { got: number })[] {
  const groups = new Map<string, T & { got: number }>();
  for (const d of drops) {
    const seen = groups.get(d.item);
    if (seen) {
      seen.got += 1;
      seen.count = Math.max(seen.count, d.count);
      seen.shards += d.shards;
      seen.new ||= d.new;
    } else {
      groups.set(d.item, { ...d, got: 1 });
    }
  }
  return [...groups.values()];
}

/** Single cards/skins get a spotlight; batches highlight legendary, skin and epic. */
export function spotlightQueue<T extends Revealed>(drops: readonly T[]): T[] {
  if (drops.length === 1) return drops.filter((d) => d.item.startsWith("card:") || d.item.startsWith("char:"));
  return sortDrops(drops).filter((d) => ["legendary", "skin", "epic"].includes(d.rarity));
}

/** Single emotes go straight to the summary. */
export const needsSummary = (drops: readonly Revealed[]) => drops.length > 1 || spotlightQueue(drops).length === 0;
