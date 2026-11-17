// One standing pool for every member, and the limited pools the server runs beside it (server/app/banners.py).
// Shared cards keep a single collectible id.
import { collectible, getItem, type Item } from "./items";
import type { Rarity } from "./manifest";
import { economy, type Banner } from "./stores/economy";

export type ResonancePool = Record<Rarity, Item[]>;
/** The standing pool, without [held]: the items a limited pool keeps to itself until it ends. */
export function poolOf(held?: ReadonlySet<string>): ResonancePool {
  const pool: ResonancePool = { legendary: [], skin: [], epic: [], limited: [], rare: [], uncommon: [], common: [] };
  for (const item of collectible) if (item.rarity && !held?.has(item.id)) pool[item.rarity].push(item);
  return pool;
}

/** Items out of the standing pool for now, as the server says. */
export function heldItems(): ReadonlySet<string> {
  return new Set(economy.value?.resonance.held);
}

/** Whether [id] can be found in a limited pool only for now: it is neither in the standing pool nor crafted. */
export function isHeld(id: string): boolean {
  return !!economy.value?.resonance.held?.includes(id);
}

/** The limited pools running at [now] (ms), soonest to end first. The server names them up to an hour early. */
export function runningBanners(now: number): Banner[] {
  const at = now / 1000;
  return (economy.value?.resonance.banners ?? []).filter((b) => b.start <= at && at < b.end).sort((a, b) => a.end - b.end);
}

/**
 * The pool to open for [id]: the running limited pool that features it, or the one that gives its tier odds when the
 * standing pool gives it none, else the standing pool ("").
 */
export function poolFor(id: string, now = Date.now()): string {
  const running = runningBanners(now);
  const featuring = running.find((b) => b.items.includes(id));
  if (featuring) return featuring.id;
  const rarity = getItem(id)?.rarity;
  if (!rarity || !economy.value || baseRates()[rarity] > 0) return "";
  return running.find((b) => (b.rates?.[rarity] ?? 0) > 0)?.id ?? "";
}

/** A banner's featured items this build knows, in the server's order. */
export function featuredItems(banner: Banner): Item[] {
  return banner.items.flatMap((id) => getItem(id) ?? []);
}

/** What is left of a banner at [now] (ms), for its countdown: days and hours, then hours and minutes. */
export function bannerLeft(banner: Banner, now: number): string {
  const minutes = Math.max(0, Math.ceil((banner.end * 1000 - now) / 60_000));
  const d = Math.floor(minutes / 1440);
  const h = Math.floor((minutes % 1440) / 60);
  if (d) return h ? `${d} 天 ${h} 小时` : `${d} 天`;
  return h ? `${h} 小时 ${minutes % 60} 分` : `${minutes} 分钟`;
}

const NO_RATES: Record<Rarity, number> = { legendary: 0, skin: 0, epic: 0, limited: 0, rare: 0, uncommon: 0, common: 0 };

/** The server's base rates; a tier it does not name (the limited tier on an older server) has none. */
export function baseRates(): Record<Rarity, number> {
  return { ...NO_RATES, ...economy.value?.resonance.rates };
}

/** The tiers a draw at [rates] can give: a tier at 0 (the limited tier where only a limited pool rates it) is out. */
export function tiersIn(rates: Record<Rarity, number>): Rarity[] {
  return (Object.keys(rates) as Rarity[]).filter((r) => rates[r] > 0);
}

/**
 * The standing pool as its page counts it: without [held], and without the tiers the server gives no odds there.
 * Before the server's economy is known nothing is left out.
 */
export function standingPool(held?: ReadonlySet<string>): ResonancePool {
  const pool = poolOf(held);
  if (!economy.value) return pool;
  const rates = baseRates();
  for (const r of Object.keys(pool) as Rarity[]) if (!(rates[r] > 0)) pool[r] = [];
  return pool;
}

/**
 * A tier with nothing left to find gives its odds to common, unless it keeps rolling repeats or is one of [kept]
 * (the server does the same). [from] are the odds before that, the standing pool's unless given. All zero until the
 * server's economy is known.
 */
export function effectiveRates(
  pool: ResonancePool, owned: Record<string, number>, from?: Record<Rarity, number>, kept?: ReadonlySet<Rarity>,
): Record<Rarity, number> {
  const res = economy.value?.resonance;
  if (!res) return { ...NO_RATES };
  const rates = { ...(from ?? baseRates()) };
  const repeating = new Set(res.repeatTiers ?? []);
  for (const rarity of ["legendary", "skin", "epic", "limited", "rare", "uncommon"] as const) {
    if (!repeating.has(rarity) && !kept?.has(rarity) && !pool[rarity].some((item) => !owned[item.id])) {
      rates.common += rates[rarity];
      rates[rarity] = 0;
    }
  }
  rates.common = +rates.common.toFixed(6);
  return rates;
}

/** The odds of a draw from [banner] by tier, before anything drops out: its own where it names them. */
export function bannerBaseRates(banner: Banner): Record<Rarity, number> {
  const rates = baseRates();
  if (!banner.rates) return rates;
  Object.assign(rates, banner.rates);
  const others = Object.entries(rates).reduce((sum, [tier, rate]) => (tier === "common" ? sum : sum + rate), 0);
  rates.common = +Math.max(0, 100 - others).toFixed(6);
  return rates;
}

/**
 * The odds of a draw from [banner] (the server does the same). `tiers`: the banner's odds; a tier with a featured
 * item left to find under `share` stays in the roll. `featured`: the featured tier's own `rate`, taken from common
 * while the save lacks one of its items. `shared`: the current chance that a draw in each shared tier is featured.
 */
export function bannerRates(
  banner: Banner, pool: ResonancePool, owned: Record<string, number>,
): { featured: number; tiers: Record<Rarity, number>; shared: { rarity: Rarity; rate: number }[] } {
  const left = featuredItems(banner).filter((item) => !owned[item.id]);
  const share = banner.share ?? 0;
  const sharedTiers = new Set(share ? left.flatMap((item) => item.rarity ?? []) : []);
  const tiers = effectiveRates(pool, owned, bannerBaseRates(banner), sharedTiers);
  if (!economy.value || !left.length) return { featured: 0, tiers, shared: [] };
  const repeats = economy.value.resonance.repeatTiers;
  const shared = [...sharedTiers].map((rarity) => ({
    rarity,
    rate: repeats?.includes(rarity) || pool[rarity].some((item) => !owned[item.id]) ? share : 100,
  }));
  const featured = Math.min(banner.rate ?? 0, tiers.common);
  tiers.common = +(tiers.common - featured).toFixed(6);
  return { featured, tiers, shared };
}

export function commonKindRates(pool: ResonancePool, owned: Record<string, number>): { card: number; emote: number } {
  const weights = economy.value?.resonance.commonKindWeights;
  if (!weights) return { card: 0, emote: 0 };
  const card = pool.common.some((item) => item.kind === "card") ? weights.card : 0;
  const emote = pool.common.some((item) => item.kind === "emote") ? weights.emote : 0;
  const common = effectiveRates(pool, owned).common;
  return { card: common * card / (card + emote), emote: common * emote / (card + emote) };
}
