<script setup lang="ts">
// The coin as a thing: it leans and casts a coral-tinted shadow. Small sizes use the 64px picture. `grey` is the
// coin not yet earned: opaque grayscale, never see-through. `sheen` runs a slow light across its face. `fill` takes
// the size from --size set on a parent instead of `size`, so CSS can resize it; it always uses the 256px picture.
import { computed, ref } from "vue";
import { usePageActive } from "../../composables/usePageActive";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import { COIN, COIN_SMALL } from "./coin";

const props = withDefaults(
  defineProps<{ size?: number; grey?: boolean; sheen?: boolean; tilt?: boolean; fill?: boolean }>(),
  { size: 72, tilt: true },
);

const pageActive = usePageActive();
const src = computed(() => (props.size <= 64 && !props.fill ? COIN_SMALL : COIN));
const failed = ref(false);
</script>

<template>
  <span
    class="park-coin" :class="{ grey, tilt, fill, paused: !pageActive }" aria-hidden="true"
    :style="fill ? { '--src': `url(${src})` } : { '--size': `${size}px`, '--src': `url(${src})` }"
  >
    <Icon v-if="failed" class="glyph" name="coin" :size="size" />
    <template v-else>
      <img :src="src" alt="" draggable="false" @error="failed = true" />
      <i v-if="!grey" class="rim"></i>
      <i v-if="sheen && !grey && !reducedMotion" class="sheen"></i>
      <i v-if="!grey && !reducedMotion" class="glint"></i>
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
  /* A crisp warm rim under the edge, plus the cast shadow growing with the coin. */
  filter:
    drop-shadow(0 max(1px, calc(var(--size) * 0.018)) 0 rgba(var(--c-900-rgb), 0.22))
    drop-shadow(0 calc(var(--size) * 0.055) calc(var(--size) * 0.065) rgba(var(--c-900-rgb), 0.28));
}
.grey img {
  filter:
    grayscale(1) contrast(0.88) brightness(1.1)
    drop-shadow(0 max(1px, calc(var(--size) * 0.016)) 0 rgba(var(--c-900-rgb), 0.14))
    drop-shadow(0 calc(var(--size) * 0.045) calc(var(--size) * 0.055) rgba(var(--c-900-rgb), 0.16));
}
.glyph {
  color: var(--c-500);
}
.grey .glyph {
  color: var(--ink-3);
}
.fill .glyph {
  width: 100%;
  height: 100%;
}
/* Subtle top-left catchlight cut to the coin's silhouette, giving stamped metal relief at rest. */
.rim,
.sheen,
.glint {
  position: absolute;
  inset: 0;
  -webkit-mask: var(--src) center / contain no-repeat;
  mask: var(--src) center / contain no-repeat;
  pointer-events: none;
}
.rim {
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.34) 0%, rgba(255, 255, 255, 0.08) 28%, transparent 52%, rgba(var(--c-900-rgb), 0.1) 100%);
  mix-blend-mode: soft-light;
}
/* A dual-band metallic gleam crossing the face now and then, cut to the coin's own outline. */
.sheen {
  background: linear-gradient(
    108deg,
    transparent 33%,
    rgba(255, 255, 255, 0.18) 43%,
    rgba(255, 255, 255, 0.68) 50%,
    rgba(255, 255, 255, 0.16) 57%,
    transparent 67%
  ) 165% 0 / 260% 100% no-repeat;
  animation: coin-sheen 4.4s var(--ease-in-out) infinite;
}
.paused .sheen {
  animation-play-state: paused;
}
/* Interactive hover sweep triggered when a parent sets --coin-glint-pos to -65% (at rest 165%). */
.glint {
  background: linear-gradient(
    112deg,
    transparent 36%,
    rgba(255, 255, 255, 0.62) 50%,
    transparent 64%
  ) var(--coin-glint-pos, 165%) 0 / 250% 100% no-repeat;
  transition: background-position var(--dur-stage) var(--ease-out);
}
@keyframes coin-sheen {
  0%, 60% { background-position: 165% 0; }
  100% { background-position: -65% 0; }
}
</style>
