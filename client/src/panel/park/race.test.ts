import { describe, expect, it } from "vitest";
import {
  HOP_AT, hits, leaders, momentOf, moving, playhead, rankOf, spots, SQUARE_AT, stacksAt, stepLength, stepStart,
  type Race, type RaceStep,
} from "./race";

// A race of the server's rules (server/app/race.py, boost 12, trip 5): side by side on the start line, a five-high
// stack on square 8, and xinyi finishing alone from the top lane's neighbour.
const START = ["jiaran", "sinuo", "xinyi", "beila", "nailin"];
const MOVES: RaceStep[] = [
  { m: "sinuo", dice: [2], steps: 2, from: 0, to: 2 },
  { m: "xinyi", dice: [3], steps: 3, from: 0, to: 3 },
  { m: "beila", dice: [3], steps: 3, from: 0, to: 3 },
  { m: "nailin", dice: [1], steps: 1, from: 0, to: 1 },
  { m: "jiaran", dice: [2], steps: 2, from: 0, to: 2 },
  { m: "beila", dice: [2], steps: 2, from: 3, to: 5, square: "trip", end: 4 },
  { m: "jiaran", dice: [2], steps: 2, from: 2, to: 4 },
  { m: "sinuo", dice: [3], steps: 3, from: 2, to: 5, square: "trip", end: 4 },
  { m: "xinyi", dice: [1], steps: 1, from: 3, to: 4 },
  { m: "nailin", dice: [2], steps: 2, from: 1, to: 3 },
  { m: "beila", dice: [1], steps: 1, from: 4, to: 5, carry: ["jiaran", "sinuo", "xinyi"], square: "trip", end: 4 },
  { m: "nailin", dice: [1], steps: 1, from: 3, to: 4 },
  { m: "sinuo", dice: [1], steps: 1, from: 4, to: 5, carry: ["xinyi", "nailin"], square: "trip", end: 4 },
  { m: "jiaran", dice: [1], steps: 1, from: 4, to: 5, carry: ["sinuo", "xinyi", "nailin"], square: "trip", end: 4 },
  { m: "xinyi", dice: [2], steps: 2, from: 4, to: 6, carry: ["nailin"] },
  { m: "beila", dice: [2], steps: 2, from: 4, to: 6, carry: ["jiaran", "sinuo"] },
  { m: "xinyi", dice: [2], steps: 2, from: 6, to: 8, carry: ["nailin", "beila", "jiaran", "sinuo"] },
  { m: "sinuo", dice: [1], steps: 1, from: 8, to: 9 },
  { m: "nailin", dice: [1], steps: 1, from: 8, to: 9, carry: ["beila", "jiaran"] },
  { m: "jiaran", dice: [2], steps: 2, from: 9, to: 11 },
  { m: "beila", dice: [3], steps: 3, from: 9, to: 12, square: "boost", end: 14 },
  { m: "sinuo", dice: [3], steps: 3, from: 9, to: 12, carry: ["nailin"], square: "boost", end: 14 },
  { m: "nailin", dice: [1], steps: 1, from: 14, to: 15 },
  { m: "xinyi", dice: [3], steps: 3, from: 8, to: 11 },
  { m: "jiaran", dice: [2], steps: 2, from: 11, to: 13, carry: ["xinyi"] },
  { m: "jiaran", dice: [1], steps: 1, from: 13, to: 14, carry: ["xinyi"] },
  { m: "nailin", dice: [2], steps: 2, from: 15, to: 17 },
  { m: "beila", dice: [2], steps: 2, from: 14, to: 16, carry: ["sinuo", "jiaran", "xinyi"] },
  { m: "sinuo", dice: [2], steps: 2, from: 16, to: 18, carry: ["jiaran", "xinyi"] },
  { m: "xinyi", dice: [2], steps: 2, from: 18, to: 20 },
];
const RANKING = ["xinyi", "jiaran", "sinuo", "nailin", "beila"];

const race = (over: Partial<Race> = {}): Race => ({
  id: 3600, phase: "running", opensAt: 3600, startsAt: 6900, hash: "", setup: { boost: 12, trip: 5 },
  odds: { win: {}, top2: {}, last: {} }, pool: {}, bettors: 0, mine: [], leadMs: 4000, stepMs: 2400, slowFrom: 25,
  slowMs: 3600, start: START, moves: MOVES, ranking: RANKING, ...over,
});
const T0 = 6900_000;

