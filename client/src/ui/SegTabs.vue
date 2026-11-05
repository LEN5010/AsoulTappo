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
.seg {
  position: relative;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 6px;
  border-radius: var(--radius-s);
  background: var(--surface);
  box-shadow: inset 0 0 0 1.5px var(--line);
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
  border-radius: var(--radius-s);
  background: var(--grad-main);
  box-shadow: var(--glow-s);
  transform-origin: 0 50%;
  will-change: transform;
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
  transition: color var(--dur-base);
}
.seg button + button::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 1.5px;
  background: var(--line-2);
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
.seg button.on {
  color: var(--on-accent);
}
.seg button:disabled {
  opacity: 0.6;
  cursor: default;
}
.seg small {
  font: 800 var(--fs-strong) var(--font-latin);
  opacity: 0.72;
}
/* Underline in place of the orange block. */
.seg.plain {
  border-radius: 0;
  box-shadow: inset 0 -2px 0 var(--line);
}
.plain .thumb {
  border-radius: 0;
  background: var(--grad-main) bottom / 100% 3px no-repeat;
  box-shadow: none;
}
.plain button + button::before {
  display: none;
}
.seg.plain button.on {
  color: var(--ink);
}
.plain small {
  font: 500 var(--fs-label) var(--font);
  color: var(--ink-3);
  opacity: 1;
}
</style>
