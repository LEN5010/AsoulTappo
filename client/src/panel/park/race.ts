// The dumpling race (protocol/PROTOCOL.md 团子赛跑): the answer of GET /api/park/race, the board at any moment of
// a race's playback, and the moments worth a word. Every client plays the same move list from the server's startsAt,
// so everything here is a pure function of the move list and the server time.

export type RaceKind = "win" | "top2" | "last";
export type RacePhase = "betting" | "starting" | "running" | "done" | "void";

/** manifest economy.park.race (scripts/asset_catalog.py PARK). */
export interface RaceConfig {
  interval: number;
  betting: number;
  /** The minute of the China day each race starts at (1140: one a day at 19:00); without it races start on multiples
   * of the interval. The server places the races; the client reads the times off them. */
  startAt?: number;
  track: number;
  dice: number[];
  payout: number;
  minOdds: number;
  depth: number;
  /** The range each member's popularity for a race is drawn from (inclusive); the server prices with it. */
  popularity?: [number, number];
  maxCoins: number;
  kinds: RaceKind[];
  /** portalGap: how far apart the portal's ends are, in squares (inclusive). */
  squares: { range: [number, number]; boost: number; trip: number; portalGap: [number, number] };
  /** The coins a race's win reaches to be told to the room. */
  roomAt: number;
}

export interface RaceStep {
  m: string;
  dice: number[];
  steps: number;
  from: number;
  to: number;
  carry?: string[];
  /** The special square landed on, and where the group is once it has acted (the same square for a flip). */
  square?: SquareKind;
  end?: number;
}

/** The special squares: boost and trip push the group on or back, a portal end takes it to the other, a flip turns
 * the stack there upside down. */
export type SquareKind = "boost" | "trip" | "portal" | "flip";

/**
 * A race's special squares, and each member's popularity, which the opening odds lean on; races dealt before the
 * portal and the flip square have neither, races dealt before popularity have none.
 */
export interface RaceSetup {
  boost: number;
  trip: number;
  portal?: [number, number];
  flip?: number;
  popularity?: Record<string, number>;
}

/** One die of the opening, rolled for the order of play. */
export interface OrderRoll { m: string; face: number }

/** A bet; once the race is settled, [prize] is what it won in coins, to a tenth (coins × odds). */
export interface RaceBet { kind: RaceKind; member: string; coins: number; odds: number; prize?: number }

export interface Race {
  id: number;
  phase: RacePhase;
  opensAt: number;
  startsAt: number;
  hash: string;
  setup: RaceSetup;
  /** The current odds; they move with the coins staked until the start. */
  odds: Record<RaceKind, Record<string, number>>;
  /** The coins staked on each selection. */
  pool: Partial<Record<RaceKind, Record<string, number>>>;
  /** Saves with a bet on this race. */
  bettors?: number;
  mine: RaceBet[];
  seed?: string;
  endsAt?: number;
  leadMs?: number;
  /** How long each round's dice take, before its first step; 0 on races from before them. */
  rollMs?: number;
  stepMs?: number;
  /** The first move of the last round, which plays at slowMs a step. */
  slowFrom?: number;
  slowMs?: number;
  /** The lanes on the start line, top lane first. */
  start?: string[];
  /** Who moves first to last, every round; missing on races from before the opening dice. */
  order?: string[];
  /** The opening's rounds of dice: everyone, then each round rolled again by those still tied. */
  rolls?: OrderRoll[][];
  moves?: RaceStep[];
  /** The dice of those after the winning move in the last round, in the order, drawn only to be shown. */
  rest?: OrderRoll[];
  ranking?: string[];
  /** My bets on the settled race, in coins: [won] is the bets' prizes summed and rounded half up. */
  result?: { staked: number; won: number; net: number };
}

export interface RaceAnswer {
  now: number;
  nextAt: number;
  race: Race | null;
  last: Race | null;
  winners: { id: number; member: string }[];
}

// The dumplings (scripts/make_tuanzi.py): 384px squares, bottom-aligned, content 90% of the width.
const ART = import.meta.glob<string>("../../assets/park/tuanzi/*.webp", { eager: true, query: "?url", import: "default" });
/** The picture of member [m]'s dumpling; "" when there is none. */
export const tuanziArt = (m: string): string =>
  Object.entries(ART).find(([path]) => path.endsWith(`/${m}.webp`))?.[1] ?? "";

