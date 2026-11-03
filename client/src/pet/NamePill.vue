<script setup lang="ts">
defineProps<{ nick: string; width: number }>();
</script>

<template>
  <div class="pill" :style="{ maxWidth: `${width}px` }">
    <span>{{ nick }}</span>
  </div>
</template>

<style scoped>
.pill {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-width: 56px;
  height: 24px;
  margin-top: -2px;
  padding: 0 10px;
  box-sizing: border-box;
  border-radius: 999px;
  background: rgba(253, 244, 231, 0.96);
  border: 1.5px solid var(--tile-border);
  box-shadow: 0 2px 0 var(--tile-lip), 0 3px 8px rgba(72, 38, 20, 0.14);
  font-family: var(--font);
  font-size: 12px;
  font-weight: 800;
  color: var(--ink);
}
.pill span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
