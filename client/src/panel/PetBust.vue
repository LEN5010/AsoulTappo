<script setup lang="ts">
import { FACE_CROP, PET_BASE, portraitFor } from "../characters";

defineProps<{
  src: string;
  /** Detail and reveal views use the original artwork. Thumbnails keep the 264px face crop. */
  detail?: boolean;
}>();
/** Room above the canvas for pictures whose headwear reaches past its top, in canvas units.
 *  A picture taller than this would be fitted by height and drift off the canvas. */
const TALL = 60;
</script>

<template>
  <svg
    :viewBox="`${FACE_CROP.x} -8 ${FACE_CROP.w} ${FACE_CROP.h + 8}`"
    preserveAspectRatio="xMidYMax meet"
    aria-hidden="true"
  >
    <svg
      :x="FACE_CROP.x"
      :y="FACE_CROP.y"
      :width="FACE_CROP.w"
      :height="FACE_CROP.h"
      :viewBox="`${FACE_CROP.x} ${FACE_CROP.y} ${FACE_CROP.w} ${FACE_CROP.h}`"
      overflow="hidden"
    >
      <image v-if="!detail && portraitFor(src)" :href="portraitFor(src)" :x="FACE_CROP.x" :y="FACE_CROP.y" :width="FACE_CROP.w" :height="FACE_CROP.h" />
      <!-- Fit by width and align bottoms, so a taller picture puts its canvas part on y 0..135. -->
      <image
        v-else :href="src" x="0" :y="-TALL" :width="PET_BASE.width" :height="PET_BASE.height + TALL"
        preserveAspectRatio="xMidYMax meet"
      />
    </svg>
  </svg>
</template>