export const KIND_NAMES: Record<RaceKind, string> = { win: "冠军", top2: "前二", last: "垫底" };

/** Whether a bet of [kind] on [member] won with [ranking] (first to last). */
export function hits(kind: RaceKind, member: string, ranking: readonly string[]): boolean {
  if (kind === "win") return ranking[0] === member;
  if (kind === "top2") return ranking.slice(0, 2).includes(member);
  return ranking[ranking.length - 1] === member;
}

// ---------------------------------------------------------------- timing

/** Moves a round: each member once, in the order (race.py run). */
export const ROUND = 5;

/** The round step [i] is in. */
export const roundOf = (i: number): number => Math.floor(i / ROUND);

/**
 * When step [i] starts, ms after startsAt: the lead, every round's dice up to its own (rollMs each), then stepMs a
 * step, and slowMs a step from slowFrom on (park_race.py playback_ms).
 */
export function stepStart(race: Race, i: number): number {
  const step = race.stepMs ?? 1;
  const slowFrom = race.slowFrom ?? race.moves?.length ?? 0;
  const slow = race.slowMs ?? step;
  const lead = (race.leadMs ?? 0) + (roundOf(i) + 1) * (race.rollMs ?? 0);
  return i < slowFrom ? lead + i * step : lead + slowFrom * step + (i - slowFrom) * slow;
}

/** How long step [i] lasts, ms. */
export function stepLength(race: Race, i: number): number {
  const slowFrom = race.slowFrom ?? race.moves?.length ?? 0;
  return i < slowFrom ? race.stepMs ?? 1 : race.slowMs ?? race.stepMs ?? 1;
}

/** When round [r]'s dice are thrown, ms after startsAt: rollMs before its first step. */
export const rollStart = (race: Race, r: number): number => stepStart(race, r * ROUND) - (race.rollMs ?? 0);

/** The rounds of a race: one more for every ROUND moves begun. */
export const roundsOf = (race: Race): number => Math.ceil((race.moves?.length ?? 0) / ROUND);

/**
 * Round [r]'s dice, in the order: the face each member's move rolls, and in the last round, for those after the
 * winning move, the faces drawn only to be shown (race.rest).
 */
export function roundDice(race: Race, r: number): OrderRoll[] {
  const out = (race.moves ?? []).slice(r * ROUND, (r + 1) * ROUND).map((s) => ({ m: s.m, face: s.steps }));
  return r === roundsOf(race) - 1 ? [...out, ...(race.rest ?? [])] : out;
}

/** Where playback is at server time [t] (ms): steps fully done, the step under way (or -1), and how far into it. */
export interface Playhead { done: number; current: number; part: number }

export function playhead(race: Race, t: number): Playhead {
  const moves = race.moves ?? [];
  const at = t - race.startsAt * 1000;
  // Few steps: a scan is plain and exact at the switch to the slow round. Between steps (a round's dice) nothing is
  // under way.
  for (let i = 0; i < moves.length; i++) {
    const from = stepStart(race, i);
    if (at < from) return { done: i, current: -1, part: 0 };
    const len = stepLength(race, i);
    if (at < from + len) return { done: i, current: i, part: (at - from) / len };
  }
  return { done: moves.length, current: -1, part: 0 };
}

/** The round whose dice are on show at server time [t] (ms), and how long ago they were thrown; null before the first. */
export function roundAt(race: Race, t: number): { round: number; since: number } | null {
  const at = t - race.startsAt * 1000;
  let round = -1;
  while (round + 1 < roundsOf(race) && at >= rollStart(race, round + 1)) round++;
  return round < 0 ? null : { round, since: at - rollStart(race, round) };
}

/*
 * A round's dice: thrown together at its start, each landing by DICE_TOSS of rollMs (staggered a little), then lying
 * still in a row until its steps begin.
 */
export const DICE_TOSS = 0.5;

/*
 * A step, as shares of its length: the mover lights up alone until HOP_AT; then the group hops to the square its die
 * gave (HOP_LEN of the step); from SQUARE_AT the special square it landed on acts (PUSH_LEN of the step), and the rest
 * of the step is still. At 2500 ms: 700 lit, 800 hopping, 700 for a special square, 300 still.
 */
