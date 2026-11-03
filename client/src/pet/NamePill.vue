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
  display: flex; align-items: center; justify-content: center; gap: 4px; min-width: 56px; height: 22px; margin-top: -2px; padding: 0 8px; box-sizing: border-box;
  border-radius: var(--r-s); background: rgba(252, 251, 250, 0.96); border: 1px solid var(--line); box-shadow: 0 2px 6px rgba(43, 35, 38, 0.12);
  font-family: var(--font); font-size: 12px; font-weight: 600; color: var(--ink);
}
.pill span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pill img { height: 16px; width: auto; }
</style>
