import { expect, it } from "vitest";
import { getCard, manifest } from "./manifest";
import { craftCost, getItem, ownsCharacter } from "./items";
import { bannerBaseRates, bannerLeft, bannerRates, baseRates, commonKindRates, effectiveRates, featuredItems, heldItems, isHeld, poolFor, poolOf, runningBanners, standingPool, tiersIn } from "./resonance";
import { economy, setEconomy } from "./stores/economy";
import { exampleEconomy } from "./test/economy";
import { realPoolCounts, realPoolSize } from "./test/pool";

const R = exampleEconomy.resonance.rates;
const W = exampleEconomy.resonance.commonKindWeights;

it("builds one all-member pool of distinct items", () => {
  const p = poolOf();
  expect(Object.fromEntries(Object.entries(p).map(([r, items]) => [r, items.length]))).toEqual(realPoolCounts());
  expect(new Set(Object.values(p).flat().map((i) => i.id)).size).toBe(realPoolSize());
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

// ---- limited pools
const T0 = Date.UTC(2026, 10, 21, 4);
const SKINS = ["char:嘉然然龙", "char:乃琳法师"];
const BANNER = { id: "forms", name: "双形态", start: T0 / 1000, end: T0 / 1000 + 7 * 86400, items: SKINS, rate: 5, pity: 90 };
function withBanner(run: () => void) {
  setEconomy({ ...exampleEconomy, resonance: { ...exampleEconomy.resonance, banners: [BANNER], held: SKINS } });
  try { run(); } finally { setEconomy(exampleEconomy); }
}
it("keeps what a limited pool holds out of the standing pool and out of crafting", () => {
  withBanner(() => {
    const p = poolOf(heldItems());
    expect(p.skin).toHaveLength(poolOf().skin.length - SKINS.length);
    expect(Object.values(p).flat().some((i) => SKINS.includes(i.id))).toBe(false);
    expect(isHeld(SKINS[0]!)).toBe(true);
    const card = poolOf().common.find((i) => i.kind === "card")!;
    expect(craftCost(card)).not.toBeNull();
    setEconomy({ ...exampleEconomy, resonance: { ...exampleEconomy.resonance, held: [card.id] } });
    expect(craftCost(card)).toBeNull();
  });
  expect(heldItems().size).toBe(0);
});
it("keeps a tier at 0 out of the standing pool and sends its cards to the banner that rates it", () => {
  const rates = { ...R, limited: 0, common: R.common + R.limited! };
  const banner = { ...BANNER, rates: { limited: 5 } };
  setEconomy({ ...exampleEconomy, resonance: { ...exampleEconomy.resonance, rates, banners: [banner] } });
  try {
    const card = poolOf().limited[0]!;
    expect(standingPool().limited).toEqual([]);
    expect(standingPool().common.length).toBe(poolOf().common.length);
    expect(tiersIn(baseRates())).not.toContain("limited");
    expect(tiersIn(bannerBaseRates(banner))).toContain("limited");
    expect(poolFor(card.id, T0)).toBe("forms");
    // No banner running: nowhere but the standing pool to send it.
    expect(poolFor(card.id, T0 - 1)).toBe("");
  } finally {
    setEconomy(exampleEconomy);
  }
  // At the example's own odds the tier is in the standing pool.
  expect(standingPool().limited.length).toBe(poolOf().limited.length);
  expect(poolFor(poolOf().limited[0]!.id, T0)).toBe("");
});
it("runs a banner between its start and its end", () => {
  withBanner(() => {
    expect(runningBanners(T0 - 1)).toEqual([]);
    expect(runningBanners(T0).map((b) => b.id)).toEqual(["forms"]);
    expect(runningBanners(T0 + 7 * 86400_000)).toEqual([]);
    expect(poolFor(SKINS[1]!, T0)).toBe("forms");
    expect(poolFor(SKINS[1]!, T0 - 1)).toBe("");
    expect(poolFor("char:嘉然山海经", T0)).toBe("");
    expect(featuredItems(BANNER).map((i) => i.name)).toEqual(["嘉然然龙", "乃琳法师"]);
  });
});
it("counts a banner's time down in days, hours and minutes", () => {
  const end = BANNER.end * 1000;
  expect(bannerLeft(BANNER, T0)).toBe("7 天");
  expect(bannerLeft(BANNER, end - (6 * 24 + 13) * 3600_000 + 60_000)).toBe("6 天 12 小时");
  expect(bannerLeft(BANNER, end - 5 * 3600_000)).toBe("5 小时 0 分");
  expect(bannerLeft(BANNER, end - 90_000)).toBe("2 分钟");
  expect(bannerLeft(BANNER, end + 1)).toBe("0 分钟");
});
it("takes a banner's rate from common until the save has every featured item", () => {
  withBanner(() => {
    const p = poolOf(heldItems());
    const { featured, tiers } = bannerRates(BANNER, p, {});
    expect(featured).toBe(5);
    expect(tiers.common).toBeCloseTo(R.common - 5);
    expect(featured + Object.values(tiers).reduce((a, b) => a + b)).toBeCloseTo(100);
    const whole = bannerRates(BANNER, p, Object.fromEntries(SKINS.map((id) => [id, 1])));
    expect(whole.featured).toBe(0);
    expect(whole.tiers.common).toBeCloseTo(R.common);
  });
});
it("reads a banner's own odds and the tiers its featured items share", () => {
  withBanner(() => {
    const { rate: _rate, ...plain } = BANNER;
    const shared = { ...plain, rates: { skin: 3, limited: 5 }, share: 40 };
    const base = bannerBaseRates(shared);
    expect(base.skin).toBe(3);
    expect(base.limited).toBe(5);
    expect(Object.values(base).reduce((a, b) => a + b)).toBeCloseTo(100);
    const p = poolOf(heldItems());
    expect(bannerRates(shared, p, {}).shared).toEqual([{ rarity: "skin", rate: 40 }]);
    // Every standing skin found: the tier stays for the featured ones.
    const owned = Object.fromEntries(p.skin.map((i) => [i.id, 1]));
    const now = bannerRates(shared, p, owned);
    expect(now.featured).toBe(0);
    expect(now.shared).toEqual([{ rarity: "skin", rate: 100 }]);
    expect(now.tiers.skin).toBe(3);
    for (const id of SKINS) owned[id] = 1;
    const whole = bannerRates(shared, p, owned);
    expect(whole.shared).toEqual([]);
    expect(whole.tiers.skin).toBe(exampleEconomy.resonance.repeatTiers?.includes("skin") ? 3 : 0);
  });
});
