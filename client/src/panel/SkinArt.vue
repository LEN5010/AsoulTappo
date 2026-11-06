<script setup lang="ts">
// A skin bust in its series slot. The wrapper keeps PetBust's 132:120 frame so the crop is not letterboxed.
import { FACE_CROP, getCharacter, skinSeries } from "../characters";
import PetBust from "./PetBust.vue";
defineProps<{ name: string; owned?: boolean; detail?: boolean }>();
const frameRatio = `${FACE_CROP.w} / ${FACE_CROP.h + 8}`;
</script>

<template>
  <span class="skin-art" :class="{ locked: !owned }">
    <span class="edition" aria-hidden="true">{{ skinSeries(name) }}</span>
    <span class="stand" :style="{ aspectRatio: frameRatio }">
      <PetBust class="figure" :src="getCharacter(name)!.bg" :detail="detail" />
    </span>
  </span>
</template>

<style scoped>
.skin-art { position: relative; display: block; aspect-ratio: 4 / 5; overflow: hidden; border-radius: var(--radius-l); background: var(--c-100); isolation: isolate; }
.edition {
  position: absolute;
  z-index: 2;
  left: 16px;
  top: 16px;
  max-width: calc(100% - 108px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 clamp(16px, 2.4cqw, 22px)/1.3 var(--font);
  color: var(--ink);
}
.stand { position: absolute; left: 7%; bottom: 8%; width: 86%; }
.figure {
  display: block;
  width: 100%;
  height: 100%;
  filter: var(--contour) drop-shadow(0 0 2.5px rgba(255, 255, 255, .9));
  transition: transform var(--dur-base) var(--ease-out), filter var(--dur-base);
}
.locked .figure { filter: var(--dim); }
</style>
