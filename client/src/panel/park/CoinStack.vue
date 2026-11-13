<script setup lang="ts">
// A little pile of coins: 1, 3 or 5 of the same picture, each a bit higher and to one side of the one under it.
// `grey` is a pile out of reach: opaque grayscale, as ParkCoin.
import { computed } from "vue";
import ParkCoin from "./ParkCoin.vue";

const props = withDefaults(defineProps<{ count?: 1 | 3 | 5; size?: number; grey?: boolean }>(), { count: 1, size: 40 });

/** Offsets of each coin from the bottom one, as fractions of the coin's size; bottom first. */
const OFFSETS: [number, number][] = [[0, 0], [0.22, -0.14], [-0.16, -0.28], [0.12, -0.44], [-0.06, -0.58]];

const coins = computed(() => OFFSETS.slice(0, props.count));
/** The box holds the whole pile, so it lines up like a single coin of the same size plus the rise. */
const box = computed(() => {
  const xs = coins.value.map(([x]) => x);
  const left = Math.min(0, ...xs);
  const width = (Math.max(0, ...xs) - left + 1) * props.size;
  const rise = -Math.min(0, ...coins.value.map(([, y]) => y)) * props.size;
  return { left: -left * props.size, width, height: props.size + rise, rise };
});
</script>

<template>
  <span class="coin-stack" aria-hidden="true" :style="{ width: `${box.width}px`, height: `${box.height}px` }">
    <ParkCoin
      v-for="([x, y], i) in coins" :key="i" :size="size" :grey="grey"
      :style="{ left: `${box.left + x * size}px`, top: `${box.rise + y * size}px` }"
    />
  </span>
</template>

<style scoped>
.coin-stack {
  position: relative;
  display: inline-block;
  flex: none;
}
.coin-stack > * {
  position: absolute;
}
</style>
