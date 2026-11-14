<script setup lang="ts">
// The race's board (protocol/PROTOCOL.md 团子赛跑): a ring of paper squares round a rectangle (race.ts boardOf,
// cellOf), square 0 in the top left corner as start and finish, the boost square a raised key, the trip square a pit.
// The space inside the ring is the infield; the page puts what fits the phase there (the slot). The board takes the
// largest square size the track's box allows, with room over the top row for a stack.
// The tuanzi stand on the squares: at the start crowded in the corner, past it stacked bottom to top, the leader
// crowned. Positions come from the move list at the server time [t] (race.ts). A step: the mover lights up (bigger,
// glowing, the others faded) while the page's big die rolls, then the group hops square by square along the ring
// (race.ts stepPath: on to the finish and back when the roll carries past it), a boost or trip square pushes it on
// the same way, and a word pops over the dumpling at the moments that matter. The hops are one Web Animations run
// each, as long as the step's hop (stepPhases); under reduced motion everything jumps and stands still.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import {
  boardOf, cellOf, HOP_AT, leaders, momentOf, moving, playhead, rankOf, saidAt, spots, SQUARE_AT, stacksAt, stageOf,
  stepLength, stepPath, stepPhases, type MomentKind, type Race, type Spot,
} from "./race";
import TuanziToken from "./TuanziToken.vue";

/** [cleared]: the race is over and its result stands in the infield; the field leaves the board. */
const props = defineProps<{ race: Race | null; t: number; track: number; members: string[]; cleared?: boolean }>();

const nameOf = (m: string) => manifest.characters.find((c) => c.id === m)?.name ?? m;

const BOOST = manifest.economy.park?.race?.squares.boost ?? 2;
const TRIP = Math.abs(manifest.economy.park?.race?.squares.trip ?? -1);
const WORDS: Record<MomentKind, string> = { lead: "领先", boost: "冲呀", trip: "哎呀", carry: "抓紧了" };

/*
 * Sizes in squares, the same as the CSS (.board): a tuanzi is D of a square, each one up a stack rises LIFT of a
 * tuanzi, its feet stand FOOT down its square, and a hop arcs ARC of a square high. On the start corner the five
 * crowd in two rows (CROWD: across and down the square, by their place in `start`).
 */
const D = 0.68;
const LIFT = 0.3;
const FOOT = 0.84;
const ARC = 0.34;
/** Keyframes per hop: enough for the parabola to read as a curve. */
const HOP_SAMPLES = 10;
/** A hop seen less than this late (ms) is squeezed to land on time instead of being skipped into. */
const CATCH_UP_MS = 150;
const CROWD: readonly [number, number][] = [[0.32, 0.62], [0.7, 0.62], [0.2, 0.92], [0.5, 0.92], [0.8, 0.92]];

const board = computed(() => boardOf(props.track));
const squares = computed(() => Array.from({ length: props.track }, (_, k) => k));
const cellStyle = (sq: number) => {
  const c = cellOf(sq, props.track);
  return { gridColumn: c.col + 1, gridRow: c.row + 1 };
};

/** The start corner's order: the race's once it is out, the members' order before. */
const lanes = computed(() => props.race?.start ?? props.members);
const moves = computed(() => (props.race?.start ? props.race.moves ?? [] : []));
const head = computed(() => (props.race && moves.value.length ? playhead(props.race, props.t) : null));
const step = computed(() => (head.value && head.value.current >= 0 ? moves.value[head.value.current] : null));
/** The mover waits for the die: lit until the group sets off. */
const waiting = computed(() => !!head.value && head.value.current >= 0 && stageOf(head.value.part) !== "walk");

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

