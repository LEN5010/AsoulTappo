import { describe, expect, it } from "vitest";
import {
  HOP_AT, hits, leaders, momentOf, moving, OPEN_AT, OPEN_ROLL_MS, openingAt, playhead, rankOf, REROLL_MS, PUSH_LEN,
  DICE_TOSS, rollStart, roundAt, roundDice, roundsOf, chinaDay, playLength, replayAt, replayTime,
  airFaces, boardOf, bounce, cellOf, cutOf, cornersOf, saidAt, squareKind, stepPath, walkPath, spots, SQUARE_AT, stacksAt, stageOf, stepLength, stepPhases, stepStart, staggered, TOSS_STAGGER_MS,
  type Race, type RaceSetup, type RaceStep,
  ROUND, type Playhead, stepTimes,
} from "./race";
import fixture from "./race.fixture.json";

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
    expect(playhead(race(), T0 + 4000 + 2 * 3000 + 1500)).toMatchObject({ done: 2, current: 2, part: 0.5 });
    expect(stepStart(race(), 25)).toBe(4000 + 25 * 3000);
    expect(stepStart(race(), 27)).toBe(4000 + 25 * 3000 + 2 * 4000);
    expect(stepLength(race(), 24)).toBe(3000);
    expect(stepLength(race(), 25)).toBe(4000);
    expect(playhead(race(), T0 + 4000 + 25 * 3000 + 1000)).toMatchObject({ done: 25, current: 25, part: 0.25 });
    // A longer opening pushes every step back.
    expect(stepStart(race({ leadMs: 7000 }), 0)).toBe(7000);
    // Without slowFrom every step is stepMs long.
    expect(stepStart(race({ slowFrom: undefined, slowMs: undefined }), 27)).toBe(4000 + 27 * 3000);
  });

  it("holds a step back for its close-up, and every step after it by as much", () => {
    // Close-ups before steps 2 and 6, 2600 ms each (park_race.py cuts_of, cut_ms).
    const r = race({ rollMs: 4800, stepMs: 5000, slowMs: 6600, rest: [], cutMs: 2600, cuts: [{ at: 2, m: "jiaran" }, { at: 6, m: "nailin" }] });
    const t = (ms: number) => T0 + ms;
    expect(cutOf(r, 2)).toEqual({ at: 2, m: "jiaran" });
    expect(cutOf(r, 3)).toBeUndefined();
    expect(stepStart(r, 2)).toBe(4000 + 4800 + 2 * 5000);
    expect(stepStart(r, 3)).toBe(4000 + 4800 + 3 * 5000 + 2600);
    // The next round's dice wait for it too; the second close-up is in that round.
    expect(rollStart(r, 1)).toBe(4000 + 4800 + 5 * 5000 + 2600);
    expect(stepStart(r, 7)).toBe(4000 + 2 * 4800 + 7 * 5000 + 2 * 2600);
    // During the close-up the step is under way and has not moved; then it plays as any other.
    expect(playhead(r, t(stepStart(r, 2) + 1300))).toEqual({ done: 2, current: 2, part: 0, cut: 0.5 });
    expect(playhead(r, t(stepStart(r, 2) + 2600 + 2500))).toMatchObject({ done: 2, current: 2, part: 0.5 });
    expect(playhead(r, t(stepStart(r, 3) + 2500))).toMatchObject({ done: 3, current: 3, part: 0.5 });
    // The words of the step before are cleared for it.
    expect(saidAt({ done: 2, current: 2, part: 0, cut: 0.1 })).toEqual({ i: 2, part: 0 });
    expect(saidAt({ done: 2, current: 2, part: 0.1 })).toEqual({ i: 1, part: 1 });
    // The end, as the server's endsAt.
    expect(stepStart(r, 29) + stepLength(r, 29) + 4000).toBe(4000 + 6 * 4800 + 25 * 5000 + 5 * 6600 + 2 * 2600 + 4000);
  });

  it("opens every round with its dice, thrown together, and moves after them in the order", () => {
    // 30 moves, six rounds; dice 2400 ms a round, steps 2500, the last round's 3300 (park_race.py playback_ms).
    const r = race({ rollMs: 2400, stepMs: 2500, slowMs: 3300, rest: [] });
    expect(roundsOf(r)).toBe(6);
    expect(rollStart(r, 0)).toBe(4000);
    expect(stepStart(r, 0)).toBe(4000 + 2400);
    expect(stepStart(r, 4)).toBe(4000 + 2400 + 4 * 2500);
    expect(stepStart(r, 5)).toBe(4000 + 2 * 2400 + 5 * 2500);
    expect(rollStart(r, 1)).toBe(4000 + 2400 + 5 * 2500);
    expect(stepStart(r, 27)).toBe(4000 + 6 * 2400 + 25 * 2500 + 2 * 3300);
    // The end, as the server's endsAt: the last step done, then the tail.
    expect(stepStart(r, 29) + stepLength(r, 29) + 4000).toBe(4000 + 6 * 2400 + 25 * 2500 + 5 * 3300 + 4000);
    // While a round's dice are out nothing is under way; the dice of the round on show.
    const t = (ms: number) => T0 + ms;
    expect(playhead(r, t(4000 + 100))).toEqual({ done: 0, current: -1, part: 0 });
    expect(playhead(r, t(rollStart(r, 1) + 10))).toEqual({ done: 5, current: -1, part: 0 });
    expect(roundAt(r, t(3999))).toBeNull();
    expect(roundAt(r, t(4000 + 2400 * DICE_TOSS))).toEqual({ round: 0, since: 2400 * DICE_TOSS });
    expect(roundAt(r, t(rollStart(r, 1) + 5))).toEqual({ round: 1, since: 5 });
    expect(roundDice(r, 1)).toEqual(MOVES.slice(5, 10).map((s) => ({ m: s.m, face: s.steps })));
    // The last round: the winning move's die and, after it, those drawn only to be shown.
    const short = race({ rollMs: 2400, moves: MOVES.slice(0, 27), rest: [{ m: "x", face: 2 }, { m: "y", face: 1 }, { m: "z", face: 3 }] });
    expect(roundDice(short, 5).map((d) => d.face)).toEqual([...MOVES.slice(25, 27).map((s) => s.steps), 2, 1, 3]);
  });

  it("lights the mover, then walks, and gives a special square its share, slower in the last round", () => {
    const p = stepPhases(2500);
    expect(p.hopAt).toBeCloseTo(700);
    expect(p.hopLen).toBeCloseTo(800);
    expect(p.squareAt).toBeCloseTo(1500);
    expect(p.pushLen).toBeCloseTo(700);
    expect(p.squareAt + p.pushLen).toBeLessThan(2500);
    const slow = stepPhases(3300);
    expect(slow.hopAt + slow.hopLen).toBeCloseTo(slow.squareAt);
    expect(SQUARE_AT + PUSH_LEN).toBeLessThan(1);
    expect([0, HOP_AT - 0.01, HOP_AT, 0.99].map(stageOf)).toEqual(["lit", "lit", "walk", "walk"]);
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
    expect(saidAt({ done: 6, current: 6, part: HOP_AT - 0.01 })).toEqual({ i: 5, part: 1 });
    expect(saidAt({ done: 6, current: 6, part: HOP_AT })).toEqual({ i: 6, part: HOP_AT });
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

  it("paces a race by the square where the server gives its steps their own lengths", () => {
    const pace = { lit: 800, hop: 400, gap: 300, act: 900, rest: 700 };
    const moves = [
      { m: "a", dice: [1], steps: 1, from: 0, to: 1 },
      { m: "b", dice: [3], steps: 3, from: 0, to: 3, square: "boost" as const, end: 5 },
      { m: "c", dice: [2], steps: 2, from: 0, to: 2, square: "portal" as const, end: 9 },
    ];
    const stepsMs = [1900, 3800, 3500];
    const r = race({ moves, stepsMs, pace, slowFrom: 3, stepMs: 5000, slowMs: 5000 });
    const lead = stepStart(r, 0);
    expect(stepStart(r, 1) - lead).toBe(1900);
    expect(stepStart(r, 2) - lead).toBe(1900 + 3800);
    // A hop takes as long on every square: one square, then three.
    expect(stepTimes(r, 0)).toMatchObject({ len: 1900, hopAt: 800, hopLen: 400, pushLen: 0 });
    expect(stepTimes(r, 1)).toMatchObject({ hopAt: 800, hopLen: 1200, squareAt: 2300, pushLen: 800 });
    // A portal walks no squares: the pace's time for a square that acts.
    expect(stepTimes(r, 2)).toMatchObject({ hopLen: 800, squareAt: 1900, pushLen: 900 });
    const t = (ms: number) => r.startsAt * 1000 + lead + 1900 + ms;
    expect(playhead(r, t(799)).part).toBeLessThan(HOP_AT);
    expect(playhead(r, t(800)).part).toBeCloseTo(HOP_AT);
    expect(playhead(r, t(2299)).part).toBeLessThan(SQUARE_AT);
    expect(playhead(r, t(2300))).toMatchObject({ current: 1, ms: 2300 });
    expect(playhead(r, t(2300)).part).toBeCloseTo(SQUARE_AT);
    expect(playhead(r, t(3799)).part).toBeLessThan(1);
    expect(playhead(r, t(3800)).current).toBe(2);
  });
  it("lays the 24 squares round a 9 × 5 board, clockwise from the top left corner, all the same size", () => {
    expect(boardOf(24)).toEqual({ cols: 9, rows: 5 });
    expect(cornersOf(24)).toEqual([0, 8, 12, 20]);
    const cells = Array.from({ length: 24 }, (_, sq) => cellOf(sq, 24));
    expect(new Set(cells.map((c) => `${c.col},${c.row}`)).size).toBe(24);
    expect(cells[0]).toEqual({ col: 0, row: 0 });
    expect(cells[8]).toEqual({ col: 8, row: 0 });
    expect(cells[12]).toEqual({ col: 8, row: 4 });
    expect(cells[20]).toEqual({ col: 0, row: 4 });
    expect(cells[23]).toEqual({ col: 0, row: 1 });
    // The finish is the start's corner; every square shares a side with the one before it.
    expect(cellOf(24, 24)).toEqual(cells[0]);
    for (let sq = 1; sq <= 24; sq++) {
      const a = cellOf(sq - 1, 24);
      const b = cellOf(sq, 24);
      expect(Math.abs(a.col - b.col) + Math.abs(a.row - b.row)).toBe(1);
    }
    // Every square is on the edge: the 7 × 3 inside is left free.
    expect(cells.every((c) => c.row === 0 || c.row === 4 || c.col === 0 || c.col === 8)).toBe(true);
  });

  it("names the special squares of a setup", () => {
    const setup: RaceSetup = { boost: 6, trip: 9, portal: [11, 16], flip: 19 };
    expect([6, 9, 11, 16, 19, 7].map((sq) => squareKind(setup, sq))).toEqual(["boost", "trip", "portal", "portal", "flip", null]);
    expect(squareKind({ boost: 6, trip: 9 }, 11)).toBeNull();
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
    // A portal or flip square walks nobody anywhere.
    const portal = { m: "xinyi", dice: [2], steps: 2, from: 4, to: 6, square: "portal" as const, end: 11 };
    expect(stepPath(portal, 24, 2, 1)).toEqual({ hop: [5, 6], push: [] });
    const flip = { m: "xinyi", dice: [2], steps: 2, from: 4, to: 6, square: "flip" as const, end: 6 };
    expect(stepPath(flip, 24, 2, 1)).toEqual({ hop: [5, 6], push: [] });
  });

  it("knows which bets won", () => {
    expect(hits("win", "xinyi", RANKING)).toBe(true);
    expect(hits("top2", "jiaran", RANKING)).toBe(true);
    expect(hits("top2", "sinuo", RANKING)).toBe(false);
    expect(hits("last", "beila", RANKING)).toBe(true);
  });
});

