// What a draw shows and in which order. Pure, so the scene only has to play it back.
import type { Rarity } from "./manifest";

export interface Revealed {
  rarity: Rarity;
  item: string;
  new: boolean;
}
type CardTier = "big" | "small" | "normal";

const ORDER: Rarity[] = ["legendary", "skin", "epic", "rare", "uncommon", "common"];
const rank = (d: Revealed) => ORDER.indexOf(d.rarity);

/** Up to this many results are dealt one tile per draw. Bigger batches group repeats. */
export const DEAL_LIMIT = 10;

/** Rarest first, then new before duplicates, otherwise in draw order. */
export function sortDrops<T extends Revealed>(drops: readonly T[]): T[] {
  return [...drops].sort((a, b) => rank(a) - rank(b) || Number(b.new) - Number(a.new));
}

/** One tile per item, so a big batch is not a wall of repeats. `got` is how many landed in this batch. */
export function groupDrops<T extends Revealed & { count: number; shards: number }>(
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

/** A dealt batch keeps draw order, like cards out of a pack. A grouped one is sorted for reading. */
export function boardOf<T extends Revealed & { count: number; shards: number }>(drops: readonly T[]): (T & { got: number })[] {
  return drops.length <= DEAL_LIMIT ? drops.map((d) => ({ ...d, got: 1 })) : groupDrops(sortDrops(drops));
}

/** Results that take the whole scene when they turn over: hidden cards, skins, a first animated card. */
export function spotlights(drop: Revealed, tier?: CardTier): boolean {
  if (drop.rarity === "legendary" || drop.rarity === "skin" || tier === "big" || tier === "small") return true;
  return drop.new && drop.rarity === "epic" && drop.item.startsWith("card:");
}

/**
 * Face down until turned. A dealt batch (ten or fewer) seals everything behind the same back, so no
 * tile gives away what the others are. A grouped batch only seals what spotlights and the rare tier,
 * which is the animated emotes: face up they would start playing the moment they land.
 */
export function sealed(drop: Revealed, grouped: boolean, tier?: CardTier): boolean {
  return grouped ? spotlights(drop, tier) || drop.rarity === "rare" : true;
}
