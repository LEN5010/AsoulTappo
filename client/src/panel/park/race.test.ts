import { describe, expect, it } from "vitest";
import { hits, moodLine, moving, playhead, rankOf, skillLine, spots, stacksAt, SQUARE_AT, type Race, type RaceStep } from "./race";

// A race the server ran (seed 3, boost 6, trip 11): beila wins riding on jiaran, who made the last move.
const START = ["jiaran", "sinuo", "beila", "xinyi", "nailin"];
const MOVES: RaceStep[] = [
  { m: "nailin", dice: [], steps: 3, from: 0, to: 3, add: [["mood", 1]] },
  { m: "beila", dice: [2], steps: 2, from: 0, to: 2, carry: ["xinyi"] },
  { m: "sinuo", dice: [1], steps: 1, from: 0, to: 1, add: [["mood", 0]] },
  { m: "jiaran", dice: [3], steps: 4, from: 0, to: 4, add: [["mood", 1]] },
  { m: "xinyi", dice: [3], steps: 2, from: 2, to: 4, add: [["mood", -1]] },
  { m: "nailin", dice: [], steps: 3, from: 3, to: 6, add: [["mood", 1]], square: "boost", end: 8 },
  { m: "jiaran", dice: [3], steps: 4, from: 4, to: 8, add: [["mood", 1]], carry: ["xinyi"] },
  { m: "xinyi", dice: [3], steps: 2, from: 8, to: 10, add: [["mood", -1]] },
  { m: "beila", dice: [3], steps: 4, from: 2, to: 6, add: [["dash", 1]], square: "boost", end: 8 },
  { m: "sinuo", dice: [3], steps: 3, from: 1, to: 4, add: [["catchup", 1], ["mood", -1]] },
  { m: "xinyi", dice: [2], steps: 1, from: 10, to: 11, add: [["mood", -1]], square: "trip", end: 10 },
  { m: "beila", dice: [2], steps: 2, from: 8, to: 10 },
  { m: "jiaran", dice: [1], steps: 2, from: 8, to: 10, add: [["mood", 1]] },
  { m: "sinuo", dice: [2], steps: 2, from: 4, to: 6, add: [["catchup", 1], ["mood", -1]], square: "boost", end: 8 },
  { m: "nailin", dice: [], steps: 2, from: 8, to: 10, carry: ["sinuo"] },
  { m: "beila", dice: [2], steps: 2, from: 10, to: 12, carry: ["jiaran", "nailin", "sinuo"] },
  { m: "jiaran", dice: [2], steps: 3, from: 12, to: 15, add: [["mood", 1]], carry: ["nailin", "sinuo"] },
  { m: "nailin", dice: [], steps: 2, from: 15, to: 17, carry: ["sinuo"] },
  { m: "xinyi", dice: [3], steps: 3, from: 10, to: 13 },
  { m: "sinuo", dice: [1], steps: 1, from: 17, to: 18, add: [["mood", 0]] },
  { m: "sinuo", dice: [2], steps: 1, from: 18, to: 19, add: [["mood", -1]] },
  { m: "beila", dice: [3], steps: 3, from: 12, to: 15 },
  { m: "jiaran", dice: [2], steps: 2, from: 15, to: 17, carry: ["beila"] },
  { m: "xinyi", dice: [1], steps: 1, from: 13, to: 14 },
  { m: "nailin", dice: [], steps: 2, from: 17, to: 19, carry: ["jiaran", "beila"] },
  { m: "jiaran", dice: [2], steps: 2, from: 19, to: 20, carry: ["beila"] },
];
const RANKING = ["beila", "jiaran", "nailin", "sinuo", "xinyi"];

const race = (over: Partial<Race> = {}): Race => ({
  id: 600, phase: "running", opensAt: 600, startsAt: 1080, hash: "", setup: { moods: {}, boost: 6, trip: 11 },
  odds: { win: {}, top2: {}, last: {} }, pool: {}, mine: [], leadMs: 3000, stepMs: 1000, start: START, moves: MOVES,
  ranking: RANKING, ...over,
});

describe("race playback", () => {
  it("replays the move list to the server's ranking", () => {
    const end = playhead(race(), 1080_000 + 3000 + MOVES.length * 1000 + 1);
    expect(end).toEqual({ done: MOVES.length, current: -1, part: 0 });
    expect(rankOf(stacksAt(START, MOVES, end))).toEqual(RANKING);
  });

  it("waits for the lead and then steps on the beat", () => {
    expect(playhead(race(), 1080_000 + 2999)).toEqual({ done: 0, current: -1, part: 0 });
    expect(playhead(race(), 1080_000 + 3000 + 2500)).toEqual({ done: 2, current: 2, part: 0.5 });
  });

  it("stacks the start bottom to top and carries the group above the mover", () => {
    const head = { done: 1, current: 1, part: 0.2 };
    const at = spots(stacksAt(START, MOVES, head));
    expect(at.beila).toEqual({ square: 2, level: 0 });
    expect(at.xinyi).toEqual({ square: 2, level: 1 });
    expect(at.jiaran).toEqual({ square: 0, level: 0 });
    expect(at.sinuo).toEqual({ square: 0, level: 1 });
    expect(moving(MOVES, head)).toEqual(["beila", "xinyi"]);
  });

  it("lands on a special square first and moves on to its end later in the step", () => {
    const early = spots(stacksAt(START, MOVES, { done: 5, current: 5, part: SQUARE_AT - 0.1 }));
    const late = spots(stacksAt(START, MOVES, { done: 5, current: 5, part: SQUARE_AT + 0.1 }));
    expect(early.nailin).toEqual({ square: 6, level: 0 });
    expect(late.nailin).toEqual({ square: 8, level: 0 });
  });

  it("knows which bets won", () => {
    expect(hits("win", "beila", RANKING)).toBe(true);
    expect(hits("top2", "jiaran", RANKING)).toBe(true);
    expect(hits("top2", "nailin", RANKING)).toBe(false);
    expect(hits("last", "xinyi", RANKING)).toBe(true);
  });

  it("writes skills and moods from their numbers", () => {
    expect(skillLine({ kind: "snack", on: 1, chance: 0.5, bonus: 1 })).toBe("掷出 1：50% 下次 +1");
    expect(skillLine({ kind: "steady", steps: 2 })).toBe("每次走 2 格");
    expect(moodLine({ delta: -1, moves: 3 })).toBe("前 3 次 −1");
    expect(moodLine({ delta: 0, moves: 0 })).toBe("");
  });
});
