<script setup lang="ts">
// The tomato timer's countdown over the own pet's monitor (src/stores/pomodoro.ts); a press opens the timer's page.
import { clockText } from "../pomodoro";
import { pomodoro, pomodoroLeft } from "../stores/pomodoro";
import Icon from "../ui/Icon.vue";

defineEmits<{ open: [] }>();
</script>

<template>
  <button
    v-if="pomodoro" type="button" class="pomo" :class="pomodoro.phase" data-hit data-no-drag
    :aria-label="pomodoro.phase === 'focus' ? '番茄钟' : '休息'" @click="$emit('open')"
  >
    <Icon :name="pomodoro.phase === 'focus' ? 'tomato' : 'cup'" :size="14" />
    <span>{{ clockText(pomodoroLeft) }}</span>
  </button>
</template>

<style scoped>
/* A small paper tag: the tomato and the minutes left; the rest shows a cup instead. */
.pomo {
  position: absolute;
  z-index: 2;
  /* Placed by its centre: the time is shorter in the rest than in the focus. */
  translate: -50% 0;
  display: flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  padding: 0 8px 0 6px;
  border: none;
  border-radius: 11px;
  background: var(--surface);
  color: var(--ink);
  box-shadow: var(--shadow-key);
  font: 700 12px/1 var(--font);
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}
.pomo .icon { color: var(--c-600); }
.pomo.rest { color: var(--ink-2); }
.pomo:hover { box-shadow: var(--shadow-key), 0 0 0 2px rgba(var(--c-500-rgb), 0.5); }
</style>
