<script setup lang="ts">
// The race's board (protocol/PROTOCOL.md 团子赛跑), drawn like a board game. On a map with a route (race.ts layoutOf) the
// squares are stepping stones laid across the slab along it, numbered, the start a faint check and the finish a bold
// one, each portal's two ends joined by a dashed line on the slab, and a few pictures of the park where no square lies;
// there is no island and no infield. Otherwise it is the lap: one thick coral slab with the ring of
// squares inlaid in it (race.ts boardOf, cellOf: all squares the same size), square 0 in the top left corner as start
// and finish (coral with a coral and white checkered finish line), the boost square a key standing up from the board,
// the trip square a pit sunk into it, the portal's two ends the same coral ring, the flip square a coral disc with
// two arrows, the again square a paper die, the hook square a coral hook, the other corners a faint picture of the park. The squares are paper in two shades by turns, parted by
// hairlines. Inside the ring the board rises as an island with a sheet of paper on it, the infield; the page puts
// what fits the phase there (the slot). The board takes the largest size the track's box allows, leaving head room
// over it for a five-high stack on the top row and its crown.
// The tuanzi stand on the squares: at the start crowded in the corner, past it stacked bottom to top, the leader
// crowned. Positions come from the move list at the server time [t] (race.ts). A step: the mover lights up (bigger,
// glowing, the others faded; its die in the page's row raised), then the group hops square by square along the ring
// (race.ts stepPath: on to the finish and back when the roll carries past it); from SQUARE_AT the special square it
// landed on acts: a boost or trip square pushes it on the same way, a portal end swallows it and the other end gives
// it back, a flip square turns its stack upside down, each tuanzi there jumping in an arc to its new height (as a
// climber does on its way to the top), an again or hook square walks the group on. Every
// hop squashes and stretches about the foot of the group's stack, and the group springs back after it lands. A word
// pops over the dumpling at the moments that matter. The moves are one Web Animations run each, as long as their part
// of the step (stepPhases) and the spring back; under reduced motion everything jumps and stands still.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { economy } from "../../stores/economy";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import alpaca from "../../assets/brand/side-alpaca.webp";
import { COIN } from "./coin";
import {
  cornersOf, cutOf, HOP_AT, layoutOf, leaders, momentOf, moving, playhead, playStep, rankOf, saidAt, sceneryCells, spots,
  SQUARE_AT, SKILL_NAMES, skillText, squareOn, stacksAt, stageOf, stepLength, stepPath, stepPhases, type MomentKind,
  type Race, type Spot,
} from "./race";
import SkillCutIn from "./SkillCutIn.vue";
import TuanziToken from "./TuanziToken.vue";

/**
 * [cleared]: the race is over and its result stands in the infield; the field leaves the board. [rate]: how fast [t]
 * runs against the wall clock (a replay at 2×); the moves play at that rate.
 */
const props = defineProps<{
  race: Race | null; t: number; track: number; members: string[]; cleared?: boolean; rate?: number;
  /** The map's name, lettered on the island under the paper. */
  caption?: string;
}>();

const nameOf = (m: string) => manifest.characters.find((c) => c.id === m)?.name ?? m;

const BOOST = economy.value?.park?.race?.squares.boost ?? 2;
const TRIP = Math.abs(economy.value?.park?.race?.squares.trip ?? -1);
const WORDS: Record<MomentKind, string> = {
  lead: "领先", boost: "冲呀", trip: "哎呀", carry: "抓紧了", skill: "", again: "再掷一次", hook: "钩住了",
};

/*
 * Sizes in units (a square's side; race.ts cellOf), the same as the CSS (.ring): a tuanzi is D wide, its feet stand
 * FOOT above the foot of its square, and a hop arcs ARC high. Each one up a stack rises LIFT of a unit, closer when
 * the stack is tall: however many there are, the top one's box rises at most RISE over its square's top, so a stack
 * on the top row stays within the head room the CSS keeps over the board (--head: half a unit, and a little for the
 * crown). On the start square the five stand in two rows inside it, three behind and two in front, at half size
 * (CROWD: across and down the square, by their place in `start`; the CSS's .tz.gated scale).
 */
const D = 0.8;
const LIFT = 0.24;
const RISE = 0.5;
const FOOT = 0.12;
const ARC = 0.42;
/** How far apart each one up a stack of [n] stands, in units. */
const stepOf = (n: number) => (n > 1 ? Math.min(LIFT, (RISE + 1 - FOOT - D) / (n - 1)) : 0);
/** A flip: how far aside the tuanzi swing (towards the middle of the board going up, the other way going down, as
 * far as the board's edge allows), and how high they jump. */
const FLIP_SWING = 0.32;
const FLIP_ARC = 0.3;
/** Keyframes per hop: enough for the parabola to read as a curve. */
const HOP_SAMPLES = 10;
/** A hop seen less than this late (ms) is squeezed to land on time instead of being skipped into. */
const CATCH_UP_MS = 150;
const CROWD: readonly [number, number][] = [[0.2, 0.56], [0.5, 0.56], [0.8, 0.56], [0.33, 0.93], [0.67, 0.93]];