// Races the server ran (server/tests/test_race.py writes the fixture and checks it still matches the rules).
describe("race replay against the server", () => {
  type Fixture = { track: number; boost: number; trip: number; races: { seed: string; setup: RaceSetup; start: string[]; order: string[]; moves: RaceStep[]; rest: { m: string; face: number }[]; ranking: string[] }[] };
  const F = fixture as unknown as Fixture;
  const kinds = new Set(F.races.flatMap((r) => r.moves.map((s) => s.square ?? "")));

  it("covers portals, flips, carrying and the walk back from the finish", () => {
    expect(kinds).toEqual(new Set(["", "boost", "trip", "portal", "flip"]));
    const moves = F.races.flatMap((r) => r.moves);
    expect(moves.some((s) => s.square === "portal" && s.end! > s.to)).toBe(true);
    expect(moves.some((s) => s.square === "portal" && s.end! < s.to)).toBe(true);
    expect(moves.some((s) => s.carry?.length)).toBe(true);
    expect(moves.some((s) => s.from + s.steps > F.track)).toBe(true);
    expect(F.races.some((r) => !r.setup.portal && r.setup.flip === undefined)).toBe(true);
    // A flip with others under the group, and a portal onto an occupied end.
    const onto = (kind: string, where: (s: RaceStep) => number) => F.races.some((r) => r.moves.some((s, i) =>
      s.square === kind && (stacksAt(r.start, r.moves, { done: i, current: -1, part: 0 }).get(where(s))?.length ?? 0) > 0));
    expect(onto("flip", (s) => s.to)).toBe(true);
    expect(onto("portal", (s) => s.end!)).toBe(true);
  });

  it("fills the last round's dice up to five, in the order", () => {
    for (const r of F.races) {
      const live = { ...r, id: 0, phase: "running", opensAt: 0, startsAt: 0, hash: "", odds: {}, pool: {}, mine: [], rollMs: 2400 } as unknown as Race;
      const last = roundDice(live, roundsOf(live) - 1);
      expect(last.map((d) => d.m)).toEqual(r.order);
      for (let k = 0; k < roundsOf(live); k++) expect(roundDice(live, k).map((d) => d.m)).toEqual(r.order);
    }
  });

  it("replays every race to the server's ranking", () => {
    for (const r of F.races) {
      const end = stacksAt(r.start, r.moves, { done: r.moves.length, current: -1, part: 0 });
      expect(rankOf(end)).toEqual(r.ranking);
      // Each step's group is the mover and what it carries, read off the stacks before it.
      for (let i = 0; i < r.moves.length; i++) {
        const s = r.moves[i];
        const before = stacksAt(r.start, r.moves, { done: i, current: -1, part: 0 }).get(s.from) ?? [];
        if (s.from) expect(before.slice(before.indexOf(s.m))).toEqual([s.m, ...(s.carry ?? [])]);
        expect(squareKind(r.setup, s.to) ?? undefined).toBe(s.square);
      }
    }
  });

  it("turns the stack on a flip square and takes a group through a portal at SQUARE_AT", () => {
    for (const r of F.races) {
      r.moves.forEach((s, i) => {
        if (s.square !== "flip" && s.square !== "portal") return;
        const at = (part: number) => stacksAt(r.start, r.moves, { done: i, current: i, part });
        const landed = at(SQUARE_AT - 0.01);
        const group = [s.m, ...(s.carry ?? [])];
        expect(landed.get(s.to)!.slice(-group.length)).toEqual(group);
        const acted = at(SQUARE_AT);
        if (s.square === "flip") expect(acted.get(s.to)).toEqual([...landed.get(s.to)!].reverse());
        else {
          expect(acted.get(s.end!)!.slice(-group.length)).toEqual(group);
          expect(acted.get(s.to) ?? []).toEqual(landed.get(s.to)!.slice(0, -group.length));
        }
      });
    }
  });
});

