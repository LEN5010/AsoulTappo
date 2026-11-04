// One pool for every member. Shared cards keep a single collectible id.
import { collectible, type Item } from "./items";
import { manifest, type Rarity } from "./manifest";

export type ResonancePool = Record<Rarity, Item[]>;
export function poolOf(): ResonancePool {
  const pool: ResonancePool = { legendary: [], skin: [], epic: [], rare: [], uncommon: [], common: [] };
  for (const item of collectible) if (item.rarity) pool[item.rarity].push(item);
  return pool;
}

export function effectiveRates(pool: ResonancePool, owned: Record<string, number>): Record<Rarity, number> {
  const rates = { ...manifest.economy.resonance.rates };
  for (const rarity of ["legendary", "skin", "epic", "rare", "uncommon"] as const) {
    if (!pool[rarity].some((item) => !owned[item.id])) {
      rates.common += rates[rarity];
      rates[rarity] = 0;
    }
  }
  return rates;
}

export function commonKindRates(pool: ResonancePool, owned: Record<string, number>): { card: number; emote: number } {
  const weights = manifest.economy.resonance.commonKindWeights;
  const card = pool.common.some((item) => item.kind === "card") ? weights.card : 0;
  const emote = pool.common.some((item) => item.kind === "emote") ? weights.emote : 0;
  const common = effectiveRates(pool, owned).common;
  return { card: common * card / (card + emote), emote: common * emote / (card + emote) };
}
