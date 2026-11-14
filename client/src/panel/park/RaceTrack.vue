<script setup lang="ts">
// The race's track (docs/design/park-ui-rebuild.md §5.3): a raised oval band with one lap of low key tiles on it,
// squares 1 to `track` in two rows (the first left to right, the second back from the right), and the starting gate
// in the left turn: square 0, five stalls side by side, the top lane first. The space inside the band is the
// infield; the page puts what fits the phase there (the slot). The track fills the height it is given: the first
// row sits under the headroom a stack needs, the second on the floor, and the infield keeps its size
// whatever it holds. Before the start and once the result is up nobody stands on a tile, so the rows close up then
// and the infield takes the stack room.
// Positions come from the move list at the server time [t] (race.ts). A step: the die tumbles over the mover (the
// mover a little bigger, the others faded), the group hops to its square, a boost or trip square pushes it on, and a
// word pops over the dumpling at the moments that matter. Hop lengths follow the step's length. Under reduced
// motion everything jumps and stands still.
import { computed, onMounted, ref } from "vue";
import { manifest } from "../../manifest";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import {
  HOP_AT, HOP_LEN, leaders, momentOf, moving, playhead, spots, SQUARE_AT, stacksAt, stepLength,
  type MomentKind, type Race, type Spot,
} from "./race";
import RaceDie from "./RaceDie.vue";
import TuanziToken from "./TuanziToken.vue";

/** [cleared]: the race is over and its result stands in the infield; the field leaves the track. */
const props = defineProps<{ race: Race | null; t: number; track: number; members: string[]; cleared?: boolean }>();

const nameOf = (m: string) => manifest.characters.find((c) => c.id === m)?.name ?? m;

const BOOST = manifest.economy.park?.race?.squares.boost ?? 2;
const TRIP = Math.abs(manifest.economy.park?.race?.squares.trip ?? -1);
const WORDS: Record<MomentKind, string> = { lead: "领先", boost: "冲呀", trip: "哎呀", carry: "抓紧了" };

/** Squares in the first row; the second row has the rest, spread over the same width. */
const COLS = computed(() => Math.ceil(props.track / 2));
const ROW2 = computed(() => props.track - COLS.value);
/** Square (1 to track) -> (column, row, squares in that row): the first row left to right, the second back. */
function cell(square: number): { col: number; row: number; n: number } {
  const s = Math.max(1, Math.min(props.track, square));
  const cols = COLS.value;
  return s <= cols ? { col: s - 1, row: 0, n: cols } : { col: props.track - s, row: 1, n: ROW2.value };
}
const squares = computed(() => Array.from({ length: props.track }, (_, k) => k + 1));

/** The lanes on the start line: the race's once it is out, the members' order before. */
const lanes = computed(() => props.race?.start ?? props.members);
const moves = computed(() => (props.race?.start ? props.race.moves ?? [] : []));
const head = computed(() => (props.race && moves.value.length ? playhead(props.race, props.t) : null));
const step = computed(() => (head.value && head.value.current >= 0 ? moves.value[head.value.current] : null));
const stepMs = computed(() => (props.race && head.value && head.value.current >= 0 ? stepLength(props.race, head.value.current) : props.race?.stepMs ?? 2400));

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
const hopped = computed(() => !!head.value && head.value.current >= 0 && head.value.part >= HOP_AT);

/** The hop each tuanzi last made, so a new hop remounts the body and replays the jump. */
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

/** The die over the mover until the hop: the face it shows and how many ride on the mover. */
const die = computed(() => {
  const s = step.value;
  const h = head.value;
  if (!s || !h || h.part >= HOP_AT) return null;
  return { m: s.m, key: h.current, face: s.dice[s.dice.length - 1] ?? s.steps };
});
/** The squares walked, popped over the group once it hops; then the boost or trip square's own push. */
const roll = computed<{ m: string; key: string; text: string; down: boolean } | null>(() => {
  const s = step.value;
  const h = head.value;
  if (!s || !h || h.part < HOP_AT) return null;
  if (s.end !== undefined && h.part >= SQUARE_AT) {
    const down = s.square === "trip";
    return { m: s.m, key: `${h.current}b`, text: down ? `−${TRIP}` : `+${BOOST}`, down };
  }
  return { m: s.m, key: `${h.current}a`, text: `+${s.steps}`, down: false };
});

