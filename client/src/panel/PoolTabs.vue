<script lang="ts">
// Shared timestamp across stage transitions (<Transition mode="out-in"> swaps PoolStage and BannerStage),
// so keyboard ArrowLeft/ArrowRight switching restores focus onto the newly mounted active tab seamlessly.
let keySwitchAt = 0;
</script>

<script setup lang="ts">
// The pools to draw from, where a stage's eyebrow sits: the standing pool first, then each limited pool with what is
// left of it. Small tab keys: the picked one is latched in coral, a limited one wears the pearl lip of its material.
import { nextTick, onMounted, ref, watch } from "vue";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";

const props = defineProps<{
  /** `fresh` marks a pool with something new on sale. */
  pools: { id: string; name: string; left?: string; fresh?: boolean }[];
  modelValue: string;
  disabled?: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [id: string];
  /** The pointer is on a pool that is not on show. */
  near: [id: string];
}>();

const root = ref<HTMLElement>();

function focusActive() {
  root.value?.querySelector<HTMLButtonElement>(".pool-tab.on")?.focus({ preventScroll: true });
}

function onKey(e: KeyboardEvent) {
  const n = props.pools.length;
  if (props.disabled || n < 2) return;
  const cur = Math.max(0, props.pools.findIndex((p) => p.id === props.modelValue));
  let next = -1;
  if (e.key === "ArrowRight") next = (cur + 1) % n;
  else if (e.key === "ArrowLeft") next = (cur - 1 + n) % n;
  else if (e.key === "Home") next = 0;
  else if (e.key === "End") next = n - 1;
  if (next < 0) return;
  e.preventDefault();
  const target = props.pools[next]!;
  if (target.id === props.modelValue) {
    focusActive();
    return;
  }
  keySwitchAt = performance.now();
  emit("update:modelValue", target.id);
}

watch(() => props.modelValue, () => {
  if (performance.now() - keySwitchAt < 800) void nextTick(focusActive);
});

onMounted(() => {
  if (performance.now() - keySwitchAt < 800) focusActive();
});
</script>

<template>
  <div ref="root" class="pool-tabs" :class="{ calm: reducedMotion }" role="tablist" aria-label="卡池" @keydown="onKey">
    <button
      v-for="p in pools" :key="p.id" type="button" role="tab"
      class="pool-tab ui-tab small" :class="{ on: p.id === modelValue, limited: !!p.left }"
      :aria-selected="p.id === modelValue"
      :tabindex="p.id === modelValue ? 0 : -1"
      :disabled="disabled"
      @pointerenter="p.id !== modelValue && emit('near', p.id)"
      @click="p.id !== modelValue && emit('update:modelValue', p.id)"
    >
      <span>{{ p.name }}</span>
      <small v-if="p.left"><Icon name="clock" :size="11" />{{ p.left }}</small>
      <i v-if="p.fresh && p.id !== modelValue" class="fresh">NEW</i>
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
/* The tab key at its small size (.ui-tab.small in ui/tokens.css); its lip plate keeps a pearl gradient's corners. */
.pool-tab {
  margin-bottom: 3px;
}
.pool-tab.limited {
  padding-right: 6px;
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
  --lip: var(--pearl);
  color: var(--ink);
}
.pool-tab.limited.on small {
  background: rgba(255, 255, 255, 0.78);
  color: var(--ink);
}
.pool-tab.limited.on small :deep(svg) {
  color: var(--pearl-deep);
}
.pool-tab:disabled:not(.on) small {
  background: color-mix(in srgb, var(--c-200) 45%, var(--c-100));
  color: var(--ink-3);
}
.pool-tab:disabled:not(.on) small :deep(svg) {
  color: var(--ink-3);
}
.fresh {
  position: absolute;
  right: -7px;
  top: -8px;
  z-index: 1;
  padding: 2px 5px;
  border-radius: 5px;
  background: var(--c-700);
  color: #fff;
  font: 800 10px/1.1 var(--font-latin);
  font-style: normal;
  letter-spacing: 0.04em;
}
@keyframes pearl-lip {
  from { background-position: 0% 50%; }
  to { background-position: 100% 50%; }
}
</style>
