<script setup lang="ts">
// Live paw on the backpack stage. Pointer motion updates `pet` every frame, so this stays its
// own component: reading that state from EmotesPage would re-render the sticker grid with it.
import PetView from "../pet/PetView.vue";
import type { EmoteFrame } from "../pet/EmotePlayer";
import { pet } from "../stores/pet";

defineProps<{ character: string; emote: EmoteFrame | null }>();

const SCALE = 1.42;
const EMOTE = 86;
const BUBBLE = { x: 36, y: 62 };
</script>

<template>
  <PetView
    :character="character" :scale="SCALE"
    :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
    :left-down="pet.left" :right-down="pet.right" :emote="emote" :min-emote="38"
    :max-emote="EMOTE" :bubble-shift="BUBBLE"
  />
</template>

<style scoped>
/* Contour stays on the still background. The paw and keyboard move inside .art, and a filter
   on .art would redraw the whole pet on every pointer frame. Same split as the room seats. */
:deep(.bg) {
  filter: var(--sticker-lg);
}
</style>
