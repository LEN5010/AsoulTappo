<script setup lang="ts">
// The race's track (docs/design/amusement-park.md §6.6, docs/design/park-ui-rebuild.md §5.3): one lap of flat floor
// tiles, squares 0 to `track` in two rows (the first left to right, the second back from the right), joined by a
// turn at each end. The space inside the lap is the infield; the page puts what fits the phase there (the slot).
// The track fills the height it is given: the first row sits under the headroom a full stack needs, the second
// on the floor, and the infield between them keeps its size whatever it holds, so nothing on the track moves when
// the phase changes.
// A tuanzi sits on the one below it, LIFT of its size higher. Positions come from the move list at the server time
// [t]; a tuanzi that moves (and those it carries) hops there in CSS: a stretch on take-off, an arc, a squash on
// landing. Under reduced motion it jumps.
import { computed, onMounted, ref } from "vue";
import { manifest } from "../../manifest";
import { reducedMotion } from "../../stores/theme";
import { moving, playhead, spots, stacksAt, SQUARE_AT, type Race, type Spot } from "./race";
import TuanziToken from "./TuanziToken.vue";

const props = defineProps<{ race: Race | null; t: number; track: number; members: string[] }>();

const nameOf = (m: string) => manifest.characters.find((c) => c.id === m)?.name ?? m;

const BOOST = manifest.economy.park?.race?.squares.boost ?? 2;
const TRIP = Math.abs(manifest.economy.park?.race?.squares.trip ?? -1);

/** Squares in the first row; the second row has the rest, spread over the same width. */
const COLS = computed(() => Math.ceil((props.track + 1) / 2));
const ROW2 = computed(() => props.track + 1 - COLS.value);
/** Square -> (column, row, squares in that row): the first row left to right, the second back from the right. */
function cell(square: number): { col: number; row: number; n: number } {
  const s = Math.max(0, Math.min(props.track, square));
  const cols = COLS.value;
  return s < cols ? { col: s, row: 0, n: cols } : { col: props.track - s, row: 1, n: ROW2.value };
}
const squares = computed(() => Array.from({ length: props.track + 1 }, (_, s) => s));

const head = computed(() => (props.race?.moves ? playhead(props.race, props.t) : null));
const places = computed<Record<string, Spot>>(() => {
  const r = props.race;
  if (r?.start && r.moves && head.value) return spots(stacksAt(r.start, r.moves, head.value));
  // Before the start the order is secret: everyone waits side by side.
  return Object.fromEntries(props.members.map((m) => [m, { square: 0, level: 0 }]));
});
const lineup = computed(() => !props.race?.start);
const movers = computed(() => (props.race?.moves && head.value ? moving(props.race.moves, head.value) : []));

/** The hop each tuanzi last made: its step and part, so a new hop remounts the body and replays the jump. */
const hops = computed(() => {
  const out: Record<string, string> = {};
  const r = props.race;
  if (!r?.moves || !head.value) return out;
  const upto = head.value.current >= 0 ? head.value.current : head.value.done - 1;
  for (let i = 0; i <= upto && i < r.moves.length; i++) {
    const s = r.moves[i];
    const late = i === head.value.current && head.value.part >= SQUARE_AT && s.end !== undefined;
    for (const m of [s.m, ...(s.carry ?? [])]) out[m] = late || (i < upto && s.end !== undefined) ? `${i}b` : `${i}a`;
  }
  return out;
});
/**
 * The number over the mover's head in the step under way: the squares it walks, then the boost or trip square's
 * own push once it lands there. Keyed like the hops, so each one pops once.
 */
const roll = computed<{ m: string; key: string; text: string; down: boolean } | null>(() => {
  const r = props.race;
  const h = head.value;
  if (!r?.moves || !h || h.current < 0) return null;
  const s = r.moves[h.current];
  if (!s) return null;
  if (s.end !== undefined && h.part >= SQUARE_AT) {
    const down = s.square === "trip";
    return { m: s.m, key: `${h.current}b`, text: down ? `−${TRIP}` : `+${BOOST}`, down };
  }
  return { m: s.m, key: `${h.current}a`, text: `+${s.steps}`, down: false };
});
const rollMs = computed(() => Math.max(560, Math.round((props.race?.stepMs ?? 1300) * 0.7)));

