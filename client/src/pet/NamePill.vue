<script setup lang="ts">
// A paper name tag under a pet, led by a tick in the member's colour.
// `height` and `font` (px) override the default size, for partners drawn small.
defineProps<{ nick: string; width: number; color?: string; height?: number; font?: number }>();
</script>

<template>
  <div
    class="pill"
    :style="{ maxWidth: `${width}px`, height: height ? `${height}px` : undefined, fontSize: font ? `${font}px` : undefined }"
  >
    <i v-if="color" :style="{ background: color }" aria-hidden="true"></i>
    <span>{{ nick }}</span>
  </div>
</template>

<style scoped>
.pill {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 56px;
  height: 22px;
  margin-top: 1px;
  padding: 0 10px;
  box-sizing: border-box;
  border-radius: 11px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 4px 10px -4px rgba(var(--shadow-rgb), 0.3);
  font-family: var(--font);
  font-size: var(--fs-label);
  font-weight: 800;
  color: var(--ink);
}
.pill i {
  flex: none;
  width: 4px;
  height: 11px;
  border-radius: 1px;
}
.pill span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
