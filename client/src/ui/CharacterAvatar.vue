<script setup lang="ts">
// Pure character bust cropped from the pet background (excludes monitor at x<=86 and desk at y>=113).
import { computed } from "vue";
import { FACE_CROP, getCharacter, PET_BASE } from "../characters";
import { characterColor } from "../manifest";

const props = withDefaults(defineProps<{ character: string; size?: number }>(), { size: 40 });
const bg = computed(() => getCharacter(props.character)?.bg ?? "");
const tint = computed(() => `${characterColor(props.character)}28`);
</script>

<template>
  <span
    class="avatar"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      backgroundColor: tint,
    }"
  >
    <svg
      v-if="bg"
      class="face-svg"
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
        <image :href="bg" x="0" y="0" :width="PET_BASE.width" :height="PET_BASE.height" />
      </svg>
    </svg>
  </span>
</template>

<style scoped>
.avatar {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex: none;
}
.face-svg {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
