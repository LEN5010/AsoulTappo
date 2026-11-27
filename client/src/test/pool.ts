import { manifest } from "../manifest";
import type { Rarity } from "../manifest";

// Non-starter emotes per tier of the pool. They change only with a new emote set; cards and skins are counted from
// the manifest, so adding a skin or a card needs no change in the tests.
const POOL_EMOTES: Partial<Record<Rarity, number>> = { common: 320, uncommon: 120, rare: 60 };

/** The size of each tier of the resonance pool, counted from the manifest's cards and skins. */
export function realPoolCounts(): Record<Rarity, number> {
  const counts: Record<Rarity, number> = { legendary: 0, skin: 0, epic: 0, limited: 0, rare: 0, uncommon: 0, common: 0 };
  for (const [rarity, n] of Object.entries(POOL_EMOTES)) counts[rarity as Rarity] += n;
  for (const card of manifest.cards) counts[card.rarity] += 1;
  counts.skin = manifest.skins.length;
  return counts;
}

export const realPoolSize = () => Object.values(realPoolCounts()).reduce((a, b) => a + b, 0);
