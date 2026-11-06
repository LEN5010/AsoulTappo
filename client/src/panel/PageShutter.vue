<script setup lang="ts">
// Two bands that sweep out from behind the sidebar. cover() ends with the page
// hidden, which is when MainPanel swaps it; reveal() carries on off to the right.
import { ref } from "vue";
import { EASE_IN_OUT as EASE } from "../ui/motion";

defineProps<{ title: string; label: string }>();

const LEFT = "translateX(-112%)";
const HOME = "translateX(0)";
const RIGHT = "translateX(112%)";
/** Opening the panel gets the full sweep; everyday page turns stay out of the way. */
const OPEN = { revealMs: 315, lagMs: 52 };
const TURN = { revealMs: 455, lagMs: 36 };
const COVER_MS = 395;

const root = ref<HTMLElement>();
const under = ref<HTMLElement>();
const over = ref<HTMLElement>();
let held: Animation[] = [];
/** Bumped on every cover so the title's letters rise again. */
const take = ref(0);
let revealing = false;
let rewound = false;

const show = (visible: boolean) => {
  if (root.value) root.value.style.visibility = visible ? "visible" : "hidden";
};
const settled = (list: Animation[]) => Promise.allSettled(list.map((a) => a.finished));
function sweep(first: HTMLElement, second: HTMLElement, from: string, to: string, duration: number, lag: number): Animation[] {
  return [first, second].map((el, i) =>
    el.animate([{ transform: from }, { transform: to }], { duration, delay: i * lag, easing: EASE, fill: "both" }),
  );
}

/** Start out covered, for the panel's opening frame. */
function hold() {
  take.value++;
  show(true);
  held = [under.value!, over.value!].map((el) => el.animate([{ transform: HOME }], { duration: 0, fill: "forwards" }));
}

async function cover() {
  take.value++;
  show(true);
  held = sweep(under.value!, over.value!, LEFT, HOME, COVER_MS, TURN.lagMs);
  await settled(held);
}

/** Resolves true when rewind() sent the bands back, which leaves the page covered again. */
async function reveal(opening: boolean): Promise<boolean> {
  const { revealMs, lagMs } = opening ? OPEN : TURN;
  const previous = held;
  held = sweep(over.value!, under.value!, HOME, RIGHT, revealMs, lagMs);
  previous.forEach((a) => a.cancel());
  revealing = true;
  rewound = false;
  await settled(held);
  revealing = false;
  if (rewound) return true;
  held.forEach((a) => a.cancel());
  held = [];
  show(false);
  return false;
}

function rewind() {
  if (!revealing || rewound) return;
  rewound = true;
  held.forEach((a) => a.reverse());
}

defineExpose({ hold, cover, reveal, rewind });
</script>

<template>
  <div ref="root" class="shutter" aria-hidden="true">
    <div ref="under" class="band under"></div>
    <div ref="over" class="band over">
      <span :key="take" class="title">
        <b><i v-for="(c, n) in [...title]" :key="n" :style="{ '--n': n }">{{ c }}</i></b>
        <small>{{ label }}</small>
      </span>
    </div>
  </div>
</template>

<style scoped>
.shutter {
  position: absolute;
  inset: 0;
  z-index: 1;
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
  transform: translateX(-112%);
  will-change: transform;
}
.under {
  background: var(--c-200);
}
.over {
  background: var(--c-500);
  overflow: hidden;
}
.title {
  position: absolute;
  left: calc(50% + var(--side-w) / 2);
  top: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translate(-50%, -50%);
  white-space: nowrap;
}
.title b {
  display: flex;
  font: 800 112px/0.9 var(--font-latin);
  letter-spacing: 0.01em;
  color: #fff;
}
/* Letter by letter, the same rise as the draw's opening title. */
.title i {
  display: block;
  font-style: normal;
  animation: letter-rise 420ms var(--ease-spring) calc(60ms + var(--n) * 24ms) both;
}
.title small {
  margin-top: 6px;
  font: 800 var(--fs-title) var(--font);
  color: var(--ink);
}
@keyframes letter-rise {
  0% { opacity: 0; transform: translateY(60%) scaleY(1.3); }
  100% { opacity: 1; transform: none; }
}
</style>
