<script setup lang="ts">
// Two slanted bands that sweep out from behind the sidebar. cover() ends with the page
// hidden, which is when MainPanel swaps it; reveal() carries on off to the right.
import { ref } from "vue";

defineProps<{ title: string; label: string }>();

const SKEW = "skewX(-8deg)";
const LEFT = `translateX(-112%) ${SKEW}`;
const HOME = `translateX(0) ${SKEW}`;
const RIGHT = `translateX(112%) ${SKEW}`;
const EASE = "cubic-bezier(0.7, 0, 0.2, 1)";
const COVER_MS = 255;
const REVEAL_MS = 315;
const LAG_MS = 52;

const root = ref<HTMLElement>();
const under = ref<HTMLElement>();
const over = ref<HTMLElement>();
let held: Animation[] = [];
let revealing = false;
let rewound = false;

const show = (visible: boolean) => {
  if (root.value) root.value.style.visibility = visible ? "visible" : "hidden";
};
const settled = (list: Animation[]) => Promise.allSettled(list.map((a) => a.finished));
function sweep(first: HTMLElement, second: HTMLElement, from: string, to: string, duration: number): Animation[] {
  return [first, second].map((el, i) =>
    el.animate([{ transform: from }, { transform: to }], { duration, delay: i * LAG_MS, easing: EASE, fill: "both" }),
  );
}

/** Start out covered, for the panel's opening frame. */
function hold() {
  show(true);
  held = [under.value!, over.value!].map((el) => el.animate([{ transform: HOME }], { duration: 0, fill: "forwards" }));
}

async function cover() {
  show(true);
  held = sweep(under.value!, over.value!, LEFT, HOME, COVER_MS);
  await settled(held);
}

/** Resolves true when rewind() sent the bands back, which leaves the page covered again. */
async function reveal(): Promise<boolean> {
  const previous = held;
  held = sweep(over.value!, under.value!, HOME, RIGHT, REVEAL_MS);
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
      <span class="title">
        <b>{{ title }}</b>
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
  transform: translateX(-112%) skewX(-8deg);
  will-change: transform;
}
.under {
  background: var(--accent-soft);
}
.over {
  background: var(--accent);
  overflow: hidden;
}
.over::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  right: 16%;
  width: 22%;
  background: rgba(255, 255, 255, 0.14);
}
.title {
  position: absolute;
  left: calc(50% + 90px);
  top: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translate(-50%, -50%) skewX(8deg);
  white-space: nowrap;
}
.title b {
  font: italic 800 112px/0.9 var(--font-latin);
  letter-spacing: 0.01em;
  color: #fff;
}
.title small {
  margin-top: 6px;
  font: 24px var(--font-display);
  color: var(--ink);
}
</style>
