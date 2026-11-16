// What the dou dizhu table works out for itself: where the cards of a hand lie, which card a pointer is on, what a
// rank key picks, and the order a play is laid out in. No state: panel/ddz/DdzTable.vue holds it.
import { rank } from "./rules";

/** A row of [n] overlapping cards [w] wide in [avail] px: the step between cards and the row's width. */
export function fan(n: number, avail: number, w: number, maxStep: number): { step: number; width: number } {
  if (n <= 1) return { step: 0, width: n ? w : 0 };
  const step = Math.max(6, Math.min(maxStep, (avail - w) / (n - 1)));
  return { step, width: step * (n - 1) + w };
}

/**
 * The card under [x] (px from the row's left edge) in a row of [n] cards laid [step] apart: every card but the last
 * shows only its left strip. -1 outside the row.
 */
export function cardAt(x: number, n: number, step: number, w: number): number {
  if (n === 0 || x < 0 || x > step * (n - 1) + w) return -1;
  return step > 0 ? Math.min(n - 1, Math.floor(x / step)) : 0;
}

/**
 * A rank key pressed: one more card of rank [r] joins the selection, and once all of them are in, they all leave.
 * [hand] is held highest first, so the cards of a rank are picked in the order they lie.
 */
export function pickRank(hand: readonly number[], selected: ReadonlySet<number>, r: number): Set<number> {
  const out = new Set(selected);
  const mine = hand.filter((c) => rank(c) === r);
  const next = mine.find((c) => !out.has(c));
  if (next !== undefined) out.add(next);
  else for (const c of mine) out.delete(c);
  return out;
}

/** The jokers' key: the small one, then the big one, then neither. */
export function pickJokers(hand: readonly number[], selected: ReadonlySet<number>): Set<number> {
  const out = new Set(selected);
  const mine = [52, 53].filter((c) => hand.includes(c));
  const next = mine.find((c) => !out.has(c));
  if (next !== undefined) out.add(next);
  else for (const c of mine) out.delete(c);
  return out;
}

/** The rank a key picks: 3 to 9, 0 for ten, J Q K A, and 2; null for any other key. */
export function rankOfKey(key: string): number | null {
  if (key.length !== 1) return null;
  if (key >= "3" && key <= "9") return Number(key);
  return ({ "0": 10, j: 11, q: 12, k: 13, a: 14, "2": 15 } as Record<string, number>)[key.toLowerCase()] ?? null;
}

/**
 * A play as it is laid on the table: the ranks held most first (the trios of a plane before what they carry), then
 * from the highest rank down.
 */
export function arrange(cards: readonly number[]): number[] {
  const count = new Map<number, number>();
  for (const c of cards) count.set(rank(c), (count.get(rank(c)) ?? 0) + 1);
  return [...cards].sort((a, b) => count.get(rank(b))! - count.get(rank(a))! || rank(b) - rank(a) || a - b);
}
