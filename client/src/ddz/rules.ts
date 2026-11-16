// Dou dizhu (斗地主) hands: what a set of cards is and whether it beats another. The same rules as the server's
// ddz_rules.py, which decides; both are checked against rules.fixture.json, so the play key lights up for exactly the
// plays the server takes. Hints are the client's own.
//
// Cards are 0..53: floor(card / 4) + 3 is the rank for 0..51 (3..10, J=11, Q=12, K=13, A=14, 2=15) and card % 4 the
// suit (0 spade, 1 heart, 2 club, 3 diamond); 52 is the small joker (rank 16), 53 the big one (17).

export const SMALL_JOKER = 16;
export const BIG_JOKER = 17;
export const ACE = 14;

export type HandKind = "solo" | "pair" | "trio" | "bomb" | "rocket" | "trio1" | "trio2" | "straight" | "pairs" | "plane" |
  "plane1" | "plane2" | "four2" | "four22";
/** A reading of some cards: `size` trios, pairs or cards in the run (1 without one), `main` the rank compared. */
export interface Hand { kind: HandKind; size: number; main: number }

export const rank = (card: number): number => (card < 52 ? Math.floor(card / 4) + 3 : card - 36);
/** 0 spade, 1 heart, 2 club, 3 diamond; -1 for a joker. */
export const suit = (card: number): number => (card < 52 ? card % 4 : -1);
export const isRed = (card: number): boolean => card === 53 || suit(card) === 1 || suit(card) === 3;
const LABELS: Record<number, string> = { 11: "J", 12: "Q", 13: "K", 14: "A", 15: "2" };
export const rankLabel = (r: number): string => LABELS[r] ?? String(r);

/** A hand as it is held: highest rank first, suits in order within a rank. */
export const sortHand = (cards: readonly number[]): number[] => [...cards].sort((a, b) => rank(b) - rank(a) || a - b);

function counts(cards: readonly number[]): Map<number, number> {
  const count = new Map<number, number>();
  for (const c of cards) count.set(rank(c), (count.get(rank(c)) ?? 0) + 1);
  return count;
}

/** Top ranks of the runs of [size] ranks in a row, none past the ace, within [have]. */
function runs(have: readonly number[], size: number): number[] {
  const pool = new Set(have.filter((r) => r <= ACE));
  const out: number[] = [];
  for (const top of [...pool].sort((a, b) => a - b)) {
    let whole = true;
    for (let i = 0; i < size; i++) if (!pool.has(top - i)) { whole = false; break; }
    if (whole) out.push(top);
  }
  return out;
}

