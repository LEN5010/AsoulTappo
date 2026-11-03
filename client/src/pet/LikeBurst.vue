<script setup lang="ts">
// The theme's animated like, played once over the pet each time it is sent.
import { onBeforeUnmount, ref, watch } from "vue";
import { freshAnimationUrl } from "../asset";

const props = defineProps<{ src: string; beat: number | null; size: number; x: number; y: number }>();
const shown = ref<{ url: string; key: number } | null>(null);
let release: (() => void) | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;

function stop() {
  clearTimeout(timer);
  release?.();
  release = null;
  shown.value = null;
}

watch(() => props.beat, async (beat) => {
  if (beat === null || !props.src) return;
  const fresh = await freshAnimationUrl(props.src);
  if (props.beat !== beat) return fresh.release();
  stop();
  release = fresh.release;
  shown.value = { url: fresh.url, key: beat };
  timer = setTimeout(stop, 2600);
});
onBeforeUnmount(stop);
</script>

<template>
  <img
    v-if="shown" :key="shown.key" class="like" :src="shown.url" alt="" draggable="false"
    :style="{ width: `${size}px`, height: `${size}px`, left: `${x - size / 2}px`, top: `${y - size / 2}px` }"
  />
</template>

<style scoped>
.like { position: absolute; object-fit: contain; pointer-events: none; z-index: 6; }
</style>
