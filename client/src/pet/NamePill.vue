<script setup lang="ts">
defineProps<{ nick: string; width: number }>();
</script>

<template>
  <div class="pill ui-plate" :style="{ maxWidth: `${width}px` }">
    <span>{{ nick }}</span>
  </div>
</template>

<style scoped>
.pill {
  --plate-bg: var(--ink);
  --plate-edge: var(--glow-s);
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  height: 22px;
  margin-top: 1px;
  padding: 0 11px;
  box-sizing: border-box;
  font-family: var(--font);
  font-size: var(--fs-label);
  font-weight: 800;
  color: var(--on-ink);
}
.pill span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