/** Who leads after each step, worked out once a race. */
const leadAfter = computed(() => (props.race?.start && moves.value.length ? leaders(props.race.start, moves.value) : []));
const moment = computed(() => {
  const s = step.value;
  const h = head.value;
  if (!s || !h) return null;
  const i = h.current;
  const m = momentOf(s, i ? leadAfter.value[i - 1] : lanes.value[0], leadAfter.value[i]);
  return m && h.part >= m.from ? { ...m, key: `${i}${m.kind}`, text: WORDS[m.kind] } : null;
});

/** The last step is done and the result not yet up: the field stands still, the winner crowned. */
const tail = computed(() => {
  const r = props.race;
  const h = head.value;
  return !!r?.endsAt && !!h && h.current < 0 && h.done === moves.value.length && props.t < r.endsAt * 1000;
});
const winner = computed(() => (tail.value ? props.race?.ranking?.[0] ?? "" : ""));

// Hops start only after the first paint, so opening the page mid-race does not make everyone jump at once.
const ready = ref(false);
onMounted(() => requestAnimationFrame(() => (ready.value = true)));

const timing = computed(() => ({
  "--cols": COLS.value,
  "--hop": `${Math.round(stepMs.value * HOP_LEN)}ms`,
  "--die": `${Math.round(stepMs.value * HOP_AT)}ms`,
  "--roll": `${Math.round(stepMs.value * 0.36)}ms`,
}));

function style(m: string) {
  const p = places.value[m] ?? { square: 0, level: 0, lane: 0 };
  const lift = movers.value.includes(m) ? 40 : 10;
  if (!p.square) return { "--lane": p.lane ?? 0, zIndex: lift + (p.lane ?? 0) };
  const { col, row, n } = cell(p.square);
  const tall = stacks.value.get(p.square)?.length ?? 1;
  return {
    "--col": col, "--row": row, "--n": n, "--lvl": p.level, "--above": above.value[m] ?? 0, "--tl": Math.max(1, tall - 1),
    zIndex: lift + p.level,
  };
}
function tileStyle(s: number) {
  const { col, row, n } = cell(s);
  return { "--col": col, "--row": row, "--n": n };
}
/** Words near the right turn open to the left, so they stay on the paper. */
const flipped = (m: string) => {
  const p = places.value[m];
  return !!p?.square && cell(p.square).col >= cell(p.square).n - 2;
};
</script>

