<script setup lang="ts">
// The page-turn bands, played for a draw: they cover the scene while the request runs, then carry on
// off to the right. They say nothing about the result; every tile is face down until it is turned.
import { ref } from "vue";
import { EASE_IN_OUT } from "../ui/motion";

defineProps<{ count: number }>();

const LEFT = "translateX(-112%)";
const HOME = "translateX(0)";
const RIGHT = "translateX(112%)";
const COVER_MS = 200;
const LEAVE_MS = 320;
const LAG_MS = 40;
const TITLE = [..."RESONANCE"];

const root = ref<HTMLElement>();
const under = ref<HTMLElement>();
const over = ref<HTMLElement>();
/** Bumped on every cover so the title's letters rise again. */
const take = ref(0);

const done = (list: Animation[]) => Promise.allSettled(list.map((a) => a.finished)).then(() => undefined);
function slide(els: HTMLElement[], from: string, to: string, duration: number): Animation[] {
  return els.map((el, i) =>
    el.animate([{ transform: from }, { transform: to }], { duration, delay: i * LAG_MS, easing: EASE_IN_OUT, fill: "both" }),
  );
}

let held: Animation[] = [];
function hold(list: Animation[]) {
  held.forEach((a) => a.cancel());
  held = list;
  return done(list);
}

/** Bands in, title up. Resolves once the scene is covered. */
function cover(): Promise<void> {
  take.value += 1;
  root.value!.style.visibility = "visible";
  return hold(slide([under.value!, over.value!], LEFT, HOME, COVER_MS));
}

/** Both bands leave to the right, uncovering the board. */
async function leave(): Promise<void> {
  await hold(slide([over.value!, under.value!], HOME, RIGHT, LEAVE_MS));
  root.value!.style.visibility = "hidden";
}

defineExpose({ cover, leave });
</script>

<template>
  <div ref="root" class="bands" aria-hidden="true">
    <div ref="under" class="band under"></div>
    <div ref="over" class="band over">
      <span :key="take" class="title">
        <b class="letters"><i v-for="(c, n) in TITLE" :key="n" :style="{ '--n': n }">{{ c }}</i></b>
        <small>共鸣 ×{{ count }}</small>
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
.band {
  position: absolute;
  top: -2px;
  bottom: -2px;
  left: -8%;
  width: 116%;
  overflow: hidden;
  transform: translateX(-112%);
  will-change: transform;
}
.under {
  background: var(--c-200);
}
.over {
  background: var(--c-500);
}
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
  letter-spacing: 0.01em;
  color: #fff;
  text-shadow: 0 2px 0 rgba(var(--shadow-rgb), 0.08);
}
.letters i {
  display: block;
  font-style: normal;
  animation: letter-rise 420ms var(--ease-spring) calc(60ms + var(--n) * 24ms) both;
}
.title small {
  margin-top: 6px;
  font: 800 var(--fs-title) var(--font);
  color: var(--ink);
  animation: label-in 320ms var(--ease-out) 120ms both;
}

@keyframes letter-rise {
  0% { opacity: 0; transform: translateY(60%) scaleY(1.3); }
  100% { opacity: 1; transform: none; }
}
@keyframes label-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}
</style>
