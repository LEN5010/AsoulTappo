import { expect, it } from "vitest";
import { manifest } from "./manifest";
import { craftCost, getItem, ownsCharacter } from "./items";
import { commonKindRates, effectiveRates, poolOf } from "./resonance";

it("builds one all-member pool with 549 distinct items", () => {
  const p = poolOf();
  expect([p.common.length,p.uncommon.length,p.rare.length,p.epic.length,p.legendary.length,p.skin.length]).toEqual([372,75,60,23,10,9]);
  expect(new Set(Object.values(p).flat().map((i) => i.id)).size).toBe(549);
});
it("allocates 45 percent to common cards and 41.2 percent to ordinary emotes", () => {
  const p = poolOf();
  const owned = Object.fromEntries(p.common.filter((i) => i.kind === "card").map((i) => [i.id, 1]));
  for (const items of [{}, owned]) {
    const rates = commonKindRates(p, items);
    expect(rates.card).toBeCloseTo(45);
    expect(rates.emote).toBeCloseTo(41.2);
  }
  for (const tier of ["legendary", "skin", "epic", "rare", "uncommon"] as const) {
    for (const item of p[tier]) owned[item.id] = 1;
  }
  expect(commonKindRates(p, owned).card).toBeCloseTo(100 * 45 / 86.2);
  expect(commonKindRates(p, owned).emote).toBeCloseTo(100 * 41.2 / 86.2);
});
it("moves exactly the completed tier weights into common and keeps the total at 100", () => {
  const p = poolOf();
  for (const tier of ["legendary", "skin", "epic", "rare", "uncommon"] as const) {
    const owned = Object.fromEntries(p[tier].map((i) => [i.id, 1]));
    const rates = effectiveRates(p, owned);
    expect(rates[tier]).toBe(0);
    expect(rates.common).toBeCloseTo(86.2 + manifest.economy.resonance.rates[tier]);
    expect(Object.values(rates).reduce((a, b) => a + b)).toBeCloseTo(100);
  }
});
it("includes shared member cards exactly once", () => {
  const shared = manifest.cards.filter((c) => c.characters.length === 2);
  expect(shared).toHaveLength(3);
  for (const c of shared) {
    expect(Object.values(poolOf()).flat().filter((i) => i.id === `card:${c.id}`)).toHaveLength(1);
  }
});
it("original members are owned and skin ownership comes from collection", () => {
  for (const m of manifest.characters) expect(ownsCharacter(m.name, {})).toBe(true);
  for (const s of manifest.skins) {
    expect(ownsCharacter(s.name, {})).toBe(false);
    expect(ownsCharacter(s.name, { [`char:${s.name}`]: 1 })).toBe(true);
    expect(craftCost(getItem(`char:${s.name}`)!)).toBeNull();
  }
  expect(craftCost(getItem(`card:${manifest.cards.find((c) => c.rarity === "common")!.id}`)!)).toBe(480);
});
