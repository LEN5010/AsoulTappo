<script setup lang="ts">
// The diagonal coral stage curtains, played for a draw: three pleats sweep across the scene with a
// travelling silk gleam while the request runs, then peel away to the right to unveil the board.
// They say nothing about the result; every tile is face down until it is turned.
import { ref } from "vue";
import { EASE_IN_OUT } from "../ui/motion";
import Icon from "../ui/Icon.vue";

defineProps<{ count: number }>();

const LEFT = "translateX(-115%)";
const HOME = "translateX(0)";
const RIGHT = "translateX(115%)";
const COVER_MS = 230;
const LEAVE_MS = 350;
const COVER_LAG_MS = 34;
const LEAVE_LAG_MS = 38;
const COVER_EASE = "cubic-bezier(0.22, 1, 0.36, 1)";
const TITLE = [..."RESONANCE"];

const root = ref<HTMLElement>();
const under = ref<HTMLElement>();
const mid = ref<HTMLElement>();
const over = ref<HTMLElement>();
/** Bumped on every cover so the title's letters and silk gleam replay cleanly. */
const take = ref(0);

const done = (list: Animation[]) => Promise.allSettled(list.map((a) => a.finished)).then(() => undefined);
function slide(els: HTMLElement[], from: string, to: string, duration: number, lag: number, easing: string): Animation[] {
  return els.map((el, i) =>
    el.animate([{ transform: from }, { transform: to }], { duration, delay: i * lag, easing, fill: "both" }),
  );
}

let held: Animation[] = [];
function hold(list: Animation[]) {
  held.forEach((a) => a.cancel());
  held = list;
  return done(list);
}

/** Diagonal curtains snap shut from the left, title rises, silk gleam sweeps across. */
function cover(): Promise<void> {
  take.value += 1;
  root.value!.style.visibility = "visible";
  return hold(slide([under.value!, mid.value!, over.value!], LEFT, HOME, COVER_MS, COVER_LAG_MS, COVER_EASE));
}

/** Curtains peel away to the right in reverse pleat order, unveiling the board. */
async function leave(): Promise<void> {
  await hold(slide([over.value!, mid.value!, under.value!], HOME, RIGHT, LEAVE_MS, LEAVE_LAG_MS, EASE_IN_OUT));
  root.value!.style.visibility = "hidden";
}

defineExpose({ cover, leave });
</script>

<template>
  <div ref="root" class="bands" aria-hidden="true">
    <div ref="under" class="band under"></div>
    <div ref="mid" class="band mid"></div>
    <div ref="over" class="band over">
      <i :key="`g-${take}`" class="gleam"></i>
      <i class="seam-top"></i>
      <i class="seam-bot"></i>
      <span :key="take" class="title">
        <b class="letters"><i v-for="(c, n) in TITLE" :key="n" :style="{ '--n': n }">{{ c }}</i></b>
        <small class="sub">
          <i class="rule"></i>
          <Icon name="spark" :size="14" />
          <span>共鸣 ×{{ count }}</span>
          <Icon name="spark" :size="14" />
          <i class="rule"></i>
        </small>
      </span>
    </div>
  </div>
</template>

<style scoped>
.bands {
  position: absolute;
  inset: 0;
  z-index: 8;
  overflow: hidden;
  pointer-events: none;
  visibility: hidden;
}
/* Skewed via clip-path with >6% corner safety margin at rest, keeping typography inside crisp and unskewed. */
.band {
  position: absolute;
  top: -2px;
  bottom: -2px;
  left: -14%;
  width: 128%;
  overflow: hidden;
  clip-path: polygon(6% 0, 100% 0, 94% 100%, 0 100%);
  transform: translateX(-115%);
  will-change: transform;
}
.under {
  background: var(--c-200);
}
.mid {
  background: linear-gradient(108deg, var(--c-300), color-mix(in oklab, var(--c-300) 55%, #fff));
}
.over {
  background: linear-gradient(108deg, var(--c-400) 0%, var(--c-500) 42%, var(--c-600) 100%);
}
/* Travelling diagonal silk luster that bridges cover() into leave(). */
.gleam {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    108deg,
    transparent 32%,
    rgba(255, 255, 255, 0.12) 41%,
    rgba(255, 255, 255, 0.36) 48%,
    rgba(255, 255, 255, 0.1) 54%,
    transparent 63%
  ) 140% 0 / 240% 100% no-repeat;
  animation: gleam-sweep 520ms var(--ease-out) 90ms both;
}
.seam-top,
.seam-bot {
  position: absolute;
  left: 8%;
  right: 8%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.45) 25%, rgba(255, 255, 255, 0.45) 75%, transparent);
}
.seam-top { top: 20%; }
.seam-bot { bottom: 20%; }

.title {
  position: absolute;
  z-index: 2;
  left: 50%;
  top: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translate(-50%, -50%);
  white-space: nowrap;
}
.letters {
  display: flex;
  font: 800 clamp(64px, 17cqw, 112px)/0.9 var(--font-latin);
  letter-spacing: 0.015em;
  color: #fff;
  text-shadow: 0 3px 0 rgba(var(--c-900-rgb), 0.14);
}
.letters i {
  display: block;
  font-style: normal;
  animation: letter-rise 400ms var(--ease-spring) calc(48ms + var(--n) * 22ms) both;
}
.sub {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 4px 16px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.48);
  font: 800 var(--fs-heading)/1.1 var(--font);
  color: var(--ink);
  animation: label-in 300ms var(--ease-out) 110ms both;
}
.sub :deep(svg) {
  stroke-width: 0;
  fill: #fff;
}
.rule {
  width: 18px;
  height: 1.5px;
  border-radius: 1px;
  background: rgba(var(--c-900-rgb), 0.28);
}

@keyframes gleam-sweep {
  from { background-position: 140% 0; opacity: 0.3; }
  35% { opacity: 1; }
  to { background-position: -45% 0; opacity: 0.85; }
}
@keyframes letter-rise {
  0% { opacity: 0; transform: translateY(58%) scaleY(1.26); }
  100% { opacity: 1; transform: none; }
}
@keyframes label-in {
  from { opacity: 0; transform: translateY(8px) scale(0.96); }
  to { opacity: 1; transform: none; }
}
</style>
