// Order and pacing of a draw's results. Pure, so the scene only has to play them back.
import type { Rarity } from "./manifest";

export interface Revealed {
  rarity: Rarity;
  item: string;
  new: boolean;
  tier?: "big" | "small" | "normal";
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

/** Reveal every result in draw order, including duplicates and emotes. */
export function spotlightQueue<T extends Revealed>(drops: readonly T[]): T[] {
  return [...drops];
}

export const needsSummary = (drops: readonly Revealed[]) => drops.length > 1;

/** Fast-forward ordinary results; hidden cards and skins keep their reveal. */
export function nextRevealIndex(drops: readonly Revealed[], start: number, highlightsOnly: boolean): number {
  for (let i = start; i < drops.length; i++) {
    const drop = drops[i]!;
    if (!highlightsOnly || drop.rarity === "skin" || drop.tier === "big" || drop.tier === "small" || drop.rarity === "legendary") return i;
  }
  return -1;
}
