// Order and pacing of a draw's results. Pure, so the scene only has to play them back.
import { TIER_RANK, type CardTier } from "./cards";

export interface Revealed {
  tier?: CardTier;
  new: boolean;
}

const rank = (d: Revealed) => TIER_RANK[d.tier ?? "normal"];

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

/** A single draw always gets the spotlight. In a batch only hidden cards do, rarest first. */
export function spotlightQueue<T extends Revealed>(drops: readonly T[]): T[] {
  if (drops.length === 1) return [...drops];
  return sortDrops(drops).filter((d) => d.tier === "big" || d.tier === "small");
}

/** A single draw ends on its spotlight, there is nothing left to sum up. */
export const needsSummary = (drops: readonly Revealed[]) => drops.length > 1;
