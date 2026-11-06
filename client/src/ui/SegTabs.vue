<script setup lang="ts" generic="T extends string">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { reducedMotion } from "../stores/theme";
import { arrowSelect } from "./focus";
import { useSlider } from "./useSlider";

const props = defineProps<{ tabs: { id: T; label: string; count?: number | string }[]; modelValue: T; label?: string; disabled?: boolean; plain?: boolean }>();
defineEmits<{ "update:modelValue": [id: T] }>();

const track = ref<HTMLElement>();
const thumb = ref<HTMLElement>();
useSlider(track, thumb, () => props.modelValue);

// Tabs that do not fit scroll sideways: the wheel drives that, and edges fade while more is hidden.
const moreLeft = ref(false);
const moreRight = ref(false);
function measure() {
  const el = track.value;
  if (!el) return;
  moreLeft.value = el.scrollLeft > 1;
  moreRight.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
}
function onWheel(e: WheelEvent) {
  const el = track.value;
  if (!el || el.scrollWidth <= el.clientWidth || e.deltaX) return;
  e.preventDefault();
  el.scrollLeft += e.deltaY;
}
watch(
  () => props.modelValue,
  () =>
    nextTick(() => {
      const el = track.value;
      const on = el?.querySelector<HTMLElement>(".on");
      if (!el || !on) return;
      el.scrollTo({ left: on.offsetLeft - (el.clientWidth - on.offsetWidth) / 2, behavior: reducedMotion.value ? "auto" : "smooth" });
    }),
);
const observer = new ResizeObserver(measure);
onMounted(() => {
  measure();
  if (track.value) observer.observe(track.value);
});
onBeforeUnmount(() => observer.disconnect());
</script>

<template>
  <div
    ref="track" class="seg" :class="{ plain, 'more-left': moreLeft, 'more-right': moreRight }" role="tablist" :aria-label="label"
    @scroll.passive="measure" @wheel="onWheel" @keydown="arrowSelect($event, track)"
  >
    <i ref="thumb" class="thumb" aria-hidden="true"></i>
    <button
      v-for="t in tabs" :key="t.id" type="button" role="tab" :aria-selected="t.id === modelValue"
      :disabled="disabled" :class="{ on: t.id === modelValue }" @click="$emit('update:modelValue', t.id)"
    >
      <span>{{ t.label }}</span>
      <small v-if="t.count !== undefined">{{ t.count }}</small>
    </button>
  </div>
</template>

<style scoped>
/* A row of joined keys. The lip is a bottom border rather than a shadow, so the edge fades of a
 * scrolling row cannot cut it off. The picked key is the sliding thumb, latched in coral. */
.seg {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0;
  padding: 0 2px;
  border-radius: var(--radius-key);
  border-bottom: 3px solid var(--c-200);
  background: linear-gradient(180deg, #fff, var(--key-white-shade));
  box-shadow: 0 4px 8px -3px rgba(var(--shadow-rgb), 0.25);
  overflow-x: auto;
  scrollbar-width: none;
  flex: none;
}
.seg::-webkit-scrollbar {
  display: none;
}
.seg.more-right {
  mask-image: linear-gradient(90deg, #000 calc(100% - 36px), transparent);
}
.seg.more-left {
  mask-image: linear-gradient(270deg, #000 calc(100% - 36px), transparent);
}
.seg.more-left.more-right {
  mask-image: linear-gradient(90deg, transparent, #000 36px, #000 calc(100% - 36px), transparent);
}
.thumb {
  position: absolute;
  left: 0;
  top: 0;
  opacity: 0;
  transform-origin: 0 50%;
  will-change: transform;
}
/* The face fills its key. The row's 2px padding is the only side gap, so an 8px radius
 * sits concentric in the 10px track. 2px above and below keeps it off the track lip. */
.thumb::before {
  content: "";
  position: absolute;
  inset: 2px 0;
  border-radius: var(--radius-key-s);
  background: var(--c-500);
  box-shadow: 0 1px 0 var(--c-600);
}
.seg button {
  position: relative;
  flex: 1 0 auto;
  min-width: 64px;
  height: 32px;
  padding: 0 14px;
  box-sizing: border-box;
  border: 0;
  background: transparent;
  cursor: pointer;
  font: 800 var(--fs-strong) var(--font);
  color: var(--ink-2);
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: color var(--dur-base), transform var(--dur-press) ease-out;
}
.seg button + button::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 1px;
  background: var(--c-200);
  transition: opacity var(--dur-fast);
}
.seg button.on::before,
.seg button.on + button::before {
  opacity: 0;
}
.seg button:focus-visible {
  outline-offset: -4px;
}
.seg button:hover:not(:disabled):not(.on) {
  color: var(--ink);
}
.seg button:active:not(:disabled):not(.on) {
  transform: translateY(1px);
}
.seg button.on {
  color: var(--ink);
}
.seg button:disabled {
  opacity: 0.6;
  cursor: default;
}
.seg small {
  font: 800 var(--fs-strong) var(--font-latin);
  opacity: 0.72;
}
/* Underline tabs, for series: a coral bar under the picked one. */
.seg.plain {
  padding: 0 6px;
  border-radius: 0;
  border-bottom: 0;
  background: none;
  box-shadow: inset 0 -2px 0 var(--c-100);
}
.plain .thumb::before {
  inset: auto 0 0;
  height: 3px;
  border-radius: 0;
  background: var(--c-500);
  box-shadow: none;
}
.plain button + button::before {
  display: none;
}
.plain small {
  font: 500 var(--fs-label) var(--font);
  color: var(--ink-3);
  opacity: 1;
}
</style>
