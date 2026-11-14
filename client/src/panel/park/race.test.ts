import { describe, expect, it } from "vitest";
import {
  HOP_AT, hits, leaders, momentOf, moving, OPEN_AT, OPEN_ROLL_MS, openingAt, playhead, rankOf, REROLL_MS, ROLL_AT,
  airFaces, boardOf, bounce, cellOf, saidAt, stepPath, walkPath, spots, SQUARE_AT, stacksAt, stageOf, stepLength, stepPhases, stepStart, staggered, TOSS_STAGGER_MS,
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
  odds: { win: {}, top2: {}, last: {} }, pool: {}, bettors: 0, mine: [], leadMs: 4000, stepMs: 3000, slowFrom: 25,
  slowMs: 4000, start: START, moves: MOVES, ranking: RANKING, ...over,
});
const T0 = 6900_000;

describe("race playback", () => {
  it("replays the move list to the server's ranking", () => {
    const end = playhead(race(), T0 + 4000 + 25 * 3000 + 5 * 4000 + 1);
    expect(end).toEqual({ done: MOVES.length, current: -1, part: 0 });
    expect(rankOf(stacksAt(START, MOVES, end))).toEqual(RANKING);
  });

  it("waits for the lead, steps on the beat and slows down for the last round", () => {
    expect(playhead(race(), T0 + 3999)).toEqual({ done: 0, current: -1, part: 0 });
    expect(playhead(race(), T0 + 4000 + 2 * 3000 + 1500)).toEqual({ done: 2, current: 2, part: 0.5 });
    expect(stepStart(race(), 25)).toBe(4000 + 25 * 3000);
    expect(stepStart(race(), 27)).toBe(4000 + 25 * 3000 + 2 * 4000);
    expect(stepLength(race(), 24)).toBe(3000);
    expect(stepLength(race(), 25)).toBe(4000);
    expect(playhead(race(), T0 + 4000 + 25 * 3000 + 1000)).toEqual({ done: 25, current: 25, part: 0.25 });
    // A longer opening pushes every step back.
    expect(stepStart(race({ leadMs: 7000 }), 0)).toBe(7000);
    // Without slowFrom every step is stepMs long.
    expect(stepStart(race({ slowFrom: undefined, slowMs: undefined }), 27)).toBe(4000 + 27 * 3000);
  });

  it("lights the mover for a second, rolls the die, then walks, slower in the last round", () => {
    const p = stepPhases(3000);
    expect(p.rollAt).toBeCloseTo(1000);
    expect(p.rollLen).toBeCloseTo(800);
    expect(p.hopAt).toBeCloseTo(1800);
    expect(p.hopLen).toBeCloseTo(800);
    expect(p.squareAt).toBeCloseTo(2600);
    expect(p.squareAt + p.pushLen).toBeCloseTo(3000);
    const slow = stepPhases(4000);
    expect(slow.rollAt).toBeCloseTo(4000 / 3);
    expect(slow.hopAt + slow.hopLen).toBeCloseTo(slow.squareAt);
    expect([0, ROLL_AT - 0.01, ROLL_AT, HOP_AT - 0.01, HOP_AT, 0.99].map(stageOf)).toEqual(
      ["lit", "lit", "roll", "roll", "walk", "walk"],
    );
    // Nobody leaves the square until the die has landed.
    const at = (part: number) => spots(stacksAt(START, MOVES, { done: 0, current: 0, part })).sinuo;
    expect(at(HOP_AT - 0.01)).toEqual({ square: 0, level: 0, lane: 1 });
    expect(at(HOP_AT)).toEqual({ square: 2, level: 0 });
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

  it("keeps a step's words up while the next mover is lit", () => {
    expect(saidAt({ done: 5, current: 5, part: 0.9 })).toEqual({ i: 5, part: 0.9 });
    expect(saidAt({ done: 6, current: 6, part: ROLL_AT - 0.01 })).toEqual({ i: 5, part: 1 });
    expect(saidAt({ done: 6, current: 6, part: ROLL_AT })).toEqual({ i: 6, part: ROLL_AT });
    expect(saidAt({ done: 0, current: 0, part: 0.1 })).toEqual({ i: 0, part: 0.1 });
    expect(saidAt({ done: 0, current: -1, part: 0 })).toBeNull();
  });

  it("rolls the order at the start, again for the ties, then lines the field up", () => {
    const rolls = [
      START.map((m, i) => ({ m, face: [6, 6, 3, 3, 1][i] })),
      [{ m: "jiaran", face: 5 }, { m: "sinuo", face: 2 }, { m: "xinyi", face: 4 }, { m: "beila", face: 4 }],
      [{ m: "xinyi", face: 2 }, { m: "beila", face: 5 }],
    ];
    const r = race({ order: ["jiaran", "sinuo", "beila", "xinyi", "nailin"], rolls, leadMs: 4000 + 2 * 1500 });
    const at = (ms: number) => openingAt(r, T0 + ms);
    expect(at(0)).toEqual({ round: -1, rolling: [], tumbling: false, since: 0, faces: {}, lined: false });
    expect(at(OPEN_AT + 100)).toMatchObject({ round: 0, rolling: START, tumbling: true, since: 100, faces: {} });
    expect(at(OPEN_AT + OPEN_ROLL_MS)).toMatchObject({ round: 0, tumbling: false, faces: { jiaran: 6, nailin: 1 } });
    // The second round: the four tied tumble on their old faces, nailin keeps its 1.
    const second = at(OPEN_AT + REROLL_MS + 10)!;
    expect(second).toMatchObject({ round: 1, rolling: ["jiaran", "sinuo", "xinyi", "beila"], tumbling: true });
    expect(second.faces).toEqual({ jiaran: 6, sinuo: 6, xinyi: 3, beila: 3, nailin: 1 });
    expect(at(OPEN_AT + 2 * REROLL_MS + OPEN_ROLL_MS)).toMatchObject({
      round: 2, tumbling: false, lined: false, faces: { jiaran: 5, sinuo: 2, xinyi: 2, beila: 5, nailin: 1 },
    });
    // Lined up: every die shows its first-round face again, high to low along the order.
    const lined = at(OPEN_AT + 3 * REROLL_MS)!;
    expect(lined.lined).toBe(true);
    expect(lined.faces).toEqual(Object.fromEntries(rolls[0].map((x) => [x.m, x.face])));
    const along = r.order!.map((m) => lined.faces[m]);
    expect(along).toEqual([6, 6, 3, 3, 1]);
    expect(along.every((f, i) => !i || f <= along[i - 1])).toBe(true);
    // The opening ends where the first step starts; races without dice have none.
    expect(at(7000 - 1)?.lined).toBe(true);
    expect(at(7000)).toBeNull();
    expect(stepStart(r, 0)).toBe(7000);
    expect(openingAt(race(), T0 + 1000)).toBeNull();
  });

  it("tosses a die through other faces and staggers the opening's dice", () => {
    for (const pool of [[1, 2, 3], [1, 2, 3, 4, 5, 6]]) {
      for (const face of pool) {
        for (const seed of [0, 1, 7]) {
          const air = airFaces(face, pool, seed);
          expect(air).toHaveLength(4);
          expect(air).not.toContain(face);
          expect(air.every((f, j) => !j || f !== air[j - 1])).toBe(true);
          expect(air.every((f) => pool.includes(f))).toBe(true);
        }
      }
    }
    expect(airFaces(3, [3], 0)).toEqual([]);
    expect(staggered(800, 0, 5)).toEqual({ delay: 0, ms: 800 - 4 * TOSS_STAGGER_MS });
    const last = staggered(800, 4, 5);
    expect(last.delay + last.ms).toBe(800);
    expect(staggered(800, 0, 1)).toEqual({ delay: 0, ms: 800 });
    // A squeezed roll keeps most of its length for the toss.
    const short = staggered(200, 4, 5);
    expect(short.delay + short.ms).toBeCloseTo(200);
    expect(short.ms).toBeGreaterThanOrEqual(150);
  });

  it("lays the 24 squares round a 9 × 5 board, clockwise from the top left corner", () => {
    expect(boardOf(24)).toEqual({ cols: 9, rows: 5 });
    const cells = Array.from({ length: 24 }, (_, sq) => cellOf(sq, 24));
    expect(new Set(cells.map((c) => `${c.col},${c.row}`)).size).toBe(24);
    expect(cells[0]).toEqual({ col: 0, row: 0 });
    expect(cells[8]).toEqual({ col: 8, row: 0 });
    expect(cells[12]).toEqual({ col: 8, row: 4 });
    expect(cells[20]).toEqual({ col: 0, row: 4 });
    expect(cells[23]).toEqual({ col: 0, row: 1 });
    // The finish is the start's corner; every square is next to the one before it.
    expect(cellOf(24, 24)).toEqual(cells[0]);
    for (let sq = 1; sq <= 24; sq++) {
      const a = cellOf(sq - 1, 24);
      const b = cellOf(sq, 24);
      expect(Math.abs(a.col - b.col) + Math.abs(a.row - b.row)).toBe(1);
    }
    // Every square is on the edge: the 7 × 3 inside is left free.
    expect(cells.every((c) => c.row === 0 || c.row === 4 || c.col === 0 || c.col === 8)).toBe(true);
  });

  it("walks square by square, turning back at the finish", () => {
    expect(walkPath(5, 3, 24)).toEqual([6, 7, 8]);
    expect(walkPath(22, 2, 24)).toEqual([23, 24]);
    expect(walkPath(22, 3, 24)).toEqual([23, 24, 23]);
    expect(walkPath(23, 3, 24)).toEqual([24, 23, 22]);
    expect(walkPath(6, -1, 24)).toEqual([5]);
    for (let from = 0; from < 24; from++) {
      for (const n of [1, 2, 3]) expect(walkPath(from, n, 24).at(-1)).toBe(bounce(from + n, 24));
    }
    const hop = { m: "xinyi", dice: [3], steps: 3, from: 20, to: 23 };
    expect(stepPath(hop, 24, 2, 1)).toEqual({ hop: [21, 22, 23], push: [] });
    const bounced = { m: "xinyi", dice: [3], steps: 3, from: 22, to: 23, square: "trip" as const, end: 22 };
    expect(stepPath(bounced, 24, 2, 1)).toEqual({ hop: [23, 24, 23], push: [22] });
    const boosted = { m: "xinyi", dice: [2], steps: 2, from: 4, to: 6, square: "boost" as const, end: 8 };
    expect(stepPath(boosted, 24, 2, 1)).toEqual({ hop: [5, 6], push: [7, 8] });
  });

  it("knows which bets won", () => {
    expect(hits("win", "xinyi", RANKING)).toBe(true);
    expect(hits("top2", "jiaran", RANKING)).toBe(true);
    expect(hits("top2", "sinuo", RANKING)).toBe(false);
    expect(hits("last", "beila", RANKING)).toBe(true);
  });
});
