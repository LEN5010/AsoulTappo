<script setup lang="ts">
// Round avatar cropped from the character's pet background (the face area), with an optional frame.
import { computed } from "vue";
import { FACE_CROP, getCharacter, PET_BASE } from "../characters";
import { characterColor, getDecor } from "../manifest";
import { assetUrl } from "../asset";

const props = withDefaults(defineProps<{ character: string; size?: number; frame?: string | null; round?: boolean }>(), {
  size: 40, frame: null, round: true,
});
const bg = computed(() => getCharacter(props.character)?.bg ?? "");
const style = computed(() => {
  const k = props.size / FACE_CROP.size;
  return {
    width: `${props.size}px`,
    height: `${props.size}px`,
    borderRadius: props.round ? "50%" : "22%",
    backgroundColor: `${characterColor(props.character)}33`,
    backgroundImage: bg.value ? `url("${bg.value}")` : "none",
    backgroundSize: `${PET_BASE.width * k}px ${PET_BASE.height * k}px`,
    backgroundPosition: `${-FACE_CROP.x * k}px ${-FACE_CROP.y * k}px`,
  };
});
const frameImg = computed(() => assetUrl(getDecor(props.frame)?.img));
</script>

<template>
  <span class="avatar" :style="{ width: `${size * (frameImg ? 1.36 : 1)}px`, height: `${size * (frameImg ? 1.36 : 1)}px` }">
    <span class="face" :style="style"></span>
    <img v-if="frameImg" class="frame" :src="frameImg" alt="" draggable="false" />
  </span>
</template>

<style scoped>
.avatar { position: relative; display: inline-grid; place-items: center; flex: none; }
.face { display: block; background-repeat: no-repeat; box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.7); }
.frame { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; pointer-events: none; }
</style>
