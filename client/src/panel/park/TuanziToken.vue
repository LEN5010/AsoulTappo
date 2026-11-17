<script setup lang="ts">
// A tuanzi as a tactile board-game token: the member's dumpling picture framed in a crisp white porcelain contour,
// resting on a warm coral-cream thickness edge and a soft grounded shadow.
// The size is `size` unless the caller sets --tuanzi-size (for sizes that follow the layout). `grey` is opaque
// grayscale, for a field that cannot be bet on.
import { computed } from "vue";
import { tuanziArt } from "./race";

const props = withDefaults(defineProps<{ member: string; size?: 24 | 32 | 48 | 72; grey?: boolean }>(), { size: 48 });
const src = computed(() => tuanziArt(props.member));
const box = computed(() => `var(--tuanzi-size, ${props.size}px)`);
</script>

<template>
  <span
    v-if="src" class="tuanzi-token" :class="[`s${size}`, { grey }]"
    :style="{ width: box, height: box }"
  >
    <img class="pic" :src="src" alt="" draggable="false" />
  </span>
  <i v-else class="tuanzi-token blank" :style="{ width: box, height: box }" aria-hidden="true"></i>
</template>

<style scoped>
.tuanzi-token {
  --rim: 1.7px;
  --pedestal: 2.2px;
  --shade: 2.2px;
  --pedestal-tint: var(--c-200);
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  line-height: 0;
  filter:
    drop-shadow(var(--rim) 0 0 #fff)
    drop-shadow(calc(var(--rim) * -1) 0 0 #fff)
    drop-shadow(0 var(--rim) 0 #fff)
    drop-shadow(0 calc(var(--rim) * -1) 0 #fff)
    drop-shadow(0 var(--pedestal) 0 var(--pedestal-tint))
    drop-shadow(0 calc(var(--pedestal) + 1px) var(--shade) rgba(var(--c-900-rgb), 0.28));
  user-select: none;
}
.tuanzi-token.s24 {
  --rim: 1.25px;
  --pedestal: 1.2px;
  --shade: 1.3px;
}
.tuanzi-token.s32 {
  --rim: 1.45px;
  --pedestal: 1.6px;
  --shade: 1.6px;
}
.tuanzi-token.s72 {
  --rim: 2.4px;
  --pedestal: 3px;
  --shade: 2.8px;
}
.pic {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  filter: saturate(1.04) contrast(1.02);
  pointer-events: none;
}
.tuanzi-token.grey {
  --pedestal-tint: color-mix(in oklab, var(--c-200) 32%, #d8d2d4);
}
.tuanzi-token.grey .pic {
  filter: grayscale(1) contrast(0.95) brightness(1.02);
}
.blank {
  border-radius: 50%;
  background: var(--c-100);
  filter: none;
}
</style>
