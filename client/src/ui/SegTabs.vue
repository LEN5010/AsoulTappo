<script setup lang="ts" generic="T extends string">
defineProps<{ tabs: { id: T; label: string; count?: number }[]; modelValue: T; label?: string }>();
defineEmits<{ "update:modelValue": [id: T] }>();
</script>

<template>
  <div class="seg" role="tablist" :aria-label="label">
    <button
      v-for="t in tabs" :key="t.id" type="button" role="tab" :aria-selected="t.id === modelValue"
      :class="{ on: t.id === modelValue }" @click="$emit('update:modelValue', t.id)"
    >
      {{ t.label }}<small v-if="t.count !== undefined">{{ t.count }}</small>
    </button>
  </div>
</template>

<style scoped>
.seg { display: flex; gap: 2px; padding: 4px; border-radius: 999px; background: var(--paper-2); box-shadow: inset 0 1px 2px rgba(70, 35, 45, 0.06); }
.seg button {
  flex: 1; min-width: 0; height: 32px; border: none; border-radius: 999px; background: none; cursor: pointer;
  font: inherit; font-size: 13px; font-weight: 600; color: var(--ink-2); white-space: nowrap; transition: background 150ms, color 150ms;
}
.seg button:hover { color: var(--ink); }
.seg button.on { background: #fff; color: var(--ink); box-shadow: 0 2px 6px rgba(70, 35, 45, 0.12), inset 0 -2px 0 var(--accent); }
.seg small { margin-left: 4px; font-size: 11px; color: var(--ink-3); font-weight: 600; }
</style>