/** The hop each tuanzi last made: `${step}a` to the die's square, `${step}b` on past a boost or trip square. */
const hops = computed(() => {
  const out: Record<string, string> = {};
  const h = head.value;
  if (!h) return out;
  const upto = h.current >= 0 ? h.current : h.done - 1;
  for (let i = 0; i <= upto && i < moves.value.length; i++) {
    const s = moves.value[i];
    let key = s.end !== undefined ? `${i}b` : `${i}a`;
    if (i === h.current) {
      if (h.part < HOP_AT) continue;
      key = h.part >= SQUARE_AT && s.end !== undefined ? `${i}b` : `${i}a`;
    }
    for (const m of [s.m, ...(s.carry ?? [])]) out[m] = key;
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
  if (s.end !== undefined && w.part >= SQUARE_AT) {
    const down = s.square === "trip";
    return { m: s.m, key: `${w.i}b`, text: down ? `−${TRIP}` : `+${BOOST}`, down };
  }
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
  return m && w.part >= m.from ? { ...m, key: `${i}${m.kind}`, text: WORDS[m.kind] } : null;
});

/** The last step is done and the result not yet up: the field stands still, the start corner flashing. */
const tail = computed(() => {
  const r = props.race;
  const h = head.value;
  return !!r?.endsAt && !!h && h.current < 0 && h.done === moves.value.length && props.t < r.endsAt * 1000;
});

// ---------------------------------------------------------------- where each tuanzi stands

/** A spot in squares from the board's top left: across, down to the feet, and the height in its stack. */
interface At { x: number; y: number; lvl: number }
function atOf(p: Spot | undefined): At {
  if (!p?.square) {
    const [x, y] = CROWD[(p?.lane ?? 0) % CROWD.length];
    return { x, y, lvl: 0 };
  }
  const c = cellOf(p.square, props.track);
  return { x: c.col + 0.5, y: c.row + FOOT, lvl: p.level };
}
const ats = computed<Record<string, At>>(() => Object.fromEntries(props.members.map((m) => [m, atOf(places.value[m])])));

function style(m: string) {
  const a = ats.value[m];
  // Lower on the board is nearer: in front; up a stack in front of those under it; the movers over everyone.
  const z = 10 + Math.round(a.y * 10) + a.lvl + (movers.value.includes(m) ? 100 : 0);
  return { "--x": a.x, "--y": a.y, "--lvl": a.lvl, "--above": above.value[m] ?? 0, zIndex: z };
}
/** Words near the right edge open to the left, so they stay on the paper. */
const flipped = (m: string) => ats.value[m].x > board.value.cols - 2;

// ---------------------------------------------------------------- the hops

// Hops start only after the first paint, so opening the page mid-race does not make everyone jump at once.
const ready = ref(false);
const boardEl = ref<HTMLElement | null>(null);
const tzEls: Record<string, HTMLElement> = {};
let frame = 0;
onMounted(() => (frame = requestAnimationFrame(() => (ready.value = true))));
onBeforeUnmount(() => cancelAnimationFrame(frame));

/** Where the tuanzi was before the latest change, to hop from. */
let was: Record<string, At> = {};
watch(() => props.race?.id, () => (was = {}));

/** A spot as the transform the CSS gives it (.tz), in px for a square [cell] px wide. */
function pose(a: At, cell: number, up = 0): string {
  const d = cell * D;
  return `translate(${a.x * cell - d / 2}px, ${(a.y - up) * cell - d - a.lvl * d * LIFT}px)`;
}

watch(hops, (now, before) => {
  const r = props.race;
  const h = head.value;
  const el = boardEl.value;
  if (ready.value && !reducedMotion.value && r && h && el && before) {
    const cell = el.getBoundingClientRect().width / board.value.cols;
    for (const m of props.members) {
      const key = now[m];
      const from = was[m];
      const node = tzEls[m];
      if (!key || key === before[m] || !from || !node || typeof node.animate !== "function") continue;
      const i = Number.parseInt(key, 10);
      const s = moves.value[i];
      if (!s) continue;
      const path = stepPath(s, props.track, BOOST, TRIP)[key.endsWith("b") ? "push" : "hop"];
      if (!path.length) continue;
      const lvl = [s.m, ...(s.carry ?? [])].indexOf(m);
      const to = ats.value[m];
      const points: At[] = [from, ...path.map((sq, j) => {
        if (j === path.length - 1) return to;
        const c = cellOf(sq, props.track);
        return { x: c.col + 0.5, y: c.row + FOOT, lvl: Math.max(0, lvl) };
      })];
      // Each hop is sampled: across at an even pace, up and down on a parabola. One easing for both would stall the
      // tuanzi at the top of every hop and rush it at each landing.
      const frames: Keyframe[] = [];
      const n = points.length - 1;
      for (let j = 0; j < n; j++) {
        const p = points[j]!;
        const q = points[j + 1]!;
        for (let k = 0; k < HOP_SAMPLES; k++) {
          const u = k / HOP_SAMPLES;
          const at = { x: p.x + (q.x - p.x) * u, y: p.y + (q.y - p.y) * u, lvl: p.lvl + (q.lvl - p.lvl) * u };
          frames.push({ offset: (j + u) / n, transform: pose(at, cell, ARC * 4 * u * (1 - u)) });
        }
      }
      frames.push({ offset: 1, transform: pose(points[n]!, cell) });
      const p = stepPhases(stepLength(r, i));
      const b = key.endsWith("b");
      const full = b ? p.pushLen : p.hopLen;
      // The clock ticks every 100 ms, so a hop is seen up to a tick late. Within a tick it plays from its start a
      // little faster and still lands on time (skipping ahead would make it jump); a page opened mid-hop picks it up
      // where it is.
      const late = h.current === i ? Math.max(0, (h.part - (b ? SQUARE_AT : HOP_AT)) * stepLength(r, i)) : 0;
      if (late < CATCH_UP_MS) node.animate(frames, { duration: Math.max(1, full - late) });
      else node.animate(frames, { duration: full }).currentTime = late;
    }
  }
  was = { ...ats.value };
}, { flush: "post" });
</script>

<template>
  <div class="track" :class="{ calm: reducedMotion }">
    <div
      ref="boardEl" class="board" :class="{ live: ready && step, cleared }"
      :style="{ '--cols': board.cols, '--rows': board.rows }"
    >
      <div
        v-for="sq in squares" :key="sq" class="tile" :style="cellStyle(sq)"
        :class="{ start: sq === 0, boost: sq === race?.setup.boost, trip: sq === race?.setup.trip, flash: tail && sq === 0 }"
      >
        <span v-if="sq === race?.setup.boost" class="mark" :title="`+${BOOST}`">
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" /></svg>{{ BOOST }}
        </span>
        <span v-else-if="sq === race?.setup.trip" class="mark" :title="`−${TRIP}`">
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" /></svg>{{ TRIP }}
        </span>
        <span v-if="sq" class="num">{{ sq }}</span>
      </div>
      <div class="infield"><slot /></div>
      <div
        v-for="m in members" :key="m" :ref="(el) => { if (el) tzEls[m] = el as HTMLElement }" class="tz" :data-m="m"
        :class="{
          gated: !places[m]?.square, moving: movers.includes(m), mover: step?.m === m, top: (places[m]?.level ?? 0) > 0,
          waiting: waiting && step?.m === m,
        }"
        :style="style(m)" :title="nameOf(m)"
      >
        <div class="body"><TuanziToken :member="m" /></div>
        <b v-if="ready && roll?.m === m" :key="roll.key" class="roll" :class="{ down: roll.down, side: above[m] }" aria-hidden="true">{{ roll.text }}</b>
        <span v-if="ready && moment?.m === m" :key="moment.key" class="say" :class="[moment.kind, { flip: flipped(m) }]" aria-hidden="true">
          {{ moment.text }}
        </span>
        <span v-if="leader === m && !above[m]" class="crown" aria-hidden="true"><Icon name="crown" :size="22" /></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The track is the size container: the board takes the largest squares its box allows, with room above for stacks. */
