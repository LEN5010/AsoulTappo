import { describe, expect, it } from "vitest";
import fixture from "./rules.fixture.json";
import { beats, classify, hints, isBomb, playable, rank, rankLabel, sortHand } from "./rules";

/** One card of each rank given, cycling suits so equal ranks are different cards. */
function cardsOf(...ranks: number[]): number[] {
  const used = new Map<number, number>();
  return ranks.map((r) => {
    if (r === 16) return 52;
    if (r === 17) return 53;
    const i = used.get(r) ?? 0;
    used.set(r, i + 1);
    return (r - 3) * 4 + i;
  });
}
const ranksOf = (cards: number[]) => cards.map(rank).sort((a, b) => a - b);

describe("ddz rules", () => {
  it("reads every fixture hand the way the server does", () => {
    const reads = fixture.reads as unknown as [number[], [string, number, number][]][];
    expect(reads.length).toBeGreaterThan(500);
    for (const [cards, want] of reads) {
      const got = classify(cards).map((h) => [h.kind, h.size, h.main]);
      expect(got, cards.join(",")).toEqual(want);
    }
  });

  it("decides every fixture pair the way the server does", () => {
    const pairs = fixture.beats as unknown as [number[], number[], boolean][];
    expect(pairs.length).toBeGreaterThan(300);
    for (const [a, b, want] of pairs) expect(beats(a, b), `${a} on ${b}`).toBe(want);
  });

  it("ranks and labels cards", () => {
    expect(rank(0)).toBe(3);
    expect(rank(51)).toBe(15);
    expect(rank(52)).toBe(16);
    expect(rank(53)).toBe(17);
    expect([3, 10, 11, 12, 13, 14, 15].map(rankLabel)).toEqual(["3", "10", "J", "Q", "K", "A", "2"]);
    expect(sortHand([0, 53, 4, 52, 1]).map(rank)).toEqual([17, 16, 4, 3, 3]);
  });

  it("knows what may be played", () => {
    expect(playable([], null)).toBe(false);
    expect(playable(cardsOf(3), null)).toBe(true);
    expect(playable(cardsOf(3, 4), null)).toBe(false);
    expect(playable(cardsOf(4), cardsOf(3))).toBe(true);
    expect(playable(cardsOf(3), cardsOf(4))).toBe(false);
    expect(isBomb(cardsOf(5, 5, 5, 5))).toBe(true);
    expect(isBomb([52, 53])).toBe(true);
    expect(isBomb(cardsOf(5, 5, 5))).toBe(false);
  });
});

describe("ddz hints", () => {
  it("offers only plays that beat the last one, lowest first, bombs last", () => {
    const hand = cardsOf(3, 5, 5, 7, 9, 9, 9, 9, 16, 17);
    const got = hints(hand, cardsOf(4));
    expect(got.map(ranksOf)).toEqual([[7], [16], [17], [5], [9], [9, 9, 9, 9], [16, 17]]);
    for (const cards of got) expect(beats(cards, cardsOf(4))).toBe(true);
  });

  it("keeps whole groups before breaking larger ones", () => {
    const got = hints(cardsOf(6, 6, 6, 8, 8, 10), cardsOf(4, 4));
    expect(got.map(ranksOf)).toEqual([[8, 8], [6, 6]]);
  });

  it("takes the least useful cards along with a trio", () => {
    const hand = cardsOf(3, 4, 4, 9, 9, 9, 12, 12, 12);
    expect(hints(hand, cardsOf(5, 5, 5, 6)).map(ranksOf)).toEqual([[3, 9, 9, 9], [3, 12, 12, 12]]);
    expect(hints(hand, cardsOf(5, 5, 5, 6, 6)).map(ranksOf)).toEqual([[4, 4, 9, 9, 9], [4, 4, 12, 12, 12]]);
  });

  it("finds runs", () => {
    const hand = cardsOf(4, 5, 6, 7, 8, 9, 9, 15);
    expect(hints(hand, cardsOf(3, 4, 5, 6, 7)).map(ranksOf)).toEqual([[4, 5, 6, 7, 8], [5, 6, 7, 8, 9]]);
    expect(hints(cardsOf(5, 5, 6, 6, 7, 7, 8), cardsOf(3, 3, 4, 4, 5, 5)).map(ranksOf)).toEqual([[5, 5, 6, 6, 7, 7]]);
    expect(hints(cardsOf(7, 7, 7, 8, 8, 8, 3, 4), cardsOf(4, 4, 4, 5, 5, 5, 9, 10)).map(ranksOf)).toEqual([[3, 4, 7, 7, 7, 8, 8, 8]]);
  });

  it("answers a bomb only with a bigger one or the rocket", () => {
    const hand = cardsOf(4, 4, 4, 4, 9, 9, 9, 9, 16, 17, 15);
    expect(hints(hand, cardsOf(6, 6, 6, 6)).map(ranksOf)).toEqual([[9, 9, 9, 9], [16, 17]]);
    expect(hints(hand, [52, 53])).toEqual([]);
    expect(hints(cardsOf(3, 4), cardsOf(15))).toEqual([]);
  });

  it("leads with the whole hand when it is one, then from the lowest rank up", () => {
    expect(hints(cardsOf(3, 4, 5, 6, 7), null)[0].length).toBe(5);
    const got = hints(cardsOf(3, 5, 5, 8, 8, 8, 11, 11, 11, 11, 16, 17), null);
    expect(got.map(ranksOf)).toEqual([[3], [5, 5], [3, 8, 8, 8], [11, 11, 11, 11], [16, 17]]);
    for (const cards of got) expect(classify(cards).length).toBeGreaterThan(0);
    expect(hints(cardsOf(8, 8, 8), null).map(ranksOf)).toEqual([[8, 8, 8]]);
  });

  it("every hint is playable, over many random hands", () => {
    let seed = 7;
    const rand = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
    for (let round = 0; round < 300; round++) {
      const deck = Array.from({ length: 54 }, (_, i) => i);
      for (let i = deck.length - 1; i > 0; i--) {
        const j = Math.floor(rand() * (i + 1));
        [deck[i], deck[j]] = [deck[j], deck[i]];
      }
      const hand = deck.slice(0, 17);
      const led = hints(deck.slice(17, 34), null);
      expect(led.length).toBeGreaterThan(0);
      for (const last of led) {
        for (const cards of hints(hand, last)) {
          expect(playable(cards, last), `${cards} on ${last}`).toBe(true);
          expect(cards.every((c) => hand.includes(c))).toBe(true);
          expect(new Set(cards).size).toBe(cards.length);
        }
      }
    }
  });
});
