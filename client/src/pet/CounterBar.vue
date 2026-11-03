<script setup lang="ts">
import Icon from "../ui/Icon.vue";

defineProps<{ count: number; view: "today" | "total"; width: number; quickOpen: boolean }>();
defineEmits<{ toggleView: []; quick: []; menu: [] }>();
const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <div class="bar" :style="{ width: `${width}px` }">
    <button type="button" class="count" :title="view === 'today' ? '今日敲击，点击切换累计' : '累计敲击，点击切换今日'" @click="$emit('toggleView')">
      <span><b>{{ fmt(count) }}</b><small>{{ view === "today" ? "今日" : "累计" }}</small></span>
    </button>
    <slot />
    <button type="button" class="round spark" :class="{ on: quickOpen }" title="发表情" aria-label="发表情" @click="$emit('quick')">
      <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4z" fill="currentColor" /></svg>
    </button>
    <button type="button" class="round" title="打开面板" aria-label="打开面板" @click="$emit('menu')"><Icon name="menu" :size="17" /></button>
  </div>
</template>

<style scoped>
.bar {
  position: relative; display: flex; align-items: center; gap: 4px; height: 36px; margin-top: -4px; padding: 0 4px 0 0; box-sizing: border-box;
  border-radius: var(--r-l); background: rgba(252, 251, 250, 0.98); border: 1px solid var(--line-2); box-shadow: 0 4px 12px rgba(43, 35, 38, 0.14);
  font-family: var(--font); color: var(--ink);
}
.count { flex: 1; min-width: 0; align-self: stretch; display: flex; align-items: center; padding: 0 0 0 12px; border: none; border-radius: var(--r-l) 0 0 var(--r-l); background: none; cursor: pointer; font: inherit; color: inherit; }
/* number and unit share a baseline; the pair is centered in the bar */
.count span { display: inline-flex; align-items: baseline; gap: 5px; line-height: 1; padding-top: 1px; }
.count b { font-size: 17px; font-weight: 800; font-variant-numeric: tabular-nums; }
.count small { font-size: 11px; font-weight: 700; color: var(--ink-3); }
.round {
  width: 28px; height: 28px; flex: none; border-radius: var(--r-m); border: none; display: grid; place-items: center; cursor: pointer;
  background: var(--paper-2); color: var(--ink-2); transition: background 150ms, color 150ms, transform 150ms;
}
.round:hover { color: var(--ink); background: var(--paper-3); }
.spark { background: rgba(var(--accent-rgb), 0.14); color: var(--accent); }
.spark:hover { background: rgba(var(--accent-rgb), 0.24); color: var(--accent); }
.spark.on { background: var(--accent); color: var(--on-accent); }
</style>