describe("a replay's clock", () => {
  const r = { id: 0, phase: "done", opensAt: 0, startsAt: 1000, endsAt: 1100, hash: "", setup: {}, odds: {}, pool: {}, mine: [] } as unknown as Race;

  it("plays from its start at the wall clock's pace, or twice as fast, and stops at the end", () => {
    expect(playLength(r)).toBe(100_000);
    const c = replayAt(r, 0, 50_000, 1);
    expect(replayTime(r, c, 50_000)).toBe(1_000_000);
    expect(replayTime(r, c, 60_000)).toBe(1_010_000);
    const fast = replayAt(r, 10_000, 60_000, 2);
    expect(replayTime(r, fast, 70_000)).toBe(1_030_000);
    expect(replayTime(r, fast, 999_000)).toBe(1_100_000);
    // A local clock that steps back never plays it backwards.
    expect(replayTime(r, fast, 59_000)).toBe(1_010_000);
  });

  it("jumps within the race only", () => {
    expect(replayAt(r, -5, 0, 1).from).toBe(0);
    expect(replayAt(r, 1e9, 0, 1).from).toBe(100_000);
  });

  it("names a race's day as the server does: the China day of its start", () => {
    // 2026-11-15 19:00 in China is 11:00 UTC.
    expect(chinaDay(Date.UTC(2026, 10, 15, 11) / 1000)).toBe("2026-11-15");
    expect(chinaDay(Date.UTC(2026, 10, 15, 16, 30) / 1000)).toBe("2026-11-16");
  });
});