const board = computed(() => layoutOf(props.track, props.race?.setup.map?.path));
const routed = computed(() => board.value.routed);
const corners = computed(() => (routed.value ? [] : cornersOf(props.track)));
/** On a route the finish is a square of its own; on the lap it is the start. */
const squares = computed(() => Array.from({ length: props.track + (routed.value ? 1 : 0) }, (_, k) => k));
const finish = computed(() => (routed.value ? props.track : 0));
const cellStyle = (sq: number) => {
  const c = board.value.cell(sq);
  return { gridColumn: c.col + 1, gridRow: c.row + 1 };
};
/** On a route: the continuous stone channel, the step chevrons along it, the scenery, and each portal's curved arc. */
const originDeg = computed(() => {
  if (props.track < 1) return 0;
  const a = board.value.cell(0);
  const b = board.value.cell(1);
  return Math.round((Math.atan2(b.row - a.row, b.col - a.col) * 180) / Math.PI);
});
const routePoints = computed(() =>
  routed.value ? squares.value.map((sq) => `${board.value.cell(sq).col + 0.5},${board.value.cell(sq).row + 0.5}`).join(" ") : "",
);
const wayPath = computed(() => {
  if (!routed.value) return "";
  const f = (n: number) => Math.round(n * 1000) / 1000;
  const parts: string[] = [];
  for (let sq = 0; sq < props.track; sq++) {
    const a = board.value.cell(sq);
    const b = board.value.cell(sq + 1);
    const ux = b.col - a.col;
    const uy = b.row - a.row;
    const mx = (a.col + b.col) / 2 + 0.5;
    const my = (a.row + b.row) / 2 + 0.5;
    const tx = mx + ux * 0.028;
    const ty = my + uy * 0.028;
    const bx = mx - ux * 0.032;
    const by = my - uy * 0.032;
    parts.push(`M${f(bx - uy * 0.062)} ${f(by + ux * 0.062)}L${f(tx)} ${f(ty)}L${f(bx + uy * 0.062)} ${f(by - ux * 0.062)}`);
  }
  return parts.join("");
});
const SCENERY = ["ferris", "alpaca", "crown"] as const;
const scenery = computed(() =>
  (routed.value ? sceneryCells(board.value, props.track, SCENERY.length) : []).map((c, k) => ({ ...c, kind: SCENERY[k] })),
);
const links = computed(() => {
  const setup = props.race?.setup;
  const pairs: (readonly [number, number])[] = setup?.map
    ? setup.map.squares.filter((q) => q.kind === "portal" && q.to !== undefined).map((q) => [q.at, q.to!] as const)
    : setup?.portal ? [setup.portal] : [];
  if (!pairs.length) return [];
  const { cols, rows } = board.value;
  const cx = cols / 2;
  const cy = rows / 2;
  const clamp = (v: number, hi: number) => Math.min(hi - 0.22, Math.max(0.22, v));
  const f = (n: number) => Math.round(n * 1000) / 1000;
  const mid = (sq: number) => ({ x: board.value.cell(sq).col + 0.5, y: board.value.cell(sq).row + 0.5 });
  return pairs.map(([at, to]) => {
    const a = mid(at);
    const b = mid(to);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    const bow = Math.min(0.85, Math.max(0.38, len * 0.22));
    const q1 = { x: mx + (-dy / len) * bow, y: my + (dx / len) * bow };
    const q2 = { x: mx + (dy / len) * bow, y: my + (-dx / len) * bow };
    const pick = Math.hypot(q1.x - cx, q1.y - cy) <= Math.hypot(q2.x - cx, q2.y - cy) ? q1 : q2;
    const q = { x: clamp(pick.x, cols), y: clamp(pick.y, rows) };
    const r = Math.min(0.33, len * 0.28);
    const la = Math.hypot(q.x - a.x, q.y - a.y) || 1;
    const lb = Math.hypot(q.x - b.x, q.y - b.y) || 1;
    const p1 = { x: f(a.x + ((q.x - a.x) / la) * r), y: f(a.y + ((q.y - a.y) / la) * r) };
    const p2 = { x: f(b.x + ((q.x - b.x) / lb) * r), y: f(b.y + ((q.y - b.y) / lb) * r) };
    return { key: at, at, d: `M${p1.x} ${p1.y}Q${f(q.x)} ${f(q.y)} ${p2.x} ${p2.y}`, p1, p2 };
  });
});
/** The special square on [sq], with the squares a boost or trip there moves. */
const squareAt = (sq: number) => (sq && sq < props.track ? squareOn(props.race?.setup, sq, BOOST, TRIP) : null);
const kindOf = (sq: number) => squareAt(sq)?.kind ?? null;
/** The corners other than the start, each with a faint picture unless a special square is there. */
const DECOS = ["ferris", "coin", "alpaca"] as const;
const decoOf = (sq: number): (typeof DECOS)[number] | null =>
  (kindOf(sq) ? null : DECOS[corners.value.indexOf(sq) - 1] ?? null);
/** Which corner of the ring a square rounds, for its radius. */
const cornerClass = (sq: number) => ["tl", "tr", "br", "bl"][corners.value.indexOf(sq)] ?? "";

/** The start corner's order: the race's once it is out, the members' order before. */
const lanes = computed(() => props.race?.start ?? props.members);
const moves = computed(() => (props.race?.start ? props.race.moves ?? [] : []));
const head = computed(() => (props.race && moves.value.length ? playhead(props.race, props.t) : null));
const step = computed(() => (head.value && head.value.current >= 0 ? moves.value[head.value.current] : null));
/** The mover waits for the die: lit until the group sets off. */
const waiting = computed(() => !!head.value && head.value.current >= 0 && stageOf(head.value.part) !== "walk");
/** The special square acting in the step under way (lit while it does), and the squares it lights. */
const acting = computed(() => {
  const s = step.value;
  const h = head.value;
  if (!s?.square || !h || h.part < SQUARE_AT) return [] as number[];
  return s.square === "portal" && s.end !== undefined ? [s.to, s.end] : [s.to];
});

const stacks = computed(() =>
  head.value ? stacksAt(lanes.value, moves.value, head.value) : new Map<number, string[]>([[0, [...lanes.value]]]),
);
const places = computed<Record<string, Spot>>(() => spots(stacks.value));
/** The square under the active mover while its step plays. */
const activeSq = computed(() => (ready.value && step.value ? places.value[step.value.m]?.square ?? -1 : -1));
/** How many stand on each member, for what floats over a stack. */
const above = computed(() => {
  const out: Record<string, number> = {};
  for (const [square, s] of stacks.value) s.forEach((m, k) => (out[m] = square ? s.length - 1 - k : 0));
  return out;
});
const movers = computed(() => (head.value ? moving(moves.value, head.value) : []));
/** Who is ahead once the first group has moved: crowned. */
const leader = computed(() => {
  const h = head.value;
  return h && (h.done > 0 || (h.current >= 0 && h.part >= HOP_AT)) ? rankOf(stacks.value)[0] : "";
});

/**
 * The move each tuanzi last made: `${step}a` the hop to the die's square, `${step}b` what the special square there did
 * (for a flip, every tuanzi in the stack it turned).
 */
const hops = computed(() => {
  const out: Record<string, string> = {};
  const h = head.value;
  if (!h) return out;
  const upto = h.current >= 0 ? h.current : h.done - 1;
  const st = new Map<number, string[]>([[0, [...lanes.value]]]);
  for (let i = 0; i <= upto && i < moves.value.length; i++) {
    const s = moves.value[i];
    const under = i === h.current;
    if (under && h.part < HOP_AT) break;
    const acted = (s.end !== undefined || !!s.stack) && !(under && h.part < SQUARE_AT);
    playStep(st, s, acted);
    const key = `${i}${acted ? "b" : "a"}`;
    // Without a square the group has nothing more to do when a climber under it moves: it keeps its hop.
    for (const m of [s.m, ...(s.carry ?? [])]) out[m] = s.end === undefined ? `${i}a` : key;
    if (acted && s.square === "flip") for (const m of st.get(s.to) ?? []) out[m] = key;
    if (acted) for (const m of s.react ?? []) out[m] = key;
  }
  return out;
});

/**
 * The step whose words are up: the one under way, or the one before while the next mover is still lit, so a word
 * that pops late in a step stays a while.
 */
const said = computed(() => (head.value ? saidAt(head.value) : null));
/** The squares walked, popped over the group once it hops; then the boost or trip square's own push. */
const roll = computed<{ m: string; key: string; text: string; down: boolean } | null>(() => {
  const w = said.value;
  const s = w ? moves.value[w.i] : undefined;
  if (!w || !s || w.part < HOP_AT) return null;
  if ((s.square === "boost" || s.square === "trip") && w.part >= SQUARE_AT) {
    const down = s.square === "trip";
    const by = squareAt(s.to)?.by ?? (down ? TRIP : BOOST);
    return { m: s.m, key: `${w.i}b`, text: down ? `−${by}` : `+${by}`, down };
  }
  if (s.square === "again" && w.part >= SQUARE_AT) return { m: s.m, key: `${w.i}b`, text: `+${s.dice[1]}`, down: false };
  return { m: s.m, key: `${w.i}a`, text: `+${s.steps}`, down: false };
});

/** Who leads after each step, worked out once a race. */
const leadAfter = computed(() => (props.race?.start && moves.value.length ? leaders(props.race.start, moves.value) : []));
const moment = computed(() => {
  const w = said.value;
  const s = w ? moves.value[w.i] : undefined;
  if (!w || !s) return null;
  const i = w.i;
  const m = momentOf(s, i ? leadAfter.value[i - 1] : lanes.value[0], leadAfter.value[i]);
  if (!m || w.part < m.from) return null;
  // A skill's word is its name: the mover's own, or the climber's.
  const text = m.kind === "skill" ? SKILL_NAMES[m.m === s.m && s.skill ? s.skill : "climb"] ?? "" : WORDS[m.kind];
  return { ...m, key: `${i}${m.kind}`, text };
});

