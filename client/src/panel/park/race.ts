// The dumpling race (protocol/PROTOCOL.md 团子赛跑): the answer of GET /api/park/race, the board at any moment of
// a race's playback, and the moments worth a word. Every client plays the same move list from the server's startsAt,
// so everything here is a pure function of the move list and the server time.

export type RaceKind = "win" | "top2" | "last";
export type RacePhase = "betting" | "starting" | "running" | "done" | "void";

/** manifest economy.park.race (scripts/asset_catalog.py PARK). */
export interface RaceConfig {
  interval: number;
  betting: number;
  track: number;
  dice: number[];
  payout: number;
  minOdds: number;
  depth: number;
  maxCoins: number;
  kinds: RaceKind[];
  squares: { range: [number, number]; boost: number; trip: number };
  roomAt: number;
}

export interface RaceStep {
  m: string;
  dice: number[];
  steps: number;
  from: number;
  to: number;
  carry?: string[];
  square?: "boost" | "trip";
  end?: number;
}

export interface RaceBet { kind: RaceKind; member: string; coins: number; odds: number; prize?: number }

export interface Race {
  id: number;
  phase: RacePhase;
  opensAt: number;
  startsAt: number;
  hash: string;
  setup: { boost: number; trip: number };
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
  stepMs?: number;
  /** The first move of the last round, which plays at slowMs a step. */
  slowFrom?: number;
  slowMs?: number;
  /** The lanes on the start line, top lane first. */
  start?: string[];
  moves?: RaceStep[];
  ranking?: string[];
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

/** When step [i] starts, ms after startsAt: the lead, then stepMs a step, and slowMs a step from slowFrom on. */
export function stepStart(race: Race, i: number): number {
  const step = race.stepMs ?? 1;
  const slowFrom = race.slowFrom ?? race.moves?.length ?? 0;
  const slow = race.slowMs ?? step;
  const lead = race.leadMs ?? 0;
  return i < slowFrom ? lead + i * step : lead + slowFrom * step + (i - slowFrom) * slow;
}

/** How long step [i] lasts, ms. */
export function stepLength(race: Race, i: number): number {
  const slowFrom = race.slowFrom ?? race.moves?.length ?? 0;
  return i < slowFrom ? race.stepMs ?? 1 : race.slowMs ?? race.stepMs ?? 1;
}

/** Where playback is at server time [t] (ms): steps fully done, the step under way (or -1), and how far into it. */
export interface Playhead { done: number; current: number; part: number }

export function playhead(race: Race, t: number): Playhead {
  const moves = race.moves ?? [];
  const at = t - race.startsAt * 1000;
  if (at < stepStart(race, 0)) return { done: 0, current: -1, part: 0 };
  // Few steps: a scan is plain and exact at the switch to the slow round.
  for (let i = 0; i < moves.length; i++) {
    const from = stepStart(race, i);
    const len = stepLength(race, i);
    if (at < from + len) return { done: i, current: i, part: (at - from) / len };
  }
  return { done: moves.length, current: -1, part: 0 };
}

/*
 * A step, as shares of its length: the die tumbles over the mover until HOP_AT; then the group hops to the square
 * the die gives (HOP_LEN of the step); a group that landed on the boost or trip square hops on to its end at
 * SQUARE_AT.
 */
export const HOP_AT = 0.3;
export const HOP_LEN = 0.24;
export const SQUARE_AT = 0.68;

// ---------------------------------------------------------------- the board

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
 * The squares after [head]: every step done, and the step under way once its hop has begun (at its landing square,
 * then past the boost or trip square from SQUARE_AT). Square 0 is the start line in lane order; the others stacks,
 * bottom to top.
 */
export function stacksAt(start: readonly string[], moves: readonly RaceStep[], head: Playhead): Map<number, string[]> {
  const stacks = new Map<number, string[]>([[0, [...start]]]);
  const upto = head.current >= 0 ? head.current + 1 : head.done;
  for (let i = 0; i < upto && i < moves.length; i++) {
    const s = moves[i];
    const under = i === head.current;
    if (under && head.part < HOP_AT) break;
    const group = lift(stacks, s.from, s.m);
    put(stacks, s.end === undefined || (under && head.part < SQUARE_AT) ? s.to : s.end, group);
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