// Hops start only after the first paint, so opening the page mid-race does not make everyone jump at once.
const ready = ref(false);
onMounted(() => requestAnimationFrame(() => (ready.value = true)));

const hopMs = computed(() => Math.min(620, Math.round((props.race?.stepMs ?? 1300) * 0.48)));

function style(m: string, i: number) {
  const p = places.value[m] ?? { square: 0, level: 0 };
  const { col, row, n } = cell(p.square);
  return {
    "--col": col,
    "--row": row,
    "--n": n,
    "--lvl": p.level,
    "--dx": lineup.value ? (i - (props.members.length - 1) / 2) * 0.2 + 0.4 : 0,
    zIndex: (movers.value.includes(m) ? 40 : 10) + p.level,
  };
}
function tileStyle(s: number) {
  const { col, row, n } = cell(s);
  return { "--col": col, "--row": row, "--n": n };
}
</script>

<template>
  <div class="track" :class="{ calm: reducedMotion }">
    <div class="board" :style="{ '--cols': COLS, '--hop': `${hopMs}ms`, '--roll': `${rollMs}ms` }">
      <i class="turn left" aria-hidden="true"></i>
      <i class="turn right" aria-hidden="true"></i>
      <div
        v-for="s in squares" :key="s" class="tile" :style="tileStyle(s)"
        :class="{ start: s === 0, finish: s === track, boost: s === race?.setup.boost, trip: s === race?.setup.trip }"
      >
        <span v-if="s === 0" class="mark">起点</span>
        <span v-else-if="s === track" class="mark">终点</span>
        <span v-else-if="s === race?.setup.boost" class="mark" :title="`+${BOOST}`">
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" /></svg>{{ BOOST }}
        </span>
        <span v-else-if="s === race?.setup.trip" class="mark" :title="`−${TRIP}`">
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" /></svg>{{ TRIP }}
        </span>
        <span v-else class="num">{{ s }}</span>
      </div>
      <div class="infield"><slot /></div>
      <div
        v-for="(m, i) in members" :key="m" class="tz" :class="{ moving: movers.includes(m) }" :style="style(m, i)"
        :title="nameOf(m)"
      >
        <div :key="ready ? hops[m] ?? 'rest' : 'rest'" class="body" :class="{ hop: ready && hops[m] && movers.includes(m) }">
          <TuanziToken :member="m" />
        </div>
        <b
          v-if="ready && roll?.m === m" :key="roll.key" class="roll" :class="{ down: roll.down }" aria-hidden="true"
        >{{ roll.text }}</b>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The track is the size container: squares follow its width, the two rows its height. */
