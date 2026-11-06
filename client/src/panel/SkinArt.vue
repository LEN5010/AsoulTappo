<script setup lang="ts">
// A skin as an acrylic standee in a tonal slot: the bust in a clear edge on an oval base, its series above.
import { getCharacter, skinSeries } from "../characters";
import PetBust from "./PetBust.vue";
defineProps<{ name: string; owned?: boolean; detail?: boolean }>();
</script>

<template>
  <span class="skin-art" :class="{ locked: !owned }">
    <span class="edition" aria-hidden="true">{{ skinSeries(name) }}</span>
    <i class="base" aria-hidden="true"></i>
    <PetBust class="figure" :src="getCharacter(name)!.bg" :detail="detail" />
  </span>
</template>

<style scoped>
.skin-art { position: relative; display: block; aspect-ratio: 4 / 5; overflow: hidden; border-radius: var(--radius-l); background: var(--c-100); isolation: isolate; }
.edition { position: absolute; left: 16px; top: 16px; right: 16px; font: 800 clamp(16px, 2.4cqw, 22px)/1.3 var(--font); color: var(--ink); }
.base { position: absolute; left: 18%; right: 18%; bottom: 11%; height: 6%; border-radius: 50%; background: rgba(255, 255, 255, .85); box-shadow: 0 3px 0 var(--c-200), 0 6px 10px -4px rgba(var(--c-900-rgb), .3); }
.figure { position: absolute; width: 88%; height: 62%; left: 6%; bottom: 14%; filter: var(--contour) drop-shadow(0 0 2.5px rgba(255, 255, 255, .9)); transition: transform var(--dur-base) var(--ease-out), filter var(--dur-base); }
.locked .figure { filter: var(--dim); }
</style>