export const HOP_AT = 0.28;
export const HOP_LEN = 0.32;
export const SQUARE_AT = HOP_AT + HOP_LEN;
export const PUSH_LEN = 0.28;

/** Where a step is: the mover lit, the group walking (and pushed on by a square). */
export type StepStage = "lit" | "walk";
export const stageOf = (part: number): StepStage => (part < HOP_AT ? "lit" : "walk");

/** A step of [len] ms in ms from its start: the hop, and what a special square does. */
export interface StepPhases { hopAt: number; hopLen: number; squareAt: number; pushLen: number }

export function stepPhases(len: number): StepPhases {
  return { hopAt: len * HOP_AT, hopLen: len * HOP_LEN, squareAt: len * SQUARE_AT, pushLen: len * PUSH_LEN };
}

/**
 * The step whose words are up at [head]: the one under way, or the one before while the next mover is still lit, so
 * a word that pops late in a step stays until the next group sets off. [part] is how far into that step.
 */
export function saidAt(head: Playhead): { i: number; part: number } | null {
  if (head.current < 0) return null;
  return head.current > 0 && head.part < HOP_AT ? { i: head.current - 1, part: 1 } : { i: head.current, part: head.part };
}

// ---------------------------------------------------------------- a die toss

/*
 * A die toss (RaceDie), as shares of its length: thrown up to TOSS_TOP, down on the ground at TOSS_LAND, where it
 * shows its face; then a squash and two smaller bounces. In the air it flashes other faces, AIR_FACES of them.
 */
export const TOSS_TOP = 0.38;
export const TOSS_LAND = 0.7;
export const AIR_FACES = 4;
/** How far apart the opening's dice leave the hand, ms. */
export const TOSS_STAGGER_MS = 35;

/** The faces a die flashes in the air before landing on [face]: from [pool], never [face], turned by [seed]. */
export function airFaces(face: number, pool: readonly number[], seed: number): number[] {
  const others = [...new Set(pool)].filter((f) => f !== face);
  if (!others.length) return [];
  return Array.from({ length: AIR_FACES }, (_, j) => others[(seed + j) % others.length]);
}

/** The [k]th of [n] dice tossed together within [len] ms: when it leaves and how long it flies, the last landing at [len]. */
export function staggered(len: number, k: number, n: number): { delay: number; ms: number } {
  const gap = Math.min(TOSS_STAGGER_MS, len / 4 / Math.max(1, n - 1));
  return { delay: k * gap, ms: len - (n - 1) * gap };
}

// ---------------------------------------------------------------- the opening

/*
 * Before the first step, inside leadMs (park_race.py lead_ms): round k of the order's dice starts OPEN_AT + k ×
 * REROLL_MS after startsAt and tumbles for OPEN_ROLL_MS; REROLL_MS after the last round starts, the field lines up in
 * its order and stands so until the first step. OPEN_AT leaves time for the poll that brings the dice: the server
 * starts a race on its next tick, about a second after startsAt.
 */
export const OPEN_AT = 1500;
export const OPEN_ROLL_MS = 800;
export const REROLL_MS = 1500;

export interface Opening {
  /** The round of dice on show (0 is everyone), -1 before the first. */
  round: number;
  /** The members rolling in that round; their dice tumble until it lands. */
  rolling: string[];
  tumbling: boolean;
  /** How long ago that round's dice left the hand, ms. */
  since: number;
  /**
   * The face each member's die shows: while the dice are out, its latest roll that has landed; once the field lines
   * up, its first-round roll, so the faces read high to low along the order (the rerolls have already played).
   */
  faces: Record<string, number>;
  /** The order is settled and the field lines up in it. */
  lined: boolean;
}

