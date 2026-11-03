<script setup lang="ts">
import { computed } from "vue";
import { characterColor, getDecor, resolveAsset } from "../manifest";
import { toHttpBase } from "../net/protocol";
import { settings } from "../stores/settings";

const props = defineProps<{ character: string; frame?: string | null; size?: number }>();
const px = computed(() => props.size ?? 26);
const color = computed(() => characterColor(props.character));
const frameImg = computed(() => {
  const d = getDecor(props.frame);
  return d ? resolveAsset(d.img, toHttpBase(settings.serverUrl), import.meta.env.BASE_URL) : "";
});
</script>

<template>
  <span class="avatar" :style="{ width: `${px * 1.4}px`, height: `${px * 1.4}px` }">
    <span class="face" :style="{ width: `${px}px`, height: `${px}px`, background: color, fontSize: `${px * 0.5}px` }">{{ character.slice(0, 1) }}</span>
    <img v-if="frameImg" class="frame" :src="frameImg" alt="" draggable="false" />
  </span>
</template>

<style scoped>
.avatar { position: relative; display: inline-grid; place-items: center; flex: none; }
.face { border-radius: 50%; color: #fff; display: grid; place-items: center; font-weight: 700; box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.5); }
.frame { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; pointer-events: none; }
</style>
