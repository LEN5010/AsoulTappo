<script setup lang="ts">
// A big hidden card worn as a name plate: the strip across the eyes in a gold frame, playing the
// card video, with the nickname in white on a dark wash at the left.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { assetUrl } from "../asset";
import { reducedMotion } from "../stores/theme";
import { PLATE_CROPS, plateArt, plateCard, videoFace } from "./plates";
import { followVideo } from "./plateVideo";

const props = withDefaults(
  defineProps<{ card: string; nick: string; width: number; height: number; color?: string; still?: boolean; font?: number }>(),
  { color: undefined, still: false, font: undefined },
);

const FRAME = 2;
const card = computed(() => plateCard(props.card));
const crop = computed(() => PLATE_CROPS[props.card]);
const inner = computed(() => ({ w: props.width - FRAME * 2, h: props.height - FRAME * 2 }));
const stillArt = computed(() => (crop.value ? plateArt(crop.value, inner.value.w, inner.value.h) : null));
const playing = computed(() => !!card.value?.video && !props.still && !reducedMotion.value);

const canvas = ref<HTMLCanvasElement>();
const drawn = ref(false);
let stop: (() => void) | undefined;

watch([playing, card, canvas, inner], () => {
  stop?.();
  stop = undefined;
  drawn.value = false;
  const cvs = canvas.value, src = card.value?.video, cr = crop.value;
  const ctx = cvs?.getContext("2d");
  if (!playing.value || !cvs || !ctx || !src || !cr) return;
  const { w, h } = inner.value;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  cvs.width = Math.round(w * dpr);
  cvs.height = Math.round(h * dpr);
  stop = followVideo(assetUrl(src), (video) => {
    const art = plateArt(videoFace(cr, performance.now()), w, h);
    const k = video.videoWidth / art.width;
    ctx.drawImage(video, -art.left * k, -art.top * k, w * k, h * k, 0, 0, cvs.width, cvs.height);
    drawn.value = true;
  });
}, { immediate: true, flush: "post" });
onBeforeUnmount(() => stop?.());

const px = (n: number) => `${n}px`;
</script>

<template>
  <div
    v-if="card && stillArt" class="plate frame-gold"
    :style="{ width: px(width), height: px(height), '--r': px(Math.round(height * 0.27)) }"
  >
    <div class="win">
      <img
        class="art" :src="assetUrl(card.thumb)" alt="" draggable="false" decoding="async"
        :style="{ width: px(stillArt.width), height: px(stillArt.height), left: px(stillArt.left), top: px(stillArt.top) }"
      />
      <canvas v-if="playing" ref="canvas" class="art" :class="{ on: drawn }" :style="{ width: px(inner.w), height: px(inner.h) }"></canvas>
      <div class="name" :style="{ maxWidth: px(inner.w - 8), fontSize: font ? px(font) : undefined }">
        <i v-if="color" :style="{ background: color }" aria-hidden="true"></i>
        <span>{{ nick }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plate {
  position: relative;
  flex: none;
  margin-top: 1px;
  padding: 2px;
  box-sizing: border-box;
  border-radius: var(--r);
  background: var(--frame-fill);
  background-size: var(--frame-size);
  background-position: var(--frame-at);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.2), 0 5px 12px -5px rgba(var(--shadow-rgb), 0.45);
}
.win {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: calc(var(--r) - 2px);
  background: var(--ink);
}
.art {
  position: absolute;
  display: block;
  max-width: none;
  pointer-events: none;
  user-select: none;
}
canvas.art {
  left: 0;
  top: 0;
  opacity: 0;
  transition: opacity var(--dur-slow);
}
canvas.art.on {
  opacity: 1;
}
/* The wash grows with the name and fades out to its right, so a short name leaves the face clear. */
.name {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px 0 9px;
  box-sizing: border-box;
  background: linear-gradient(90deg, color-mix(in oklab, var(--ink) 74%, transparent), color-mix(in oklab, var(--ink) 52%, transparent));
  font-family: var(--font);
  font-size: var(--fs-label);
  font-weight: 800;
  color: var(--on-ink);
  text-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.75), 0 0 6px rgba(var(--shadow-rgb), 0.45);
  white-space: nowrap;
}
.name::after {
  content: "";
  position: absolute;
  left: 100%;
  top: 0;
  bottom: 0;
  width: 20px;
  background: linear-gradient(90deg, color-mix(in oklab, var(--ink) 52%, transparent), transparent);
  pointer-events: none;
}
.name i {
  flex: none;
  width: 4px;
  height: 11px;
  border-radius: 1px;
}
.name span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