/**
 * The close-up the step under way opens with: its member's skill, named and explained, before the step moves. [at] is
 * how far in it is, read once as it comes up.
 */
const cut = computed(() => {
  const r = props.race;
  const h = head.value;
  if (!r || !h || h.cut === undefined) return null;
  const c = cutOf(r, h.current);
  const skill = c ? r.setup.skills?.[c.m] : undefined;
  if (!c || !skill) return null;
  return {
    key: `${r.id}:${c.at}`, m: c.m, who: nameOf(c.m), name: SKILL_NAMES[skill.id] ?? "", text: skillText(skill),
    color: manifest.characters.find((x) => x.id === c.m)?.color, ms: (r.cutMs ?? 0) / Math.max(0.01, props.rate ?? 1), at: h.cut,
  };
});

/** The last step is done and the result not yet up: the field stands still, the start corner flashing. */
const tail = computed(() => {
  const r = props.race;
  const h = head.value;
  return !!r?.endsAt && !!h && h.current < 0 && h.done === moves.value.length && props.t < r.endsAt * 1000;
});

// ---------------------------------------------------------------- where each tuanzi stands

/** A spot in units from the ring's top left: across, down to the feet, the height in its stack and how far it rises. */
interface At { x: number; y: number; lvl: number; rise: number }
/** The middle of [square], at the feet's height, [lvl] up a stack of [n]. */
function footOf(square: number, lvl: number, n: number): At {
  const c = board.value.cell(square);
  return { x: c.col + 0.5, y: c.row + 1 - FOOT, lvl, rise: lvl * stepOf(n) };
}
function atOf(p: Spot | undefined): At {
  if (!p?.square) {
    const [x, y] = CROWD[(p?.lane ?? 0) % CROWD.length];
    const c = board.value.cell(0);
    return { x: c.col + x, y: c.row + y, lvl: 0, rise: 0 };
  }
  return footOf(p.square, p.level, stacks.value.get(p.square)?.length ?? 1);
}
const ats = computed<Record<string, At>>(() => Object.fromEntries(props.members.map((m) => [m, atOf(places.value[m])])));

function style(m: string) {
  const a = ats.value[m];
  // Lower on the board is nearer: in front; up a stack in front of those under it; the movers over everyone.
  const z = 10 + Math.round(a.y * 10) + a.lvl + (movers.value.includes(m) ? 100 : 0);
  // --over: how far the top of its stack rises over it, in units, for what floats over the stack.
  const sq = places.value[m]?.square;
  const over = (above.value[m] ?? 0) * stepOf(sq ? stacks.value.get(sq)?.length ?? 1 : 1);
  return { "--x": a.x, "--y": a.y, "--rise": a.rise, "--over": over, zIndex: z };
}
/** Words near the right edge open to the left, so they stay on the paper. */
const flipped = (m: string) => ats.value[m].x > board.value.cols - 2.5;

// ---------------------------------------------------------------- the moves

// Moves start only after the first paint, so opening the page mid-race does not make everyone jump at once.
const ready = ref(false);
const ringEl = ref<HTMLElement | null>(null);
const tzEls: Record<string, HTMLElement> = {};
let frame = 0;
onMounted(() => (frame = requestAnimationFrame(() => (ready.value = true))));
onBeforeUnmount(() => cancelAnimationFrame(frame));

const rate = computed(() => props.rate ?? 1);
// A change of rate carries the moves under way along.
watch(rate, (k) => {
  for (const node of Object.values(tzEls)) for (const a of node.getAnimations?.() ?? []) a.playbackRate = k;
});

/** Where the tuanzi was before the latest change, to move from. */
let was: Record<string, At> = {};
watch(() => props.race?.id, () => (was = {}));

/** A spot as the transform the CSS gives it (.tz), in px for a unit [unit] px long; [up] lifts it, [aside] moves it across. */
function pose(a: At, unit: number, up = 0, aside = 0): string {
  const d = unit * D;
  return `translate(${(a.x + aside) * unit - d / 2}px, ${(a.y - up - a.rise) * unit - d}px)`;
}

/*
 * Squash and stretch, (across, down), about the foot of the group's stack, so a stack squashes as one: crouched before
 * take-off and on each landing (SQUAT), drawn out on the way up (STRETCH); after the last landing it springs back
 * through SETTLE (an overshoot and back) in SETTLE_MS more.
 */
type Scale = readonly [number, number];
const SQUAT: Scale = [1.12, 0.86];
const STRETCH: Scale = [0.92, 1.1];
const LEVEL: Scale = [1, 1];
const SETTLE: readonly Scale[] = [[0.96, 1.05], [1.02, 0.98], LEVEL];
const SETTLE_MS = 260;
/** The share of a hop's flight spent getting up to full stretch, and from there back to level. */
const UP_PART = 0.2;
const LEVEL_PART = 0.8;

const mix = (a: Scale, b: Scale, u: number): Scale => [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u];
/** A keyframe: [a] lifted [up] and moved [aside], squashed by [k] about the foot of its stack. */
function keyAt(offset: number, a: At, unit: number, k: Scale, up = 0, aside = 0, extra: Keyframe = {}): Keyframe {
  return {
    offset, transform: `${pose(a, unit, up, aside)} scale(${k[0]}, ${k[1]})`,
    transformOrigin: `50% ${unit * D + a.rise * unit}px`, ...extra,
  };
}
/** The spring back after landing at [a], from offset [land] to 1. */
const settle = (land: number, a: At, unit: number): Keyframe[] =>
  SETTLE.map((k, j) => keyAt(land + ((1 - land) * (j + 1)) / SETTLE.length, a, unit, k));
/** Where in a flight [u] (0 take-off, 1 landing) the squash is: crouched, stretched, level, crouched again. */
function flightScale(u: number): Scale {
  if (u < UP_PART) return mix(SQUAT, STRETCH, u / UP_PART);
  if (u < LEVEL_PART) return mix(STRETCH, LEVEL, (u - UP_PART) / (LEVEL_PART - UP_PART));
  return mix(LEVEL, SQUAT, (u - LEVEL_PART) / (1 - LEVEL_PART));
}

/**
 * A walk along [points], one hop a square, in [ms] and SETTLE_MS more: a crouch, then across at an even pace and up
 * and down on a parabola, landing crouched on each square, and the spring back at the end.
 */
function walkFrames(points: At[], unit: number, ms: number): Keyframe[] {
  // One easing for both would stall the tuanzi at the top of every hop and rush it at each landing.
  const land = ms / (ms + SETTLE_MS);
  const crouch = land * 0.1;
  const frames: Keyframe[] = [keyAt(0, points[0]!, unit, LEVEL)];
  const n = points.length - 1;
  for (let j = 0; j < n; j++) {
    const p = points[j]!;
    const q = points[j + 1]!;
    for (let k = 0; k < HOP_SAMPLES; k++) {
      const u = k / HOP_SAMPLES;
      const at = { x: p.x + (q.x - p.x) * u, y: p.y + (q.y - p.y) * u, lvl: 0, rise: p.rise + (q.rise - p.rise) * u };
      frames.push(keyAt(crouch + ((land - crouch) * (j + u)) / n, at, unit, flightScale(u), ARC * 4 * u * (1 - u)));
    }
  }
  frames.push(keyAt(land, points[n]!, unit, SQUAT), ...settle(land, points[n]!, unit));
  return frames;
}

