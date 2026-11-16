import { expect, it } from "vitest";
import { getCard, manifest } from "./manifest";
import { craftCost, getItem, ownsCharacter } from "./items";
import { baseRates, commonKindRates, effectiveRates, poolOf } from "./resonance";
import { economy, setEconomy } from "./stores/economy";
import { exampleEconomy } from "./test/economy";

const R = exampleEconomy.resonance.rates;
const W = exampleEconomy.resonance.commonKindWeights;

it("builds one all-member pool with 590 distinct items", () => {
  const p = poolOf();
  expect([p.common.length,p.uncommon.length,p.rare.length,p.limited.length,p.epic.length,p.legendary.length,p.skin.length])
    .toEqual([372,75,60,36,23,10,14]);
  expect(new Set(Object.values(p).flat().map((i) => i.id)).size).toBe(590);
  // Holo versions come from their card's draws, never from a tier of the pool.
  expect(Object.values(p).flat().some((i) => i.id.startsWith("holo:"))).toBe(false);
  expect(p.limited.every((i) => i.kind === "card" && getCard(i.ref)?.series.startsWith("wardrobe-"))).toBe(true);
  // the economy names no craft price for them
  expect(p.limited.map(craftCost).every((c) => c === null)).toBe(true);
});
it("splits common between cards and ordinary emotes by their weights", () => {
  const p = poolOf();
  const owned = Object.fromEntries(p.common.filter((i) => i.kind === "card").map((i) => [i.id, 1]));
  for (const items of [{}, owned]) {
    const rates = commonKindRates(p, items);
    expect(rates.card).toBeCloseTo(R.common * W.card / (W.card + W.emote));
    expect(rates.emote).toBeCloseTo(R.common * W.emote / (W.card + W.emote));
  }
  for (const tier of ["legendary", "skin", "epic", "rare", "uncommon", "limited"] as const) {
    for (const item of p[tier]) owned[item.id] = 1;
  }
  // The hidden tier keeps its odds for repeats; the other completed tiers go to common.
  const common = 100 - R.epic;
  expect(commonKindRates(p, owned).card).toBeCloseTo(common * W.card / (W.card + W.emote));
  expect(commonKindRates(p, owned).emote).toBeCloseTo(common * W.emote / (W.card + W.emote));
});
it("moves exactly the completed tier weights into common and keeps the total at 100", () => {
  const p = poolOf();
  for (const tier of ["legendary", "skin", "rare", "uncommon", "limited"] as const) {
    const owned = Object.fromEntries(p[tier].map((i) => [i.id, 1]));
    const rates = effectiveRates(p, owned);
    expect(rates[tier]).toBe(0);
    expect(rates.common).toBeCloseTo(R.common + economy.value!.resonance.rates[tier]!);
    expect(Object.values(rates).reduce((a, b) => a + b)).toBeCloseTo(100);
  }
});
it("keeps the hidden tier's odds once it is complete, for repeats", () => {
  const p = poolOf();
  const rates = effectiveRates(p, Object.fromEntries(p.epic.map((i) => [i.id, 1])));
  expect(rates.epic).toBe(economy.value!.resonance.rates.epic);
  expect(rates.common).toBeCloseTo(R.common);
});
it("gives the limited tier no odds on a server that does not name it", () => {
  const { limited, ...rest } = R;
  setEconomy({ ...exampleEconomy, resonance: { ...exampleEconomy.resonance, rates: { ...rest, common: R.common + limited! } } });
  try {
    expect(baseRates().limited).toBe(0);
    const rates = effectiveRates(poolOf(), {});
    expect(rates.limited).toBe(0);
    expect(rates.common).toBeCloseTo(R.common + limited!);
    expect(Object.values(rates).reduce((a, b) => a + b)).toBeCloseTo(100);
  } finally {
    setEconomy(exampleEconomy);
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
