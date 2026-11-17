<script setup lang="ts">
// A close-up of a skill at work: the board dims, a coral band crosses it, the member's dumpling is slapped on as a
// large sticker and its skill is named and explained. It fills its parent (the board) and sizes itself by --u, a
// square's side. It plays once, [ms] long; [at] (0 to 1) is how far in it already is when it comes up, for a page
// opened or a replay moved part way through.
import TuanziToken from "./TuanziToken.vue";

const props = defineProps<{
  member: string; who: string; name: string; text: string; color?: string; ms: number; at?: number; paused?: boolean;
}>();

const delay = `${-Math.min(0.98, Math.max(0, props.at ?? 0)) * props.ms}ms`;
</script>

<template>
  <div
    class="cut-in" :class="{ paused }" role="status" :aria-label="`${who} ${name}：${text}`"
    :style="{ '--ms': `${ms}ms`, '--delay': delay, '--who': color }"
  >
    <div class="band">
      <i class="rays" aria-hidden="true"><i></i></i>
      <i class="flash" aria-hidden="true"></i>
      <span class="art" aria-hidden="true"><TuanziToken :member="member" /></span>
      <span class="tag" aria-hidden="true">SKILL</span>
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
 * In shares of --ms: the band is across by 10%, the sticker lands at 16%, the name pops from 20%, the line under it
 * is up by 36%; everything holds, and leaves from 88%.
 */
