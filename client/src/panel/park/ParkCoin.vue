<script setup lang="ts">
// The coin as a thing: it leans and casts a coral-tinted shadow. Small sizes use the 64px picture. `grey` is the
// coin not yet earned: opaque grayscale, never see-through. `sheen` runs a slow light across its face. `fill` takes
// the size from --size set on a parent instead of `size`, so CSS can resize it; it always uses the 256px picture.
import { computed, ref } from "vue";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import { COIN, COIN_SMALL } from "./coin";

const props = withDefaults(
  defineProps<{ size?: number; grey?: boolean; sheen?: boolean; tilt?: boolean; fill?: boolean }>(),
  { size: 72, tilt: true },
);

const src = computed(() => (props.size <= 64 && !props.fill ? COIN_SMALL : COIN));
const failed = ref(false);
</script>

<template>
  <span
    class="park-coin" :class="{ grey, tilt, fill }" aria-hidden="true"
    :style="fill ? { '--src': `url(${src})` } : { '--size': `${size}px`, '--src': `url(${src})` }"
  >
    <Icon v-if="failed" class="glyph" name="coin" :size="size" />
    <template v-else>
      <img :src="src" alt="" draggable="false" @error="failed = true" />
      <i v-if="sheen && !grey && !reducedMotion" class="sheen"></i>
    </template>
  </span>
</template>

<style scoped>
.park-coin {
  position: relative;
  display: inline-block;
  flex: none;
  width: var(--size);
  height: var(--size);
  line-height: 0;
  user-select: none;
}
.park-coin.tilt {
  rotate: -8deg;
}
.park-coin img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  /* The shadow grows with the coin. */
  filter: drop-shadow(0 calc(var(--size) * 0.05) calc(var(--size) * 0.06) rgba(var(--c-900-rgb), 0.3));
}
.grey img {
  filter: grayscale(1) brightness(1.12) drop-shadow(0 calc(var(--size) * 0.05) calc(var(--size) * 0.06) rgba(var(--c-900-rgb), 0.18));
}
.glyph {
  color: var(--gold);
}
.grey .glyph {
  color: var(--ink-3);
}
.fill .glyph {
  width: 100%;
  height: 100%;
}
/* A band of light crossing the face now and then, cut to the coin's own outline. */
.sheen {
  position: absolute;
  inset: 0;
  background: linear-gradient(105deg, transparent 38%, rgba(255, 255, 255, 0.55) 50%, transparent 62%) 160% 0 / 260% 100% no-repeat;
  mask: var(--src) center / contain no-repeat;
  -webkit-mask: var(--src) center / contain no-repeat;
  animation: coin-sheen 4.2s var(--ease-in-out) infinite;
  pointer-events: none;
}
@keyframes coin-sheen {
  0%, 60% { background-position: 160% 0; }
  100% { background-position: -60% 0; }
}
</style>
