// The dumpling race (protocol/PROTOCOL.md 团子赛跑): the answer of GET /api/park/race, the board at any moment of
// a race's playback, and the moments worth a word. Every client plays the same move list from the server's startsAt,
// so everything here is a pure function of the move list and the server time.

export type RaceKind = "win" | "top2" | "last";
export type RacePhase = "betting" | "starting" | "running" | "done" | "void";

/** economy.park.race (server/app/economy.py). */
export interface RaceConfig {
  interval: number;
  betting: number;
  /** The minute of the China day each race starts at (1140: one a day at 19:00); without it races start on multiples
   * of the interval. The server places the races; the client reads the times off them. */
  startAt?: number;
  track: number;
  /** The die of races dealt before forms. */
  dice: number[];
  /** The forms a race deals its members, each with the faces of the die it rolls for that race. */
  forms?: RaceForm[];
  /** The maps a race is run on, one drawn for each; without them, the lap of `track` with five squares dealt. */
  maps?: RaceMap[];
  /** The skills a race deals its members instead of forms, each with the faces of its die. */
  skills?: (RaceSkill & { dice: number[] })[];
  /** Simulated races behind a race's chances. */
  sims?: number;
  payout: number;
  minOdds: number;
  /** The most a bet pays of its fair odds: odds × chance stays at or under it. */
  fairCap?: number;
  depth: number;
  /** The popularity range of races dealt before forms (inclusive). */
  popularity?: [number, number];
  /** The most a save stakes on a race; 0 or missing, any number. */
  maxCoins?: number;
  kinds: RaceKind[];
  /** portalGap: how far apart the portal's ends are, in squares (inclusive). */
  squares: { range: [number, number]; boost: number; trip: number; portalGap: [number, number] };
  /** The coins a race's win reaches to be told to the room. */
  roomAt: number;
  /** The order of play drawn again every round from the second on (1.3.0). */
  shuffle?: boolean;
  /** The alpaca: out on the finish once a dumpling is past the middle, driving back towards the start (1.3.0). */
  alpaca?: { dice: number[] };
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
  /** The mover's skill, when it acted in this step. */
  skill?: string;
  /** A solo's riders, left behind on the square it moved from. */
  left?: string[];
  /** The climbers the group landed on, gone to the top; [stack] is the square then, bottom to top. */
  react?: string[];
  stack?: string[];
}

/** The special squares: boost and trip push the group on or back, a portal end takes it to the other, a flip turns
 * the stack there upside down, again rolls the mover's die once more, a hook pulls the group onto the nearest
 * dumplings ahead. */
export type SquareKind = "boost" | "trip" | "portal" | "flip" | "again" | "hook";

/** A special square of a map: where, what, and its number: the squares a boost or trip moves, a portal's other end. */
export interface MapSquare { at: number; kind: SquareKind; by?: number; to?: number }

/**
 * A map a race is run on: its own lap and squares. With a `path` the squares take a route across the board instead
 * of the lap: the cell ([column, row] from the top left) of every square from the start (0) to the finish (`track`).
 */
export interface RaceMap { id: string; name: string; track: number; squares: MapSquare[]; path?: [number, number][] }

/** A skill as a race deals it: `chance` in percent, `by` in squares, as the skill needs them. */
export interface RaceSkill { id: string; chance?: number; by?: number }

export const SKILL_NAMES: Record<string, string> = {
  steady: "稳健", burst: "爆发", chase: "追赶", porter: "驮运", solo: "独行", dash: "冲线", shield: "护盾", climb: "登顶",
};

/** What a skill does, in a few words. */
export function skillText(k: RaceSkill): string {
  switch (k.id) {
    case "burst": return `${k.chance}% 概率走两倍点数`;
    case "chase": return `排在最后时多走 ${k.by} 格`;
    case "porter": return `背着团子时多走 ${k.by} 格`;
    case "solo": return `${k.chance}% 独走，每留一只 +${k.by} 格`;
    case "dash": return "超过终点时停在终点";
    case "shield": return "不受绊倒和回退传送影响";
    case "climb": return "被叠上时移到最上层";
    default: return "无额外效果";
  }
}

/** A form a race deals: its id and the faces of the die its member rolls. */
export interface RaceForm { id: string; dice: number[] }

/** The forms' names, best first. */
export const FORM_NAMES: Record<string, string> = { great: "极佳", good: "良好", normal: "普通", tired: "疲惫", poor: "很差" };

/**
 * A race's special squares; each member's form, the die it rolls for the race and how often it took each kind's
 * places over `chance.sims` simulated races, which the odds open at. Races dealt before the portal and the flip square
 * have neither; races dealt before forms have no forms, dice or chance (everyone rolls the config's dice) and may
 * have each member's popularity, which their opening odds leaned on.
 */
export interface RaceSetup {
  /** Races dealt before maps: where the boost and trip squares are (they move by the config's numbers). */
  boost?: number;
  trip?: number;
  portal?: [number, number];
  flip?: number;
  /** The map the race is run on, with its own lap and squares, and each member's skill. */
  map?: RaceMap;
  skills?: Record<string, RaceSkill>;
  forms?: Record<string, string>;
  dice?: Record<string, number[]>;
  chance?: { sims: number } & Record<RaceKind, Record<string, number>>;
  popularity?: Record<string, number>;
  /** Races run by the rules beyond the squares (1.3.0): the order drawn every round, and the alpaca, out once a
   * dumpling is past square [at] (the middle of the track), with the faces of its die. */
  shuffle?: boolean;
  alpaca?: { at: number; dice: number[] };
}

export interface RacePace { lit: number; hop: number; gap: number; act: number; rest: number }

/** One die of the opening, rolled for the order of play. */
export interface OrderRoll { m: string; face: number }

/** A bet; once the race is settled, [prize] is what it won in coins, to a tenth (coins × odds). */
export interface RaceBet { kind: RaceKind; member: string; coins: number; odds: number; prize?: number }