<template>
  <div class="track" :class="{ calm: reducedMotion }">
    <div class="board" :class="{ live: ready && step, flat: !race?.start || cleared, cleared }" :style="timing">
      <i class="oval" aria-hidden="true"></i>
      <div class="infield"><slot /></div>
      <div class="gate" aria-hidden="true">
        <i v-for="k in 5" :key="k" class="stall"></i>
      </div>
      <div
        v-for="s in squares" :key="s" class="tile" :style="tileStyle(s)"
        :class="{ finish: s === track, boost: s === race?.setup.boost, trip: s === race?.setup.trip, flash: tail && s === track }"
      >
        <span v-if="s === track" class="mark">终点</span>
        <span v-else-if="s === race?.setup.boost" class="mark" :title="`+${BOOST}`">
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" /></svg>{{ BOOST }}
        </span>
        <span v-else-if="s === race?.setup.trip" class="mark" :title="`−${TRIP}`">
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" /></svg>{{ TRIP }}
        </span>
        <span v-else class="num">{{ s }}</span>
      </div>
      <div
        v-for="m in members" :key="m" class="tz"
        :class="{
          gated: !places[m]?.square, moving: movers.includes(m), mover: step?.m === m, top: (places[m]?.level ?? 0) > 0,
        }"
        :style="style(m)" :title="nameOf(m)"
      >
        <div :key="ready ? hops[m] ?? 'rest' : 'rest'" class="body" :class="{ hop: ready && hopped && hops[m] && movers.includes(m) }">
          <TuanziToken :member="m" />
        </div>
        <RaceDie v-if="ready && die?.m === m" :key="die.key" class="die" :class="{ side: above[m] }" :face="die.face" />
        <b v-if="ready && roll?.m === m" :key="roll.key" class="roll" :class="{ down: roll.down, side: above[m] }" aria-hidden="true">{{ roll.text }}</b>
        <span v-if="ready && moment?.m === m" :key="moment.key" class="say" :class="[moment.kind, { flip: flipped(m) }]" aria-hidden="true">
          {{ moment.text }}
        </span>
        <span v-if="winner === m" class="crown" aria-hidden="true"><Icon name="crown" :size="22" /></span>
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
  /*
   * Across: the gate (1.2 squares), the row's squares, the right turn (0.8 of a square). A tuanzi is about a square
   * wide, smaller when the track is short of height; each one up a stack rises --lift.
   */
  --pad: 16px;
  --cell: calc((100cqw - 2 * var(--pad)) / (var(--cols) + 2));
  --gw: calc(var(--cell) * 1.2);
  --cv: calc(var(--cell) * 0.8);
  --lane: calc(var(--cell) * var(--cols));
  --d: min(58px, calc(var(--cell) * 0.95), 15.5cqh);
  --lift: calc(var(--d) * 0.36);
  /* Room over a tile for a stack: three at full lift; a taller stack squeezes its lift to fit. */
  --head: calc(var(--d) * 2);
  /* Before the start nobody stands on a tile: the rows close up and the infield takes the room. */
  --tile-h: clamp(16px, calc(var(--cell) * 0.4), 26px);
  --lip: 4px;
  --rim: 7px;
  --band: calc(var(--tile-h) + var(--lip) + 2 * var(--rim));
  /* The first row's tiles sit under room for five in a stack; the second row stands on the floor. */
  --top-y: calc(var(--head) + var(--rim) + 6px);
  --bot-y: calc(100cqh - var(--tile-h) - var(--lip) - var(--rim) - 10px);
  /* The gate spans both rows: five stalls, a tuanzi in each a little smaller when they are short. */
  --gate-top: calc(var(--top-y) - var(--rim) + 3px);
  --gate-h: calc(var(--bot-y) + var(--tile-h) + var(--lip) + var(--rim) - 3px - var(--gate-top));
  --stall: calc((var(--gate-h) - 5px) / 5);
  --g: min(calc(var(--d) * 0.9), calc(var(--stall) * 0.86), calc(var(--gw) - 12px));
  position: absolute;
  inset: 0;
}
.board.flat {
  --head: 0px;
}
.board.cleared .tz {
  opacity: 0;
  visibility: hidden;
  transition: opacity var(--dur-slow), visibility 0s var(--dur-slow);
}
/* The rows slide apart when the race comes out. */
.oval,
.gate,
.infield {
  transition: top var(--dur-stage) var(--ease-in-out), height var(--dur-stage) var(--ease-in-out);
}
.tile {
  transition: transform var(--dur-stage) var(--ease-in-out);
}
.tile,
.tz {
  --cw: calc(var(--lane) / var(--n));
  --lft: min(var(--lift), calc((var(--head) - var(--d)) / var(--tl, 1)));
  --y: calc(var(--top-y) + var(--row) * (var(--bot-y) - var(--top-y)));
}

/* ---- the band: a raised oval, its wall showing under the outer edge and along the infield's far edge */
.oval {
  position: absolute;
  left: var(--pad);
  right: var(--pad);
  top: calc(var(--top-y) - var(--rim));
  height: calc(var(--bot-y) - var(--top-y) + var(--band));
  box-sizing: border-box;
  border: var(--band) solid var(--c-200);
  border-radius: var(--gw) var(--cv) var(--cv) var(--gw) / 50%;
  background: var(--c-50);
  box-shadow:
    0 var(--lip) 0 var(--c-300),
    0 10px 18px -12px rgba(var(--c-900-rgb), 0.4),
    inset 0 var(--lip) 0 var(--c-300);
}