/** The opening at server time [t] (ms), or null when the race has none (an older race) or it is over. */
export function openingAt(race: Race, t: number): Opening | null {
  const rolls = race.rolls;
  if (!rolls?.length || !race.order) return null;
  const at = t - race.startsAt * 1000;
  if (at >= (race.leadMs ?? 0)) return null;
  let round = -1;
  while (round + 1 < rolls.length && at >= OPEN_AT + (round + 1) * REROLL_MS) round++;
  const tumbling = round >= 0 && at < OPEN_AT + round * REROLL_MS + OPEN_ROLL_MS;
  const lined = at >= OPEN_AT + rolls.length * REROLL_MS;
  const faces: Record<string, number> = {};
  const upto = lined ? 0 : round - (tumbling ? 1 : 0);
  for (let k = 0; k <= upto; k++) for (const r of rolls[k]) faces[r.m] = r.face;
  const since = round >= 0 ? at - (OPEN_AT + round * REROLL_MS) : 0;
  return { round, rolling: round >= 0 ? rolls[round].map((r) => r.m) : [], tumbling, since, faces, lined };
}

// ---------------------------------------------------------------- the board

/*
 * The board is a ring of `track` squares, all the same size, round a rectangle BOARD_ROWS squares high (24 squares:
 * 9 × 5; of the rings 24 squares make, 8 × 6 gives smaller squares in every panel the race is shown in). Square 0,
 * the start, is the top left corner and also square `track`, the finish; the squares go clockwise: along the top to
 * the right, down the right side, back along the bottom, up the left side. A unit is a square's side.
 */
export const BOARD_ROWS = 5;

/** The board's size in squares (and units): across and down. */
export interface Board { cols: number; rows: number }

/** The board for a [track] (even, 14 or more). */
export function boardOf(track: number): Board {
  return { cols: track / 2 + 2 - BOARD_ROWS, rows: BOARD_ROWS };
}

/** The squares in the corners, clockwise from the start. */
export function cornersOf(track: number): number[] {
  const { cols, rows } = boardOf(track);
  return [0, cols - 1, cols + rows - 2, 2 * cols + rows - 3];
}

/** A square on the board: its column and row from the top left, which are also its top left corner in units. */
export interface Cell { col: number; row: number }

/** Where [square] sits on the board; square `track` is square 0. */
export function cellOf(square: number, track: number): Cell {
  const { cols, rows } = boardOf(track);
  let p = ((square % track) + track) % track;
  if (p < cols) return { col: p, row: 0 };
  if ((p -= cols - 1) < rows) return { col: cols - 1, row: p };
  if ((p -= rows - 1) < cols) return { col: cols - 1 - p, row: rows - 1 };
  return { col: 0, row: rows - 1 - (p - cols + 1) };
}

/** The special square on [square] of [setup], if any. */
export function squareKind(setup: RaceSetup | undefined, square: number): SquareKind | null {
  if (!setup) return null;
  if (square === setup.boost) return "boost";
  if (square === setup.trip) return "trip";
  if (setup.portal?.includes(square)) return "portal";
  if (square === setup.flip) return "flip";
  return null;
}

/** Where a move of [steps] from [from] ends: past the finish it walks back from it (race.py bounce). */
export const bounce = (square: number, track: number): number =>
  square > track ? 2 * track - square : Math.max(0, square);

/**
 * The squares a group passes, one at a time, moving [steps] (back when negative) from [from]: up to the finish and
 * back down from it when the move carries past it. The last is where it lands.
 */
export function walkPath(from: number, steps: number, track: number): number[] {
  const out: number[] = [];
  let at = from;
  let dir = Math.sign(steps);
  for (let k = 0; k < Math.abs(steps); k++) {
    if (dir > 0 && at >= track) dir = -1;
    if (dir < 0 && at <= 0) break;
    at += dir;
    out.push(at);
  }
  return out;
}

/**
 * The squares of step [s], one at a time: the hop the die gives, then the push of a boost (+[boost]) or trip (−[trip])
 * square, each ending where the server says (to, end). A portal or flip square walks no squares: push is empty.
 */
export function stepPath(s: RaceStep, track: number, boost: number, trip: number): { hop: number[]; push: number[] } {
  const hop = walkPath(s.from, s.steps, track);
  const walks = s.square === "boost" || s.square === "trip";
  const push = s.end === undefined || !walks ? [] : walkPath(s.to, s.square === "trip" ? -trip : boost, track);
  return { hop, push };
}

/** A dumpling's place: its square and its height in the stack there (0 at the bottom); on square 0, its lane. */
export interface Spot { square: number; level: number; lane?: number }

/**
 * Square 0 holds the dumplings still on the start line, side by side in lane order; every other square a stack,
 * bottom to top. A move from square 0 takes the mover alone; anywhere else it takes those above it too.
 */