/**
 * Into one portal end and out of the other, in [ms] and SETTLE_MS more: a crouch, shrinking down to the floor of the
 * square, growing out of the other drawn out, landing crouched and springing back.
 */
function portalFrames(from: At, to: At, unit: number, ms: number): Keyframe[] {
  const land = ms / (ms + SETTLE_MS);
  const gone = [0, 0] as const;
  return [
    keyAt(0, from, unit, LEVEL, 0, 0, { opacity: 1 }),
    keyAt(land * 0.12, from, unit, SQUAT, 0, 0, { opacity: 1 }),
    keyAt(land * 0.42, from, unit, gone, 0, 0, { opacity: 0 }),
    keyAt(land * 0.55, to, unit, gone, 0, 0, { opacity: 0 }),
    keyAt(land * 0.85, to, unit, STRETCH, 0, 0, { opacity: 1 }),
    keyAt(land, to, unit, SQUAT, 0, 0, { opacity: 1 }),
    ...settle(land, to, unit).map((f) => ({ ...f, opacity: 1 })),
  ];
}

/**
 * A flip, in [ms] and SETTLE_MS more: an arc from the old height to the new, drawn out in the air, landing crouched
 * and springing back. Those going up swing towards the middle of the board, those going down the other way, no
 * further than keeps them on the board (inside the ring).
 */
function flipFrames(from: At, to: At, unit: number, ms: number): Keyframe[] {
  const inward = from.x <= board.value.cols / 2 ? 1 : -1;
  // Room to the ring's edge on the outward side: from the square's middle, less half a tuanzi.
  const room = Math.max(0, (inward > 0 ? from.x : board.value.cols - from.x) - D / 2);
  const swing = to.lvl === from.lvl ? 0 : to.lvl > from.lvl ? inward * FLIP_SWING : -inward * Math.min(FLIP_SWING, room);
  const land = ms / (ms + SETTLE_MS);
  const frames: Keyframe[] = [];
  for (let k = 0; k < HOP_SAMPLES * 2; k++) {
    const u = k / (HOP_SAMPLES * 2);
    const at = { x: from.x, y: from.y, lvl: 0, rise: from.rise + (to.rise - from.rise) * u };
    frames.push(keyAt(land * u, at, unit, k ? flightScale(u) : LEVEL, FLIP_ARC * 4 * u * (1 - u), swing * Math.sin(Math.PI * u)));
  }
  frames.push(keyAt(land, to, unit, SQUAT), ...settle(land, to, unit));
  return frames;
}

watch(hops, (now, before) => {
  const r = props.race;
  const h = head.value;
  const el = ringEl.value;
  if (ready.value && !reducedMotion.value && r && h && el && before) {
    // The ring has no border or padding: its box is the board in units, the tuanzi's frame of reference.
    const unit = el.getBoundingClientRect().width / board.value.cols;
    for (const m of props.members) {
      const key = now[m];
      const from = was[m];
      const node = tzEls[m];
      if (!key || key === before[m] || !from || !node || typeof node.animate !== "function") continue;
      const i = Number.parseInt(key, 10);
      const s = moves.value[i];
      if (!s) continue;
      const b = key.endsWith("b");
      const to = ats.value[m];
      const p = stepPhases(stepLength(r, i));
      // The clock ticks every 100 ms, so a move is seen up to a tick late. Within a tick it plays from its start a
      // little faster and still lands on time (skipping ahead would make it jump); a page opened mid-move picks it up
      // where it is. The spring back after landing (SETTLE_MS) runs on into the rest of the step.
      const late = h.current === i ? Math.max(0, (h.part - (b ? SQUARE_AT : HOP_AT)) * stepLength(r, i)) : 0;
      const full = b ? p.pushLen : p.hopLen;
      // A tick of the clock is rate × as long on the race's time.
      const catchUp = CATCH_UP_MS * rate.value;
      const ms = late < catchUp ? Math.max(1, full - late) : full;
      let frames: Keyframe[];
      if (b && s.square === "portal") frames = portalFrames(from, to, unit, ms);
      else if (b && (s.square === "flip" || s.react?.includes(m))) frames = flipFrames(from, to, unit, ms);
      else {
        const by = squareAt(s.to)?.by;
        const path = stepPath(s, props.track, by ?? BOOST, by ?? TRIP)[b ? "push" : "hop"];
        if (!path.length) continue;
        const lvl = [s.m, ...(s.carry ?? [])].indexOf(m);
        const n = 1 + (s.carry?.length ?? 0);
        frames = walkFrames([from, ...path.map((sq, j) => (j === path.length - 1 ? to : footOf(sq, Math.max(0, lvl), n)))], unit, ms);
      }
      const run = node.animate(frames, { duration: ms + SETTLE_MS });
      run.playbackRate = rate.value;
      if (late >= catchUp) run.currentTime = late;
    }
  }
  was = { ...ats.value };
}, { flush: "post" });
</script>