/* ---- the starting gate: a white key block in the left turn, five stalls, a coral checker on its front edge */
.gate {
  position: absolute;
  z-index: 2;
  left: calc(var(--pad) + 4px);
  width: calc(var(--gw) - 8px);
  top: var(--gate-top);
  height: var(--gate-h);
  display: flex;
  flex-direction: column;
  gap: 3px;
  box-sizing: border-box;
  padding: 4px 9px 4px 4px;
  border-radius: calc(var(--gw) * 0.42) var(--radius-s) var(--radius-s) calc(var(--gw) * 0.42);
  background: linear-gradient(180deg, #fff, var(--key-white-shade));
  box-shadow: 0 var(--lip) 0 var(--c-300), 0 6px 10px -6px rgba(var(--c-900-rgb), 0.35);
}
.gate::after {
  content: "";
  position: absolute;
  top: 6px;
  bottom: 6px;
  right: 0;
  width: 6px;
  border-radius: 0 3px 3px 0;
  background: repeating-conic-gradient(var(--c-500) 0 25%, #fff 0 50%) 0 0 / 6px 6px;
}
/* A stall: a slot sunk into the gate. */
.stall {
  flex: 1;
  border-radius: var(--radius-s);
  background: var(--c-100);
  box-shadow: inset 0 2px 3px rgba(var(--c-900-rgb), 0.14);
}

/* ---- the tiles: low keys on the band, not to be pressed */
.tile {
  position: absolute;
  z-index: 2;
  left: 0;
  top: 0;
  width: calc(var(--cw) - 5px);
  height: var(--tile-h);
  transform: translate(calc(var(--pad) + var(--gw) + var(--col) * var(--cw) + 2.5px), var(--y));
  display: grid;
  place-items: center;
  box-sizing: border-box;
  border-radius: var(--radius-s);
  background: linear-gradient(180deg, #fff, var(--key-white-shade));
  box-shadow: 0 var(--lip) 0 var(--c-300);
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
/* The finish: a coral key with a checker along the edge the field comes in by. */
.tile.finish {
  background: var(--c-500);
  box-shadow: 0 var(--lip) 0 var(--c-700);
  overflow: hidden;
}
.tile.finish::after {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  right: 0;
  width: 10px;
  background: repeating-conic-gradient(var(--c-700) 0 25%, #fff 0 50%) 0 0 / 10px 10px;
  background-size: 10px 10px;
  opacity: 0.85;
}
.tile.finish .mark {
  margin-right: 8px;
  color: #fff;
}
.tile.finish.flash {
  animation: finish-flash 900ms var(--ease-out) 2;
}
@keyframes finish-flash {
  40% { box-shadow: 0 var(--lip) 0 var(--c-700), 0 0 0 4px rgba(var(--c-500-rgb), 0.45), var(--glow-l); }
}
/* The boost square: a key standing taller than the rest, an arrow up. */
.tile.boost {
  background: linear-gradient(180deg, var(--c-200), var(--c-300));
  box-shadow: 0 calc(var(--lip) + 4px) 0 var(--c-500), 0 10px 10px -6px rgba(var(--c-900-rgb), 0.35);
  translate: 0 -4px;
}
.tile.boost .mark,
.tile.trip .mark {
  font: 800 var(--fs-number)/1 var(--font-latin);
}
/* The trip square: a pit sunk into the band, an arrow down. */
.tile.trip {
  background: color-mix(in oklab, var(--c-300) 70%, var(--c-500));
  box-shadow: inset 0 4px 5px rgba(var(--c-900-rgb), 0.38), inset 0 -1px 0 rgba(255, 255, 255, 0.5);
  translate: 0 calc(var(--lip) * 0.6);
}
.tile.trip .mark {
  color: var(--c-900);
}
.mark svg {
  width: 12px;
  height: 12px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

/* ---- the infield: inside the band, right of the gate */
.infield {
  position: absolute;
  z-index: 1;
  left: calc(var(--pad) + var(--gw) + 4px);
  right: calc(var(--pad) + var(--cv) + 4px);
  top: calc(var(--top-y) + var(--tile-h) + var(--lip) + var(--rim) + 8px);
  bottom: calc(100cqh - var(--bot-y) + var(--rim) + 8px);
  display: flex;
  flex-direction: column;
}

/* ---- a tuanzi stands on its tile, --lift higher for each one below it; in the gate, on its stall's floor */
.tz {
  --size: var(--d);
  --tuanzi-size: var(--size);
  position: absolute;
  z-index: 10;
  left: 0;
  top: 0;
  width: var(--size);
  height: var(--size);
  transform: translate(
    calc(var(--pad) + var(--gw) + (var(--col) + 0.5) * var(--cw) - var(--d) / 2),
    calc(var(--y) + var(--tile-h) * 0.55 - var(--d) - var(--lvl) * var(--lft))
  );
  transition:
    transform var(--hop) var(--ease-in-out),
    width var(--hop) var(--ease-in-out),
    height var(--hop) var(--ease-in-out);
}
.tz.gated {
  --size: var(--g);
  transform: translate(
    calc(var(--pad) + 8px + (var(--gw) - 21px) / 2 - var(--g) / 2),
    calc(var(--gate-top) + 4px + (var(--lane) + 1) * var(--stall) - var(--g) - 6px)
  );
}
/* A soft shadow at the feet of the one at the bottom of a stack (or alone): it stays down while the body hops. */
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
/* While a step plays: the one rolling a bit bigger, everyone not moving faded towards the paper. */
.tz.mover .body {
  scale: 1.12;
}
.board.live .tz:not(.moving) .body {
  filter: saturate(0.45) contrast(0.86) brightness(1.08);
}
/* Take-off stretch, the arc, the squash on landing, then at rest. */
.hop {
  animation: hop var(--hop) linear both;
}
@keyframes hop {
  0% { transform: translateY(0) scale(1.08, 0.9); }
  14% { transform: translateY(-6%) scale(0.9, 1.12); animation-timing-function: ease-out; }
  50% { transform: translateY(-42%) scale(0.96, 1.05); animation-timing-function: ease-in; }
  82% { transform: translateY(0) scale(1.14, 0.84); }
  100% { transform: translateY(0) scale(1, 1); }
}

/* ---- over the group: the die, then the squares walked; aside: a word */
.die,
.roll {
  position: absolute;
  left: 50%;
  bottom: calc(100% + var(--above, 0) * var(--lft) + 4px);
  pointer-events: none;
}
/* Over a stack there is no room above: beside its top instead, on the side away from the word. */
.die.side,
.roll.side {
  left: calc(50% - var(--d) * 0.55);
  bottom: calc(100% + var(--above) * var(--lft) - var(--d) * 0.5);
  translate: -100% 0;
}
.tz .die.side {
  margin-left: 0;
}
/* The die (RaceDie): tumbling in and settling on its face. */
.tz .die {
  --s: max(20px, calc(var(--d) * 0.46));
  position: absolute;
  margin-left: calc(var(--s) / -2);
  animation: die var(--die) var(--ease-out) both;
}
@keyframes die {
  0% { opacity: 0; transform: translateY(-70%) rotate(-320deg) scale(0.5); }
  12% { opacity: 1; }
  55% { transform: translateY(6%) rotate(12deg) scale(1.06); }
  70% { transform: translateY(-14%) rotate(-5deg) scale(1); }
  84% { transform: translateY(0) rotate(0) scale(1); }
  100% { opacity: 1; transform: none; }
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
  bottom: calc(76% + var(--above, 0) * var(--lft));
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
.calm .body,
.calm .oval,
.calm .gate,
.calm .infield,
.calm .tile {
  transition: none;
}
.calm .hop,
.calm .die,
.calm .roll,
.calm .say,
.calm .crown,
.calm .tile.finish.flash {
  animation: none;
}

@container panel (max-width: 760px) {
  .board {
    --pad: 12px;
    --rim: 5px;
  }
  .say {
    padding: 3px 7px;
    font-size: var(--fs-label);
  }
}
</style>
