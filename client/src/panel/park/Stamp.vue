<script setup lang="ts">
// One stamp on the stamp card: the coin inked in coral, set down a little crooked (a stable lean from [index],
// within ±8°). `empty` is the slot still waiting for its stamp: a dashed circle.
import { computed } from "vue";
import { COIN, COIN_SMALL } from "./coin";

const props = withDefaults(defineProps<{ index: number; empty?: boolean; size?: number }>(), { size: 32 });

/** -8..8 degrees, the same for an index every time. */
const leanOf = (i: number) => ((i * 7 + 3) % 17) - 8;
const style = computed(() => {
  const box = { width: `${props.size}px`, height: `${props.size}px` };
  if (props.empty) return box;
  // Laid twice, so where the mask goes by brightness the coin's light field inks almost solid.
  const url = `url(${props.size <= 64 ? COIN_SMALL : COIN})`;
  const layers = `${url}, ${url}`;
  return { ...box, rotate: `${leanOf(props.index)}deg`, maskImage: layers, WebkitMaskImage: layers };
});
</script>

<template>
  <i class="stamp" :class="{ empty }" :style="style" aria-hidden="true"></i>
</template>

<style scoped>
.stamp {
  display: inline-block;
  flex: none;
  background: var(--c-600);
  opacity: 0.85;
  mask-position: center;
  mask-size: contain;
  mask-repeat: no-repeat;
  /* By brightness: the coin's light field takes the ink and its dark outlines stay pale, like a carved seal.
   * Where luminance masks are not supported the stamp is the coin's plain outline. */
  mask-mode: luminance;
  -webkit-mask-position: center;
  -webkit-mask-size: contain;
  -webkit-mask-repeat: no-repeat;
}
.stamp.empty {
  box-sizing: border-box;
  border: 2px dashed var(--c-200);
  border-radius: 50%;
  background: none;
  opacity: 1;
}
</style>
