<script setup lang="ts">
// The tile matching board (docs/design/park-link.md 6): emote tiles on the sheet, sized to the box it is given, with
// half a tile of room around them for links that run outside the board. A tile is a physical object, not a key:
// white face, emote, soft shadow; the picked one lifts on a spring and wears a coral ring. Tiles are keyed by their own
// ids (stores/parkLink linkTiles) and placed by transform, so a tile that moves after a pair is taken slides there and
// settles. Pressing a tile emits its id; the caller finds its cell on the current board. A link that has just been made
// runs over the board as a coral line from one tile to the other, then draws itself in after them, while the pair it
// took pops and goes with a ring at each. A new game deals its tiles in on a diagonal wave; a shuffle turns them over
// on the same wave.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { EASE_OUT } from "../../ui/motion";
import { EMPTY } from "./link";

export interface LinkLine { key: number; points: [number, number][] }
export interface LinkGhost { id: number; kind: number; at: number }

const props = defineProps<{
  rows: number;
  cols: number;
  board: number[];
  tiles: number[];
  /** Kind index -> image URL, and name for the tile's label. */
  faces: string[];
  names: string[];
  selected: number | null;
  /** The smallest cell pitch; the caller keeps room for the board at this size. */
  minPitch: number;
  hint: number[];
  lines: LinkLine[];
  ghosts: LinkGhost[];
  shake: number | null;
  /** A new value deals the tiles in (a new game on the board). */
  deal: number;
  /** A new value turns the tiles over (a shuffle has just come in). */
  flip: number;
  dim: boolean;
  disabled: boolean;
  calm: boolean;
}>();
const emit = defineEmits<{ pick: [id: number] }>();

/** The largest cell pitch, in pixels. */
const MAX_PITCH = 78;
/** Each step of a wave down the board's diagonals starts this much later. */
const WAVE_MS = 14;
const DEAL_MS = 360;
const FLIP_MS = 380;
/** The spring the tiles land on: a little past their place, then back. */
const SPRING = "cubic-bezier(0.34, 1.56, 0.64, 1)";

const stage = ref<HTMLElement>();
const board = ref<HTMLElement>();
const box = ref({ w: 0, h: 0 });
/** The board is being resized: tiles take their new places without sliding. */
const sizing = ref(false);
let sizingFrame = 0;

const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver((entries) => {
  const r = entries[0]?.contentRect;
  if (!r) return;
  box.value = { w: r.width, h: r.height };
  sizing.value = true;
  cancelAnimationFrame(sizingFrame);
  sizingFrame = requestAnimationFrame(() => {
    sizingFrame = requestAnimationFrame(() => (sizing.value = false));
  });
});
watch(stage, (el, was) => {
  if (was) observer?.unobserve(was);
  if (el) observer?.observe(el);
});
onBeforeUnmount(() => {
  observer?.disconnect();
  cancelAnimationFrame(sizingFrame);
});

/** One cell's side; the board plus half a cell of ring on each side fits the box. */
const pitch = computed(() => {
  const { w, h } = box.value;
  if (!w || !h) return props.minPitch;
  const fit = Math.min(w / (props.cols + 1), h / (props.rows + 1));
  return Math.max(props.minPitch, Math.min(MAX_PITCH, Math.floor(fit)));
});
const gap = computed(() => Math.max(2, Math.min(6, Math.round(pitch.value * 0.07))));
const tileSize = computed(() => pitch.value - gap.value);
const width = computed(() => (props.cols + 1) * pitch.value);
const height = computed(() => (props.rows + 1) * pitch.value);

/** The top left corner of cell [i]'s tile. */
function placeOf(i: number): string {
  const r = Math.floor(i / props.cols);
  const c = i % props.cols;
  const x = (c + 0.5) * pitch.value + gap.value / 2;
  const y = (r + 0.5) * pitch.value + gap.value / 2;
  return `translate(${x}px, ${y}px)`;
}

const cells = computed(() => {
  const out: { id: number; at: number; kind: number }[] = [];
  props.tiles.forEach((id, at) => {
    const kind = props.board[at] ?? EMPTY;
    if (id !== EMPTY && kind !== EMPTY) out.push({ id, at, kind });
  });
  // In the order the tiles were dealt, wherever they stand now: a shift then moves no node in the document (a node
  // moved there starts over without its slide).
  return out.sort((x, y) => x.id - y.id);
});
const hinted = computed(() => new Set(props.hint));

