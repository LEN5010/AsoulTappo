<script setup lang="ts">
// The pools to draw from, where a stage's eyebrow sits: the standing pool first, then each limited pool with what is
// left of it. Small keys: the picked one is latched in coral, a limited one wears the pearl lip of its material.
import { arrowSelect } from "../ui/focus";
import Icon from "../ui/Icon.vue";

defineProps<{ pools: { id: string; name: string; left?: string }[]; modelValue: string; disabled?: boolean }>();
defineEmits<{ "update:modelValue": [id: string] }>();
</script>

<template>
  <div class="pool-tabs" role="tablist" aria-label="卡池" @keydown="arrowSelect($event, $el)">
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
  margin-bottom: 10px;
}
.pool-tab {
  --lip: var(--c-200);
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 30px;
  padding: 0 12px;
  border: 0;
  border-bottom: 3px solid var(--lip);
  border-radius: var(--radius-key-s);
  background: linear-gradient(180deg, #fff, var(--key-white-shade));
  box-shadow: 0 4px 8px -4px rgba(var(--shadow-rgb), 0.3);
  color: var(--ink-2);
  font: 800 var(--fs-body)/1 var(--font);
  white-space: nowrap;
  cursor: pointer;
  transition: transform var(--dur-release) var(--ease-spring), border-color var(--dur-fast), color var(--dur-fast);
}
.pool-tab:hover:not(:disabled):not(.on) {
  color: var(--ink);
  transform: translateY(-1px);
}
.pool-tab:active:not(:disabled):not(.on) {
  transform: translateY(2px);
  border-bottom-width: 1px;
  margin-bottom: 2px;
  transition-duration: var(--dur-press);
}
.pool-tab.on {
  --lip: var(--c-600);
  background: var(--c-500);
  color: var(--ink);
  cursor: default;
}
.pool-tab:disabled:not(.on) {
  opacity: 0.6;
  cursor: default;
}
.pool-tab small {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-caption)/1 var(--font);
  color: var(--ink-3);
}
/* A limited pool: the pearl sheen drifts along its lip, and stays on the key once it is picked. */
.pool-tab.limited {
  --lip: var(--pearl);
  border-image: linear-gradient(100deg, var(--holo-pink), var(--holo-lilac), var(--holo-mint), var(--holo-cream)) 1;
  border-image-width: 0 0 3px;
  border-radius: var(--radius-key-s) var(--radius-key-s) 2px 2px;
}
.pool-tab.limited.on {
  background: linear-gradient(115deg, color-mix(in srgb, var(--holo-pink) 70%, #fff), color-mix(in srgb, var(--holo-lilac) 78%, #fff) 45%,
    color-mix(in srgb, var(--holo-mint) 70%, #fff) 80%, color-mix(in srgb, var(--holo-cream) 80%, #fff));
  border-image: none;
  --lip: var(--pearl-deep);
  border-radius: var(--radius-key-s);
}
.pool-tab.limited.on small {
  color: var(--night);
}
</style>