/** Every way to read [cards] as one hand; empty when they are none. */
export function classify(cards: readonly number[]): Hand[] {
  const rs = cards.map(rank).sort((a, b) => a - b);
  const n = rs.length;
  if (n === 0) return [];
  const count = counts(cards);
  const by = (k: number) => [...count].filter(([, c]) => c === k).map(([r]) => r).sort((a, b) => a - b);
  const distinct = count.size;
  const top = rs[n - 1];
  const out: Hand[] = [];

  if (n === 1) return [{ kind: "solo", size: 1, main: top }];
  if (n === 2) {
    if (rs[0] === SMALL_JOKER && rs[1] === BIG_JOKER) return [{ kind: "rocket", size: 1, main: BIG_JOKER }];
    return distinct === 1 ? [{ kind: "pair", size: 1, main: top }] : [];
  }
  if (n === 3) return distinct === 1 ? [{ kind: "trio", size: 1, main: top }] : [];
  if (n === 4 && distinct === 1) return [{ kind: "bomb", size: 1, main: top }];

  const twos = by(2), threes = by(3), fours = by(4);
  const wholeRun = top <= ACE && top - rs[0] === distinct - 1;
  if (distinct === n && n >= 5 && wholeRun) out.push({ kind: "straight", size: n, main: top });
  if (twos.length === distinct && distinct >= 3 && wholeRun) out.push({ kind: "pairs", size: distinct, main: top });
  if (threes.length === distinct && distinct >= 2 && wholeRun) out.push({ kind: "plane", size: distinct, main: top });

  // A trio, or trios in a row, with one other card each: 4 cards a trio.
  if (n % 4 === 0 && n / 4 >= 1 && n / 4 <= 5) {
    const size = n / 4;
    for (const t of size === 1 ? threes : runs(threes, size)) out.push({ kind: size === 1 ? "trio1" : "plane1", size, main: t });
  }
  // The same with a pair each: 5 cards a trio. What is left must be whole pairs, none of jokers.
  const wholePairs = (skip: (r: number) => boolean) =>
    [...count].every(([r, c]) => skip(r) || ((c === 2 || c === 4) && r < SMALL_JOKER));
  if (n % 5 === 0 && n / 5 >= 1 && n / 5 <= 4) {
    const size = n / 5;
    for (const t of size === 1 ? threes : runs(threes, size)) {
      if (wholePairs((r) => r > t - size && r <= t)) out.push({ kind: size === 1 ? "trio2" : "plane2", size, main: t });
    }
  }
  if (n === 6) for (const r of fours) out.push({ kind: "four2", size: 1, main: r });
  if (n === 8) for (const r of fours) if (wholePairs((x) => x === r)) out.push({ kind: "four22", size: 1, main: r });
  return out;
}

export function handBeats(a: Hand, b: Hand): boolean {
  if (a.kind === "rocket") return true;
  if (b.kind === "rocket") return false;
  if (a.kind === "bomb") return b.kind !== "bomb" || a.main > b.main;
  return a.kind === b.kind && a.size === b.size && a.main > b.main;
}

/** Whether [cards] may be played on [last]: some reading of the one beats some reading of the other. */
export function beats(cards: readonly number[], last: readonly number[]): boolean {
  const mine = classify(cards), theirs = classify(last);
  return mine.some((a) => theirs.some((b) => handBeats(a, b)));
}

/** Whether [cards] may be played now: a hand, and one that beats [last] unless the seat leads (null). */
export const playable = (cards: readonly number[], last: readonly number[] | null): boolean =>
  cards.length > 0 && (last ? beats(cards, last) : classify(cards).length > 0);

/** A bomb or the rocket: they double the stake. */
export const isBomb = (cards: readonly number[]): boolean => classify(cards).some((h) => h.kind === "bomb" || h.kind === "rocket");

// ------------------------------------------------------------------ hints
/** The hand's cards by rank, each rank's cards in order. */
function byRank(hand: readonly number[]): Map<number, number[]> {
  const out = new Map<number, number[]>();
  for (const c of [...hand].sort((a, b) => a - b)) {
    const r = rank(c);
    if (!out.has(r)) out.set(r, []);
    out.get(r)!.push(c);
  }
  return out;
}

/**
 * What a hint takes along with trios or fours: [n] single cards, or [n] pairs when [pairs], from ranks not in [skip].
 * Cards of ranks held least go first (a lone card before one of a pair, a pair before part of a trio), lowest rank
 * first; null when the hand has not enough.
 */
function along(held: Map<number, number[]>, skip: Set<number>, n: number, pairs: boolean): number[] | null {
  const ranks = [...held.keys()].filter((r) => !skip.has(r) && (!pairs || (r < SMALL_JOKER && held.get(r)!.length >= 2)))
    .sort((a, b) => held.get(a)!.length - held.get(b)!.length || a - b);
  const out: number[] = [];
  const each = pairs ? 2 : 1;
  for (const r of ranks) {
    const cards = held.get(r)!;
    for (let i = 0; i + each <= cards.length && out.length < n * each; i += each) out.push(...cards.slice(i, i + each));
    if (out.length === n * each) return out;
  }
  return null;
}