/** A close-up: before step [at] moves, member [m]'s skill is named and explained. */
export interface RaceCut { at: number; m: string }

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
  /** The steps that open with a close-up of a member's skill (the first time it is at work), and how long each holds its step back. */
  cuts?: RaceCut[];
  cutMs?: number;
  /**
   * A race paced by the square (park_race.py paced_times): every step's own length, and the times it is made of:
   * the mover lit, a hop of one square, the pause before a special square acts, a square that moves the group
   * without walking it, and the rest after.
   */
  stepsMs?: number[];
  pace?: RacePace;
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
  /** Started races: whether the move list is there to play (false on old races whose list is gone: result only). */
  replay?: boolean;
  /**
   * Races run by the rules beyond the squares (setup.shuffle, setup.alpaca): each round's order (ALPACA for the
   * alpaca once it takes turns) and with setup.shuffle the dice it was rolled for by, as [rolls] are the opening's
   * ([] for the first round, which the opening decides), the alpaca's turns, and the step after which it came out;
   * and their times: each round of the dice for an order, the change of order after them, opening each round from the
   * second, each turn's length and the pace it is made of, the alpaca's coming out (park_race.py paced_times).
   */
  orders?: string[][];
  orderRolls?: OrderRoll[][][];
  drives?: RaceDrive[];
  enter?: number;
  orderRollMs?: number;
  shuffleMs?: number;
  drivesMs?: number[];
  drivePace?: DrivePace;
  enterMs?: number;
}

/** The alpaca's name in a race's orders and rest (race.py ALPACA). */
export const ALPACA = "alpaca";

/**
 * One of the alpaca's turns (race.py run): in round [r], before step [at], rolling [face]; it drives from square
 * [from] to [to], towards the start. [back]: the square it left for the finish before driving, nobody being ahead of
 * it; [take]: the square it stopped on, bottom to top, when it carried anyone; [home]: it went back to the finish
 * after, nobody being left ahead of it, and left them there.
 */
export interface RaceDrive {
  r: number; at: number; face: number; from: number; to: number; back?: number; take?: string[]; home?: boolean;
}

/** The pace of the alpaca's turns, ms (park_race.py DRIVE): its die lit, a way to or from the finish, a square
 * driven, picking up its riders, the rest after. */
export interface DrivePace { lit: number; away: number; sq: number; take: number; rest: number }

