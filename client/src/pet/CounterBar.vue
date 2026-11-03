<script setup lang="ts">
import Icon from "../ui/Icon.vue";

defineProps<{ count: number; view: "today" | "total"; width: number; quickOpen: boolean }>();
defineEmits<{ toggleView: []; quick: []; menu: [] }>();
const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <div class="bar" :style="{ width: `${width}px` }">
    <button
      type="button" class="count"
      :title="view === 'today' ? '今日敲击，点击切换累计' : '累计敲击，点击切换今日'"
      @click="$emit('toggleView')"
    >
      <span><b>{{ fmt(count) }}</b><small>{{ view === "today" ? "今日" : "累计" }}</small></span>
    </button>
    <slot />
    <button type="button" class="round spark" :class="{ on: quickOpen }" title="发表情" aria-label="发表情" @click="$emit('quick')">
      <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 2.5l2.5 7L21.5 12l-7 2.5L12 21.5l-2.5-7L2.5 12l7-2.5z" fill="currentColor" />
      </svg>
    </button>
    <button type="button" class="round" title="打开面板" aria-label="打开面板" @click="$emit('menu')">
      <Icon name="menu" :size="15" />
    </button>
  </div>
</template>

<style scoped>
.bar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 5px;
  height: 38px;
  margin-top: -4px;
  padding: 0 4px 0 0;
  box-sizing: border-box;
  border-radius: 999px;
  background: rgba(253, 244, 231, 0.98);
  border: 2px solid var(--tile-border);
  box-shadow: 0 3px 0 var(--tile-lip), 0 6px 14px rgba(72, 38, 20, 0.16);
  font-family: var(--font);
  color: var(--ink);
}
.count {
  flex: 1;
  min-width: 0;
  align-self: stretch;
  display: flex;
  align-items: center;
  padding: 0 0 0 14px;
  border: none;
  border-radius: 999px 0 0 999px;
  background: none;
  cursor: pointer;
  font: inherit;
  color: inherit;
}
.count span {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  line-height: 1;
  padding-top: 1px;
}
.count b {
  font-size: 17px;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
}
.count small {
  font-size: 11px;
  font-weight: 800;
  color: var(--ink-2);
}
.round {
  width: 26px;
  height: 26px;
  padding: 0;
  margin: 0;
  box-sizing: border-box;
  flex: none;
  border-radius: 50%;
  border: 1.5px solid var(--tile-border);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: var(--card);
  color: var(--ink-2);
  transition: background 140ms, color 140ms, transform 140ms, border-color 140ms;
}
.round svg,
.round :deep(.icon) {
  display: block;
  flex: none;
}
.round:hover {
  color: var(--ink);
  background: #FFF1E2;
  transform: scale(1.06);
}
.spark {
  background: var(--accent-soft);
  border-color: #F3B391;
  color: var(--accent-deep);
}
.spark:hover {
  background: #FFD4BC;
  color: var(--on-accent);
}
.spark.on {
  background: var(--accent);
  border-color: var(--accent-deep);
  color: var(--on-accent);
  transform: rotate(45deg);
}
</style>