/** A path's corners as SVG points; ring cells (-1, rows, cols) fall on the board's edge. */
const pointsOf = (points: [number, number][]) =>
  points.map(([r, c]) => `${(c + 1) * pitch.value},${(r + 1) * pitch.value}`).join(" ");

function press(id: number) {
  if (!props.disabled) emit("pick", id);
}

/**
 * Runs [frames] on every tile on the board, each starting a wave step later per diagonal from the top left. The first
 * frame holds until a tile's turn, so the board never shows its tiles before they come in.
 */
function wave(frames: Keyframe[], duration: number, easing: string): void {
  if (props.calm || !board.value) return;
  for (const el of board.value.querySelectorAll<HTMLElement>(".cell[data-at] > .tile")) {
    const at = Number((el.parentElement as HTMLElement).dataset.at);
    const step = Math.floor(at / props.cols) + (at % props.cols);
    el.animate(frames, { duration, delay: step * WAVE_MS, easing, fill: "backwards" });
  }
}
/** The tiles rise onto the board from a little below, each landing on the spring. */
function dealIn(): void {
  wave([{ opacity: 0, transform: "translateY(12px) scale(0.5)" }, { opacity: 1, transform: "translateY(0) scale(1)" }], DEAL_MS, SPRING);
}
/** The tiles come round edge on, showing their new faces. */
function flipIn(): void {
  wave(
    [{ transform: "perspective(320px) rotateY(90deg) scale(0.9)" }, { transform: "perspective(320px) rotateY(0deg) scale(1)" }],
    FLIP_MS, EASE_OUT,
  );
}
onMounted(dealIn);
watch(() => props.deal, dealIn, { flush: "post" });
watch(() => props.flip, flipIn, { flush: "post" });
</script>

<template>
  <div ref="stage" class="link-stage" :class="{ calm }">
    <div
      ref="board" class="link-board" :class="{ sizing, dim, disabled }"
      :style="{ width: `${width}px`, height: `${height}px`, '--tile': `${tileSize}px` }"
    >
      <button
        v-for="t in cells" :key="t.id" type="button" tabindex="-1" class="cell" :data-at="t.at" :aria-label="names[t.kind]"
        :style="{ transform: placeOf(t.at) }" @pointerdown.left.prevent="press(t.id)"
      >
        <span class="tile" :class="{ on: selected === t.id, hint: hinted.has(t.id), shake: shake === t.id }">
          <img :src="faces[t.kind]" alt="" draggable="false" decoding="async" />
        </span>
      </button>

      <span
        v-for="g in ghosts" :key="`g${g.id}`" class="cell ghost" aria-hidden="true"
        :style="{ transform: placeOf(g.at) }"
      >
        <i class="ring"></i>
        <span class="tile on"><img :src="faces[g.kind]" alt="" draggable="false" /></span>
      </span>

      <svg v-if="lines.length" class="lines" :viewBox="`0 0 ${width} ${height}`" aria-hidden="true">
        <g v-for="l in lines" :key="l.key">
          <polyline class="under" :points="pointsOf(l.points)" pathLength="100" />
          <polyline class="over" :points="pointsOf(l.points)" pathLength="100" />
        </g>
      </svg>
    </div>
  </div>
</template>

<style scoped>
.link-stage {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
}
.link-board {
  position: relative;
  flex: none;
  transition: filter var(--dur-base) var(--ease-out), opacity var(--dur-base) var(--ease-out);
}
.link-board.dim {
  filter: saturate(0.6);
  opacity: 0.55;
}

/* A cell holds its tile at its place on the board; the tile inside lifts, shakes and turns on its own. */
.cell {
  position: absolute;
  left: 0;
  top: 0;
  width: var(--tile);
  height: var(--tile);
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  /* Slides once the pair has begun to go, and settles a little past its place. */
  transition: transform 300ms cubic-bezier(0.34, 1.3, 0.64, 1) 110ms;
}
.sizing .cell,
.calm .cell {
  transition: none;
}
.disabled .cell {
  cursor: default;
}
.cell:focus-visible {
  outline: none;
}