.track {
  container-type: size;
  position: relative;
  width: 100%;
}
.board {
  /* Room over the top row for a stack: HEAD of a square. */
  --head: 0.55;
  --cell: min(calc((100cqw - 24px) / var(--cols)), calc((100cqh - 16px) / (var(--rows) + var(--head))));
  /* A tuanzi (D of a square) and the rise of each one up a stack (LIFT of a tuanzi); see RaceTrack's script. */
  --d: calc(var(--cell) * 0.68);
  --lift: calc(var(--d) * 0.3);
  --gap: max(3px, calc(var(--cell) * 0.04));
  position: absolute;
  left: 50%;
  top: calc((100cqh - (var(--rows) + var(--head)) * var(--cell)) / 2 + var(--head) * var(--cell));
  display: grid;
  grid-template-columns: repeat(var(--cols), var(--cell));
  grid-template-rows: repeat(var(--rows), var(--cell));
  translate: -50% 0;
}
.board.cleared .tz {
  opacity: 0;
  visibility: hidden;
  transition: opacity var(--dur-slow), visibility 0s var(--dur-slow);
}

/* ---- the squares: paper, not to be pressed, a small number in the corner */
.tile {
  position: relative;
  margin: calc(var(--gap) / 2);
  display: grid;
  place-items: center;
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--c-100), 0 1px 2px rgba(var(--c-900-rgb), 0.08);
}
.tile .num {
  position: absolute;
  left: 7%;
  top: 5%;
  font: 700 var(--fs-caption)/1 var(--font-latin);
  color: var(--ink-3);
}
/* The start, also the finish: a gold foil ring and a coral checker along its top edge. */
.tile.start {
  box-shadow: 0 2px 6px -2px rgba(var(--c-900-rgb), 0.3);
  border: 3px solid transparent;
  background: linear-gradient(var(--c-50), var(--c-50)) padding-box, var(--grad-gold) border-box;
  overflow: hidden;
}
.tile.start::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 16%;
  background: repeating-conic-gradient(var(--c-500) 0 25%, #fff 0 50%) 0 0 / max(8px, calc(var(--cell) * 0.08)) max(8px, calc(var(--cell) * 0.08));
}
.tile.start.flash {
  animation: finish-flash 900ms var(--ease-out) 2;
}
@keyframes finish-flash {
  40% { box-shadow: 0 0 0 4px rgba(var(--c-500-rgb), 0.45), var(--glow-l); }
}
.mark {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.mark svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* The boost square: a key standing up from the paper, an arrow up. */
.tile.boost {
  background: linear-gradient(180deg, var(--c-200), var(--c-300));
  box-shadow: 0 5px 0 var(--c-500), 0 10px 10px -6px rgba(var(--c-900-rgb), 0.35);
  translate: 0 -4px;
}
/* The trip square: a pit sunk into the paper, an arrow down. */
.tile.trip {
  background: color-mix(in oklab, var(--c-300) 70%, var(--c-500));
  box-shadow: inset 0 5px 7px rgba(var(--c-900-rgb), 0.4), inset 0 -1px 0 rgba(255, 255, 255, 0.5);
}
.tile.trip .mark {
  color: var(--c-900);
}
.tile.boost .num,
.tile.trip .num {
  color: var(--ink-2);
}

/* ---- the infield: the 7 × 3 inside the ring */
.infield {
  position: relative;
  z-index: 1;
  grid-row: 2 / -2;
  grid-column: 2 / -2;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: calc(var(--gap) * 2);
}

/* ---- a tuanzi stands on its square, --lift higher for each one below it */
.tz {
  position: absolute;
  z-index: 10;
  left: 0;
  top: 0;
  width: var(--d);
  height: var(--d);
  --tuanzi-size: var(--d);
  transform: translate(
    calc(var(--x) * var(--cell) - var(--d) / 2),
    calc(var(--y) * var(--cell) - var(--d) - var(--lvl) * var(--lift))
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
/* Crowded on the start corner a little smaller. */
.tz.gated .body {
  scale: 0.84;
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
  bottom: calc(100% + var(--above, 0) * var(--lift) + 4px);
  pointer-events: none;
}
/* Over a stack there is no room above: beside its top instead, on the side away from the word. */
.roll.side {
  left: calc(50% - var(--d) * 0.55);
  bottom: calc(100% + var(--above) * var(--lift) - var(--d) * 0.5);
  translate: -100% 0;
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
  animation: roll var(--roll) var(--ease-out) both;
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
  bottom: calc(76% + var(--above, 0) * var(--lift));
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
.say.boost {
  background: var(--c-500);
  color: var(--ink);
  box-shadow: 0 0 0 2px var(--surface), 0 6px 12px -6px rgba(var(--c-900-rgb), 0.4);
}
.say.lead::after,
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
  bottom: 92%;
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
.calm .tile.start.flash {
  animation: none;
}

/* Small squares: smaller words and marks. */
@container (max-width: 620px), (max-height: 380px) {
  .say {
    padding: 3px 7px;
    font-size: var(--fs-label);
  }
  .mark {
    font-size: var(--fs-strong);
  }
  .mark svg {
    width: 11px;
    height: 11px;
  }
}
</style>