<template>
  <div class="track" :class="{ calm: reducedMotion }">
    <div class="board" :class="{ live: ready && step, cleared, routed }" :style="{ '--w': board.cols, '--h': board.rows }">
      <div ref="ringEl" class="ring">
        <svg v-if="routed && routePoints" class="route" :viewBox="`0 0 ${board.cols} ${board.rows}`" aria-hidden="true">
          <polyline class="groove" :points="routePoints" />
          <polyline class="bridge" :points="routePoints" />
        </svg>
        <span
          v-for="c in scenery" :key="c.kind" class="scene" :class="c.kind" aria-hidden="true"
          :style="{ gridColumn: c.col + 1, gridRow: c.row + 1 }"
        >
          <Icon v-if="c.kind !== 'alpaca'" :name="c.kind" :size="24" />
        </span>
        <div
          v-for="sq in squares" :key="sq" class="tile" :data-sq="sq" :style="cellStyle(sq)"
          :class="[cornerClass(sq), kindOf(sq), {
            start: sq === 0, finish: routed && sq === finish, alt: sq % 2 === 1, flash: tail && sq === finish,
            acting: acting.includes(sq), spot: activeSq === sq,
          }]"
        >
          <i v-if="routed && sq && sq < track" class="no" aria-hidden="true">{{ sq }}</i>
          <svg
            v-if="sq === 0" class="origin" :style="{ rotate: `${originDeg}deg` }" viewBox="0 0 16 16"
            aria-hidden="true"
          ><path d="M4.2 4.2 8 8l-3.8 3.8M8.6 4.2 12.4 8l-3.8 3.8" /></svg>
          <span v-else-if="routed && sq === finish" class="goal" aria-hidden="true"><Icon name="crown" :size="16" /></span>
          <span v-else-if="kindOf(sq) === 'boost'" class="cap" :title="`+${squareAt(sq)?.by}`">
            <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 7.4 6 3.8l3.5 3.6M2.5 10.4 6 6.8l3.5 3.6" /></svg>+{{ squareAt(sq)?.by }}
          </span>
          <span v-else-if="kindOf(sq) === 'trip'" class="pit" :title="`−${squareAt(sq)?.by}`">
            <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 1.8 6 5.4l3.5-3.6M2.5 4.8 6 8.4l3.5-3.6" /></svg>−{{ squareAt(sq)?.by }}
          </span>
          <span v-else-if="kindOf(sq) === 'again'" class="redo" title="再掷一次" aria-hidden="true">
            <svg viewBox="0 0 16 16"><rect x="2.5" y="2.5" width="11" height="11" rx="2.6" /><circle cx="5.6" cy="5.6" r="1.1" /><circle cx="10.4" cy="5.6" r="1.1" /><circle cx="8" cy="8" r="1.1" /><circle cx="5.6" cy="10.4" r="1.1" /><circle cx="10.4" cy="10.4" r="1.1" /></svg>
          </span>
          <span v-else-if="kindOf(sq) === 'hook'" class="grab" title="钩索" aria-hidden="true">
            <svg viewBox="0 0 16 16"><path d="M8 2v7.2a3 3 0 1 1-6 0V8M8 2 5.6 4.4M8 2l2.4 2.4M11 9.5l3 3M14 9.5l-3 3" /></svg>
          </span>
          <span v-else-if="kindOf(sq) === 'portal'" class="gate" aria-hidden="true"><i></i></span>
          <span v-else-if="kindOf(sq) === 'flip'" class="turn" aria-hidden="true">
            <svg viewBox="0 0 16 16"><path d="M5 13.5V2.5M2 5.5l3-3 3 3M11 2.5v11M8 10.5l3 3 3-3" /></svg>
          </span>
          <Icon v-else-if="decoOf(sq) === 'ferris'" class="deco ferris" name="ferris" :size="24" />
          <img v-else-if="decoOf(sq) === 'coin'" class="deco coin" :src="COIN" alt="" draggable="false" />
          <img v-else-if="decoOf(sq) === 'alpaca'" class="deco alpaca" :src="alpaca" alt="" draggable="false" />
        </div>
        <svg v-if="routed && wayPath" class="ways" :viewBox="`0 0 ${board.cols} ${board.rows}`" aria-hidden="true">
          <path class="way" :d="wayPath" />
        </svg>
        <template v-if="!routed">
          <div class="island"><span v-if="caption" class="plate">{{ caption }}</span></div>
          <div v-if="$slots.default" class="infield"><slot /></div>
        </template>
        <svg v-if="links.length" class="links" :viewBox="`0 0 ${board.cols} ${board.rows}`" aria-hidden="true">
          <g v-for="l in links" :key="l.key" class="warp" :class="{ lit: acting.includes(l.at) }">
            <path class="halo" :d="l.d" />
            <path class="chord" :d="l.d" />
            <circle class="node" :cx="l.p1.x" :cy="l.p1.y" r="0.065" />
            <circle class="node" :cx="l.p2.x" :cy="l.p2.y" r="0.065" />
          </g>
        </svg>
        <div
          v-for="m in members" :key="m" :ref="(el) => { if (el) tzEls[m] = el as HTMLElement }" class="tz" :data-m="m"
          :class="{
            gated: !places[m]?.square, moving: movers.includes(m), mover: step?.m === m, top: (places[m]?.level ?? 0) > 0,
            waiting: waiting && step?.m === m,
          }"
          :style="style(m)" :title="nameOf(m)"
        >
          <div class="body"><TuanziToken :member="m" /></div>
          <b v-if="ready && roll?.m === m" :key="roll.key" class="roll" :class="{ down: roll.down, side: above[m] || (places[m]?.level ?? 0) >= 2, flip: flipped(m) }" aria-hidden="true">{{ roll.text }}</b>
          <span v-if="ready && moment?.m === m" :key="moment.key" class="say" :class="[moment.kind, { flip: flipped(m) }]" aria-hidden="true">
            {{ moment.text }}
          </span>
          <span v-if="leader === m && !above[m]" class="crown" aria-hidden="true"><Icon name="crown" :size="22" /></span>
        </div>
        <SkillCutIn
          v-if="ready && cut" :key="cut.key" :member="cut.m" :who="cut.who" :name="cut.name" :text="cut.text"
          :color="cut.color" :ms="cut.ms" :at="cut.at"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The track is the size container: the board takes the largest size its box allows, centred under the head room. */
.track {
  container-type: size;
  position: relative;
  width: 100%;
}
/*
 * The slab: coral, RIM of a unit round the ring, standing LIP of a unit on a darker edge like a key. --u is a unit
 * (a square's side) in px; the board is --w × --h units plus the rim, and the lip under it. Over it there is room
 * for a stack on the top row, which rises at most RISE (half a unit) past the square's top, and the crown or a word on
 * it (--head: half a unit and 8px).
 */
.board {
  --rim: 0.08;
  --lip: 0.06;
  --head-u: 0.5;
  --head-px: 8px;
  --u: min(
    calc((100cqw - 8px) / (var(--w) + 2 * var(--rim))),
    calc((100cqh - 12px) / (var(--h) + 2 * var(--rim) + var(--lip) + var(--head-u)))
  );
  --head: calc(var(--head-px) + var(--u) * var(--head-u));
  /* A tuanzi (D of a unit); see RaceTrack's script. */
  --d: calc(var(--u) * 0.8);
  --line: max(1px, calc(var(--u) * 0.024));
  --ring-r: calc(var(--u) * 0.2);
  position: absolute;
  left: 50%;
  top: calc(var(--head) + (100cqh - var(--head) - (var(--h) + 2 * var(--rim) + var(--lip)) * var(--u)) / 2);
  translate: -50% 0;
  padding: calc(var(--rim) * var(--u));
  border-radius: calc(var(--ring-r) + var(--rim) * var(--u));
  background: var(--c-500);
  box-shadow:
    inset 0 1.5px 0 rgba(255, 255, 255, 0.42),
    inset 0 -1px 0 rgba(var(--c-900-rgb), 0.12),
    0 calc(var(--lip) * var(--u)) 0 var(--c-600),
    0 calc(var(--lip) * var(--u) + 2px) calc(var(--u) * 0.3) calc(var(--u) * -0.1) rgba(var(--c-900-rgb), 0.35);
}
/* Map-only thumbnail on the stall page: no stacks stand over it, so the board takes the full box. */
.track.mini .board {
  --head-u: 0;
  --head-px: 0px;
  --u: min(
    calc((100cqw - 4px) / (var(--w) + 2 * var(--rim))),
    calc((100cqh - 6px) / (var(--h) + 2 * var(--rim) + var(--lip)))
  );
}
.board.cleared .tz {
  opacity: 0;
  visibility: hidden;
  transition: opacity var(--dur-slow), visibility 0s var(--dur-slow);
}

/*
 * The ring: the grid of squares and the tuanzi's frame of reference (no border, no padding: race.ts units from its
 * top left). Its own face is the hairline colour that shows between the squares.
 */
.ring {
  position: relative;
  display: grid;
  grid-template-columns: repeat(var(--w), var(--u));
  grid-template-rows: repeat(var(--h), var(--u));
  border-radius: var(--ring-r);
  background: var(--c-300);
}
/*
 * On a route the squares are stepping stones linked along a recessed stone course: no full face of its own, a faint
 * print of dots on the coral, and the route bridge joining each stone to the next while keeping parallel columns apart.
 */