.track {
  container-type: size;
  position: relative;
  width: 100%;
}
.board {
  /* The lane runs between the two turns; a row's squares share it, so both rows end flush with the turns. */
  --pad: 22px;
  --bw: calc(100cqw - 2 * var(--pad));
  --arc: clamp(26px, calc(var(--bw) * 0.06), 48px);
  --lane: calc(var(--bw) - 2 * var(--arc));
  --cell: calc(var(--lane) / var(--cols));
  /* A tuanzi is 48px at most, smaller when the squares are; each one up a stack rises LIFT. */
  --d: min(48px, calc(var(--cell) * 0.92));
  --lift: calc(var(--d) * 0.375);
  --tile-h: clamp(20px, calc(var(--cell) * 0.5), 30px);
  /* The first row's top leaves room for five in a stack hopping; the second row stands on the floor. */
  --top-y: calc(var(--d) * 1.38 + 4 * var(--lift) - var(--tile-h) * 0.45 + 4px);
  --bot-y: calc(100cqh - var(--tile-h) - 14px);
  position: absolute;
  inset: 0 var(--pad);
}
.tile,
.tz {
  --cw: calc(var(--lane) / var(--n));
  --y: calc(var(--top-y) + var(--row) * (var(--bot-y) - var(--top-y)));
}
/* ---- the floor: flat tiles, not keys */
.tile {
  position: absolute;
  left: 0;
  top: 0;
  width: calc(var(--cw) - 4px);
  height: var(--tile-h);
  transform: translate(calc(var(--arc) + var(--col) * var(--cw) + 2px), var(--y));
  display: grid;
  place-items: center;
  box-sizing: border-box;
  border-radius: var(--radius-s);
  background: var(--c-100);
}
.tile .num {
  font: 800 var(--fs-label)/1 var(--font-latin);
  color: var(--ink-3);
}
.tile .mark {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  font: 800 var(--fs-label)/1 var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.tile.start,
.tile.finish {
  background: var(--c-500);
}
.tile.boost {
  background: var(--c-300);
}
.tile.boost .mark,
.tile.trip .mark {
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.tile.trip {
  background: transparent;
  border: 2px dashed var(--c-300);
}
.tile.trip .mark {
  color: var(--c-700);
}
.mark svg {
  width: 12px;
  height: 12px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* The turns: a band of the floor bending from one row to the other at each end. */
.turn {
  position: absolute;
  top: calc(var(--top-y) + var(--tile-h) * 0.1);
  height: calc(var(--bot-y) - var(--top-y) + var(--tile-h) * 0.8);
  width: calc(var(--arc) - 2px);
  box-sizing: border-box;
  border: calc(var(--tile-h) * 0.8) solid var(--c-100);
}
.turn.right {
  left: calc(var(--arc) + var(--lane) + 2px);
  border-left: 0;
  border-radius: 0 100% 100% 0 / 0 50% 50% 0;
}
.turn.left {
  left: 0;
  border-right: 0;
  border-radius: 100% 0 0 100% / 50% 0 0 50%;
}

/* ---- the infield: between the rows, inside the turns */
.infield {
  position: absolute;
  z-index: 1;
  left: calc(var(--arc) + 6px);
  right: calc(var(--arc) + 6px);
  top: calc(var(--top-y) + var(--tile-h) + 12px);
  bottom: calc(100cqh - var(--bot-y) + 12px);
  display: flex;
  flex-direction: column;
}

/* ---- a tuanzi stands on its square's tile, LIFT higher for each one below it */
.tz {
  --tuanzi-size: var(--d);
  position: absolute;
  left: 0;
  top: 0;
  width: var(--d);
  height: var(--d);
  transform: translate(
    calc(var(--arc) + (var(--col) + 0.5 + var(--dx)) * var(--cw) - var(--d) / 2),
    calc(var(--y) + var(--tile-h) * 0.45 - var(--d) - var(--lvl) * var(--lift))
  );
  transition: transform var(--hop) var(--ease-in-out);
}
.body {
  width: 100%;
  height: 100%;
  transform-origin: 50% 97%;
}
.body > * {
  display: block;
}
/* Take-off stretch, the arc, the squash on landing, then at rest. */
.hop {
  animation: hop var(--hop) linear both;
}
@keyframes hop {
  0% { transform: translateY(0) scale(1.08, 0.9); }
  14% { transform: translateY(-6%) scale(0.9, 1.12); animation-timing-function: ease-out; }
  50% { transform: translateY(-38%) scale(0.96, 1.05); animation-timing-function: ease-in; }
  82% { transform: translateY(0) scale(1.14, 0.84); }
  100% { transform: translateY(0) scale(1, 1); }
}
/* The squares walked, popped over the head: the coral digits with the white outline of the desk's combo count. */
.roll {
  position: absolute;
  left: 50%;
  bottom: 100%;
  font: 800 calc(var(--d) * 0.5) / 1 var(--font-latin);
  color: var(--c-600);
  -webkit-text-stroke: 4px var(--surface);
  paint-order: stroke fill;
  text-shadow: 0 2px 6px rgba(var(--c-900-rgb), 0.25);
  white-space: nowrap;
  pointer-events: none;
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
.calm .tz {
  transition: none;
}
/* Without motion the number stands over the head for the step, still. */
.calm .roll {
  animation: none;
}
.calm .hop {
  animation: none;
}

@container panel (max-width: 760px) {
  .board {
    --pad: 14px;
  }
}
</style>
