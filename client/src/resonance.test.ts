import { expect, it } from "vitest";
import { manifest } from "./manifest";
import { craftCost, getItem, ownsCharacter } from "./items";
import { effectiveRates, poolOf } from "./resonance";

it("builds one all-member pool with 428 distinct items", () => {
  const p = poolOf();
  expect([p.common.length,p.rare.length,p.epic.length,p.legendary.length,p.skin.length]).toEqual([378,15,24,8,3]);
  expect(new Set(Object.values(p).flat().map((i) => i.id)).size).toBe(428);
});
it("moves exactly the completed tier weights into common and keeps the total at 100", () => {
  const p = poolOf();
  for (const tier of ["legendary", "skin", "epic", "rare"] as const) {
    const owned = Object.fromEntries(p[tier].map((i) => [i.id, 1]));
    const rates = effectiveRates(p, owned);
    expect(rates[tier]).toBe(0);
    expect(rates.common).toBe(89.5 + manifest.economy.resonance.rates[tier]);
    expect(Object.values(rates).reduce((a, b) => a + b)).toBe(100);
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
