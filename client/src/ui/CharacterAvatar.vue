<script setup lang="ts">
// Pure character bust cropped from the pet background (excludes monitor at x<=86 and desk at y>=113).
import { computed } from "vue";
import PetBust from "../panel/PetBust.vue";
import { getCharacter } from "../characters";
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
    <PetBust v-if="bg" class="face-svg" :src="bg" />
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
