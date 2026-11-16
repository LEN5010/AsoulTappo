<script setup lang="ts">
// The small mark of an owned holo version (镭射款) in a card's corner: a still disc of foil hues on a white rim.
defineProps<{ size?: number }>();
</script>

<template>
  <i class="holo-badge" :style="size ? { '--size': `${size}px` } : undefined" title="镭射款" aria-label="镭射款" role="img"></i>
</template>

<style scoped>
.holo-badge {
  --size: 14px;
  display: block;
  width: var(--size);
  height: var(--size);
  border-radius: 50%;
  background:
    radial-gradient(circle at 34% 30%, rgba(255, 255, 255, 0.95), transparent 38%),
    conic-gradient(from 210deg, var(--holo-pink), var(--holo-cream), var(--holo-mint), var(--holo-lilac), var(--holo-pink));
  box-shadow: 0 0 0 1.5px #fff, 0 1px 3px rgba(var(--shadow-rgb), 0.35);
}
</style>
