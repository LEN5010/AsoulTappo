<script setup lang="ts">
// One stamp on the stamp card: the coin inked in vermilion coral, set down a little crooked (a stable lean and ink
// bias from [index], within ±8°). `empty` is a debossed paper socket waiting for its stamp; `next` highlights the very
// next socket to be stamped.
import { computed } from "vue";
import { reducedMotion } from "../../stores/theme";
import { COIN, COIN_SMALL } from "./coin";

const props = withDefaults(defineProps<{ index: number; empty?: boolean; next?: boolean; size?: number }>(), { size: 32 });

/** -8..8 degrees, the same for an index every time. */
const leanOf = (i: number) => ((i * 7 + 3) % 17) - 8;
/** Slight off-centre ink pressure per stamp (28%..56%), so a row of stamps reads like hand-pressed ink. */
const inkX = (i: number) => 28 + ((i * 11) % 29);
const inkY = (i: number) => 26 + ((i * 13) % 27);

const style = computed(() => {
  const box = { width: `${props.size}px`, height: `${props.size}px` };
  if (props.empty) return box;
  // Laid twice, so where the mask goes by brightness the coin's light field inks almost solid.
  const url = `url(${props.size <= 64 ? COIN_SMALL : COIN})`;
  const layers = `${url}, ${url}`;
  return {
    ...box,
    rotate: `${leanOf(props.index)}deg`,
    "--ink-at": `${inkX(props.index)}% ${inkY(props.index)}%`,
    WebkitMaskImage: layers,
    maskImage: layers,
  };
});
</script>

<template>
  <i class="stamp" :class="{ empty, next: empty && next, calm: reducedMotion }" :style="style" aria-hidden="true"></i>
</template>

<style scoped>
.stamp {
  display: inline-block;
  flex: none;
  background: radial-gradient(circle at var(--ink-at, 38% 34%), var(--c-500) 0%, var(--c-600) 56%, var(--c-700) 100%);
  opacity: 0.9;
  -webkit-mask-position: center;
  -webkit-mask-size: contain;
  -webkit-mask-repeat: no-repeat;
  mask-position: center;
  mask-size: contain;
  mask-repeat: no-repeat;
  /* By brightness: the coin's light field takes the ink and its dark outlines stay pale, like a carved seal.
   * Where luminance masks are not supported the stamp is the coin's plain outline. */
  -webkit-mask-mode: luminance;
  mask-mode: luminance;
  filter: drop-shadow(0 0.5px 0 rgba(var(--c-900-rgb), 0.14));
  transition: transform var(--dur-base) var(--ease-spring), opacity var(--dur-fast) var(--ease-out);
}
/* Debossed socket pressed into the tonal stamp card. */
.stamp.empty {
  box-sizing: border-box;
  border: 1.5px dashed var(--c-300);
  border-radius: 50%;
  background: color-mix(in oklab, var(--c-200) 36%, var(--c-50));
  box-shadow:
    inset 0 1px 2px rgba(var(--c-900-rgb), 0.08),
    0 1px 0 rgba(255, 255, 255, 0.7);
  filter: none;
  opacity: 1;
}
/* The next socket in line: warmer rim and sunlit paper base. */
.stamp.empty.next {
  border-color: var(--c-500);
  background: color-mix(in oklab, var(--c-50) 75%, #fff);
  box-shadow:
    inset 0 1px 2px rgba(var(--c-500-rgb), 0.18),
    0 0 0 2px rgba(var(--c-500-rgb), 0.16);
}
.stamp.calm {
  transition: none;
}
</style>