// Races the server ran on its maps with skills dealt (server/app/race.py, the example economy): between them every
// special square and every skill acts.
import { computed, ref } from "vue";
import mapRaces from "./raceMaps.fixture.json";
import { createBoardStepper, createStackStepper, stepCursor, layoutOf, playStep, sceneryCells, skillText, squareOn, trackOf, SKILL_NAMES } from "./race";

describe("a race on a map with skills", () => {
  const races = mapRaces as unknown as { setup: RaceSetup; start: string[]; moves: RaceStep[]; ranking: string[] }[];

  it("is rebuilt from its moves alone, to the server's ranking", () => {
    for (const r of races) {
      const end = stacksAt(r.start, r.moves, { done: r.moves.length, current: -1, part: 0 });
      expect(rankOf(end)).toEqual(r.ranking);
    }
  });

  it("walks every step to the squares the server names", () => {
    for (const r of races) {
      const track = trackOf(r.setup, 24);
      expect(track).toBe(r.setup.map!.track);
      for (const s of r.moves) {
        const by = squareOn(r.setup, s.to)?.by ?? 0;
        const { hop, push } = stepPath(s, track, by, by);
        expect(hop[hop.length - 1]).toBe(s.to);
        if (s.square === "boost" || s.square === "trip" || s.square === "again") expect(push[push.length - 1]).toBe(s.end);
        if (s.square === "hook") expect(push[push.length - 1] ?? s.to).toBe(s.end);
        if (s.square === "portal" || s.square === "flip" || !s.square) expect(push).toEqual([]);
      }
    }
  });

  it("shows the die's face in the round's dice, whatever a skill added", () => {
    const moves: RaceStep[] = [
      { m: "a", dice: [2], steps: 4, from: 0, to: 4, skill: "burst" },
      { m: "b", dice: [3, 1], steps: 3, from: 0, to: 3, square: "again", end: 4 },
    ];
    expect(roundDice({ moves, rest: [] } as unknown as Race, 0).map((d) => d.face)).toEqual([2, 3]);
  });

  it("finds a map's squares from either end of a portal", () => {
    const setup: RaceSetup = { map: { id: "t", name: "t", track: 20, squares: [
      { at: 3, kind: "boost", by: 4 }, { at: 6, kind: "portal", to: 11 }, { at: 9, kind: "hook" },
    ] } };
    expect(squareOn(setup, 3)).toEqual({ at: 3, kind: "boost", by: 4 });
    expect(squareOn(setup, 6)?.to).toBe(11);
    expect(squareOn(setup, 11)).toEqual({ at: 11, kind: "portal", to: 6 });
    expect(squareKind(setup, 9)).toBe("hook");
    expect(squareKind(setup, 10)).toBeNull();
    // Before maps the boost and trip squares move by the config's numbers.
    expect(squareOn({ boost: 5, trip: 7, portal: [9, 13] }, 5, 2, -1)).toEqual({ at: 5, kind: "boost", by: 2 });
    expect(squareOn({ boost: 5, trip: 7, portal: [9, 13] }, 7, 2, -1)).toEqual({ at: 7, kind: "trip", by: 1 });
    expect(squareOn({ boost: 5, trip: 7, portal: [9, 13] }, 13)?.to).toBe(9);
  });

  it("leaves a solo's riders where they stood and puts a climber on top", () => {
    const stacks = new Map<number, string[]>([[3, ["a", "b", "c"]], [5, ["d"]]]);
    playStep(stacks, { m: "a", dice: [1], steps: 3, from: 3, to: 6, skill: "solo", left: ["b", "c"] });
    expect(stacks.get(3)).toEqual(["b", "c"]);
    expect(stacks.get(6)).toEqual(["a"]);
    playStep(stacks, { m: "b", dice: [2], steps: 2, from: 3, to: 5, carry: ["c"], react: ["d"], stack: ["b", "c", "d"] });
    expect(stacks.get(5)).toEqual(["b", "c", "d"]);
  });

  it("stops a dash on the finish it would pass", () => {
    expect(stepPath({ m: "a", dice: [3], steps: 3, from: 22, to: 24, skill: "dash" }, 24, 0, 0).hop).toEqual([23, 24]);
    expect(stepPath({ m: "a", dice: [3], steps: 3, from: 22, to: 23 }, 24, 0, 0).hop).toEqual([23, 24, 23]);
  });

  it("names a skill's moment after the skill", () => {
    expect(momentOf({ m: "a", dice: [2], steps: 4, from: 0, to: 4, skill: "burst" }, "b", "a")).toEqual({ kind: "skill", m: "a", from: HOP_AT });
    expect(momentOf({ m: "a", dice: [2], steps: 2, from: 0, to: 2, react: ["c"], stack: ["a", "c"] }, "b", "b"))
      .toEqual({ kind: "skill", m: "c", from: SQUARE_AT });
    for (const id of ["steady", "burst", "chase", "porter", "solo", "dash", "shield", "climb"]) {
      expect(SKILL_NAMES[id]).toBeTruthy();
      expect(skillText({ id, chance: 25, by: 2 })).toBeTruthy();
    }
  });
});

