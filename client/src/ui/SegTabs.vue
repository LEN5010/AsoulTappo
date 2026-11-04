<script setup lang="ts" generic="T extends string">
import { ref } from "vue";
import { useSlider } from "./useSlider";

const props = defineProps<{ tabs: { id: T; label: string; count?: number }[]; modelValue: T; label?: string; disabled?: boolean }>();
defineEmits<{ "update:modelValue": [id: T] }>();

const track = ref<HTMLElement>();
const thumb = ref<HTMLElement>();
useSlider(track, thumb, () => props.modelValue);
</script>

<template>
  <div ref="track" class="seg" role="tablist" :aria-label="label">
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
  background: var(--surface);
  box-shadow: inset 0 -2px 0 var(--line-2);
  overflow-x: auto;
  scrollbar-width: none;
  flex: none;
}
.seg::-webkit-scrollbar {
  display: none;
}
.thumb {
  position: absolute;
  left: 0;
  top: 0;
  opacity: 0;
  background: var(--accent);
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
  font: 800 14px var(--font);
  color: var(--ink-2);
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: color 180ms;
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
  font: italic 800 14px var(--font-latin);
  opacity: 0.72;
}
</style>
