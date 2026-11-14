<script setup lang="ts">
// A die of the race: a small white key with coral pips, 1 to 6 as on a die. The size is --s (22px by default); the
// key's own shadow is --die-shadow.
// With [toss] it is thrown when it mounts (remount it with :key for each throw): up with a turn and a drift, down
// onto a shadow that grows as it falls, a squash and two smaller bounces. In the air it flashes other faces
// (race.ts airFaces, from [toss.pool]) and lands on [face]. The motion is one Web Animations run on transform and
// opacity; [toss.at] is how far into the throw it already is (a page opened mid-throw). No throw without motion.
// A die that gets thrown (toss passed, null between throws) stands on its contact shadow.
import { onMounted, ref } from "vue";
import { reducedMotion } from "../../stores/theme";
import { airFaces, TOSS_LAND, TOSS_TOP } from "./race";

/** A throw: [ms] long after [delay]; [height] how high, in % of the die (120 by default). */
export interface Toss { ms: number; delay?: number; at?: number; pool: readonly number[]; seed?: number; height?: number }

const props = defineProps<{ face: number; toss?: Toss | null }>();

const air = props.toss && !reducedMotion.value ? airFaces(props.face, props.toss.pool, props.toss.seed ?? 0) : [];
const cube = ref<HTMLElement | null>(null);
const shade = ref<HTMLElement | null>(null);
const faces = ref<HTMLElement[]>([]);
const final = ref<HTMLElement | null>(null);

// Shares of the throw after landing: squash, first bounce up and down, second bounce up and down.
const SQUASH = TOSS_LAND + 0.04;
const B1 = 0.8;
const B1_DOWN = 0.86;
const B2 = 0.91;
const B2_DOWN = 0.96;
const UP = "cubic-bezier(0.2, 0.7, 0.4, 1)";
const DOWN = "cubic-bezier(0.55, 0, 0.85, 0.4)";

/** translate in % of the die, rotation in degrees, scale; 720° is upright again, so every frame keeps one form. */
const pose = (x: number, y: number, r: number, sx = 1, sy = sx) =>
  `translate(${x}%, ${y}%) rotate(${r}deg) scale(${sx}, ${sy})`;

onMounted(() => {
  const t = props.toss;
  const el = cube.value;
  if (!t || reducedMotion.value || !el || typeof el.animate !== "function") return;
  const timing: KeyframeAnimationOptions = { duration: t.ms, delay: t.delay ?? 0, fill: "backwards" };
  const start = (a: Animation) => {
    if (t.at) a.currentTime = t.at;
  };
  // A squash keeps the die on the ground: shrunk to sy about its middle, it is lowered by (1 − sy) / 2 of its height.
  const squash = (sx: number, sy: number) => pose(0, ((1 - sy) / 2) * 100, 720, sx, sy);
  start(el.animate([
    { offset: 0, transform: pose(0, 0, 0), easing: UP },
    { offset: TOSS_TOP, transform: pose(22, -(t.height ?? 120), 400, 1.14), easing: DOWN },
    { offset: TOSS_LAND, transform: pose(0, 0, 720), easing: "ease-out" },
    { offset: SQUASH, transform: squash(1.16, 0.8), easing: UP },
    { offset: B1, transform: pose(0, -22, 720, 0.97, 1.04), easing: DOWN },
    { offset: B1_DOWN, transform: squash(1.07, 0.92), easing: UP },
    { offset: B2, transform: pose(0, -7, 720), easing: DOWN },
    { offset: B2_DOWN, transform: squash(1.03, 0.97), easing: "ease-out" },
    { offset: 1, transform: pose(0, 0, 720) },
  ], timing));
  shade.value && start(shade.value.animate([
    { offset: 0, transform: "scale(1)", opacity: 1, easing: UP },
    { offset: TOSS_TOP, transform: "scale(0.45)", opacity: 0.3, easing: DOWN },
    { offset: TOSS_LAND, transform: "scale(1)", opacity: 1 },
    { offset: SQUASH, transform: "scale(1.12)", opacity: 1, easing: UP },
    { offset: B1, transform: "scale(0.82)", opacity: 0.75, easing: DOWN },
    { offset: B1_DOWN, transform: "scale(1)", opacity: 1, easing: UP },
    { offset: B2, transform: "scale(0.94)", opacity: 0.9, easing: DOWN },
    { offset: 1, transform: "scale(1)", opacity: 1 },
  ], timing));
  // Each air face shows for its slice of the flight, the last one until the landing; the face itself from there on.
  const slice = TOSS_LAND / Math.max(1, air.length);
  faces.value.forEach((f, k) => {
    const from = k * slice;
    const to = (k + 1) * slice;
    const frames: Keyframe[] = [{ offset: 0, opacity: k ? 0 : 1 }];
    if (k) frames.push({ offset: from, opacity: 0 }, { offset: from, opacity: 1 });
    frames.push({ offset: to, opacity: 1 }, { offset: to, opacity: 0 }, { offset: 1, opacity: 0 });
    start(f.animate(frames, { ...timing, fill: "both" }));
  });
  if (final.value && air.length) {
    start(final.value.animate([
      { offset: 0, opacity: 0 }, { offset: TOSS_LAND, opacity: 0 }, { offset: TOSS_LAND, opacity: 1 }, { offset: 1, opacity: 1 },
    ], { ...timing, fill: "backwards" }));
  }
});
</script>

