// What a draw shows and in which order. Pure, so the scene only has to play it back.
import type { Rarity } from "./manifest";

export interface Revealed {
  rarity: Rarity;
  item: string;
  new: boolean;
  /** The card's holo version (镭射款): `new` is then the holo version's, `cardNew` the card's. */
  holo?: boolean;
  cardNew?: boolean;
}
type CardTier = "big" | "small" | "normal";

const ORDER: Rarity[] = ["legendary", "skin", "epic", "limited", "rare", "uncommon", "common"];
/** A holo version is worth what a limited card is (see BOARD_POINTS on the server), so it reads just after one. */
const rank = (d: Revealed) => (d.holo ? ORDER.indexOf("limited") + 0.5 : ORDER.indexOf(d.rarity));

/** Up to this many results are dealt one tile per draw. Bigger batches group repeats. */
export const DEAL_LIMIT = 10;

/** Rarest first, then new before duplicates, otherwise in draw order. */
export function sortDrops<T extends Revealed>(drops: readonly T[]): T[] {
  return [...drops].sort((a, b) => rank(a) - rank(b) || Number(b.new) - Number(a.new));
}

/** Two items in one: a holo draw and a plain draw of the same card are tiles of their own. */
export const dropKey = (d: Revealed) => (d.holo ? `holo:${d.item}` : d.item);

/** Items a batch adds to the collection: a holo draw can bring its card as well. */
export const newItems = (drops: readonly Revealed[]) =>
  drops.reduce((n, d) => n + Number(d.new) + Number(!!d.holo && !!d.cardNew), 0);

/** One tile per item, so a big batch is not a wall of repeats. `got` is how many landed in this batch. */
export function groupDrops<T extends Revealed & { count: number; shards: number }>(
  drops: readonly T[],
): (T & { got: number })[] {
  const groups = new Map<string, T & { got: number }>();
  for (const d of drops) {
    const key = dropKey(d);
    const seen = groups.get(key);
    if (seen) {
      seen.got += 1;
      seen.count = Math.max(seen.count, d.count);
      seen.shards += d.shards;
      seen.new ||= d.new;
      if (d.cardNew) seen.cardNew = true;
    } else {
      groups.set(key, { ...d, got: 1 });
    }
  }
  return [...groups.values()];
}

/** A dealt batch keeps draw order, like cards out of a pack. A grouped one is sorted for reading. */
export function boardOf<T extends Revealed & { count: number; shards: number }>(drops: readonly T[]): (T & { got: number })[] {
  return drops.length <= DEAL_LIMIT ? drops.map((d) => ({ ...d, got: 1 })) : groupDrops(sortDrops(drops));
}

/**
 * Results that take the whole scene when they turn over: hidden cards, skins, every card with a [video] (a repeat
 * too: it plays before it turns into shards), a first limited card, a first holo version.
 */
export function spotlights(drop: Revealed, tier?: CardTier, video = false): boolean {
  if (drop.rarity === "legendary" || drop.rarity === "skin" || tier === "big" || tier === "small") return true;
  if (drop.holo) return drop.new;
  if (video) return true;
  return drop.new && (drop.rarity === "epic" || drop.rarity === "limited") && drop.item.startsWith("card:");
}

/**
 * Face down until turned. A dealt batch (ten or fewer) seals everything behind the same back, so no
 * tile gives away what the others are. A grouped batch only seals what spotlights, the rare tier,
 * which is the animated emotes (face up they would start playing the moment they land), and holo
 * versions, which flash as they turn.
 */
export function sealed(drop: Revealed, grouped: boolean, tier?: CardTier, video = false): boolean {
  return grouped ? spotlights(drop, tier, video) || drop.rarity === "rare" || !!drop.holo : true;
}
