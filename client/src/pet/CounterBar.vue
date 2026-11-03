<script setup lang="ts">
import Icon from "../ui/Icon.vue";

defineProps<{ count: number; view: "today" | "total"; width: number; quickOpen: boolean }>();
defineEmits<{ toggleView: []; quick: []; menu: [] }>();
const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <div class="bar" :style="{ width: `${width}px` }">
    <button type="button" class="count" :title="view === 'today' ? '今日敲击，点击切换累计' : '累计敲击，点击切换今日'" @click="$emit('toggleView')">
      <b>{{ fmt(count) }}</b><small>{{ view === "today" ? "今日" : "累计" }}</small>
    </button>
    <slot />
    <button type="button" class="round spark" :class="{ on: quickOpen }" title="发表情" aria-label="发表情" @click="$emit('quick')">
      <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4z" fill="currentColor" /></svg>
    </button>
    <button type="button" class="round" title="打开面板" aria-label="打开面板" @click="$emit('menu')"><Icon name="menu" :size="16" /></button>
  </div>
</template>

<style scoped>
.bar {
  position: relative; display: flex; align-items: center; gap: 6px; height: 34px; margin-top: -4px; padding: 0 4px 0 6px; box-sizing: border-box;
  border-radius: 999px; background: rgba(255, 252, 249, 0.96); box-shadow: 0 4px 14px rgba(50, 20, 30, 0.22), inset 0 0 0 1.5px rgba(var(--accent-rgb), 0.35);
  font-family: var(--font); color: var(--ink);
}
.count { flex: 1; min-width: 0; display: flex; align-items: baseline; gap: 6px; padding: 0 8px; height: 100%; border: none; background: none; cursor: pointer; font: inherit; color: inherit; text-align: left; }
.count b { font-size: 17px; font-weight: 800; font-variant-numeric: tabular-nums; letter-spacing: 0.01em; }
.count small { font-size: 11px; color: var(--ink-3); font-weight: 600; }
.round { width: 26px; height: 26px; flex: none; border-radius: 50%; border: none; display: grid; place-items: center; cursor: pointer; background: var(--paper-2); color: var(--ink-2); transition: transform 120ms; }
.round:hover { transform: scale(1.08); color: var(--ink); }
.spark { background: var(--accent); color: var(--on-accent); box-shadow: 0 2px 6px rgba(var(--accent-rgb), 0.45); }
.spark.on { transform: rotate(45deg); }
</style>