.cut-in {
  position: absolute;
  inset: 0;
  z-index: 400;
  border-radius: inherit;
  overflow: hidden;
  pointer-events: none;
  background: rgba(var(--c-900-rgb), 0.34);
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
  height: calc(var(--u) * 2.3);
  translate: 0 -50%;
  background: var(--grad-sky);
  --paper: 0;
  box-shadow:
    inset 0 calc(var(--u) * 0.07) 0 var(--surface),
    inset 0 calc(var(--u) * -0.07) 0 var(--surface),
    0 calc(var(--u) * 0.1) calc(var(--u) * 0.3) rgba(var(--c-900-rgb), 0.3);
  animation-name: band;
}
@keyframes band {
  0% { clip-path: inset(-40% 100% -40% 0); }
  10%, 88% { clip-path: inset(-40% 0 -40% 0); }
  100% { clip-path: inset(-40% 0 -40% 100%); }
}
/* The member's colour: a thin line under the band's top edge. */
.band::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: calc(var(--u) * 0.07);
  height: calc(var(--u) * 0.06);
  background: var(--who, var(--c-600));
}
/* Printed into the coral, behind the type: halftone dots on the right half. */
.band::after {
  content: "";
  position: absolute;
  inset: 0;
  background: #fff;
  opacity: 0.3;
  mask:
    url("../../assets/patterns/halftone.svg") 0 0 / 280px 140px repeat-x,
    linear-gradient(90deg, transparent 45%, #000 85%);
  mask-composite: intersect;
}

/* Turning rays behind the sticker, as behind a rare card. */
.rays {
  position: absolute;
  left: calc(var(--u) * 2.1);
  top: 50%;
  width: calc(var(--u) * 5.4);
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  overflow: hidden;
  mask: radial-gradient(circle, #000 14%, transparent 64%);
  opacity: 0.55;
  animation-name: rays;
}
.rays i {
  position: absolute;
  inset: -20%;
  background: repeating-conic-gradient(#fff 0 6deg, transparent 6deg 24deg);
  animation: turn 40s linear infinite;
  animation-delay: 0s;
  animation-fill-mode: none;
}
@keyframes rays {
  0%, 12% { opacity: 0; scale: 0.5; }
  20%, 88% { opacity: 0.55; scale: 1; }
  100% { opacity: 0; scale: 1; }
}
@keyframes turn {
  to { rotate: 360deg; }
}

/* The sticker: slapped on from large, a little askew, over both edges of the band. */
.art {
  position: absolute;
  left: calc(var(--u) * 2.1);
  top: 50%;
  --tuanzi-size: calc(var(--u) * 3);
  width: var(--tuanzi-size);
  height: var(--tuanzi-size);
  translate: -50% -52%;
  rotate: -7deg;
  filter: drop-shadow(0 calc(var(--u) * 0.08) calc(var(--u) * 0.12) rgba(var(--c-900-rgb), 0.35));
  animation-name: slap;
}
.art :deep(.tuanzi-token) {
  filter: var(--sticker-lg);
}
@keyframes slap {
  0%, 9% { opacity: 0; scale: 1.9; rotate: -18deg; }
  16% { opacity: 1; scale: 0.94; rotate: -5deg; animation-timing-function: var(--ease-spring); }
  21% { scale: 1.04; rotate: -8deg; }
  26%, 88% { opacity: 1; scale: 1; rotate: -7deg; }
  100% { opacity: 0; scale: 1; rotate: -7deg; translate: -120% -52%; }
}
/* The white flash of the landing. */
.flash {
  position: absolute;
  left: calc(var(--u) * 2.1);
  top: 50%;
  width: calc(var(--u) * 3.6);
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  background: radial-gradient(circle, #fff 30%, transparent 68%);
  animation-name: flash;
}
@keyframes flash {
  0%, 14% { opacity: 0; scale: 0.4; }
  17% { opacity: 0.95; scale: 1; }
  28%, 100% { opacity: 0; scale: 1.5; }
}

.words {
  position: absolute;
  left: calc(var(--u) * 4);
  right: calc(var(--u) * 0.3);
  top: 50%;
  translate: 0 -50%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: calc(var(--u) * 0.1);
  color: var(--ink);
}
.who {
  display: inline-flex;
  align-items: center;
  gap: calc(var(--u) * 0.08);
  font: 800 max(11px, calc(var(--u) * 0.22)) / 1 var(--font);
  color: var(--ink);
  animation-name: rise;
}
.who i {
  width: calc(var(--u) * 0.06);
  height: calc(var(--u) * 0.24);
  border-radius: 1px;
  background: var(--who, var(--c-700));
}
/* The skill's name: white with the ink's outline, a letter at a time. */
.name {
  display: flex;
  font: 800 calc(var(--u) * 0.86) / 1 var(--font);
  letter-spacing: 0.04em;
  color: var(--surface);
  -webkit-text-stroke: calc(var(--u) * 0.1) var(--ink);
  paint-order: stroke fill;
}
.name span {
  display: inline-block;
  animation-name: pop;
  animation-delay: calc(var(--delay) + var(--ms) * 0.035 * var(--k));
}
@keyframes pop {
  0%, 20% { opacity: 0; translate: 0 40%; scale: 0.6; }
  25% { opacity: 1; translate: 0 -12%; scale: 1.12; }
  29%, 88% { opacity: 1; translate: 0 0; scale: 1; }
  100% { opacity: 0; translate: 0 0; scale: 1; }
}
/* What it does: a strip of paper under the name. */
.text {
  padding: calc(var(--u) * 0.07) calc(var(--u) * 0.16);
  border-radius: var(--radius-s);
  background: var(--surface);
  --paper: 1;
  color: var(--ink);
  font: 800 max(12px, calc(var(--u) * 0.27)) / 1.2 var(--font);
  white-space: nowrap;
  box-shadow: 0 2px 0 rgba(var(--c-900-rgb), 0.2);
  animation-name: strip;
}
@keyframes rise {
  0%, 18% { opacity: 0; translate: 0 60%; }
  26%, 88% { opacity: 1; translate: 0 0; }
  100% { opacity: 0; }
}
@keyframes strip {
  0%, 28% { opacity: 0; clip-path: inset(0 100% 0 0); }
  36%, 88% { opacity: 1; clip-path: inset(0 0 0 0); }
  100% { opacity: 0; clip-path: inset(0 0 0 0); }
}
/* The label in the corner of the band, in the display face. */
.tag {
  position: absolute;
  right: calc(var(--u) * 0.3);
  bottom: calc(var(--u) * 0.16);
  font: 800 calc(var(--u) * 0.5) / 1 var(--font-latin);
  letter-spacing: 0.08em;
  color: var(--surface);
  opacity: 0.5;
  animation-name: tag;
}
@keyframes tag {
  0%, 12% { opacity: 0; translate: 30% 0; }
  22%, 88% { opacity: 0.5; translate: 0 0; }
  100% { opacity: 0; }
}
</style>