describe("a map's route on the board", () => {
  // "R3 D2 L3" from [1, 1]: seven squares, the finish under the start.
  const path: [number, number][] = [[1, 1], [2, 1], [3, 1], [4, 1], [4, 2], [4, 3], [3, 3], [2, 3], [1, 3]];

  it("puts every square on its cell, the board as large as the route, from its top left", () => {
    const board = layoutOf(8, path);
    expect(board).toMatchObject({ cols: 4, rows: 3, routed: true });
    expect(board.cell(0)).toEqual({ col: 0, row: 0 });
    expect(board.cell(4)).toEqual({ col: 3, row: 1 });
    // The finish is a square of its own; squares past either end stay on the ends.
    expect(board.cell(8)).toEqual({ col: 0, row: 2 });
    expect(board.cell(11)).toEqual({ col: 0, row: 2 });
    expect(board.cell(-1)).toEqual({ col: 0, row: 0 });
  });

  it("is the lap without a route, or with one of another length", () => {
    for (const board of [layoutOf(24), layoutOf(24, path)]) {
      expect(board).toMatchObject({ ...boardOf(24), routed: false });
      expect(board.cell(24)).toEqual(cellOf(0, 24));
      expect(board.cell(5)).toEqual(cellOf(5, 24));
    }
  });

  it("finds room for the scenery off the route, apart from each other", () => {
    const board = layoutOf(8, path);
    const cells = sceneryCells(board, 8, 3);
    const taken = new Set(path.map(([c, r]) => `${c - 1},${r - 1}`));
    expect(cells.length).toBeGreaterThan(0);
    for (const c of cells) expect(taken.has(`${c.col},${c.row}`)).toBe(false);
    for (const a of cells) for (const b of cells) if (a !== b) expect(Math.abs(a.col - b.col) + Math.abs(a.row - b.row)).toBeGreaterThan(1);
    // A board the route fills has none.
    expect(sceneryCells(layoutOf(2, [[0, 0], [1, 0], [2, 0]]), 2, 3)).toEqual([]);
  });

  it("updates downstream Vue computed squares when skipping a full completed step", () => {
    const start = ["a", "b"];
    const moves: RaceStep[] = [{ m: "a", dice: [2], steps: 2, from: 0, to: 2 }];
    const cursor = ref({ completed: 0, partial: -1 });
    const stepStacks = createStackStepper();
    const stacks = computed(() => stepStacks(start, moves, cursor.value.completed, cursor.value.partial));
    const squares = computed(() => Object.fromEntries(Object.entries(spots(stacks.value)).map(([m, s]) => [m, s.square])));

    const firstRef = stacks.value;
    expect(squares.value).toEqual({ a: 0, b: 0 });
    expect(stacks.value).toBe(firstRef);

    // Skipping an entire step while paused (`partial` stays -1) must return a fresh Map reference.
    cursor.value = { completed: 1, partial: -1 };
    expect(stacks.value).not.toBe(firstRef);
    expect(squares.value).toEqual({ a: 2, b: 0 });
  });
});

