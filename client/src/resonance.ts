// One pool for every member. Shared cards keep a single collectible id.
import { collectible, type Item } from "./items";
import type { Rarity } from "./manifest";
import { economy } from "./stores/economy";

export type ResonancePool = Record<Rarity, Item[]>;
export function poolOf(): ResonancePool {
  const pool: ResonancePool = { legendary: [], skin: [], epic: [], rare: [], uncommon: [], common: [] };
  for (const item of collectible) if (item.rarity) pool[item.rarity].push(item);
  return pool;
}

const NO_RATES: Record<Rarity, number> = { legendary: 0, skin: 0, epic: 0, rare: 0, uncommon: 0, common: 0 };

/**
 * A tier with nothing left to find gives its odds to common, unless it keeps rolling repeats (the server does the same).
 * All zero until the server's economy is known.
 */
export function effectiveRates(pool: ResonancePool, owned: Record<string, number>): Record<Rarity, number> {
  const res = economy.value?.resonance;
  if (!res) return { ...NO_RATES };
  const rates = { ...res.rates };
  const repeating = new Set(res.repeatTiers ?? []);
  for (const rarity of ["legendary", "skin", "epic", "rare", "uncommon"] as const) {
    if (!repeating.has(rarity) && !pool[rarity].some((item) => !owned[item.id])) {
      rates.common += rates[rarity];
      rates[rarity] = 0;
    }
  }
  return rates;
}

export function commonKindRates(pool: ResonancePool, owned: Record<string, number>): { card: number; emote: number } {
  const weights = economy.value?.resonance.commonKindWeights;
  if (!weights) return { card: 0, emote: 0 };
  const card = pool.common.some((item) => item.kind === "card") ? weights.card : 0;
  const emote = pool.common.some((item) => item.kind === "emote") ? weights.emote : 0;
  const common = effectiveRates(pool, owned).common;
  return { card: common * card / (card + emote), emote: common * emote / (card + emote) };
}
