<script setup lang="ts">
// A tuanzi as a die-cut sticker: the member's tuanzi picture with a white contour and a 1px shadow.
import { computed } from "vue";
import { tuanziArt } from "./race";

const props = withDefaults(defineProps<{ member: string; size?: 24 | 32 | 48 | 72 }>(), { size: 48 });
const src = computed(() => tuanziArt(props.member));
</script>

<template>
  <img
    v-if="src" class="tuanzi-token" :class="`s${size}`" :src="src" alt="" draggable="false"
    :style="{ width: `${size}px`, height: `${size}px` }"
  />
  <i v-else class="tuanzi-token blank" :style="{ width: `${size}px`, height: `${size}px` }" aria-hidden="true"></i>
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
.blank {
  border-radius: 50%;
  background: var(--c-100);
}
</style>
