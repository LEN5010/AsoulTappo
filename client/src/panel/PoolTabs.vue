<script setup lang="ts">
// The pools to draw from, where a stage's eyebrow sits: the standing pool first, then each limited pool with what is
// left of it. Small keys: the picked one is latched in coral, a limited one wears the pearl lip of its material.
import { reducedMotion } from "../stores/theme";
import { arrowSelect } from "../ui/focus";
import Icon from "../ui/Icon.vue";

defineProps<{ pools: { id: string; name: string; left?: string }[]; modelValue: string; disabled?: boolean }>();
defineEmits<{ "update:modelValue": [id: string] }>();
</script>

<template>
  <div class="pool-tabs" :class="{ calm: reducedMotion }" role="tablist" aria-label="卡池" @keydown="arrowSelect($event, $el)">
    <button
      v-for="p in pools" :key="p.id" type="button" role="tab" class="pool-tab" :class="{ on: p.id === modelValue, limited: !!p.left }"
      :aria-selected="p.id === modelValue" :disabled="disabled" @click="$emit('update:modelValue', p.id)"
    >
      <span>{{ p.name }}</span>
      <small v-if="p.left"><Icon name="clock" :size="11" />{{ p.left }}</small>
    </button>
  </div>
</template>

<style scoped>
.pool-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 7px;
}
/* Keycap with a separate rounded lip plate (::before) under its face (::after), so gradient pearl lips keep full
 * corner rounding and pressing never moves the bottom edge or reflows layout. */
.pool-tab {
  --face: linear-gradient(180deg, #fff, var(--key-white-shade));
  --face-inset: inset 0 1px 0 rgba(255, 255, 255, 0.8);
  --lip: var(--c-200);
  --key-lip-h: 3px;
  --key-y: 0px;
  --lip-shadow: 0 4px 8px -3px rgba(var(--c-900-rgb), 0.24);
  position: relative;
  isolation: isolate;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 30px;
  margin-bottom: 3px;
  padding: 0 12px;
  box-sizing: border-box;
  border: 0;
  border-radius: var(--radius-key-s);
  background: none;
  color: var(--ink-2);
  font: 800 var(--fs-body)/1 var(--font);
  white-space: nowrap;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transform: translateY(var(--key-y));
  transition:
    transform var(--dur-release) var(--ease-spring),
    color var(--dur-fast);
}
.pool-tab.limited {
  padding-right: 6px;
}
.pool-tab::before,
.pool-tab::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
}
.pool-tab::before {
  z-index: -2;
  background: var(--lip);
  box-shadow: var(--lip-shadow);
  transform: translateY(var(--key-lip-h));
  transition:
    transform var(--dur-release) var(--ease-spring),
    box-shadow var(--dur-release) var(--ease-spring);
}
.pool-tab::after {
  z-index: -1;
  background: var(--face);
  box-shadow: var(--face-inset);
}
.pool-tab:hover:not(:disabled):not(.on) {
  --face: #fff;
  --key-y: -1px;
  color: var(--ink);
}
/* Latched: sits partway down on a 1px lip sliver. */
.pool-tab.on {
  --face: linear-gradient(180deg, var(--c-400), var(--c-500));
  --face-inset: inset 0 1px 0 rgba(255, 255, 255, 0.36);
  --lip: var(--c-600);
  --key-y: 2px;
  --key-lip-h: 1px;
  --lip-shadow: 0 2px 5px -2px rgba(var(--c-900-rgb), 0.22);
  color: var(--ink);
  cursor: default;
}
.pool-tab:active:not(:disabled):not(.on) {
  --key-y: 3px;
  --key-lip-h: 0px;
  --lip-shadow: 0 1px 2px -1px rgba(var(--c-900-rgb), 0.2);
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
.pool-tab:active:not(:disabled):not(.on)::before {
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
.pool-tab:disabled:not(.on) {
  --face: var(--c-100);
  --face-inset: none;
  --lip: transparent;
  --key-y: 0px;
  --key-lip-h: 0px;
  --lip-shadow: none;
  color: var(--ink-3);
  cursor: default;
}
/* Countdown capsule inside a limited pool key. */
.pool-tab small {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 20px;
  padding: 0 7px 0 5px;
  box-sizing: border-box;
  border-radius: 5px;
  background: color-mix(in srgb, var(--holo-lilac) 24%, var(--c-50));
  color: var(--night);
  font: 800 var(--fs-caption)/1 var(--font);
  font-variant-numeric: tabular-nums;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.pool-tab small :deep(svg) {
  color: var(--pearl-deep);
  transition: color var(--dur-fast);
}
/* A limited pool: the pearl sheen drifts along its rounded lip, and fills the face once latched. */
.pool-tab.limited:not(.on):not(:disabled) {
  --face: linear-gradient(180deg, #fff 36%, color-mix(in srgb, var(--holo-lilac) 14%, #fff));
  --lip: var(--grad-pearl);
  color: var(--night);
}
.pool-tab.limited:not(.on):not(:disabled):hover {
  --face: linear-gradient(180deg, #fff 55%, color-mix(in srgb, var(--holo-pink) 14%, #fff));
}
.pool-tab.limited:not(.on):not(:disabled)::before {
  background-size: 220% 100%;
  animation: pearl-lip 7s var(--ease-in-out) infinite alternate;
}
.calm .pool-tab.limited::before {
  animation: none;
}
.pool-tab.limited.on {
  --face: linear-gradient(115deg, color-mix(in srgb, var(--holo-pink) 62%, #fff), color-mix(in srgb, var(--holo-lilac) 72%, #fff) 44%,
    color-mix(in srgb, var(--holo-mint) 62%, #fff) 78%, color-mix(in srgb, var(--holo-cream) 74%, #fff));
  --face-inset: inset 0 1px 0 rgba(255, 255, 255, 0.68);
  --lip: var(--pearl-deep);
  color: var(--night);
}
.pool-tab.limited.on small {
  background: var(--night);
  color: #fff;
}
.pool-tab.limited.on small :deep(svg) {
  color: var(--holo-lilac);
}
.pool-tab:disabled:not(.on) small {
  background: color-mix(in srgb, var(--c-200) 45%, var(--c-100));
  color: var(--ink-3);
}
.pool-tab:disabled:not(.on) small :deep(svg) {
  color: var(--ink-3);
}
@keyframes pearl-lip {
  from { background-position: 0% 50%; }
  to { background-position: 100% 50%; }
}
</style>