<template>
  <span class="race-die" aria-hidden="true">
    <i v-if="toss !== undefined" ref="shade" class="shade"></i>
    <span ref="cube" class="cube">
      <span ref="final" class="pips" :class="`f${face}`"><i v-for="k in face" :key="k"></i></span>
      <span
        v-for="(f, k) in air" :key="`a${k}`" :ref="(el) => el && (faces[k] = el as HTMLElement)" class="pips air"
        :class="`f${f}`"
      ><i v-for="p in f" :key="p"></i></span>
    </span>
  </span>
</template>

<style scoped>
.race-die {
  --s: 22px;
  position: relative;
  display: inline-block;
  flex: none;
  width: var(--s);
  height: var(--s);
}
/* The contact shadow: full on the ground, smaller and fainter the higher the die is. */
.shade {
  position: absolute;
  left: 8%;
  right: 8%;
  bottom: -9%;
  height: 20%;
  border-radius: 50%;
  background: radial-gradient(closest-side, rgba(var(--c-900-rgb), 0.3), rgba(var(--c-900-rgb), 0));
}
/* A coral rim and a deeper lip keep the white key apart from the white page it is thrown on. */
.cube {
  position: absolute;
  inset: 0;
  border-radius: 24%;
  background: linear-gradient(180deg, #fff 40%, var(--c-50));
  box-shadow:
    inset 0 0 0 max(1px, calc(var(--s) * 0.035)) var(--c-300),
    var(--die-shadow, 0 max(2px, calc(var(--s) * 0.06)) 0 var(--c-400),
      0 calc(var(--s) * 0.1) calc(var(--s) * 0.16) calc(var(--s) * -0.05) rgba(var(--c-900-rgb), 0.4));
}
.pips {
  position: absolute;
  inset: 14%;
  display: grid;
  grid-template: repeat(3, 1fr) / repeat(3, 1fr);
}
.pips.air {
  opacity: 0;
}
.pips i {
  width: 72%;
  aspect-ratio: 1;
  place-self: center;
  border-radius: 50%;
  background: var(--c-700);
}
.f1 i { grid-area: 2 / 2; }
.f2 i:nth-child(1) { grid-area: 1 / 1; }
.f2 i:nth-child(2) { grid-area: 3 / 3; }
.f3 i:nth-child(1) { grid-area: 1 / 1; }
.f3 i:nth-child(2) { grid-area: 2 / 2; }
.f3 i:nth-child(3) { grid-area: 3 / 3; }
.f4 i:nth-child(1),
.f5 i:nth-child(1),
.f6 i:nth-child(1) { grid-area: 1 / 1; }
.f4 i:nth-child(2),
.f5 i:nth-child(2),
.f6 i:nth-child(2) { grid-area: 1 / 3; }
.f4 i:nth-child(3),
.f5 i:nth-child(3),
.f6 i:nth-child(3) { grid-area: 3 / 1; }
.f4 i:nth-child(4),
.f5 i:nth-child(4),
.f6 i:nth-child(4) { grid-area: 3 / 3; }
.f5 i:nth-child(5) { grid-area: 2 / 2; }
.f6 i:nth-child(5) { grid-area: 2 / 1; }
.f6 i:nth-child(6) { grid-area: 2 / 3; }
</style>
