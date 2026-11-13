// The dumpling race (protocol/PROTOCOL.md 团子赛跑): the answer of GET /api/park/race, the board at any moment of
// a race's playback, and the short lines for skills and moods. Every client plays the same move list from the
// server's startsAt, so the board here is a pure function of the move list and the server time.

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
  sims: number;
  maxCoins: number;
  kinds: RaceKind[];
  squares: { range: [number, number]; boost: number; trip: number };
  skills: Record<string, RaceSkill>;
  moods: { id: string; delta: number; moves: number }[];
  roomAt: number;
}
export interface RaceSkill { kind: "snack" | "dash" | "reroll" | "catchup" | "steady"; on?: number; chance?: number; bonus?: number; steps?: number }

export interface RaceStep {
  m: string;
  dice: number[];
  steps: number;
  from: number;
  to: number;
  add?: [string, number][];
  snack?: number;
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
  setup: { moods: Record<string, string>; boost: number; trip: number };
  odds: Record<RaceKind, Record<string, number>>;
  pool: Record<string, { coins: number; bettors: number }>;
  mine: RaceBet[];
  seed?: string;
  endsAt?: number;
  leadMs?: number;
  stepMs?: number;
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

export const KIND_NAMES:Record<RaceKind, string> = { win: "冠军", top2: "前二", last: "垫底" };

export const MOOD_NAMES: Record<string, string> = {
  hot: "火热", excited: "兴奋", normal: "正常", sleepy: "有点困", slacking: "摸鱼",
};

export const SKILL_NAMES: Record<RaceSkill["kind"], string> = {
  snack: "加餐", steady: "稳步", dash: "冲刺", reroll: "重来", catchup: "追赶",
};

const pct = (p = 0) => `${Math.round(p * 100)}%`;

/** One short line of what a skill does, from its numbers. */
export function skillLine(s: RaceSkill): string {
  switch (s.kind) {
    case "snack":
      return `掷出 ${s.on}：${pct(s.chance)} 下次 +${s.bonus}`;
    case "steady":
      return `每次走 ${s.steps} 格`;
    case "dash":
      return `掷出 ${s.on}：${pct(s.chance)} 再 +${s.bonus}`;
    case "reroll":
      return `掷出 ${s.on}：${pct(s.chance)} 重掷`;
    case "catchup":
      return `垫底时 +${s.bonus}`;
  }
}

/** What a mood does, short: "前 4 次 +1"; "" for none. */
export function moodLine(m: { delta: number; moves: number } | undefined): string {
  if (!m || !m.delta || !m.moves) return "";
  return `前 ${m.moves} 次 ${m.delta > 0 ? "+" : "−"}${Math.abs(m.delta)}`;
}

/** Whether a bet of [kind] on [member] won with [ranking] (first to last). */
export function hits(kind: RaceKind, member: string, ranking: readonly string[]): boolean {
  if (kind === "win") return ranking[0] === member;
  if (kind === "top2") return ranking.slice(0, 2).includes(member);
  return ranking[ranking.length - 1] === member;
}

// ---------------------------------------------------------------- playback

/** A dumpling's place: its square and its height in the stack there (0 at the bottom). */
export interface Spot { square: number; level: number }

/** Where playback is at server time [t] (ms): steps fully done, the step under way (or -1), and how far into it. */
export interface Playhead { done: number; current: number; part: number }

export function playhead(race: Race, t: number): Playhead {
  const moves = race.moves ?? [];
  const step = race.stepMs ?? 1;
  const from = race.startsAt * 1000 + (race.leadMs ?? 0);
  if (t < from) return { done: 0, current: -1, part: 0 };
  const i = Math.floor((t - from) / step);
  if (i >= moves.length) return { done: moves.length, current: -1, part: 0 };
  return { done: i, current: i, part: (t - from - i * step) / step };
}

/** The share of a step after which a group that landed on a boost or trip square moves on to its end. */
export const SQUARE_AT = 0.55;

function lift(stacks: Map<number, string[]>, from: number, member: string): string[] {
  const s = stacks.get(from) ?? [];
  const k = s.indexOf(member);
  if (k < 0) return [member];
  const group = s.slice(k);
  if (k) stacks.set(from, s.slice(0, k));
  else stacks.delete(from);
  return group;
}

function put(stacks: Map<number, string[]>, square: number, group: string[]): void {
  stacks.set(square, [...(stacks.get(square) ?? []), ...group]);
}

/**
 * The stacks after [head]: every step done, and the step under way at its landing square (or past the boost or
 * trip square once its share SQUARE_AT is over). Squares map to their members, bottom to top.
 */
export function stacksAt(start: readonly string[], moves: readonly RaceStep[], head: Playhead): Map<number, string[]> {
  const stacks = new Map<number, string[]>([[0, [...start]]]);
  const upto = head.current >= 0 ? head.current + 1 : head.done;
  for (let i = 0; i < upto && i < moves.length; i++) {
    const s = moves[i];
    const group = lift(stacks, s.from, s.m);
    const partial = i === head.current && head.part < SQUARE_AT;
    if (s.end === undefined || partial) put(stacks, s.to, group);
    else put(stacks, s.end, group);
  }
  return stacks;
}

export function spots(stacks: Map<number, string[]>): Record<string, Spot> {
  const out: Record<string, Spot> = {};
  for (const [square, s] of stacks) s.forEach((m, level) => (out[m] = { square, level }));
  return out;
}

/** The members moving in the step under way (the mover and those it carries). */
export function moving(moves: readonly RaceStep[], head: Playhead): string[] {
  const s = head.current >= 0 ? moves[head.current] : undefined;
  return s ? [s.m, ...(s.carry ?? [])] : [];
}

/** Ranking from the final stacks: the higher square first, then the higher in a stack. */
export function rankOf(stacks: Map<number, string[]>): string[] {
  return [...stacks.entries()].sort((a, b) => b[0] - a[0]).flatMap(([, s]) => [...s].reverse());
}
