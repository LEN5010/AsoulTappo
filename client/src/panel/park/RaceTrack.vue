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
/** On a route: the pictures where no square lies, and each portal's two ends (their middles, in units). */
const SCENERY = ["ferris", "alpaca", "crown"] as const;
const scenery = computed(() =>
  (routed.value ? sceneryCells(board.value, props.track, SCENERY.length) : []).map((c, k) => ({ ...c, kind: SCENERY[k] })),
);
const links = computed(() => {
  if (!routed.value) return [];
  const mid = (sq: number) => ({ x: board.value.cell(sq).col + 0.5, y: board.value.cell(sq).row + 0.5 });
  return (props.race?.setup.map?.squares ?? []).filter((q) => q.kind === "portal" && q.to !== undefined)
    .map((q) => ({ key: q.at, a: mid(q.at), b: mid(q.to!) }));
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
        <svg v-if="links.length" class="links" :viewBox="`0 0 ${board.cols} ${board.rows}`" aria-hidden="true">
          <line v-for="l in links" :key="l.key" :x1="l.a.x" :y1="l.a.y" :x2="l.b.x" :y2="l.b.y" />
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
            acting: acting.includes(sq),
          }]"
        >
          <i v-if="routed && sq && sq < track && !kindOf(sq)" class="no" aria-hidden="true">{{ sq }}</i>
          <span v-if="kindOf(sq) === 'boost'" class="cap" :title="`+${squareAt(sq)?.by}`">
            <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" /></svg>+{{ squareAt(sq)?.by }}
          </span>
          <span v-else-if="kindOf(sq) === 'trip'" class="pit" :title="`−${squareAt(sq)?.by}`">
            <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" /></svg>−{{ squareAt(sq)?.by }}
          </span>
          <span v-else-if="kindOf(sq) === 'again'" class="redo" title="再掷一次" aria-hidden="true">
            <svg viewBox="0 0 16 16"><rect x="2.5" y="2.5" width="11" height="11" rx="2.6" /><circle cx="5.6" cy="5.6" r="1" /><circle cx="10.4" cy="5.6" r="1" /><circle cx="8" cy="8" r="1" /><circle cx="5.6" cy="10.4" r="1" /><circle cx="10.4" cy="10.4" r="1" /></svg>
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
        <template v-if="!routed">
          <div class="island"><span v-if="caption" class="plate">{{ caption }}</span></div>
          <div v-if="$slots.default" class="infield"><slot /></div>
        </template>
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
  --u: min(
    calc((100cqw - 8px) / (var(--w) + 2 * var(--rim))),
    calc((100cqh - 12px) / (var(--h) + 2 * var(--rim) + var(--lip) + 0.5))
  );
  --head: calc(8px + var(--u) * 0.5);
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
    inset 0 1.5px 0 rgba(255, 255, 255, 0.4),
    inset 0 -1px 0 rgba(var(--c-900-rgb), 0.12),
    0 calc(var(--lip) * var(--u)) 0 var(--c-600),
    0 calc(var(--lip) * var(--u) + 2px) calc(var(--u) * 0.3) calc(var(--u) * -0.1) rgba(var(--c-900-rgb), 0.35);
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
 * On a route the squares are stepping stones across the slab: no face of its own, a faint print of dots on the coral,
 * each stone inlaid by itself.
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
  mask: url("../../assets/patterns/halftone.svg") 0 0 / calc(var(--u) * 3.2) calc(var(--u) * 1.6);
  pointer-events: none;
}
.routed .ring::after {
  display: none;
}
.routed .tile {
  margin: calc(var(--u) * 0.035);
  border-radius: calc(var(--u) * 0.14);
  box-shadow:
    inset 0 calc(var(--u) * 0.04) calc(var(--u) * 0.06) rgba(var(--c-900-rgb), 0.2),
    0 1px 0 rgba(255, 255, 255, 0.45),
    0 0 0 var(--line) rgba(var(--c-900-rgb), 0.1);
}
/* A square's number, small in its corner. */
.no {
  position: absolute;
  left: 9%;
  top: 8%;
  font: 800 max(9px, calc(var(--u) * 0.17)) / 1 var(--font-latin);
  font-style: normal;
  color: var(--c-400);
}
/* The finish of a route: the bold check of a flag, a paper ring inside it. */
.routed .tile.finish {
  overflow: hidden;
  background: repeating-conic-gradient(var(--c-500) 0 25%, #fff 0 50%) 0 0 / calc(var(--u) * 0.31) calc(var(--u) * 0.31);
}
.routed .tile.start::after {
  display: none;
}
/* A portal's two ends: a dashed line across the slab, under the stones. */
.links {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
  pointer-events: none;
}
.links line {
  stroke: #fff;
  stroke-opacity: 0.7;
  stroke-width: 0.07;
  stroke-linecap: round;
  stroke-dasharray: 0.02 0.19;
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
    inset 0 calc(var(--u) * 0.05) calc(var(--u) * 0.08) rgba(var(--c-900-rgb), 0.28),
    inset 0 0 0 1px rgba(var(--c-900-rgb), 0.1);
  pointer-events: none;
}

/* ---- the squares: paper in two shades by turns, a hairline between */
.tile {
  position: relative;
  display: grid;
  place-items: center;
  margin: calc(var(--line) / 2);
  background: var(--surface);
}
.tile.alt {
  background: var(--c-100);
}
.tile.tl { border-top-left-radius: calc(var(--ring-r) - var(--line) / 2); }
.tile.tr { border-top-right-radius: calc(var(--ring-r) - var(--line) / 2); }
.tile.br { border-bottom-right-radius: calc(var(--ring-r) - var(--line) / 2); }
.tile.bl { border-bottom-left-radius: calc(var(--ring-r) - var(--line) / 2); }
/* The start, also the finish: a faint coral check, with a coral and white checkered line where the lap ends. */
.tile.start {
  overflow: hidden;
  background: repeating-conic-gradient(var(--c-200) 0 25%, var(--c-50) 0 50%) 0 0 / calc(var(--u) * 0.25) calc(var(--u) * 0.25);
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
.tile.start.flash {
  animation: finish-flash 900ms var(--ease-out) 2;
}
@keyframes finish-flash {
  40% { box-shadow: inset 0 0 0 calc(var(--u) * 0.08) rgba(255, 255, 255, 0.7), var(--glow-l); }
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
/* The boost square: a key of the slab standing up out of the paper, an arrow up and the squares it pushes. */
.cap,
.pit {
  position: absolute;
  inset: 12%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: calc(var(--u) * 0.04);
  border-radius: var(--radius-key-s);
  font: 800 max(var(--fs-strong), calc(var(--u) * 0.28)) / 1 var(--font-latin);
  color: var(--ink);
}
.cap {
  bottom: calc(12% + var(--u) * 0.07);
  background: linear-gradient(180deg, var(--c-400), var(--c-500));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 calc(var(--u) * 0.07) 0 var(--c-600),
    0 calc(var(--u) * 0.07 + 2px) calc(var(--u) * 0.14) calc(var(--u) * -0.04) rgba(var(--c-900-rgb), 0.4);
}
/* The trip square: a pit sunk through the paper into the slab, an arrow down and the squares it sets back. */
.pit {
  background: color-mix(in oklab, var(--c-600) 80%, var(--c-700));
  box-shadow:
    inset 0 calc(var(--u) * 0.08) calc(var(--u) * 0.1) rgba(var(--c-900-rgb), 0.55),
    inset 0 -1px 0 rgba(255, 255, 255, 0.35),
    0 1px 0 rgba(255, 255, 255, 0.8);
}
/* Both ends of the portal: the same coral ring round a hole into the slab, so they read as a pair. */
.gate {
  position: absolute;
  inset: 16%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--c-500);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), 0 calc(var(--u) * 0.04) 0 var(--c-600);
}
.gate i {
  width: 58%;
  height: 58%;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 40%, var(--c-200), var(--c-400) 60%, var(--c-600));
  box-shadow: inset 0 calc(var(--u) * 0.04) calc(var(--u) * 0.06) rgba(var(--c-900-rgb), 0.45), 0 0 0 calc(var(--u) * 0.04) #fff;
}
/* The flip square: a paper disc on the slab, an arrow up beside an arrow down. */
.turn {
  position: absolute;
  inset: 14%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--c-100);
  box-shadow: 0 0 0 calc(var(--u) * 0.05) var(--c-500), 0 calc(var(--u) * 0.06) 0 calc(var(--u) * 0.02) var(--c-600);
  color: var(--c-700);
}
.turn svg {
  width: 62%;
  height: 62%;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* The again square: a paper die lying on the slab. */
.redo {
  position: absolute;
  inset: 16%;
  display: grid;
  place-items: center;
  border-radius: 24%;
  background: var(--surface);
  box-shadow: 0 0 0 calc(var(--u) * 0.04) var(--c-500), 0 calc(var(--u) * 0.07) 0 calc(var(--u) * 0.02) var(--c-600);
  color: var(--c-600);
  rotate: -8deg;
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
/* The hook square: a coral disc with a hook thrown ahead. */
.grab {
  position: absolute;
  inset: 14%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--c-500);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), 0 calc(var(--u) * 0.06) 0 var(--c-600);
  color: var(--ink);
}
.grab svg {
  width: 62%;
  height: 62%;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* A portal, flip, again or hook square at work: it swells once, a glow coming and going round it. */
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
.tile.acting .gate,
.tile.acting .turn,
.tile.acting .redo,
.tile.acting .grab {
  animation: acting 520ms var(--ease-out);
}
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
  width: max(12px, calc(var(--u) * 0.24));
  height: max(12px, calc(var(--u) * 0.24));
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

/* ---- inside the ring the slab rises again, an island; the infield is a sheet of paper on it */
.island,
.infield {
  grid-row: 2 / -2;
  grid-column: 2 / -2;
}
.island {
  position: relative;
  z-index: 2;
  margin: calc(var(--line) * -0.5);
  border-radius: calc(var(--u) * 0.08);
  background: var(--c-500);
  box-shadow:
    inset 0 1.5px 0 rgba(255, 255, 255, 0.35),
    0 calc(var(--u) * 0.05) 0 var(--c-600),
    0 calc(var(--u) * 0.05 + 1px) calc(var(--u) * 0.12) rgba(var(--c-900-rgb), 0.3);
}
/* The map's name, lettered on the island's lower edge. */
.plate {
  position: absolute;
  left: calc(var(--u) * 0.3);
  bottom: calc(var(--u) * 0.035);
  font: 800 clamp(9px, calc(var(--u) * 0.16), var(--fs-caption)) / 1 var(--font);
  letter-spacing: 0.12em;
  color: color-mix(in oklab, var(--ink) 72%, var(--c-500));
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
  background: radial-gradient(closest-side, rgba(var(--c-900-rgb), 0.32), transparent);
}
.tz.top::before {
  display: none;
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
/* The squares walked: the coral digits with the white outline of the desk's combo count. */
.roll {
  font: 800 calc(var(--d) * 0.5) / 1 var(--font-latin);
  color: var(--c-600);
  -webkit-text-stroke: 4px var(--surface);
  paint-order: stroke fill;
  text-shadow: 0 2px 6px rgba(var(--c-900-rgb), 0.25);
  white-space: nowrap;
  translate: -50% 0;
  animation: roll 1100ms var(--ease-out) both;
}
.roll.down {
  color: var(--ink-2);
}
@keyframes roll {
  0% { opacity: 0; transform: translateY(10px) scale(0.6); }
  22% { opacity: 1; transform: translateY(0) scale(1.15); }
  40% { transform: translateY(-2px) scale(1); }
  78% { opacity: 1; transform: translateY(-10px); }
  100% { opacity: 0; transform: translateY(-16px); }
}
/* A word: a white speech bubble off the head's upper right (upper left near the right turn). */
.say {
  position: absolute;
  z-index: 3;
  left: 72%;
  bottom: calc(76% + var(--over, 0) * var(--u));
  padding: 4px 9px;
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
  left: 6px;
  bottom: -5px;
  width: 9px;
  height: 9px;
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
  right: 6px;
}
.say.lead,
.say.skill,
.say.boost {
  background: var(--c-500);
  color: var(--ink);
  box-shadow: 0 0 0 2px var(--surface), 0 6px 12px -6px rgba(var(--c-900-rgb), 0.4);
}
.say.lead::after,
.say.skill::after,
.say.boost::after {
  background: var(--c-500);
  box-shadow: 2px 2px 0 0 var(--surface);
}
@keyframes say {
  from { opacity: 0; transform: scale(0.4); }
}
/* The winner, crowned while the field stands still at the line. */
.crown {
  position: absolute;
  left: 50%;
  bottom: 80%;
  translate: -50% 0;
  color: var(--c-600);
  filter: drop-shadow(0 1px 0 #fff) drop-shadow(0 -1px 0 #fff) drop-shadow(1px 0 0 #fff) drop-shadow(-1px 0 0 #fff);
  animation: say 420ms var(--ease-pop) both;
}


.calm .tz,
.calm .body {
  transition: none;
}
.calm .tz.waiting .body,
.calm .roll,
.calm .say,
.calm .crown,
.calm .tile.start.flash,
.calm .tile.acting .gate,
.calm .tile.acting .turn,
.calm .tile.acting .gate::after,
.calm .tile.acting .turn::after {
  animation: none;
}

/* A small board (the race page's bill): the map alone, its marks without their arrows and the squares' numbers. */
@container (max-width: 420px) {
  .no,
  .plate,
  .cap svg,
  .pit svg {
    display: none;
  }
  .cap,
  .pit {
    font-size: calc(var(--u) * 0.4);
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
