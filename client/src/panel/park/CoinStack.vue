<script setup lang="ts">
// A little pile of coins: 1, 3 or 5 of the same picture, each a bit higher, angled its own way, and set to one side
// of the one under it. `grey` is a pile out of reach: opaque grayscale, as ParkCoin. Parents may set `--stack-fan` to
// fan the upper coins slightly apart on hover.
import { computed } from "vue";
import { reducedMotion } from "../../stores/theme";
import ParkCoin from "./ParkCoin.vue";

const props = withDefaults(
  defineProps<{ count?: 1 | 3 | 5; size?: number; grey?: boolean; sheen?: boolean }>(),
  { count: 1, size: 40 },
);

/** Offsets of each coin from the bottom one, as fractions of the coin's size; bottom first. */
const OFFSETS: [number, number][] = [[0, 0], [0.23, -0.15], [-0.17, -0.3], [0.13, -0.46], [-0.06, -0.6]];
const LEANS = [-7, 4, -11, 5, -5];

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
  <span class="coin-stack" :class="{ calm: reducedMotion }" aria-hidden="true" :style="{ width: `${box.width}px`, height: `${box.height}px` }">
    <ParkCoin
      v-for="([x, y], i) in coins" :key="i" :size="size" :grey="grey" :tilt="false"
      :sheen="sheen && i === coins.length - 1"
      :style="{
        left: `${box.left + x * size}px`,
        top: `${box.rise + y * size}px`,
        '--i': i,
        '--lean': `${LEANS[i] ?? -8}deg`,
      }"
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
  transform: translateY(calc(var(--i, 0) * var(--stack-fan, 0px))) rotate(var(--lean, -8deg));
  transition: transform var(--dur-base) var(--ease-spring);
}
.calm > * {
  transition: none;
}
</style>