const fixtureRaces = (mapRaces as unknown as Pick<Required<Race>, "setup" | "start" | "moves" | "ranking">[]).map((fixture) => {
  const running = {
    ...fixture, id: 3600, opensAt: 3600, startsAt: 6900, phase: "running" as const, hash: "",
    odds: { win: {}, top2: {}, last: {} }, pool: {}, mine: [], leadMs: 4000, stepMs: 2400,
    slowFrom: Math.floor((fixture.moves.length - 1) / ROUND) * ROUND, slowMs: 3600,
  };
  const endsAt = running.startsAt + Math.ceil(stepStart(running, running.moves.length) / 1000);
  const times: number[] = [];
  for (let t = running.startsAt * 1000 - 250; t <= endsAt * 1000 + 1000; t += 250) times.push(t);
  return { race: { ...running, endsAt }, times };
});

function referenceHops(start: string[], moves: RaceStep[], h: Playhead) {
  const out: Record<string, string> = {};
  const upto = h.current >= 0 ? h.current : h.done - 1;
  const st = new Map<number, string[]>([[0, [...start]]]);
  for (let i = 0; i <= upto && i < moves.length; i++) {
    const s = moves[i];
    const under = i === h.current;
    if (under && h.part < HOP_AT) break;
    const acted = (s.end !== undefined || !!s.stack) && !(under && h.part < SQUARE_AT);
    playStep(st, s, acted);
    const key = `${i}${acted ? "b" : "a"}`;
    // Without a square the group has nothing more to do when a climber under it moves: it keeps its hop.
    for (const m of [s.m, ...(s.carry ?? [])]) out[m] = s.end === undefined ? `${i}a` : key;
    if (acted && s.square === "flip") for (const m of st.get(s.to) ?? []) out[m] = key;
    if (acted && s.react?.length) for (const m of s.stack ?? s.react) out[m] = key;
  }
  return out;
}