function lift(stacks: Map<number, string[]>, from: number, member: string): string[] {
  const s = stacks.get(from) ?? [];
  const k = s.indexOf(member);
  if (k < 0) return [member];
  const group = from === 0 ? [member] : s.slice(k);
  const rest = from === 0 ? s.filter((m) => m !== member) : s.slice(0, k);
  if (rest.length) stacks.set(from, rest);
  else stacks.delete(from);
  return group;
}

function put(stacks: Map<number, string[]>, square: number, group: string[]): void {
  stacks.set(square, [...(stacks.get(square) ?? []), ...group]);
}

/**
 * Plays step [s] on [stacks]: the group lifted off its square and put on top at its landing square; with [acted], the
 * special square there acts too: the group goes on to `end` (a boost, trip or portal square), or the whole stack on
 * the flip square turns upside down, the group just put on top included (race.py run).
 */
export function playStep(stacks: Map<number, string[]>, s: RaceStep, acted = true): void {
  const group = lift(stacks, s.from, s.m);
  put(stacks, s.end === undefined || !acted ? s.to : s.end, group);
  if (acted && s.square === "flip") stacks.get(s.to)?.reverse();
}

/**
 * The squares after [head]: every step done, and the step under way once its hop has begun (at its landing square,
 * then, from SQUARE_AT, past the special square there). Square 0 is the start line in lane order; the others stacks,
 * bottom to top.
 */
export function stacksAt(start: readonly string[], moves: readonly RaceStep[], head: Playhead): Map<number, string[]> {
  const stacks = new Map<number, string[]>([[0, [...start]]]);
  const upto = head.current >= 0 ? head.current + 1 : head.done;
  for (let i = 0; i < upto && i < moves.length; i++) {
    const under = i === head.current;
    if (under && head.part < HOP_AT) break;
    playStep(stacks, moves[i], !(under && head.part < SQUARE_AT));
  }
  return stacks;
}

export function spots(stacks: Map<number, string[]>): Record<string, Spot> {
  const out: Record<string, Spot> = {};
  for (const [square, s] of stacks) {
    s.forEach((m, k) => (out[m] = square ? { square, level: k } : { square, level: 0, lane: k }));
  }
  return out;
}

/** The members moving in the step under way (the mover and those it carries). */
export function moving(moves: readonly RaceStep[], head: Playhead): string[] {
  const s = head.current >= 0 ? moves[head.current] : undefined;
  return s ? [s.m, ...(s.carry ?? [])] : [];
}

/**
 * The order on the track, first to last: the higher square first, then the higher in a stack; on the start line
 * the top lane first (as the server ranks).
 */
export function rankOf(stacks: Map<number, string[]>): string[] {
  return [...stacks.entries()].sort((a, b) => b[0] - a[0]).flatMap(([square, s]) => (square ? [...s].reverse() : s));
}

/** The leader after each step in full (index i: after step i). */
export function leaders(start: readonly string[], moves: readonly RaceStep[]): string[] {
  return moves.map((_, i) => rankOf(stacksAt(start, moves, { done: i + 1, current: -1, part: 0 }))[0]);
}

// ---------------------------------------------------------------- moments worth a word

export type MomentKind = "lead" | "boost" | "trip" | "carry";

/** A word over the mover in the step under way: what, from which share of the step on. */
export interface Moment { kind: MomentKind; m: string; from: number }

/**
 * The step's moment, if any, by weight: a fall on the trip square, a push on the boost square, taking the lead,
 * carrying others along. [before] is the leader before the step, [after] the leader once it is done.
 */
export function momentOf(s: RaceStep, before: string | undefined, after: string | undefined): Moment | null {
  if (s.square === "trip") return { kind: "trip", m: s.m, from: SQUARE_AT };
  if (s.square === "boost") return { kind: "boost", m: s.m, from: SQUARE_AT };
  if (after && before !== after && [s.m, ...(s.carry ?? [])].includes(after)) {
    return { kind: "lead", m: after, from: HOP_AT + HOP_LEN };
  }
  if (s.carry?.length) return { kind: "carry", m: s.m, from: HOP_AT + HOP_LEN };
  return null;
}