.routed .ring {
  background: none;
}
.routed .ring::before {
  content: "";
  position: absolute;
  inset: 0;
  background: #fff;
  opacity: 0.14;
  -webkit-mask: url("../../assets/patterns/halftone.svg") 0 0 / calc(var(--u) * 3.2) calc(var(--u) * 1.6);
  mask: url("../../assets/patterns/halftone.svg") 0 0 / calc(var(--u) * 3.2) calc(var(--u) * 1.6);
  pointer-events: none;
}
.routed .ring::after {
  display: none;
}
.route,
.ways,
.links {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
  pointer-events: none;
}
.route {
  z-index: 0;
}
.route .groove,
.route .bridge {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.route .groove {
  stroke: var(--c-600);
  stroke-width: 0.48;
}
.route .bridge {
  stroke: var(--c-200);
  stroke-width: 0.34;
}
.ways {
  z-index: 2;
}
.ways .way {
  fill: none;
  stroke: var(--c-600);
  stroke-width: 0.032;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.routed .tile {
  z-index: 1;
  margin: calc(var(--u) * 0.055);
  border-radius: calc(var(--u) * 0.14);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.7),
    inset 0 calc(var(--u) * -0.025) 0 var(--c-100),
    0 calc(var(--u) * 0.02) calc(var(--u) * 0.05) rgba(var(--c-900-rgb), 0.16),
    0 0 0 var(--line) rgba(var(--c-900-rgb), 0.12);
}
/* A square's number, tucked cleanly in its top-left corner outside any special stone's inlay. */
.no {
  position: absolute;
  z-index: 2;
  left: 5%;
  top: 4.5%;
  padding: 1px 2.5px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.9);
  font: 800 max(8.5px, calc(var(--u) * 0.135)) / 1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
  pointer-events: none;
}
/* The finish of a route: a bold checkered flag framing a gold-rimmed champion medallion. */
.routed .tile.finish {
  overflow: hidden;
  background: repeating-conic-gradient(var(--c-500) 0 25%, #fff 0 50%) 0 0 / calc(var(--u) * 0.28) calc(var(--u) * 0.28);
}
.routed .tile.start::after {
  display: none;
}
.goal {
  position: absolute;
  inset: 19%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(180deg, color-mix(in oklab, var(--gold-soft) 32%, #fff), var(--gold-soft));
  box-shadow:
    0 0 0 max(1.5px, calc(var(--u) * 0.04)) var(--gold),
    0 calc(var(--u) * 0.03) calc(var(--u) * 0.08) rgba(var(--c-900-rgb), 0.28);
  color: var(--gold);
}
.goal :deep(.icon) {
  width: 64%;
  height: 64%;
}
/* A portal's two ends: a gentle curved dashed arc linking rim to rim across the board. */
.links {
  z-index: 4;
}
.warp .halo,
.warp .chord {
  fill: none;
  stroke-linecap: round;
}
.warp .halo {
  stroke: var(--c-600);
  stroke-opacity: 0.52;
  stroke-width: 0.085;
  stroke-dasharray: 0.09 0.15;
}
.warp .chord {
  stroke: #fff;
  stroke-opacity: 0.94;
  stroke-width: 0.048;
  stroke-dasharray: 0.09 0.15;
}
.warp .node {
  fill: #fff;
  stroke: var(--c-600);
  stroke-width: 0.03;
}
.warp.lit .halo {
  stroke: var(--c-500);
  stroke-opacity: 0.95;
  stroke-width: 0.12;
}
/* Pictures of the park printed on the slab where no square lies. */
.scene {
  display: grid;
  place-items: center;
  color: #fff;
  opacity: 0.42;
  pointer-events: none;
}
.scene svg {
  width: 62%;
  height: 62%;
}
.scene.alpaca {
  margin: 10%;
  background: #fff;
  -webkit-mask: url("../../assets/brand/side-alpaca.webp") center / contain no-repeat;
  mask: url("../../assets/brand/side-alpaca.webp") center / contain no-repeat;
}

/* Inlaid: the slab's edge shades the squares along it. */
.ring::after {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 1;
  border-radius: inherit;
  box-shadow:
    inset 0 calc(var(--u) * 0.05) calc(var(--u) * 0.08) rgba(var(--c-900-rgb), 0.26),
    inset 0 0 0 1px rgba(var(--c-900-rgb), 0.1);
  pointer-events: none;
}

/* ---- the squares: paper in two shades by turns, a hairline between; never keycaps */
.tile {
  position: relative;
  display: grid;
  place-items: center;
  margin: calc(var(--line) / 2);
  background: var(--surface);
  transition: box-shadow var(--dur-base) var(--ease-out);
}
.tile.alt {
  background: var(--c-100);
}
/* Active mover's stone: ringed in warm coral so the mover anchors to the board. */
.tile.spot {
  z-index: 2;
  box-shadow:
    inset 0 0 0 max(2px, calc(var(--u) * 0.055)) var(--c-500),
    0 0 calc(var(--u) * 0.18) rgba(var(--c-500-rgb), 0.45);
}
.tile.tl { border-top-left-radius: calc(var(--ring-r) - var(--line) / 2); }
.tile.tr { border-top-right-radius: calc(var(--ring-r) - var(--line) / 2); }
.tile.br { border-bottom-right-radius: calc(var(--ring-r) - var(--line) / 2); }
.tile.bl { border-bottom-left-radius: calc(var(--ring-r) - var(--line) / 2); }
/* The start (and on the lap, also the finish): coral check with a directional launch chevron towards square 1. */
.tile.start {
  overflow: hidden;
  background:
    radial-gradient(circle, rgba(255, 255, 255, 0.82) 34%, transparent 66%),
    repeating-conic-gradient(var(--c-200) 0 25%, var(--c-50) 0 50%) 0 0 / calc(var(--u) * 0.25) calc(var(--u) * 0.25);
}
.routed .tile.start {
  box-shadow:
    inset 0 0 0 max(2px, calc(var(--u) * 0.045)) var(--c-400),
    0 calc(var(--u) * 0.02) calc(var(--u) * 0.05) rgba(var(--c-900-rgb), 0.16);
}
.origin {
  width: 52%;
  height: 52%;
  fill: none;
  stroke: var(--c-600);
  stroke-width: 2.3;
  stroke-linecap: round;
  stroke-linejoin: round;
  opacity: 0.85;
  pointer-events: none;
}
.board:not(.routed) .origin {
  translate: 0 -8%;
}
.tile.start::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: calc(var(--u) * 0.2);
  background: repeating-conic-gradient(var(--c-500) 0 25%, #fff 0 50%) 0 0 / calc(var(--u) * 0.2) calc(var(--u) * 0.2);
}
.tile.flash {
  animation: finish-flash 900ms var(--ease-out) 2;
}
@keyframes finish-flash {
  40% { box-shadow: inset 0 0 0 calc(var(--u) * 0.08) rgba(255, 255, 255, 0.78), var(--glow-l); }
}
/* The other corners: a faint picture of the park. */
.deco {
  width: 56%;
  height: 56%;
  object-fit: contain;
  pointer-events: none;
  user-select: none;
}
.deco.ferris {
  color: var(--c-300);
}
.deco.coin {
  opacity: 0.4;
}
.deco.alpaca {
  height: 74%;
  opacity: 0.28;
  filter: grayscale(1);
}
/* Boost & trip squares: flush inlaid stone pads (never raised keycaps!). */
.cap,
.pit {
  position: absolute;
  inset: 13.5%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: calc(var(--u) * 0.02);
  border-radius: calc(var(--u) * 0.12);
  font: 800 max(11.5px, calc(var(--u) * 0.26)) / 1 var(--font-latin);
}
/* Boost: warm coral inlay flush with the tile, double chevron up. */
.cap {
  background: linear-gradient(180deg, var(--c-200), var(--c-300));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.7),
    inset 0 0 0 max(1.5px, calc(var(--u) * 0.038)) var(--c-500);
  color: var(--ink);
}
/* Trip: recessed terracotta pit sunk into the slab, crisp white chevron & digits. */
.pit {
  background: var(--c-700);
  box-shadow:
    inset 0 calc(var(--u) * 0.06) calc(var(--u) * 0.09) rgba(var(--c-900-rgb), 0.48),
    inset 0 -1px 0 rgba(255, 255, 255, 0.28),
    0 1px 0 rgba(255, 255, 255, 0.8);
  color: #fff;
}
/* Both ends of the portal: flush coral collar round a glowing hole into the slab. */
.gate {
  position: absolute;
  inset: 16.5%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--c-500);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.5),
    inset 0 0 0 max(1px, calc(var(--u) * 0.025)) var(--c-600);
}
.gate i {
  width: 58%;
  height: 58%;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 40%, #fff, var(--c-300) 58%, var(--c-600));
  box-shadow: inset 0 calc(var(--u) * 0.04) calc(var(--u) * 0.06) rgba(var(--c-900-rgb), 0.42), 0 0 0 calc(var(--u) * 0.038) #fff;
}
/* The flip square: flush inlaid disc on the tile, arrows up and down. */
.turn {
  position: absolute;
  inset: 15%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--c-100);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.75),
    inset 0 0 0 max(1.5px, calc(var(--u) * 0.042)) var(--c-500);
  color: var(--c-700);
}
.turn svg {
  width: 62%;
  height: 62%;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.9;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* The again square: flush inlaid die emblem on the stone. */
.redo {
  position: absolute;
  inset: 17%;
  display: grid;
  place-items: center;
  border-radius: 24%;
  background: var(--surface);
  box-shadow:
    inset 0 1px 0 #fff,
    inset 0 0 0 max(1.5px, calc(var(--u) * 0.04)) var(--c-500);
  color: var(--c-700);
  rotate: -6deg;
}
.redo svg {
  width: 100%;
  height: 100%;
}
.redo rect {
  fill: none;
}
.redo circle {
  fill: currentColor;
}
/* The hook square: flush coral medallion with a grappling hook. */
.grab {
  position: absolute;
  inset: 15%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(180deg, var(--c-300), var(--c-400));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    inset 0 0 0 max(1.5px, calc(var(--u) * 0.038)) var(--c-600);
  color: var(--ink);
}
.grab svg {
  width: 62%;
  height: 62%;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.9;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* Any special square at work: swells once with a coral glow round it. */
.cap::after,
.pit::after,
.gate::after,
.turn::after,
.redo::after,
.grab::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: var(--glow-l);
  opacity: 0;
  pointer-events: none;
}
.tile.acting .cap,
.tile.acting .pit,
.tile.acting .gate,
.tile.acting .turn,
.tile.acting .redo,
.tile.acting .grab {
  animation: acting 520ms var(--ease-out);
}
.tile.acting .cap::after,
.tile.acting .pit::after,
.tile.acting .gate::after,
.tile.acting .turn::after,
.tile.acting .redo::after,
.tile.acting .grab::after {
  animation: acting-glow 520ms var(--ease-out);
}
@keyframes acting {
  40% { transform: scale(1.12); }
}
@keyframes acting-glow {
  40% { opacity: 1; }
}
.cap svg,
.pit svg {
  width: max(11px, calc(var(--u) * 0.22));
  height: max(11px, calc(var(--u) * 0.22));
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

/* ---- inside the lap ring the slab rises as a stadium island with a park watermark and nameplate */
.island,
.infield {
  grid-row: 2 / -2;
  grid-column: 2 / -2;
}
.island {
  position: relative;
  z-index: 2;
  margin: calc(var(--line) * -0.5);
  border-radius: calc(var(--u) * 0.1);
  background: linear-gradient(180deg, var(--c-400), var(--c-500) 45%);
  box-shadow:
    inset 0 1.5px 0 rgba(255, 255, 255, 0.38),
    0 calc(var(--u) * 0.045) 0 var(--c-600),
    0 calc(var(--u) * 0.045 + 1px) calc(var(--u) * 0.12) rgba(var(--c-900-rgb), 0.28);
}
/* Inner stadium infield track line. */
.island::before {
  content: "";
  position: absolute;
  inset: calc(var(--u) * 0.18);
  border-radius: calc(var(--u) * 0.07);
  border: max(1px, calc(var(--u) * 0.02)) dashed rgba(255, 255, 255, 0.32);
  pointer-events: none;
}
/* Subtle A-SOUL park mark printed in the center of the stadium island. */
.island::after {
  content: "";
  position: absolute;
  left: 50%;
  top: 46%;
  width: calc(var(--u) * 1.9);
  aspect-ratio: 3.172;
  translate: -50% -50%;
  background: #fff;
  opacity: 0.2;
  -webkit-mask: url("../../assets/brand/asoul-logo.svg") center / contain no-repeat;
  mask: url("../../assets/brand/asoul-logo.svg") center / contain no-repeat;
  pointer-events: none;
}
/* The map's name, centered along the island's lower edge. */
.plate {
  position: absolute;
  left: 50%;
  bottom: calc(var(--u) * 0.26);
  translate: -50% 0;
  padding: calc(var(--u) * 0.03) calc(var(--u) * 0.14);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.24);
  font: 800 clamp(9px, calc(var(--u) * 0.15), var(--fs-label)) / 1.2 var(--font);
  letter-spacing: 0.12em;
  color: var(--ink);
  white-space: nowrap;
}
.infield {
  position: relative;
  z-index: 3;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  margin: calc(var(--u) * 0.2) calc(var(--u) * 0.22) calc(var(--u) * 0.24);
  padding: calc(var(--u) * 0.1) calc(var(--u) * 0.14);
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--c-900-rgb), 0.18), 0 calc(var(--u) * 0.06) calc(var(--u) * 0.18) calc(var(--u) * -0.06) rgba(var(--c-900-rgb), 0.3);
}

