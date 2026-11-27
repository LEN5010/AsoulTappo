<script lang="ts">
// Shared timestamp across stage transitions (<Transition mode="out-in"> swaps PoolStage and BannerStage),
// so keyboard ArrowLeft/ArrowRight switching restores focus onto the newly mounted active tab seamlessly.
let keySwitchAt = 0;
</script>

<script setup lang="ts">
// The pools to draw from, where a stage's eyebrow sits: the standing pool first, then each limited pool. Small tab keys
// with the pools' names alone, so four keep to one row: the picked one is latched in coral, a limited one wears the
// pearl lip of its material, and what is left of a limited pool shows on its stage (BannerStage.vue).
// On a series' key visual they are clear keys of its dark and the picked one is white (`.on-poster` in ui/tokens.css).
import { nextTick, onMounted, ref, watch } from "vue";
import { reducedMotion } from "../stores/theme";

const props = defineProps<{
  /** `left` (what is left of it) marks a limited pool; `fresh` marks a pool with something new on sale. */
  pools: { id: string; name: string; left?: string; fresh?: boolean }[];
  modelValue: string;
  disabled?: boolean;
  /** What they stand on: the page's paper, or a series' key visual. */
  ground?: "paper" | "poster";
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
      class="pool-tab ui-tab small" :class="{ on: p.id === modelValue, limited: !!p.left, 'on-poster': ground === 'poster' }"
      :aria-selected="p.id === modelValue"
      :tabindex="p.id === modelValue ? 0 : -1"
      :disabled="disabled"
      @pointerenter="p.id !== modelValue && emit('near', p.id)"
      @click="p.id !== modelValue && emit('update:modelValue', p.id)"
    >
      <span>{{ p.name }}</span>
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
/* On a key visual a limited pool's key is as clear as the others. */
.pool-tab.limited.on-poster:not(.on):not(:disabled) {
  --face: var(--poster-face);
  --lip: var(--poster-lip);
  color: #fff;
}
.pool-tab.limited.on {
  --face: linear-gradient(115deg, color-mix(in srgb, var(--holo-pink) 62%, #fff), color-mix(in srgb, var(--holo-lilac) 72%, #fff) 44%,
    color-mix(in srgb, var(--holo-mint) 62%, #fff) 78%, color-mix(in srgb, var(--holo-cream) 74%, #fff));
  --face-inset: inset 0 1px 0 rgba(255, 255, 255, 0.68);
  --lip: var(--pearl);
  color: var(--ink);
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
