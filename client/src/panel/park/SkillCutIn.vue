<script setup lang="ts">
// A close-up of a skill at work: the board dims softly, a framed coral ribbon crosses it, the member's dumpling lands
// on a sunburst medallion as a large die-cut sticker, and its skill is named and explained. It fills its parent (the
// board) and sizes itself by --cu (clamped to the container's width and height as well as --u, so narrow 7×7 boards and
// wide 11×5 boards alike fit without clipping). It plays once, [ms] long; [at] (0 to 1) is how far in it already is.
// With [art] the sticker is that picture instead of the member's dumpling (the alpaca's car as it comes out).
import { computed } from "vue";
import { reducedMotion } from "../../stores/theme";
import TuanziToken from "./TuanziToken.vue";

const props = defineProps<{
  member: string; who: string; name: string; text: string; color?: string; ms: number; at?: number; paused?: boolean;
  art?: string;
}>();

const delay = computed(() => `${-Math.min(0.98, Math.max(0, props.at ?? 0)) * props.ms}ms`);
</script>

<template>
  <div
    class="cut-in" :class="{ paused, calm: reducedMotion }" role="status" :aria-label="`${who} ${name}：${text}`"
    :style="{ '--ms': `${ms}ms`, '--delay': delay, '--who': color }"
  >
    <div class="band">
      <i class="sheen" aria-hidden="true"></i>
      <i class="rays" aria-hidden="true"><i></i></i>
      <i class="medallion" aria-hidden="true"></i>
      <i class="shock" aria-hidden="true"></i>
      <i class="flash" aria-hidden="true"></i>
      <span class="art" :class="{ pic: art }" aria-hidden="true">
        <img v-if="art" :src="art" alt="" draggable="false" /><TuanziToken v-else :member="member" />
      </span>
      <div class="words" aria-hidden="true">
        <small class="who"><i></i>{{ who }}</small>
        <b class="name"><span v-for="(ch, k) in name" :key="k" :style="{ '--k': k }">{{ ch }}</span></b>
        <span class="text">{{ text }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/*
 * Every part runs for the whole --ms on its own keyframes, so a negative delay puts all of them at the same moment.
 * In shares of --ms: the ribbon snaps across by 10%, the medallion and sticker land at 16% with a shockwave ring and a
 * sweep of foil sheen, the name springs up from 19%, the effect strip wipes open by 34%; everything holds and exits from 88%.
 */
.cut-in {
  container-type: size;
  --cu: min(var(--u), calc(100cqw / 9.2), calc(100cqh / 4.1));
  position: absolute;
  inset: 0;
  z-index: 400;
  border-radius: inherit;
  overflow: hidden;
  pointer-events: none;
  background:
    radial-gradient(circle at calc(var(--cu) * 2.05) 50%, rgba(255, 255, 255, 0.2), transparent 52%),
    rgba(var(--c-900-rgb), 0.22);
  animation: dim var(--ms) linear var(--delay) both;
}
.cut-in.paused,
.cut-in.paused * {
  animation-play-state: paused;
}
.cut-in * {
  animation-duration: var(--ms);
  animation-delay: var(--delay);
  animation-fill-mode: both;
  animation-timing-function: linear;
}
@keyframes dim {
  0%, 100% { opacity: 0; }
  8%, 90% { opacity: 1; }
}

.band {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: calc(var(--cu) * 2.22);
  translate: 0 -50%;
  background: linear-gradient(180deg, var(--c-400), var(--c-500) 56%, var(--c-600));
  box-shadow:
    inset 0 calc(var(--cu) * 0.075) 0 var(--surface),
    inset 0 calc(var(--cu) * -0.075) 0 var(--surface),
    0 0 0 max(1.5px, calc(var(--cu) * 0.025)) rgba(var(--c-900-rgb), 0.16),
    0 calc(var(--cu) * 0.12) calc(var(--cu) * 0.34) rgba(var(--c-900-rgb), 0.32);
  animation-name: band;
}
@keyframes band {
  0% { clip-path: inset(-55% 100% -55% 0); animation-timing-function: var(--ease-out); }
  10%, 88% { clip-path: inset(-55% 0 -55% 0); animation-timing-function: var(--ease-in); }
  100% { clip-path: inset(-55% 0 -55% 100%); }
}
/* Crisp coral-light highlight rule under the ribbon's top white rail. */
.band::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: calc(var(--cu) * 0.075);
  height: max(2px, calc(var(--cu) * 0.04));
  background: rgba(255, 255, 255, 0.36);
}
/* Printed into the coral, sparse and behind the type: halftone dots on the right half only. */
.band::after {
  content: "";
  position: absolute;
  inset: calc(var(--cu) * 0.075) 0;
  background: #fff;
  opacity: 0.26;
  -webkit-mask:
    url("../../assets/patterns/halftone.svg") 0 0 / 280px 140px repeat-x,
    linear-gradient(90deg, transparent 42%, #000 84%);
  -webkit-mask-composite: source-in;
  mask:
    url("../../assets/patterns/halftone.svg") 0 0 / 280px 140px repeat-x,
    linear-gradient(90deg, transparent 42%, #000 84%);
  mask-composite: intersect;
}

/* A diagonal foil highlight sweeping across the ribbon as the sticker lands. */
.sheen {
  position: absolute;
  inset: calc(var(--cu) * 0.075) 0;
  overflow: hidden;
  pointer-events: none;
  background: linear-gradient(105deg, transparent 36%, rgba(255, 255, 255, 0.42) 50%, transparent 64%) 140% 0 / 240% 100% no-repeat;
  animation-name: sheen;
}
@keyframes sheen {
  0%, 10% { background-position: 140% 0; opacity: 0; }
  14% { opacity: 1; animation-timing-function: var(--ease-out); }
  38%, 100% { background-position: -50% 0; opacity: 0; }
}

/* Turning sunburst rays behind the sticker medallion. */
.rays {
  position: absolute;
  left: calc(var(--cu) * 2.05);
  top: 50%;
  width: calc(var(--cu) * 5.2);
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  overflow: hidden;
  -webkit-mask: radial-gradient(circle, #000 18%, transparent 64%);
  mask: radial-gradient(circle, #000 18%, transparent 64%);
  opacity: 0.58;
  animation-name: rays;
}
/* Spins on a clock of its own, started as far in as the close-up is, so a close-up drawn afresh keeps its rays' angle. */
.rays i {
  position: absolute;
  inset: -20%;
  background: repeating-conic-gradient(#fff 0 6.5deg, transparent 6.5deg 24deg);
  animation: spin 24s linear infinite;
  animation-delay: var(--delay);
  animation-fill-mode: none;
}
@keyframes rays {
  0%, 11% { opacity: 0; scale: 0.5; animation-timing-function: var(--ease-out); }
  20%, 88% { opacity: 0.58; scale: 1; }
  100% { opacity: 0; scale: 1; }
}
@keyframes spin {
  to { rotate: 360deg; }
}

/* A cream-rimmed circular badge anchoring the dumpling across both edges of the ribbon. */
.medallion {
  position: absolute;
  left: calc(var(--cu) * 2.05);
  top: 50%;
  width: calc(var(--cu) * 2.58);
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 38%, var(--surface) 0%, var(--c-100) 64%, var(--c-200) 100%);
  box-shadow:
    inset 0 0 0 max(2px, calc(var(--cu) * 0.04)) var(--c-300),
    0 0 0 max(3px, calc(var(--cu) * 0.065)) var(--surface),
    0 calc(var(--cu) * 0.08) calc(var(--cu) * 0.2) rgba(var(--c-900-rgb), 0.28);
  animation-name: medal;
}
@keyframes medal {
  0%, 8% { opacity: 0; scale: 0.4; animation-timing-function: var(--ease-pop); }
  17%, 88% { opacity: 1; scale: 1; }
  100% { opacity: 0; scale: 0.85; }
}

/* Expanding ring of light when the sticker slaps down. */
.shock {
  position: absolute;
  left: calc(var(--cu) * 2.05);
  top: 50%;
  width: calc(var(--cu) * 3.8);
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  background: radial-gradient(circle, transparent 42%, rgba(255, 255, 255, 0.85) 50%, transparent 62%);
  animation-name: shock;
}
@keyframes shock {
  0%, 14% { opacity: 0; scale: 0.55; }
  16% { opacity: 0.95; scale: 0.72; animation-timing-function: var(--ease-out); }
  32%, 100% { opacity: 0; scale: 1.42; }
}

/* The sticker: slapped on from large, a little askew, standing proud over the medallion. */
.art {
  position: absolute;
  left: calc(var(--cu) * 2.05);
  top: 50%;
  --tuanzi-size: calc(var(--cu) * 3.08);
  width: var(--tuanzi-size);
  height: var(--tuanzi-size);
  translate: -50% -53%;
  rotate: -7deg;
  filter: drop-shadow(0 calc(var(--cu) * 0.09) calc(var(--cu) * 0.14) rgba(var(--c-900-rgb), 0.34));
  animation-name: slap;
}
.art :deep(.tuanzi-token) {
  filter: var(--sticker-lg);
}
/*
 * A picture for a sticker: wider than tall, held by its foot in the same square; a little smaller and to the right,
 * so its nose stays clear of the board's left edge, which cuts the medallion.
 */
.art.pic img {
  display: block;
  width: 82%;
  height: 100%;
  margin-left: 16%;
  object-fit: contain;
  object-position: 50% 62%;
  filter: var(--sticker-lg);
}
@keyframes slap {
  0%, 8% { opacity: 0; scale: 1.85; rotate: -18deg; animation-timing-function: var(--ease-out); }
  15% { opacity: 1; scale: 0.92; rotate: -4deg; animation-timing-function: var(--ease-spring); }
  21% { scale: 1.05; rotate: -8deg; animation-timing-function: var(--ease-out); }
  26%, 88% { opacity: 1; scale: 1; rotate: -7deg; animation-timing-function: var(--ease-in); }
  100% { opacity: 0; scale: 0.96; rotate: -7deg; translate: -95% -53%; }
}
/* The white flash of the landing. */
.flash {
  position: absolute;
  left: calc(var(--cu) * 2.05);
  top: 50%;
  width: calc(var(--cu) * 3.5);
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  background: radial-gradient(circle, #fff 28%, transparent 66%);
  animation-name: flash;
}
@keyframes flash {
  0%, 13% { opacity: 0; scale: 0.4; }
  16% { opacity: 0.9; scale: 1; animation-timing-function: var(--ease-out); }
  27%, 100% { opacity: 0; scale: 1.45; }
}

.words {
  position: absolute;
  left: calc(var(--cu) * 3.72);
  right: calc(var(--cu) * 0.32);
  top: 50%;
  translate: 0 -50%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: calc(var(--cu) * 0.09);
  color: var(--ink);
}
.who {
  display: inline-flex;
  align-items: center;
  gap: max(5px, calc(var(--cu) * 0.07));
  padding: max(2px, calc(var(--cu) * 0.04)) max(8px, calc(var(--cu) * 0.13)) max(2px, calc(var(--cu) * 0.04)) max(6px, calc(var(--cu) * 0.09));
  border-radius: 999px;
  background: var(--surface);
  box-shadow: 0 2px 0 rgba(var(--c-900-rgb), 0.16);
  font: 800 max(11px, calc(var(--cu) * 0.21)) / 1.15 var(--font);
  color: var(--ink);
  animation-name: rise;
}
.who i {
  width: 4px;
  height: max(10px, calc(var(--cu) * 0.18));
  border-radius: 2px;
  background: var(--who, var(--c-700));
}
/* The skill's name: die-cut white lettering with the ink's outline, springing in a glyph at a time. */
.name {
  display: flex;
  font: 800 calc(var(--cu) * 0.88) / 1 var(--font);
  letter-spacing: 0.04em;
  color: var(--surface);
  -webkit-text-stroke: calc(var(--cu) * 0.11) var(--ink);
  paint-order: stroke fill;
  filter: drop-shadow(0 max(2px, calc(var(--cu) * 0.05)) 0 rgba(var(--c-900-rgb), 0.3));
}
.name span {
  display: inline-block;
  animation-name: pop;
  animation-delay: calc(var(--delay) + var(--ms) * 0.032 * var(--k));
}
@keyframes pop {
  0%, 18% { opacity: 0; translate: 0 42%; scale: 0.58; animation-timing-function: var(--ease-pop); }
  24% { opacity: 1; translate: 0 -10%; scale: 1.1; animation-timing-function: var(--ease-out); }
  29%, 88% { opacity: 1; translate: 0 0; scale: 1; }
  100% { opacity: 0; translate: 0 0; scale: 1; }
}
/* What it does: a crisp strip of paper under the name. */
.text {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: max(3px, calc(var(--cu) * 0.065)) max(8px, calc(var(--cu) * 0.16));
  border-radius: var(--radius-s);
  background: var(--surface);
  color: var(--ink);
  font: 800 max(11px, calc(var(--cu) * 0.26)) / 1.2 var(--font);
  white-space: nowrap;
  box-shadow: 0 2px 0 rgba(var(--c-900-rgb), 0.2);
  animation-name: strip;
}
@keyframes rise {
  0%, 15% { opacity: 0; translate: 0 55%; animation-timing-function: var(--ease-out); }
  24%, 88% { opacity: 1; translate: 0 0; }
  100% { opacity: 0; }
}
@keyframes strip {
  0%, 25% { opacity: 0; clip-path: inset(0 100% 0 0); animation-timing-function: var(--ease-out); }
  35%, 88% { opacity: 1; clip-path: inset(0 0 0 0); }
  100% { opacity: 0; clip-path: inset(0 0 0 0); }
}

/* Reduced motion: settled static frame without sweeps, spins or bounces. */
.cut-in.calm,
.cut-in.calm * {
  animation: none !important;
}
.cut-in.calm .sheen,
.cut-in.calm .shock,
.cut-in.calm .flash {
  display: none;
}
</style>