describe("race playback", () => {
  it("replays the move list to the server's ranking", () => {
    const end = playhead(race(), T0 + 4000 + 25 * 2400 + 5 * 3600 + 1);
    expect(end).toEqual({ done: MOVES.length, current: -1, part: 0 });
    expect(rankOf(stacksAt(START, MOVES, end))).toEqual(RANKING);
  });

  it("waits for the lead, steps on the beat and slows down for the last round", () => {
    expect(playhead(race(), T0 + 3999)).toEqual({ done: 0, current: -1, part: 0 });
    expect(playhead(race(), T0 + 4000 + 2 * 2400 + 1200)).toEqual({ done: 2, current: 2, part: 0.5 });
    expect(stepStart(race(), 25)).toBe(4000 + 25 * 2400);
    expect(stepStart(race(), 27)).toBe(4000 + 25 * 2400 + 2 * 3600);
    expect(stepLength(race(), 24)).toBe(2400);
    expect(stepLength(race(), 25)).toBe(3600);
    expect(playhead(race(), T0 + 4000 + 25 * 2400 + 900)).toEqual({ done: 25, current: 25, part: 0.25 });
    // Without slowFrom every step is stepMs long.
    expect(stepStart(race({ slowFrom: undefined, slowMs: undefined }), 27)).toBe(4000 + 27 * 2400);
  });

  it("starts side by side and leaves the start line one at a time", () => {
    const before = spots(stacksAt(START, MOVES, { done: 0, current: -1, part: 0 }));
    expect(START.map((m) => before[m])).toEqual(START.map((_, k) => ({ square: 0, level: 0, lane: k })));
    const after = spots(stacksAt(START, MOVES, { done: 1, current: -1, part: 0 }));
    expect(after.sinuo).toEqual({ square: 2, level: 0 });
    expect(after.xinyi).toEqual({ square: 0, level: 0, lane: 1 });
    expect(rankOf(stacksAt(START, MOVES, { done: 0, current: -1, part: 0 }))).toEqual(START);
  });

  it("holds the mover while the die rolls, then hops to the square and on past a special one", () => {
    const at = (part: number) => spots(stacksAt(START, MOVES, { done: 5, current: 5, part })).beila;
    expect(at(HOP_AT - 0.05)).toEqual({ square: 3, level: 1 });
    expect(at(HOP_AT + 0.05)).toEqual({ square: 5, level: 0 });
    expect(at(SQUARE_AT + 0.05)).toEqual({ square: 4, level: 0 });
  });

  it("carries the group above the mover and stacks it on top", () => {
    const head = { done: 16, current: 16, part: 0.9 };
    const at = spots(stacksAt(START, MOVES, head));
    expect(["xinyi", "nailin", "beila", "jiaran", "sinuo"].map((m) => at[m])).toEqual(
      [0, 1, 2, 3, 4].map((level) => ({ square: 8, level })),
    );
    expect(moving(MOVES, head)).toEqual(["xinyi", "nailin", "beila", "jiaran", "sinuo"]);
  });

  it("finds the moments worth a word", () => {
    const lead = leaders(START, MOVES);
    expect(lead[MOVES.length - 1]).toBe("xinyi");
    expect(momentOf(MOVES[5], lead[4], lead[5])?.kind).toBe("trip");
    expect(momentOf(MOVES[20], lead[19], lead[20])?.kind).toBe("boost");
    expect(momentOf(MOVES[0], START[0], lead[0])).toMatchObject({ kind: "lead", m: "sinuo" });
    // Already ahead on top of the stack: crossing the line alone is no new lead.
    expect(momentOf(MOVES[29], lead[28], lead[29])).toBeNull();
    expect(momentOf(MOVES[24], lead[23], lead[24])?.kind).toBe("carry");
  });

  it("knows which bets won", () => {
    expect(hits("win", "xinyi", RANKING)).toBe(true);
    expect(hits("top2", "jiaran", RANKING)).toBe(true);
    expect(hits("top2", "sinuo", RANKING)).toBe(false);
    expect(hits("last", "beila", RANKING)).toBe(true);
  });
});
