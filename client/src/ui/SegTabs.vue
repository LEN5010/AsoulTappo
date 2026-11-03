<script setup lang="ts" generic="T extends string">
defineProps<{ tabs: { id: T; label: string; count?: number }[]; modelValue: T; label?: string; disabled?: boolean }>();
defineEmits<{ "update:modelValue": [id: T] }>();
</script>

<template>
  <div class="seg" role="tablist" :aria-label="label">
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
/* Full-width rounded capsule track with puffy #FC966E pill active tab, matching WuwaTappo */
.seg {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 5px;
  border-radius: 999px;
  background: var(--paper-2);
  box-shadow: inset 0 2px 3px rgba(120, 75, 45, 0.08);
  overflow-x: auto;
  scrollbar-width: none;
  flex: none;
}
.seg::-webkit-scrollbar {
  display: none;
}
.seg button {
  position: relative;
  flex: 1 0 auto;
  min-width: 64px;
  height: 28px;
  padding: 0 12px;
  box-sizing: border-box;
  border-radius: 999px;
  border: 1.5px solid transparent;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 12.5px;
  font-weight: 800;
  color: var(--ink-2);
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  transition: background 140ms, color 140ms, transform 100ms, box-shadow 140ms;
}
.seg button:hover:not(:disabled):not(.on) {
  color: var(--ink);
  background: rgba(255, 255, 255, 0.38);
}
.seg button.on {
  background: linear-gradient(180deg, #FFB596 0%, var(--accent) 100%);
  border-color: var(--accent-deep);
  color: var(--on-accent);
  box-shadow: 0 2px 0 var(--accent-deep), inset 0 1.5px 0 rgba(255, 255, 255, 0.5);
}
.seg button:disabled {
  opacity: 0.6;
  cursor: default;
}
.seg small {
  font-size: 11px;
  font-weight: 700;
  opacity: 0.78;
  font-variant-numeric: tabular-nums;
}
</style>
