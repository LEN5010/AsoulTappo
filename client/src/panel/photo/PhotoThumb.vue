<script setup lang="ts">
// A photocard's small picture, signature included. It fills its box's width; the box keeps the card's proportions.
import { computed } from "vue";
import { isWidePhoto, type PhotoItem } from "../../photocards";
import { photoInk, photoThumb } from "../../photo/thumbs";

const props = defineProps<{ item: PhotoItem; dim?: boolean; lazy?: boolean }>();
const src = computed(() => photoThumb(props.item));
const ink = computed(() => photoInk(props.item));
const wide = computed(() => isWidePhoto(props.item));
</script>

<template>
  <span class="photo-thumb" :class="{ wide, dim }">
    <img v-if="src" class="face" :src="src" alt="" draggable="false" decoding="async" :loading="lazy ? 'lazy' : undefined" />
    <img v-if="ink" class="ink" :src="ink.src" :style="ink.style" alt="" draggable="false" decoding="async" :loading="lazy ? 'lazy' : undefined" />
  </span>
</template>

<style scoped>
.photo-thumb {
  position: relative;
  display: block;
  aspect-ratio: 54 / 86;
  overflow: hidden;
  border-radius: 1.5px;
  background: var(--c-100);
}
.wide {
  aspect-ratio: 86 / 54;
}
.face {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.ink {
  position: absolute;
}
.dim img {
  filter: var(--dim);
}
</style>
