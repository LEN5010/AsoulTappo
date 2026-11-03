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
.seg { display: flex; gap: 18px; box-shadow: inset 0 -1px 0 var(--line); overflow-x: auto; scrollbar-width: none; }
.seg button {
  position: relative; flex: none; height: 34px; padding: 0 2px; border: none; background: none; cursor: pointer;
  font: inherit; font-size: 13px; font-weight: 600; color: var(--ink-3); white-space: nowrap; transition: color 120ms;
}
.seg button:hover { color: var(--ink); }
.seg button.on { color: var(--ink); }
.seg button.on::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 2px; background: var(--accent); }
.seg small { margin-left: 4px; font-size: 11px; color: var(--ink-3); font-weight: 600; font-variant-numeric: tabular-nums; }
</style>
