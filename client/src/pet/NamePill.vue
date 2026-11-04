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
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  height: 22px;
  margin-top: 1px;
  padding: 0 11px;
  box-sizing: border-box;
  font-family: var(--font);
  font-size: 12px;
  font-weight: 800;
  color: #fff;
}
.pill::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  background: var(--ink);
  box-shadow: 3px 3px 0 var(--accent);
  transform: skewX(var(--skew));
}
.pill span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