it.each(fixtureRaces)("records every quarter second on $race.setup.map.name (#$race.moves.length)", ({ race, times }) => {
  const frames = times.map((t) => {
    const h = playhead(race, t);
    return JSON.stringify({
      stacks: [...stacksAt(race.start, race.moves, h)],
      hops: referenceHops(race.start, race.moves, h),
      movers: moving(race.moves, h),
      hasLeader: h.done > 0 || (h.current >= 0 && h.part >= HOP_AT),
    });
  });
  expect(frames).toMatchSnapshot();
});

it.each(fixtureRaces)("steps and scrubs the full board on $race.setup.map.name (#$race.moves.length)", ({ race, times }) => {
  const shuffled = [...times];
  let seed = 42;
  for (let i = shuffled.length - 1; i > 0; i--) {
    seed = (Math.imul(1664525, seed) + 1013904223) >>> 0;
    const j = Math.floor((seed / 2 ** 32) * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }

  const stepBoard = createBoardStepper();
  const stepStacks = createStackStepper();
  let previous: { cursor: ReturnType<typeof stepCursor>; board: Map<number, string[]>; standings: Map<number, string[]> } | undefined;
  for (const t of [...times, ...shuffled]) {
    const h = playhead(race, t);
    const cursor = stepCursor(h);
    const { stacks, hops } = stepBoard(race.start, race.moves, cursor.completed, cursor.partial);
    const standings = stepStacks(race.start, race.moves, cursor.completed, cursor.partial);
    const expected = [...stacksAt(race.start, race.moves, h)];
    expect([...stacks]).toEqual(expected);
    expect([...standings]).toEqual(expected);
    expect(hops).toEqual(referenceHops(race.start, race.moves, h));
    expect(cursor.completed > 0 || cursor.partial >= 0).toBe(h.done > 0 || (h.current >= 0 && h.part >= HOP_AT));
    if (previous) {
      const same = cursor.completed === previous.cursor.completed && cursor.partial === previous.cursor.partial;
      expect(stacks === previous.board).toBe(same);
      expect(standings === previous.standings).toBe(same);
    }
    previous = { cursor, board: stacks, standings };
  }
});