/* ---- a tuanzi stands on its square, --rise units up its stack (the script's stepOf) */
.tz {
  position: absolute;
  z-index: 10;
  left: 0;
  top: 0;
  width: var(--d);
  height: var(--d);
  --tuanzi-size: var(--d);
  transform: translate(
    calc(var(--x) * var(--u) - var(--d) / 2),
    calc((var(--y) - var(--rise)) * var(--u) - var(--d))
  );
  transition: transform 320ms var(--ease-out);
}
/* A soft shadow at the feet of the one at the bottom of a stack (or alone). */
.tz::before {
  content: "";
  position: absolute;
  left: 12%;
  right: 12%;
  bottom: -5%;
  height: 18%;
  border-radius: 50%;
  background: radial-gradient(closest-side, rgba(var(--c-900-rgb), 0.34), transparent);
}
.tz.top::before {
  display: none;
}
/* Contact shadow between stacked dumplings so each visibly rests on the head beneath it. */
.tz.top .body {
  filter: drop-shadow(0 max(1.5px, calc(var(--u) * 0.025)) max(1.5px, calc(var(--u) * 0.025)) rgba(var(--c-900-rgb), 0.24));
}
.body {
  width: 100%;
  height: 100%;
  transform-origin: 50% 97%;
  transition: scale var(--dur-slow) var(--ease-out), filter var(--dur-slow) var(--ease-out);
}
.body > * {
  display: block;
}
/* On the start square the five stand smaller, in two rows (CROWD). */
.tz.gated .body {
  scale: 0.5;
}
.tz.gated::before {
  left: 24%;
  right: 24%;
  bottom: 0;
}
/* While a step plays: the one rolling a bit bigger, everyone not moving faded towards the paper. */
.tz.mover .body {
  scale: 1.14;
}
.board.live .tz:not(.moving) .body {
  filter: saturate(0.45) contrast(0.86) brightness(1.08);
}
/* The one whose turn it is, until it sets off: a coral glow around it, breathing. */
.tz.waiting .body {
  filter: drop-shadow(0 0 3px var(--c-500)) drop-shadow(0 0 3px var(--c-500)) drop-shadow(0 0 10px var(--c-500));
  animation: wait-glow 1s var(--ease-in-out) infinite alternate;
}
@keyframes wait-glow {
  from { filter: drop-shadow(0 0 2px var(--c-500)) drop-shadow(0 0 1px var(--c-500)) drop-shadow(0 0 4px rgba(var(--c-500-rgb), 0.6)); }
}
/* ---- over the group: the squares walked; aside: a word */
.roll {
  position: absolute;
  left: 50%;
  bottom: calc(100% + var(--over, 0) * var(--u) + 4px);
  pointer-events: none;
}
/* Over a stack there is no room above: beside its top instead, on the side away from the word. */
.roll.side {
  left: calc(50% - var(--d) * 0.55);
  bottom: calc(100% + var(--over, 0) * var(--u) - var(--d) * 0.5);
  translate: -100% 0;
}
/* Near the right turn the word is on the left, so the digits go right. */
.roll.side.flip {
  left: calc(50% + var(--d) * 0.55);
  translate: 0 0;
}
/* The squares walked: coral digits with a crisp white sticker outline. */
.roll {
  font: 800 calc(var(--d) * 0.5) / 1 var(--font-latin);
  color: var(--c-600);
  -webkit-text-stroke: clamp(2.5px, calc(var(--d) * 0.08), 4.2px) var(--surface);
  paint-order: stroke fill;
  text-shadow: 0 2px 6px rgba(var(--c-900-rgb), 0.25);
  white-space: nowrap;
  translate: -50% 0;
  animation: roll 1100ms var(--ease-out) both;
}
.roll.down {
  color: var(--c-800);
}
@keyframes roll {
  0% { opacity: 0; transform: translateY(10px) scale(0.6); }
  22% { opacity: 1; transform: translateY(0) scale(1.15); }
  40% { transform: translateY(-2px) scale(1); }
  78% { opacity: 1; transform: translateY(-10px); }
  100% { opacity: 0; transform: translateY(-16px); }
}
/* A word: a speech bubble off the head's upper right (upper left near the right turn). */
.say {
  position: absolute;
  z-index: 3;
  left: 72%;
  bottom: calc(76% + var(--over, 0) * var(--u));
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--surface);
  box-shadow: 0 0 0 2px var(--c-300), 0 6px 12px -6px rgba(var(--c-900-rgb), 0.4);
  font: 800 var(--fs-strong)/1.1 var(--font);
  color: var(--ink);
  white-space: nowrap;
  pointer-events: none;
  transform-origin: 0 100%;
  animation: say 360ms var(--ease-pop) both;
}
.say::after {
  content: "";
  position: absolute;
  z-index: -1;
  left: 7px;
  bottom: -4px;
  width: 8px;
  height: 8px;
  background: var(--surface);
  box-shadow: 2px 2px 0 0 var(--c-300);
  transform: rotate(45deg) skew(8deg, 8deg);
  border-radius: 0 0 3px 0;
}
.say.flip {
  left: auto;
  right: 72%;
  transform-origin: 100% 100%;
}
.say.flip::after {
  left: auto;
  right: 7px;
}
.say.skill,
.say.boost {
  background: var(--c-500);
  color: var(--ink);
  box-shadow: 0 0 0 2px var(--surface), 0 6px 12px -6px rgba(var(--c-900-rgb), 0.4);
}
.say.skill::after,
.say.boost::after {
  background: var(--c-500);
  box-shadow: 2px 2px 0 0 var(--surface);
}
/* 1st-place lead callout: legendary gold-soft pill. */
.say.lead {
  background: linear-gradient(180deg, color-mix(in oklab, var(--gold-soft) 32%, #fff), var(--gold-soft));
  color: var(--ink);
  box-shadow: 0 0 0 2px var(--gold), 0 6px 12px -6px rgba(var(--c-900-rgb), 0.4);
}
.say.lead::after {
  background: var(--gold-soft);
  box-shadow: 2px 2px 0 0 var(--gold);
}
.say.trip {
  background: var(--c-100);
  color: var(--c-800);
  box-shadow: 0 0 0 2px var(--c-500), 0 6px 12px -6px rgba(var(--c-900-rgb), 0.4);
}
.say.trip::after {
  background: var(--c-100);
  box-shadow: 2px 2px 0 0 var(--c-500);
}
@keyframes say {
  from { opacity: 0; transform: scale(0.4); }
}
/* The 1st-place leader, crowned in gold with a crisp white sticker contour. */
.crown {
  position: absolute;
  left: 50%;
  bottom: 81%;
  translate: -50% 0;
  color: var(--gold);
  filter:
    drop-shadow(0 1.2px 0 #fff) drop-shadow(0 -1.2px 0 #fff)
    drop-shadow(1.2px 0 0 #fff) drop-shadow(-1.2px 0 0 #fff)
    drop-shadow(0 2px 2px rgba(var(--c-900-rgb), 0.28));
  animation: say 420ms var(--ease-pop) both;
}
.crown :deep(path) {
  fill: var(--gold-soft);
}


.calm .tz,
.calm .body,
.calm .tile {
  transition: none;
}
.calm .tz.waiting .body,
.calm .roll,
.calm .say,
.calm .crown,
.calm .tile.flash,
.calm .tile.acting .cap,
.calm .tile.acting .pit,
.calm .tile.acting .gate,
.calm .tile.acting .turn,
.calm .tile.acting .redo,
.calm .tile.acting .grab,
.calm .tile.acting .cap::after,
.calm .tile.acting .pit::after,
.calm .tile.acting .gate::after,
.calm .tile.acting .turn::after,
.calm .tile.acting .redo::after,
.calm .tile.acting .grab::after {
  animation: none;
}

/* A small board (the race page's bill): clean map preview without tiny numbers, chevrons or arrows. */
@container (max-width: 420px) {
  .no,
  .plate,
  .ways,
  .cap svg,
  .pit svg {
    display: none;
  }
  .island::after {
    width: calc(var(--u) * 2.2);
  }
  .cap,
  .pit {
    font-size: calc(var(--u) * 0.42);
  }
}

/* Small squares: smaller words. */
@container (max-width: 620px), (max-height: 380px) {
  .say {
    padding: 3px 7px;
    font-size: var(--fs-label);
  }
}
</style>
