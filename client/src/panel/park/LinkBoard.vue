<script setup lang="ts">
// The tile matching board (docs/design/park-link.md 6): emote tiles on the sheet, sized to the box it is given, with
// half a tile of room around them for links that run outside the board. A tile is a physical object, not a key:
// white face, emote, soft shadow; the picked one wears a coral ring. Tiles are keyed by their own ids (stores/parkLink
// linkTiles) and placed by transform, so a tile that moves after a pair is taken slides there. Pressing a tile emits
// its id; the caller finds its cell on the current board. A link that has just been made shows as a coral line
// over the board, with the pair it took fading out under it.
import { computed, onBeforeUnmount, ref, watch } from "vue";
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
  /** The tiles turn over (a shuffle has just come in). */
  flipping: boolean;
  dim: boolean;
  disabled: boolean;
  calm: boolean;
}>();
const emit = defineEmits<{ pick: [id: number] }>();

/** The largest cell pitch, in pixels. */
const MAX_PITCH = 78;

const stage = ref<HTMLElement>();
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
  return out;
});
const hinted = computed(() => new Set(props.hint));

/** A path's corners as SVG points; ring cells (-1, rows, cols) fall on the board's edge. */
const pointsOf = (points: [number, number][]) =>
  points.map(([r, c]) => `${(c + 1) * pitch.value},${(r + 1) * pitch.value}`).join(" ");

function press(id: number) {
  if (!props.disabled) emit("pick", id);
}
</script>

<template>
  <div ref="stage" class="link-stage" :class="{ calm }">
    <div
      class="link-board" :class="{ sizing, dim, disabled }"
      :style="{ width: `${width}px`, height: `${height}px`, '--tile': `${tileSize}px` }"
    >
      <button
        v-for="t in cells" :key="t.id" type="button" tabindex="-1" class="cell" :aria-label="names[t.kind]"
        :style="{ transform: placeOf(t.at) }" @pointerdown.left.prevent="press(t.id)"
      >
        <span
          class="tile"
          :class="{ on: selected === t.id, hint: hinted.has(t.id), shake: shake === t.id, flip: flipping && !calm }"
        >
          <img :src="faces[t.kind]" alt="" draggable="false" decoding="async" />
        </span>
      </button>

      <span
        v-for="g in ghosts" :key="`g${g.id}`" class="cell ghost" aria-hidden="true"
        :style="{ transform: placeOf(g.at) }"
      >
        <span class="tile on"><img :src="faces[g.kind]" alt="" draggable="false" /></span>
      </span>

      <svg v-if="lines.length" class="lines" :viewBox="`0 0 ${width} ${height}`" aria-hidden="true">
        <g v-for="l in lines" :key="l.key" class="link-line">
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
  /* Slides once the link has shown for a moment. */
  transition: transform 220ms var(--ease-out) 150ms;
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
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
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
  transform: translateY(-2px);
  box-shadow:
    0 0 0 3px var(--c-500),
    0 0 0 5px rgba(var(--c-500-rgb), 0.24),
    0 7px 12px -5px rgba(var(--c-900-rgb), 0.36);
}
.tile.hint:not(.on) {
  box-shadow:
    0 0 0 2px var(--c-300),
    0 0 12px 1px rgba(var(--c-500-rgb), 0.45),
    0 4px 9px -5px rgba(var(--c-900-rgb), 0.32);
  animation: hint-bob 900ms var(--ease-in-out) infinite alternate;
}
.tile.shake {
  animation: shake 280ms var(--ease-out);
}
.tile.flip {
  animation: flip 380ms var(--ease-in-out);
}
@keyframes hint-bob {
  to { transform: translateY(-3px); }
}
@keyframes shake {
  20% { transform: translateX(-3px) rotate(-3deg); }
  45% { transform: translateX(3px) rotate(3deg); }
  70% { transform: translateX(-2px) rotate(-1.5deg); }
}
@keyframes flip {
  50% { transform: rotateY(90deg) scale(0.92); }
}

/* The pair just taken, at its old place: it stays under the line, then goes. */
.ghost {
  z-index: 2;
  pointer-events: none;
  transition: none;
}
.ghost .tile {
  animation: ghost-out 130ms var(--ease-in) 130ms both;
}
@keyframes ghost-out {
  to { opacity: 0; transform: scale(0.6); }
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
.lines polyline {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 100;
}
.lines .under {
  stroke: #fff;
  stroke-width: calc(var(--tile) * 0.16 + 3px);
}
.lines .over {
  stroke: var(--c-500);
  stroke-width: calc(var(--tile) * 0.1 + 1px);
}
.link-line {
  animation: line-out 250ms linear both;
}
.link-line polyline {
  animation: line-in 90ms var(--ease-out) both;
}
@keyframes line-in {
  from { stroke-dashoffset: 100; }
  to { stroke-dashoffset: 0; }
}
@keyframes line-out {
  0%, 70% { opacity: 1; }
  100% { opacity: 0; }
}

.calm .tile,
.calm .link-board {
  transition: none;
}
.calm .tile.hint:not(.on) {
  animation: none;
  outline: 2px dashed var(--c-500);
  outline-offset: 2px;
}
.calm .tile.shake,
.calm .tile.flip,
.calm .ghost .tile,
.calm .link-line,
.calm .link-line polyline {
  animation: none;
}
.calm .cell:hover .tile:not(.on) {
  transform: none;
}
</style>