/** A finished race in GET /api/park/race/history: [day] is the China day of its start. */
export interface RacePast {
  id: number;
  day: string;
  startsAt: number;
  phase: "done" | "void";
  ranking?: string[];
  replay?: boolean;
  /** My bets on it in coins; a void race's came back in full (net 0, no won). */
  mine?: { staked: number; won?: number; net: number };
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

/** The close-up step [i] opens with, if any. */
export const cutOf = (race: Race, i: number): RaceCut | undefined => race.cuts?.find((c) => c.at === i);

/** How long step [i]'s close-up holds it back, ms: cutMs, or 0 without one. */
export const cutLength = (race: Race, i: number): number => (cutOf(race, i) ? race.cutMs ?? 0 : 0);

/**
 * When step [i]'s turn starts, ms after startsAt: the lead, every round's dice up to its own (rollMs each), then stepMs
 * a step, slowMs a step from slowFrom on, and cutMs for every close-up before it (park_race.py playback_ms). Its own
 * close-up comes first in its turn: it moves cutLength() later.
 */
export function stepStart(race: Race, i: number): number {
  const tl = timelineOf(race);
  if (tl) return i < tl.steps.length ? tl.beats[tl.steps[i]!]!.at : tl.end;
  const step = race.stepMs ?? 1;
  const slowFrom = race.slowFrom ?? race.moves?.length ?? 0;
  const slow = race.slowMs ?? step;
  const lead = (race.leadMs ?? 0) + (roundOf(i) + 1) * (race.rollMs ?? 0);
  const cuts = (race.cuts?.filter((c) => c.at < i).length ?? 0) * (race.cutMs ?? 0);
  if (race.stepsMs) return cuts + lead + before(race.stepsMs)[Math.min(i, race.stepsMs.length)]!;
  return cuts + (i < slowFrom ? lead + i * step : lead + slowFrom * step + (i - slowFrom) * slow);
}

/** Running totals of a paced race's step lengths: [i] is what the steps before step i take. */
const totals = new WeakMap<number[], number[]>();
function before(steps: number[]): number[] {
  let out = totals.get(steps);
  if (!out) {
    out = [0];
    for (const ms of steps) out.push(out[out.length - 1]! + ms);
    totals.set(steps, out);
  }
  return out;
}

/** How long step [i] lasts, ms. */
export function stepLength(race: Race, i: number): number {
  if (race.stepsMs) return race.stepsMs[i] ?? 1;
  const slowFrom = race.slowFrom ?? race.moves?.length ?? 0;
  return i < slowFrom ? race.stepMs ?? 1 : race.slowMs ?? race.stepMs ?? 1;
}

// ---------------------------------------------------------------- the rules beyond the squares, in time

/*
 * A race run by the order rolled for every round and the alpaca plays as a row of beats, ms after startsAt (park_race.py
 * paced_ms): from the second round on a round opens with the dice for its order (orderRollMs for each round of them;
 * none on races from before them) and the change of order (shuffleMs), then its dice (rollMs), then
 * the turns in the round's order: a member's step (its close-up first, then the step) or the alpaca's drive
 * (drivesMs); right after the step that brought the alpaca out comes its coming out (enterMs). The turns after the
 * winning move are only shown (rest). A drive need not be in the round of the step it comes before: the alpaca last
 * in a round and first in the next drives twice before the same step, the next round's change of order and dice in
 * between, so the beats follow the orders, never the drives' `at`.
 */
export type BeatKind = "order" | "shuffle" | "roll" | "step" | "drive" | "enter";
export interface Beat {
  kind: BeatKind;
  /** The round it is in. */
  r: number;
  /** The step of a step's beat, the drive of a drive's; -1 otherwise. */
  i: number;
  at: number;
  len: number;
  /** The steps done before it. */
  done: number;
}

/** The share of enterMs the alpaca's close-up takes; then it drives onto the finish. */
export const ENTER_CUT = 2 / 3;

/**
 * A change of where the alpaca is: out onto the finish ("enter"), off its square for the finish before drive [k]
 * ("back"), drive [k] setting off, taking those it reaches along ("glide"), back to the finish after it ("home").
 * [before]: the step it comes before; [at]: when, ms after startsAt.
 */
export interface CarEvent { kind: "enter" | "back" | "glide" | "home"; k: number; before: number; at: number }

/** A race's beats in time order; each step's and each round's dice's beat; the car's changes; when the last ends. */
export interface Timeline { beats: Beat[]; steps: number[]; rolls: number[]; cars: CarEvent[]; end: number }

const timelines = new WeakMap<Race, Timeline | null>();

/** The beats of a race run by the rules beyond the squares (it has `orders`); null for any other. Once a race. */
export function timelineOf(race: Race): Timeline | null {
  let out = timelines.get(race);
  if (out === undefined) {
    out = buildTimeline(race);
    timelines.set(race, out);
  }
  return out;
}

function buildTimeline(race: Race): Timeline | null {
  const orders = race.orders;
  const moves = race.moves;
  if (!orders?.length || !moves?.length) return null;
  const drives = race.drives ?? [];
  const beats: Beat[] = [];
  const steps: number[] = [];
  const rolls: number[] = [];
  const cars: CarEvent[] = [];
  let at = race.leadMs ?? 0;
  let i = 0;
  let k = 0;
  const push = (kind: BeatKind, r: number, n: number, len: number) => {
    beats.push({ kind, r, i: n, at, len, done: i });
    at += len;
  };
  for (let r = 0; r < orders.length && i < moves.length; r++) {
    const dice = r > 0 ? race.orderRolls?.[r]?.length ?? 0 : 0;
    if (dice && race.orderRollMs) push("order", r, -1, dice * race.orderRollMs);
    if (r > 0 && race.shuffleMs) push("shuffle", r, -1, race.shuffleMs);
    rolls.push(beats.length);
    push("roll", r, -1, race.rollMs ?? 0);
    for (const who of orders[r]!) {
      if (i >= moves.length) break;
      if (who === ALPACA) {
        const d = drives[k];
        if (!d || d.r !== r) continue;
        const from = at;
        const p = driveTimes(race, k);
        push("drive", r, k, race.drivesMs?.[k] ?? p.len);
        if (d.back !== undefined) cars.push({ kind: "back", k, before: i, at: from + p.backAt });
        cars.push({ kind: "glide", k, before: i, at: from + p.glideAt });
        if (d.home) cars.push({ kind: "home", k, before: i, at: from + p.homeAt });
        k++;
        continue;
      }
      steps.push(beats.length);
      push("step", r, i, cutLength(race, i) + stepLength(race, i));
      i++;
      if (race.enter === i - 1) {
        const from = at;
        if (race.enterMs) push("enter", r, -1, race.enterMs);
        cars.push({ kind: "enter", k: -1, before: i, at: from + (race.enterMs ?? 0) * ENTER_CUT });
      }
    }
  }
  return { beats, steps, rolls, cars, end: at };
}

/** The playhead of a race with a timeline at [at] ms after startsAt. */
function playheadOn(race: Race, tl: Timeline, at: number): Playhead {
  const n = race.moves?.length ?? 0;
  let driven = 0;
  while (driven < tl.cars.length && tl.cars[driven]!.at <= at) driven++;
  // The last beat begun by then.
  const beats = tl.beats;
  let lo = 0;
  let hi = beats.length - 1;
  let b = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (beats[mid]!.at <= at) {
      b = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  if (b < 0) return { done: 0, current: -1, part: 0, driven };
  const beat = beats[b]!;
  const into = at - beat.at;
  if (into >= beat.len) return { done: b === beats.length - 1 ? n : beat.done + (beat.kind === "step" ? 1 : 0), current: -1, part: 0, driven };
  if (beat.kind === "step") {
    const i = beat.i;
    const cut = cutLength(race, i);
    if (into < cut) return { done: i, current: i, part: 0, cut: into / cut, driven };
    const ms = into - cut;
    return { done: i, current: i, part: race.pace ? partAt(stepTimes(race, i), ms) : ms / stepLength(race, i), ms, driven };
  }
  if (beat.kind === "drive") return { done: beat.done, current: -1, part: 0, driven, drive: { k: beat.i, ms: into } };
  if (beat.kind === "order") return { done: beat.done, current: -1, part: 0, driven, order: { r: beat.r, ms: into } };
  if (beat.kind === "shuffle") return { done: beat.done, current: -1, part: 0, driven, shuffle: { r: beat.r, ms: into } };
  if (beat.kind === "enter") return { done: beat.done, current: -1, part: 0, driven, enter: into };
  return { done: beat.done, current: -1, part: 0, driven };
}

/**
 * One of the alpaca's drives in ms from its start (park_race.py drive_ms): its die lit; back to the finish first
 * (from backAt, for backLen); the drive (from glideAt, for glideLen); picking its riders up (takeAt, takeLen); home
 * to the finish after (homeAt, homeLen); the rest. In the last round slower by the same factor as the steps; the
 * server's length stands, and times that would not fit in it shrink together.
 */
export interface DrivePhases {
  len: number; backAt: number; backLen: number; glideAt: number; glideLen: number; takeAt: number; takeLen: number;
  homeAt: number; homeLen: number;
}

const DRIVE_PACE: DrivePace = { lit: 600, away: 900, sq: 300, take: 300, rest: 500 };

export function driveTimes(race: Race, k: number): DrivePhases {
  const d = race.drives?.[k];
  const len = race.drivesMs?.[k] ?? 1;
  if (!d) return { len, backAt: 0, backLen: 0, glideAt: 0, glideLen: 0, takeAt: 0, takeLen: 0, homeAt: 0, homeLen: 0 };
  const pace = race.drivePace ?? DRIVE_PACE;
  const last = Math.floor((race.slowFrom ?? Infinity) / ROUND);
  const slow = d.r >= last && race.stepMs ? (race.slowMs ?? race.stepMs) / race.stepMs : 1;
  const lit = pace.lit * slow;
  const back = d.back !== undefined ? pace.away * slow : 0;
  const glide = Math.abs(d.from - d.to) * pace.sq * slow;
  const take = d.take?.length ? pace.take * slow : 0;
  const home = d.home ? pace.away * slow : 0;
  const fit = Math.min(1, len / Math.max(1, lit + back + glide + take + home + pace.rest * slow));
  const backAt = lit * fit;
  const glideAt = backAt + back * fit;
  const takeAt = glideAt + glide * fit;
  const homeAt = takeAt + take * fit;
  return { len, backAt, backLen: back * fit, glideAt, glideLen: glide * fit, takeAt, takeLen: take * fit, homeAt, homeLen: home * fit };
}

/*
 * The car's way along a drive: a smooth start over the first GLIDE_EASE of its time, an even speed, a smooth stop
 * over the last. glideAt gives how far along the way it is at a share of the time, glideWhen the share of the time it
 * gets there, so the riders are picked up just as the car reaches them.
 */
export const GLIDE_EASE = 0.14;
const GLIDE_TOP = 1 / (1 - GLIDE_EASE);

export function glideAt(u: number): number {
  const x = Math.min(1, Math.max(0, u));
  if (x < GLIDE_EASE) return (GLIDE_TOP * x * x) / (2 * GLIDE_EASE);
  if (x > 1 - GLIDE_EASE) return 1 - (GLIDE_TOP * (1 - x) ** 2) / (2 * GLIDE_EASE);
  return GLIDE_TOP * (GLIDE_EASE / 2 + x - GLIDE_EASE);
}

export function glideWhen(p: number): number {
  const y = Math.min(1, Math.max(0, p));
  const edge = (GLIDE_TOP * GLIDE_EASE) / 2;
  if (y < edge) return Math.sqrt((2 * GLIDE_EASE * y) / GLIDE_TOP);
  if (y > 1 - edge) return 1 - Math.sqrt((2 * GLIDE_EASE * (1 - y)) / GLIDE_TOP);
  return GLIDE_EASE + y / GLIDE_TOP - GLIDE_EASE / 2;
}

/** A square one of the alpaca's drives picked dumplings up from, and its stack then, bottom to top. */
export interface Pickup { sq: number; stack: string[] }

const pickupCache = new WeakMap<Race, Pickup[][]>();

/**
 * Each drive's pickups, in the order the car reached them: its own square first (those riding it), then on towards
 * the start. Put together the other way round, bottom to top, they make the drive's `take`. Worked out once a race.
 */
export function pickupsOf(race: Race, track: number): Pickup[][] {
  const known = pickupCache.get(race);
  if (known) return known;
  const tl = timelineOf(race);
  const out: Pickup[][] = [];
  if (tl && race.start && race.moves) {
    const step = createBoardStepper(false);
    (race.drives ?? []).forEach((d, k) => {
      const e = tl.cars.findIndex((c) => c.kind === "glide" && c.k === k);
      const picks: Pickup[] = [];
      if (e >= 0) {
        const board = step(race.start!, race.moves!, tl.cars[e]!.before, -1, { race, track, driven: e });
        for (let sq = d.from; sq >= Math.max(1, d.to); sq--) {
          const stack = board.stacks.get(sq);
          if (stack?.length) picks.push({ sq, stack: [...stack] });
        }
      }
      out.push(picks);
    });
  }
  pickupCache.set(race, out);
  return out;
}

/** A turn of a round in its order: a member's step, the alpaca's drive, or after the winning move a die only shown. */
export interface Turn { m: string; face: number; step?: number; drive?: number }

/** Round [r]'s turns, in its order (race.orders; five steps a round on any other race), with each one's face. */
export function turnsOf(race: Race, r: number): Turn[] {
  const moves = race.moves ?? [];
  const order = race.orders?.[r];
  if (!order) {
    const steps = moves.slice(r * ROUND, (r + 1) * ROUND).map((s, k) => ({ m: s.m, face: s.dice[0] ?? s.steps, step: r * ROUND + k }));
    return r === roundsOf(race) - 1 ? [...steps, ...(race.rest ?? [])] : steps;
  }
  const drives = race.drives ?? [];
  let i = r * ROUND;
  let k = drives.findIndex((d) => d.r >= r);
  if (k < 0) k = drives.length;
  const rest = r === roundsOf(race) - 1 ? [...(race.rest ?? [])] : [];
  const out: Turn[] = [];
  for (const m of order) {
    if (m === ALPACA && drives[k]?.r === r) {
      out.push({ m, face: drives[k]!.face, drive: k });
      k++;
    } else if (m !== ALPACA && i < moves.length && i < (r + 1) * ROUND) {
      const s = moves[i]!;
      out.push({ m: s.m, face: s.dice[0] ?? s.steps, step: i });
      i++;
    } else {
      const x = rest.shift();
      if (x) out.push({ m: x.m, face: x.face });
    }
  }
  return out;
}

/**
 * The order on show at server time [t] (ms) on a race by the rules beyond the squares: the latest round's whose change
 * of order, or without one its dice, has begun (the opening's order before). While a round's dice for its order are
 * out, the order before stays, the alpaca at its end when it rolls for a place the first time. Null on any other race.
 */
export function orderAt(race: Race, t: number): string[] | null {
  const tl = timelineOf(race);
  if (!tl || !race.orders) return null;
  const at = t - race.startsAt * 1000;
  let r = 0;
  let rolling = -1;
  for (const b of tl.beats) {
    if (b.at > at) break;
    if (b.kind === "shuffle" || b.kind === "roll") {
      r = b.r;
      rolling = -1;
    } else if (b.kind === "order") rolling = b.r;
  }
  const out = race.orders[r] ?? null;
  if (out && rolling > r && !out.includes(ALPACA) && race.orders[rolling]?.includes(ALPACA)) return [...out, ALPACA];
  return out;
}

/**
 * When round [r]'s dice are thrown, ms after startsAt: rollMs before its first step; on a race by the rules beyond
 * the squares, where the alpaca may drive first, the round's own beat.
 */
export function rollStart(race: Race, r: number): number {
  const tl = timelineOf(race);
  if (tl) return r < tl.rolls.length ? tl.beats[tl.rolls[r]!]!.at : tl.end;
  return stepStart(race, r * ROUND) - (race.rollMs ?? 0);
}

/** The rounds of a race: one more for every ROUND moves begun. */
export const roundsOf = (race: Race): number => Math.ceil((race.moves?.length ?? 0) / ROUND);

/**
 * Round [r]'s dice, in the order: the face each member's move rolls, and in the last round, for those after the
 * winning move, the faces drawn only to be shown (race.rest).
 */
export function roundDice(race: Race, r: number): OrderRoll[] {
  if (race.orders) return turnsOf(race, r).map(({ m, face }) => ({ m, face }));
  const out = (race.moves ?? []).slice(r * ROUND, (r + 1) * ROUND).map((s) => ({ m: s.m, face: s.dice[0] ?? s.steps }));
  return r === roundsOf(race) - 1 ? [...out, ...(race.rest ?? [])] : out;
}

/**
 * Where playback is at server time [t] (ms): steps fully done, the step under way (or -1), and how far into it. While
 * the step's close-up is up it has not moved yet: [part] is 0 and [cut] how far into the close-up.
 */
export interface Playhead {
  done: number; current: number; part: number; cut?: number; ms?: number;
  /**
   * Races by the rules beyond the squares only: how many of the car's changes have come (Timeline.cars), the
   * alpaca's drive under way and how far into it, the dice for an order and the change of order under way, how far
   * into the alpaca's coming out.
   */
  driven?: number; drive?: { k: number; ms: number }; order?: { r: number; ms: number }; shuffle?: { r: number; ms: number };
  enter?: number;
}

export function playhead(race: Race, t: number): Playhead {
  const tl = timelineOf(race);
  if (tl) return playheadOn(race, tl, t - race.startsAt * 1000);
  const moves = race.moves ?? [];
  const at = t - race.startsAt * 1000;
  // Few steps: a scan is plain and exact at the switch to the slow round. Between steps (a round's dice) nothing is
  // under way.
  for (let i = 0; i < moves.length; i++) {
    const from = stepStart(race, i);
    if (at < from) return { done: i, current: -1, part: 0 };
    const cut = cutLength(race, i);
    if (at < from + cut) return { done: i, current: i, part: 0, cut: (at - from) / cut };
    const len = stepLength(race, i);
    if (at < from + cut + len) {
      const ms = at - from - cut;
      return { done: i, current: i, part: race.pace ? partAt(stepTimes(race, i), ms) : ms / len, ms };
    }
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
export interface StepPhases { len: number; hopAt: number; hopLen: number; squareAt: number; pushLen: number }

export function stepPhases(len: number): StepPhases {
  return { len, hopAt: len * HOP_AT, hopLen: len * HOP_LEN, squareAt: len * SQUARE_AT, pushLen: len * PUSH_LEN };
}

/**
 * What a special square does in step [s], in squares walked: null when it does nothing, 0 when it moves the group
 * without walking it (a portal, a flip, a climb onto the top). As park_race.py pushed().
 */
export function pushed(s: RaceStep): number | null {
  if (s.end === undefined && !s.stack) return null;
  if ((s.square === "boost" || s.square === "trip" || s.square === "again" || s.square === "hook") && s.end !== undefined) {
    return Math.max(1, Math.abs(s.end - s.to));
  }
  return 0;
}

/**
 * Step [i] of [race] in ms from its start. On a race paced by the square a hop takes the same time on every square:
 * the hop lasts its squares, a square that acts follows after the pace's gap, and the step rests for what is left of
 * its length. Else the step's length in the shares above.
 */
export function stepTimes(race: Race, i: number): StepPhases {
  const len = stepLength(race, i);
  const s = race.moves?.[i];
  const pace = race.pace;
  if (!pace || !race.stepsMs || !s) return stepPhases(len);
  // The last round's steps are longer by the same factor in all their times.
  const k = i >= (race.slowFrom ?? Infinity) && race.stepMs ? (race.slowMs ?? race.stepMs) / race.stepMs : 1;
  const push = pushed(s);
  const hopAt = pace.lit * k;
  const hopLen = Math.max(0, s.steps) * pace.hop * k;
  const squareAt = hopAt + hopLen + (push === null ? 0 : pace.gap * k);
  const pushLen = push === null ? 0 : (push ? push * pace.hop : pace.act) * k;
  // The server's length stands: times that would not fit in it shrink together.
  const fit = Math.min(1, len / Math.max(1, squareAt + pushLen));
  return { len, hopAt: hopAt * fit, hopLen: hopLen * fit, squareAt: squareAt * fit, pushLen: pushLen * fit };
}

/**
 * How far a step is at [ms] from its start, in the shares above whatever its own times are: HOP_AT when the hop sets
 * off, SQUARE_AT when the square acts (when the hop has landed, on a step with none), SQUARE_AT + PUSH_LEN when it is
 * done, 1 at the end.
 */
export function partAt(p: StepPhases, ms: number): number {
  const span = (from: number, to: number, a: number, b: number) => a + (b - a) * (to > from ? Math.min(1, Math.max(0, (ms - from) / (to - from))) : 1);
  if (ms < p.hopAt) return span(0, p.hopAt, 0, HOP_AT);
  if (ms < p.squareAt) return span(p.hopAt, p.squareAt, HOP_AT, SQUARE_AT);
  const done = p.squareAt + p.pushLen;
  if (p.pushLen > 0 && ms < done) return span(p.squareAt, done, SQUARE_AT, SQUARE_AT + PUSH_LEN);
  return span(done, p.len, p.pushLen > 0 ? SQUARE_AT + PUSH_LEN : SQUARE_AT, 1);
}

/**
 * The step whose words are up at [head]: the one under way, or the one before while the next mover is still lit, so
 * a word that pops late in a step stays until the next group sets off. [part] is how far into that step.
 */
export function saidAt(head: Playhead): { i: number; part: number } | null {
  if (head.current < 0) return null;
  // A close-up clears the words of the step before it.
  if (head.cut !== undefined) return { i: head.current, part: 0 };
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
  return diceRoundsAt(rolls, at - OPEN_AT, REROLL_MS, OPEN_ROLL_MS);
}

/**
 * Rounds of dice for an order [at] ms after the first leaves the hand: round k [step] × k in, tumbling for [tumble];
 * [step] after the last one starts the field lines up.
 */
function diceRoundsAt(rolls: OrderRoll[][], at: number, step: number, tumble: number): Opening {
  let round = -1;
  while (round + 1 < rolls.length && at >= (round + 1) * step) round++;
  const tumbling = round >= 0 && at < round * step + tumble;
  const lined = at >= rolls.length * step;
  const faces: Record<string, number> = {};
  const upto = lined ? 0 : round - (tumbling ? 1 : 0);
  for (let k = 0; k <= upto; k++) for (const r of rolls[k]!) faces[r.m] = r.face;
  const since = round >= 0 ? at - round * step : 0;
  return { round, rolling: round >= 0 ? rolls[round]!.map((r) => r.m) : [], tumbling, since, faces, lined };
}

/** A round's dice for its order (Race.orderRolls) as they play: as the opening's, scaled with orderRollMs. */
export interface OrderDice extends Opening {
  /** The round they decide the order of. */
  r: number;
  /** How long each tumbles, ms. */
  tumble: number;
}

/**
 * The dice for round r's order at playhead [h]: thrown as the opening's while their beat plays, each round of them
 * orderRollMs long and tumbling for the same share of it as the opening's (OPEN_ROLL_MS of REROLL_MS); lined up while
 * the order changes after them. Null at any other moment, and on races from before them.
 */
export function orderDiceAt(race: Race, h: Playhead | null): OrderDice | null {
  const step = race.orderRollMs;
  const on = h?.order ?? h?.shuffle;
  const rolls = on && step ? race.orderRolls?.[on.r] : undefined;
  if (!on || !step || !rolls?.length) return null;
  const tumble = (step * OPEN_ROLL_MS) / REROLL_MS;
  const at = h!.order ? on.ms : rolls.length * step + on.ms;
  return { r: on.r, tumble, ...diceRoundsAt(rolls, at, step, tumble) };
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

/**
 * How a race's squares lie on the board: `cols` by `rows` squares, and each square's cell. On the lap the start and
 * the finish are one corner; `routed` boards follow a map's route, where they are two squares.
 */
export interface Layout { cols: number; rows: number; routed: boolean; cell: (square: number) => Cell }

/** The board of a [track], along [path] when the map has one of that length. */
export function layoutOf(track: number, path?: [number, number][]): Layout {
  if (path?.length !== track + 1) return { ...boardOf(track), routed: false, cell: (sq) => cellOf(sq, track) };
  const left = Math.min(...path.map((c) => c[0]));
  const top = Math.min(...path.map((c) => c[1]));
  return {
    cols: Math.max(...path.map((c) => c[0])) - left + 1, rows: Math.max(...path.map((c) => c[1])) - top + 1, routed: true,
    cell: (sq) => {
      const [col, row] = path[Math.min(track, Math.max(0, sq))];
      return { col: col - left, row: row - top };
    },
  };
}

/**
 * Up to [n] cells of a routed board no square lies on, for the scenery: each as far from the route and from those
 * picked before as the board allows, so they spread over it.
 */
export function sceneryCells(board: Layout, track: number, n: number): Cell[] {
  const taken = new Set<string>();
  for (let sq = 0; sq <= track; sq++) taken.add(`${board.cell(sq).col},${board.cell(sq).row}`);
  const free: Cell[] = [];
  for (let row = 0; row < board.rows; row++) {
    for (let col = 0; col < board.cols; col++) if (!taken.has(`${col},${row}`)) free.push({ col, row });
  }
  const picked: Cell[] = [];
  const far = (c: Cell) => Math.min(...picked.map((p) => Math.abs(p.col - c.col) + Math.abs(p.row - c.row)), board.cols + board.rows);
  /** How many of the eight cells around are free too: scenery sits in the open, not in a gap of the route. */
  const open = (c: Cell) => free.filter((f) => f !== c && Math.abs(f.col - c.col) <= 1 && Math.abs(f.row - c.row) <= 1).length;
  while (picked.length < n) {
    const rest = free.filter((c) => !picked.includes(c) && far(c) > 1);
    if (!rest.length) break;
    picked.push(rest.reduce((best, c) => (far(c) * 10 + open(c) > far(best) * 10 + open(best) ? c : best)));
  }
  return picked;
}

/** The lap [setup] is run on: its map's, or the config's [track]. */
export const trackOf = (setup: RaceSetup | undefined, track: number): number => setup?.map?.track ?? track;

/**
 * The special square on [square] of [setup], if any: a map's as it is (a portal from either end, `to` the other);
 * on races dealt before maps, the boost and trip squares move by the config's [boost] and [trip].
 */
export function squareOn(setup: RaceSetup | undefined, square: number, boost = 0, trip = 0): MapSquare | null {
  if (!setup) return null;
  if (setup.map) {
    const q = setup.map.squares.find((x) => x.at === square || (x.kind === "portal" && x.to === square));
    if (!q) return null;
    return q.at === square ? q : { at: square, kind: "portal", to: q.at };
  }
  if (square === setup.boost) return { at: square, kind: "boost", by: boost };
  if (square === setup.trip) return { at: square, kind: "trip", by: Math.abs(trip) };
  if (setup.portal?.includes(square)) return { at: square, kind: "portal", to: setup.portal[0] + setup.portal[1] - square };
  if (square === setup.flip) return { at: square, kind: "flip" };
  return null;
}

/** The kind of special square on [square] of [setup], if any. */
export const squareKind = (setup: RaceSetup | undefined, square: number): SquareKind | null =>
  squareOn(setup, square)?.kind ?? null;

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

/** walkPath, for a walk the server ended on [end]: a dash stops on the finish it would pass (race.py run). */
function walkTo(from: number, steps: number, track: number, end: number): number[] {
  if (end === track && from + steps > track) return Array.from({ length: track - from }, (_, k) => from + k + 1);
  return walkPath(from, steps, track);
}

/**
 * The squares of step [s], one at a time: the hop the die gives, then what the square there adds: the push of a boost
 * (+[boost]) or trip (−[trip]) square, the second die of an again square, the way to the dumplings a hook pulls onto;
 * each ending where the server says (to, end). A portal or flip square walks no squares: push is empty.
 */
export function stepPath(s: RaceStep, track: number, boost: number, trip: number): { hop: number[]; push: number[] } {
  const hop = walkTo(s.from, s.steps, track, s.to);
  if (s.end === undefined) return { hop, push: [] };
  const by = s.square === "boost" ? boost : s.square === "trip" ? -trip : s.square === "again" ? s.dice[1] ?? 0
    : s.square === "hook" ? s.end - s.to : 0;
  return { hop, push: by ? walkTo(s.to, by, track, s.end) : [] };
}

/** A dumpling's place: its square and its height in the stack there (0 at the bottom); on square 0, its lane. */
export interface Spot { square: number; level: number; lane?: number }

/**
 * Square 0 holds the dumplings still on the start line, side by side in lane order; every other square a stack,
 * bottom to top. A move from square 0 takes the mover alone; anywhere else it takes those above it too.
 */
function lift(stacks: Map<number, string[]>, from: number, step: RaceStep): string[] {
  const s = stacks.get(from) ?? [];
  const k = s.indexOf(step.m);
  if (k < 0) return [step.m];
  // A solo leaves its riders: they stay on the square, on those under it.
  const group = from === 0 ? [step.m] : s.slice(k).filter((m) => !step.left?.includes(m));
  const rest = s.filter((m) => !group.includes(m));
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
  const group = lift(stacks, s.from, s);
  const end = s.end === undefined || !acted ? s.to : s.end;
  put(stacks, end, group);
  if (acted && s.square === "flip") stacks.get(s.to)?.reverse();
  // The climbers the group landed on are on top by now.
  if (acted && s.stack) stacks.set(end, [...s.stack]);
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

interface StepCursor { completed: number; partial: number; driven?: number }

/**
 * The board changes when the group leaves its square, or when its landing square acts; on a race by the rules beyond
 * the squares, also with every change of where the alpaca is ([driven]).
 */
export function stepCursor(h: Playhead, previous?: StepCursor | null): StepCursor {
  const completed = h.current >= 0 ? (h.part >= SQUARE_AT ? h.current + 1 : h.current) : h.done;
  const partial = h.current >= 0 && h.part >= HOP_AT && h.part < SQUARE_AT ? h.current : -1;
  const driven = h.driven;
  if (previous?.completed === completed && previous.partial === partial && previous.driven === driven) return previous;
  return driven === undefined ? { completed, partial } : { completed, partial, driven };
}

/**
 * A board: the stacks, each tuanzi's last move (for its animation), and on a race with the alpaca where its car is
 * parked (null before it is out; the square it drives to from the moment it sets off) and its last change.
 */
interface BoardState { stacks: Map<number, string[]>; hops: Record<string, string>; car?: number | null; carKey?: string }

/** What a board needs to play the alpaca's turns too: the race, how many of the car's changes have come, the track. */
export interface CarRun { race: Race; driven: number; track: number }

/**
 * Keep completed moves, and play a partial move on a separate snapshot so it can be scrubbed either way. With [run]
 * the car's changes (Timeline.cars) play in between, each before the step it comes before.
 */
export function createBoardStepper(withHops = true) {
  let cache: {
    start: readonly string[];
    moves: readonly RaceStep[];
    race: Race | undefined;
    completed: number;
    partial: number;
    driven: number;
    base: BoardState;
    frame: BoardState;
  } | undefined;

  function copy(board: BoardState): BoardState {
    const out: BoardState = { stacks: new Map([...board.stacks].map(([sq, stack]) => [sq, [...stack]])), hops: { ...board.hops } };
    if (board.car !== undefined) {
      out.car = board.car;
      out.carKey = board.carKey;
    }
    return out;
  }
  function apply(board: BoardState, s: RaceStep, i: number, complete: boolean) {
    playStep(board.stacks, s, complete);
    if (!withHops) return;
    const acted = complete && (s.end !== undefined || !!s.stack);
    const key = `${i}${acted ? "b" : "a"}`;
    for (const m of [s.m, ...(s.carry ?? [])]) board.hops[m] = s.end === undefined ? `${i}a` : key;
    if (acted && s.square === "flip") for (const m of board.stacks.get(s.to) ?? []) board.hops[m] = key;
    if (acted && s.react?.length) for (const m of s.stack ?? s.react) board.hops[m] = key;
  }
  /**
   * A change of the car: out onto the finish; a drive, taking everyone on the squares it passes and its own along to
   * where it stops (race.py run: the lower squares at the bottom); back to the finish, leaving its riders standing.
   * Their moves: `cd${k}` riding drive k, `cb${k}` and `ch${k}` left off it by going back before drive k or after it.
   */
  function moveCar(board: BoardState, e: CarEvent, drives: readonly RaceDrive[], track: number) {
    if (e.kind === "enter") {
      board.car = track;
      board.carKey = "e";
      return;
    }
    const d = drives[e.k];
    if (!d) return;
    if (e.kind === "glide") {
      const took: string[] = [];
      for (let sq = Math.max(1, d.to); sq <= d.from; sq++) {
        const stack = board.stacks.get(sq);
        if (!stack) continue;
        took.push(...stack);
        board.stacks.delete(sq);
      }
      if (took.length) board.stacks.set(d.to, took);
      if (withHops) for (const m of took) board.hops[m] = `cd${e.k}`;
      board.car = d.to;
    } else {
      const left = board.car ? board.stacks.get(board.car) ?? [] : [];
      if (withHops && board.car !== track) for (const m of left) board.hops[m] = `c${e.kind[0]}${e.k}`;
      board.car = track;
    }
    board.carKey = `${e.kind[0]}${e.k}`;
  }

  return (start: readonly string[], moves: readonly RaceStep[], completed: number, partial: number, run?: CarRun): BoardState => {
    const target = Math.min(completed, moves.length);
    const cars = (run && timelineOf(run.race)?.cars) || [];
    const driven = Math.min(run?.driven ?? 0, cars.length);
    if (!cache || cache.start !== start || cache.moves !== moves || cache.race !== run?.race || target < cache.completed
      || driven < cache.driven) {
      const base: BoardState = { stacks: new Map([[0, [...start]]]), hops: {} };
      if (run) {
        base.car = null;
        base.carKey = "";
      }
      cache = { start, moves, race: run?.race, completed: 0, partial: -1, driven: 0, base, frame: base };
    }
    if (cache.completed === target && cache.partial === partial && cache.driven === driven) return cache.frame;
    if (cache.completed < target || cache.driven < driven) {
      cache.base = copy(cache.base);
      for (;;) {
        const e = cars[cache.driven];
        if (e && e.before <= cache.completed) {
          if (cache.driven >= driven) break;
          moveCar(cache.base, e, run!.race.drives ?? [], run!.track);
          cache.driven++;
        } else if (cache.completed < target) {
          const i = cache.completed++;
          apply(cache.base, moves[i], i, true);
        } else break;
      }
    }
    cache.partial = partial;
    cache.frame = cache.base;
    if (partial >= 0 && partial < moves.length) {
      cache.frame = copy(cache.base);
      apply(cache.frame, moves[partial], partial, false);
    }
    return cache.frame;
  };
}

/** The standings need only the stacks, retaining their reference between board changes. */
export function createStackStepper() {
  const step = createBoardStepper(false);
  return (start: readonly string[], moves: readonly RaceStep[], completed: number, partial: number, run?: CarRun) =>
    step(start, moves, completed, partial, run).stacks;
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

/**
 * The leader after each step in full (index i: after step i); with [run] (a race by the rules beyond the squares),
 * after the alpaca's turns before it too, not those after.
 */
export function leaders(start: readonly string[], moves: readonly RaceStep[], run?: Omit<CarRun, "driven">): string[] {
  const cars = run && timelineOf(run.race)?.cars;
  if (!run || !cars) return moves.map((_, i) => rankOf(stacksAt(start, moves, { done: i + 1, current: -1, part: 0 }))[0]);
  const step = createBoardStepper(false);
  return moves.map((_, i) => rankOf(step(start, moves, i + 1, -1, { ...run, driven: carsBefore(cars, i) }).stacks)[0]);
}

/** The leader just before each step (index i: before step i), the alpaca's turns since the step before included. */
export function leadersBefore(start: readonly string[], moves: readonly RaceStep[], run: Omit<CarRun, "driven">): string[] {
  const cars = timelineOf(run.race)?.cars ?? [];
  const step = createBoardStepper(false);
  return moves.map((_, i) => rankOf(step(start, moves, i, -1, { ...run, driven: carsBefore(cars, i) }).stacks)[0]);
}

/** How many of the car's changes come before step [i]. */
function carsBefore(cars: readonly CarEvent[], i: number): number {
  let n = 0;
  while (n < cars.length && cars[n]!.before <= i) n++;
  return n;
}

// ---------------------------------------------------------------- moments worth a word

export type MomentKind = "lead" | "boost" | "trip" | "carry" | "skill" | "again" | "hook";

/** A word over the mover in the step under way: what, from which share of the step on. */
export interface Moment { kind: MomentKind; m: string; from: number }

/**
 * The step's moment, if any, by weight: a skill at work, the again or hook square, a fall on the trip square, a push on the boost square, taking the lead,
 * carrying others along. [before] is the leader before the step, [after] the leader once it is done.
 */
export function momentOf(s: RaceStep, before: string | undefined, after: string | undefined): Moment | null {
  // A skill first: the mover's as it sets off, a climber's once the group has landed on it.
  if (s.skill) return { kind: "skill", m: s.m, from: HOP_AT };
  if (s.react?.length) return { kind: "skill", m: s.react[s.react.length - 1], from: SQUARE_AT };
  if (s.square === "again" || s.square === "hook") return { kind: s.square, m: s.m, from: SQUARE_AT };
  if (s.square === "trip") return { kind: "trip", m: s.m, from: SQUARE_AT };
  if (s.square === "boost") return { kind: "boost", m: s.m, from: SQUARE_AT };
  if (after && before !== after && [s.m, ...(s.carry ?? [])].includes(after)) {
    return { kind: "lead", m: after, from: HOP_AT + HOP_LEN };
  }
  if (s.carry?.length) return { kind: "carry", m: s.m, from: HOP_AT + HOP_LEN };
  return null;
}

// ---------------------------------------------------------------- playing a finished race again

/** The China day (YYYY-MM-DD) of [ts] (unix seconds), as the server names a race's day. */
export const chinaDay = (ts: number): string => new Date((ts + 8 * 3600) * 1000).toISOString().slice(0, 10);

/**
 * A replay's own clock: [from] ms into the race at local time [anchor] (ms), running [speed] times as fast as the
 * wall clock from there.
 */
export interface ReplayClock { from: number; anchor: number; speed: number }

/** How long a race plays, ms from startsAt to endsAt. */
export const playLength = (race: Race): number => Math.max(0, ((race.endsAt ?? race.startsAt) - race.startsAt) * 1000);

/** The race's server time (ms) a replay shows at local time [now]; it stops at the end. */
export function replayTime(race: Race, c: ReplayClock, now: number): number {
  return race.startsAt * 1000 + Math.min(playLength(race), c.from + Math.max(0, now - c.anchor) * c.speed);
}

/** The clock moved to [from] ms into the race (the end at most) at [now], at [speed]. */
export function replayAt(race: Race, from: number, now: number, speed: number): ReplayClock {
  return { from: Math.max(0, Math.min(playLength(race), from)), anchor: now, speed };
}
