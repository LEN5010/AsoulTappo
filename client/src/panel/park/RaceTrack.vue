<script setup lang="ts">
// The race's track (docs/design/amusement-park.md §6.6): squares 0 to `track` in two rows that turn back at the
// right end, and the five dumplings on them. A dumpling sits on the one below with its bottom at LIFT of that
// one's height. Positions come from the move list at the server time [t]; a dumpling that moves (and those it
// carries) hops there in CSS: a stretch on take-off, an arc, a squash on landing. Under reduced motion it jumps.
import { computed, onMounted, ref } from "vue";
import { manifest } from "../../manifest";
import { reducedMotion } from "../../stores/theme";
import { moving, playhead, spots, stacksAt, SQUARE_AT, type Race, type Spot } from "./race";

const props = defineProps<{ race: Race | null; t: number; track: number; members: string[] }>();

// The dumplings (scripts/make_tuanzi.py): 384px squares, bottom-aligned, content 90% of the width.
const ART = import.meta.glob<string>("../../assets/park/tuanzi/*.webp", { eager: true, query: "?url", import: "default" });
const art = (m: string) => Object.entries(ART).find(([path]) => path.endsWith(`/${m}.webp`))?.[1] ?? "";
const color = (m: string) => manifest.characters.find((c) => c.id === m)?.color ?? "var(--c-500)";
const nameOf = (m: string) => manifest.characters.find((c) => c.id === m)?.name ?? m;

const BOOST = manifest.economy.park?.race?.squares.boost ?? 2;
const TRIP = Math.abs(manifest.economy.park?.race?.squares.trip ?? -1);

const COLS = computed(() => Math.ceil((props.track + 1) / 2));
/** Square -> (column, row): the first row left to right, the second back from the right. */
function cell(square: number): { col: number; row: number } {
  const s = Math.max(0, Math.min(props.track, square));
  const cols = COLS.value;
  return s < cols ? { col: s, row: 0 } : { col: props.track - s, row: 1 };
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

/** The hop each dumpling last made: its step and part, so a new hop remounts the body and replays the jump. */
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
// Hops start only after the first paint, so opening the page mid-race does not make everyone jump at once.
const ready = ref(false);
onMounted(() => requestAnimationFrame(() => (ready.value = true)));

const hopMs = computed(() => Math.min(620, Math.round((props.race?.stepMs ?? 1300) * 0.48)));

function style(m: string, i: number) {
  const p = places.value[m] ?? { square: 0, level: 0 };
  const { col, row } = cell(p.square);
  return {
    "--col": col,
    "--row": row,
    "--lvl": p.level,
    "--dx": lineup.value ? i * 0.16 : 0,
    zIndex: (movers.value.includes(m) ? 40 : 10) + p.level,
  };
}
function tileStyle(s: number) {
  const { col, row } = cell(s);
  return { "--col": col, "--row": row };
}
</script>

<template>
  <div class="track" :class="{ calm: reducedMotion }">
    <div class="board" :style="{ '--cols': COLS, '--hop': `${hopMs}ms` }">
      <div
        v-for="s in squares" :key="s" class="tile" :style="tileStyle(s)"
        :class="{ start: s === 0, finish: s === track, boost: s === race?.setup.boost, trip: s === race?.setup.trip }"
      >
        <span v-if="s === 0" class="mark">起点</span>
        <span v-else-if="s === track" class="mark">终点</span>
        <span v-else-if="s === race?.setup.boost" class="mark">+{{ BOOST }}</span>
        <span v-else-if="s === race?.setup.trip" class="mark">−{{ TRIP }}</span>
        <span v-else class="num">{{ s }}</span>
      </div>
      <div
        v-for="(m, i) in members" :key="m" class="tz" :class="{ moving: movers.includes(m) }" :style="style(m, i)"
        :title="nameOf(m)"
      >
        <div :key="ready ? hops[m] ?? 'rest' : 'rest'" class="body" :class="{ hop: ready && hops[m] && movers.includes(m) }">
          <img v-if="art(m)" :src="art(m)" alt="" draggable="false" />
          <i v-else class="dot" :style="{ background: color(m) }"></i>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The track is the size container; the board inside it measures squares in the track's width (cqw). */
.track {
  container-type: inline-size;
  width: 100%;
}
.board {
  /* A square's width; the dumpling a little smaller; LIFT of its height between stacked ones. */
  --cell: calc(100cqw / var(--cols));
  --d: calc(var(--cell) * 0.94);
  --lift: calc(var(--d) * 0.42);
  --tile-h: calc(var(--cell) * 0.46);
  --row-h: calc(var(--d) + 4 * var(--lift) + var(--tile-h) * 0.6);
  position: relative;
  height: calc(var(--row-h) * 2);
}
.tile {
  position: absolute;
  left: 0;
  top: 0;
  width: calc(var(--cell) - 4px);
  height: var(--tile-h);
  transform: translate(calc(var(--col) * var(--cell) + 2px), calc((var(--row) + 1) * var(--row-h) - var(--tile-h)));
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
  font: 800 var(--fs-label)/1 var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.tile.start,
.tile.finish {
  background: var(--c-300);
}
.tile.boost {
  background: var(--c-500);
}
.tile.trip {
  background: var(--c-200);
  box-shadow: inset 0 0 0 2px var(--c-600);
}
.tile.trip .mark {
  color: var(--c-700);
}
/* A dumpling stands on its square's tile, LIFT higher for each one below it. */
.tz {
  position: absolute;
  left: 0;
  top: 0;
  width: var(--d);
  height: var(--d);
  pointer-events: auto;
  transform: translate(
    calc(var(--col) * var(--cell) + (var(--cell) - var(--d)) / 2 + var(--dx) * var(--cell)),
    calc((var(--row) + 1) * var(--row-h) - var(--tile-h) * 0.55 - var(--d) - var(--lvl) * var(--lift))
  );
  transition: transform var(--hop) var(--ease-in-out);
}
.body {
  width: 100%;
  height: 100%;
  transform-origin: 50% 97%;
}
.body img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  filter: drop-shadow(0 2px 2px rgba(var(--c-900-rgb), 0.28));
  user-select: none;
}
.dot {
  position: absolute;
  left: 25%;
  bottom: 6%;
  width: 50%;
  height: 50%;
  border-radius: 50%;
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
.calm .tz {
  transition: none;
}
.calm .hop {
  animation: none;
}
</style>
