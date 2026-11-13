<script setup lang="ts">
// A tuanzi as a die-cut sticker: the member's tuanzi picture with a white contour and a 1px shadow.
// The size is `size` unless the caller sets --tuanzi-size (for sizes that follow the layout). `grey` is opaque
// grayscale, for a field that cannot be bet on.
import { computed } from "vue";
import { tuanziArt } from "./race";

const props = withDefaults(defineProps<{ member: string; size?: 24 | 32 | 48 | 72; grey?: boolean }>(), { size: 48 });
const src = computed(() => tuanziArt(props.member));
const box = computed(() => `var(--tuanzi-size, ${props.size}px)`);
</script>

<template>
  <img
    v-if="src" class="tuanzi-token" :class="[`s${size}`, { grey }]" :src="src" alt="" draggable="false"
    :style="{ width: box, height: box }"
  />
  <i v-else class="tuanzi-token blank" :style="{ width: box, height: box }" aria-hidden="true"></i>
</template>

<style scoped>
.tuanzi-token {
  display: inline-block;
  flex: none;
  object-fit: contain;
  filter: var(--sticker);
  user-select: none;
}
.tuanzi-token.s72 {
  filter: var(--sticker-lg);
}
.tuanzi-token.grey {
  filter: grayscale(1) var(--sticker);
}
.tuanzi-token.s72.grey {
  filter: grayscale(1) var(--sticker-lg);
}
.blank {
  border-radius: 50%;
  background: var(--c-100);
}
</style>