/** Plays from [hand] that beat [target] as the same kind of hand, lowest first; plays that break no larger group first. */
function sameKind(held: Map<number, number[]>, target: Hand): number[][] {
  const { kind, size, main } = target;
  const need = kind === "solo" || kind === "straight" ? 1 : kind === "pair" || kind === "pairs" ? 2
    : kind === "four2" || kind === "four22" ? 4 : 3;
  const run = kind === "straight" || kind === "pairs" || kind === "plane" || kind === "plane1" || kind === "plane2";
  const out: { cards: number[]; breaks: number; main: number }[] = [];
  const have = [...held.keys()].filter((r) => held.get(r)!.length >= need);
  const tops = (run ? runs(have, size) : have).filter((t) => t > main).sort((a, b) => a - b);
  for (const t of tops) {
    const ranks = run ? Array.from({ length: size }, (_, i) => t - size + 1 + i) : [t];
    const cards = ranks.flatMap((r) => held.get(r)!.slice(0, need));
    const breaks = ranks.filter((r) => held.get(r)!.length > need).length;
    const skip = new Set(ranks);
    let extra: number[] | null = [];
    if (kind === "trio1" || kind === "plane1") extra = along(held, skip, size, false);
    else if (kind === "trio2" || kind === "plane2") extra = along(held, skip, size, true);
    else if (kind === "four2") extra = along(held, skip, 2, false);
    else if (kind === "four22") extra = along(held, skip, 2, true);
    if (extra) out.push({ cards: [...cards, ...extra], breaks, main: t });
  }
  return out.sort((a, b) => Math.min(a.breaks, 1) - Math.min(b.breaks, 1) || a.main - b.main).map((x) => x.cards);
}

function bombsOver(held: Map<number, number[]>, over: number): number[][] {
  const out = [...held].filter(([r, cards]) => cards.length === 4 && r > over).sort((a, b) => a[0] - b[0]).map(([, cards]) => cards);
  if (held.has(SMALL_JOKER) && held.has(BIG_JOKER)) out.push([52, 53]);
  return out;
}

/**
 * Plays to offer from [hand], in the order the hint key walks them. On [last]: every play of its kind that beats it,
 * lowest first, then the bombs and the rocket. Leading (null): the whole hand when it is one hand, then each rank's
 * own group from the lowest rank up (a trio takes a card along when there is one to spare), bombs and the rocket last.
 * Empty when nothing can be played.
 */
export function hints(hand: readonly number[], last: readonly number[] | null): number[][] {
  const held = byRank(hand);
  const out: number[][] = [];
  const seen = new Set<string>();
  const add = (cards: number[]) => {
    const sorted = [...cards].sort((a, b) => a - b);
    const key = sorted.join(",");
    if (!seen.has(key)) { seen.add(key); out.push(sorted); }
  };
  if (last) {
    const theirs = classify(last);
    if (theirs.some((h) => h.kind === "rocket")) return [];
    const bomb = theirs.find((h) => h.kind === "bomb");
    if (!bomb) for (const h of theirs) for (const cards of sameKind(held, h)) add(cards);
    for (const cards of bombsOver(held, bomb ? bomb.main : 0)) add(cards);
    return out;
  }
  if (classify(hand).length) add([...hand]);
  const late: number[][] = [];
  for (const r of [...held.keys()].sort((a, b) => a - b)) {
    const cards = held.get(r)!;
    if (cards.length === 4) late.push(cards);
    else if (cards.length === 3) add([...cards, ...(along(held, new Set([r]), 1, false) ?? [])]);
    else if (r >= SMALL_JOKER && held.has(SMALL_JOKER) && held.has(BIG_JOKER)) continue;
    else add(cards);
  }
  for (const cards of late) add(cards);
  if (held.has(SMALL_JOKER) && held.has(BIG_JOKER)) add([52, 53]);
  return out.filter((cards) => classify(cards).length > 0);
}
