<script setup lang="ts">
import Icon from "../ui/Icon.vue";

defineProps<{ count: number; view: "today" | "total"; width: number; quickOpen: boolean }>();
defineEmits<{ toggleView: []; quick: []; menu: [] }>();
const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <div class="bar ui-plate" :style="{ width: `${width}px` }">
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
  --plate-bg: var(--surface);
  --plate-edge: var(--glow-s), 0 6px 16px rgba(var(--ink-rgb), 0.2);
  display: flex;
  align-items: center;
  gap: 6px;
  height: 31px;
  margin-top: -4px;
  padding: 0 7px 0 0;
  box-sizing: border-box;
  font-family: var(--font);
  color: var(--ink);
}
.count {
  flex: 1;
  min-width: 0;
  align-self: stretch;
  display: flex;
  align-items: center;
  padding: 0 0 0 13px;
  border: none;
  background: none;
  cursor: pointer;
  font: inherit;
  color: inherit;
}
.count span {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  line-height: 1;
}
.count b {
  font: 800 var(--fs-title)/1 var(--font-latin);
}
.count small {
  font-size: var(--fs-caption);
  font-weight: 800;
  color: var(--accent-deep);
}
.round {
  width: 28px;
  height: 22px;
  padding: 0;
  margin: 0;
  box-sizing: border-box;
  flex: none;
  border: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: var(--accent-tint);
  color: var(--ink);
  transition: background var(--dur-fast), color var(--dur-fast);
}
.round svg,
.round :deep(.icon) {
  display: block;
  flex: none;
}
.round:hover {
  background: var(--accent-soft);
}
.spark {
  background: var(--grad-main);
  color: var(--on-accent);
}
.spark:hover {
  background: var(--accent-hover);
}
.spark.on {
  background: var(--ink);
  color: var(--on-ink);
}
.spark svg {
  transition: transform var(--dur-slow) var(--ease-out);
}
.spark.on svg {
  transform: rotate(45deg);
}
</style>