.tile {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  border-radius: calc(var(--tile) * 0.2);
  background: linear-gradient(180deg, #fff 55%, var(--c-50));
  box-shadow:
    inset 0 -2px 0 rgba(var(--c-900-rgb), 0.05),
    0 0 0 1px rgba(var(--c-900-rgb), 0.05),
    0 1px 2px rgba(var(--c-900-rgb), 0.12),
    0 4px 9px -5px rgba(var(--c-900-rgb), 0.32);
  transition: transform var(--dur-slow) var(--ease-spring), box-shadow var(--dur-fast) var(--ease-out);
}
.tile img {
  width: 84%;
  height: 84%;
  object-fit: contain;
  pointer-events: none;
  user-select: none;
}
.cell:hover .tile:not(.on) {
  transform: translateY(-1px);
  box-shadow:
    inset 0 -2px 0 rgba(var(--c-900-rgb), 0.05),
    0 0 0 1px rgba(var(--c-900-rgb), 0.06),
    0 2px 3px rgba(var(--c-900-rgb), 0.14),
    0 6px 11px -5px rgba(var(--c-900-rgb), 0.34);
}
.disabled .cell:hover .tile:not(.on) {
  transform: none;
}
.tile.on {
  transform: translateY(-3px) scale(1.06);
  box-shadow:
    0 0 0 3px var(--c-500),
    0 0 0 5px rgba(var(--c-500-rgb), 0.24),
    0 8px 14px -5px rgba(var(--c-900-rgb), 0.38);
}
.tile.hint:not(.on) {
  box-shadow:
    0 0 0 2px var(--c-300),
    0 0 12px 1px rgba(var(--c-500-rgb), 0.45),
    0 4px 9px -5px rgba(var(--c-900-rgb), 0.32);
  animation: hint-bob 900ms var(--ease-in-out) infinite alternate;
}
/* A second pick that does not link: the first one shakes its head, damped. */
.tile.shake {
  animation: shake 320ms var(--ease-out);
}
@keyframes hint-bob {
  to { transform: translateY(-3px); }
}
@keyframes shake {
  18% { transform: translateX(-4px) rotate(-4deg); }
  40% { transform: translateX(3px) rotate(3deg); }
  62% { transform: translateX(-2px) rotate(-1.5deg); }
  82% { transform: translateX(1px) rotate(0.5deg); }
}

/* The pair just taken, at its old place, as it was picked: it swells for a beat under the line, then shrinks away
   with a ring opening out where it stood. */
.ghost {
  z-index: 2;
  pointer-events: none;
  transition: none;
}
.ghost .tile {
  animation: ghost-pop 300ms both;
}
@keyframes ghost-pop {
  0% {
    transform: translateY(-3px) scale(1.06);
    animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1);
  }
  32% {
    opacity: 1;
    transform: translateY(-5px) scale(1.16);
    animation-timing-function: cubic-bezier(0.7, 0, 0.84, 0);
  }
  100% {
    opacity: 0;
    transform: translateY(-2px) scale(0.2);
  }
}
.ghost .ring {
  position: absolute;
  inset: 0;
  border-radius: calc(var(--tile) * 0.24);
  box-shadow: 0 0 0 2px var(--c-500);
  animation: ring-out 380ms var(--ease-out) 60ms both;
}
@keyframes ring-out {
  from { opacity: 0.9; transform: scale(0.9); }
  to { opacity: 0; transform: scale(1.5); }
}

.lines {
  position: absolute;
  inset: 0;
  z-index: 3;
  width: 100%;
  height: 100%;
  overflow: visible;
  pointer-events: none;
}
/* The line runs from the first tile to the second, holds, then its tail follows it there. */
.lines polyline {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 100;
  animation: line-run 320ms both;
}
.lines .under {
  stroke: #fff;
  stroke-width: calc(var(--tile) * 0.16 + 3px);
}
.lines .over {
  stroke: var(--c-500);
  stroke-width: calc(var(--tile) * 0.1 + 1px);
}
@keyframes line-run {
  0% {
    stroke-dashoffset: 100;
    animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1);
  }
  35%,
  45% {
    stroke-dashoffset: 0;
    animation-timing-function: cubic-bezier(0.4, 0, 0.6, 1);
  }
  100% {
    stroke-dashoffset: -100;
  }
}

.calm .tile,
.calm .link-board {
  transition: none;
}
.calm .tile.on {
  transform: translateY(-2px);
}
.calm .tile.hint:not(.on) {
  animation: none;
  outline: 2px dashed var(--c-500);
  outline-offset: 2px;
}
.calm .tile.shake,
.calm .ghost .tile,
.calm .ghost .ring,
.calm .lines polyline {
  animation: none;
}
.calm .ghost .ring {
  display: none;
}
.calm .cell:hover .tile:not(.on) {
  transform: none;
}
</style>
