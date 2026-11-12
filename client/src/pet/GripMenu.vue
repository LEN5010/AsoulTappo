<script setup lang="ts">
// The strip's menu, opened from the handle at the left end of the strip or of the own name plate: fold the strip,
// swap it for the name plate and back, and the shard pops. It opens above the handle, or below where the screen
// ends above it.
import { onMounted, ref } from "vue";
import Icon from "../ui/Icon.vue";

/** `plate`: the own name plate stands in the strip's place. */
defineProps<{ plate: boolean; shardPop: boolean }>();
defineEmits<{ fold: []; swap: []; shardPop: [] }>();

const root = ref<HTMLElement>();
const down = ref(false);
// Measured before the first paint, so the menu never shows cut off first.
onMounted(() => {
  const r = root.value?.getBoundingClientRect();
  if (r && r.top < 4) down.value = true;
});
</script>

<template>
  <div ref="root" class="grip-menu" :class="{ down }" role="menu" aria-label="任务栏" data-hit data-no-drag>
    <button type="button" role="menuitem" @click="$emit('fold')">
      <Icon name="fold" :size="16" /><span>收起任务栏</span>
    </button>
    <button type="button" role="menuitem" @click="$emit('swap')">
      <Icon name="swap" :size="16" /><span>{{ plate ? "换回任务栏" : "换成铭牌" }}</span>
    </button>
    <button type="button" role="menuitemcheckbox" :aria-checked="shardPop" @click="$emit('shardPop')">
      <Icon name="shard" :size="16" /><span>显示敲击碎片</span>
      <Icon class="tick" :class="{ on: shardPop }" name="check" :size="14" />
    </button>
  </div>
</template>

<style scoped>
.grip-menu {
  position: absolute;
  left: 0;
  bottom: calc(100% + 8px);
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 150px;
  padding: 4px;
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 8px 20px -6px rgba(var(--shadow-rgb), 0.35);
  font: 700 var(--fs-body)/1 var(--font);
  animation: rise-in var(--dur-base) var(--ease-out);
  cursor: default;
}
.grip-menu.down {
  top: calc(100% + 8px);
  bottom: auto;
  animation-name: drop-in;
}
.grip-menu button {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink);
  font: inherit;
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast);
}
.grip-menu button:hover {
  background: var(--c-50);
}
.grip-menu button:active {
  background: var(--c-100);
}
.grip-menu button:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: -2px;
}
.grip-menu .icon {
  color: var(--ink-2);
}
/* The font's ink sits below the middle of its line box; lifted, the label lines up with the icon. */
.grip-menu span {
  position: relative;
  top: -0.03em;
}
.grip-menu .tick {
  margin-left: auto;
  color: var(--c-600);
  visibility: hidden;
}
.grip-menu .tick.on {
  visibility: visible;
}
@keyframes rise-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}
@keyframes drop-in {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
}
</style>
