<script setup lang="ts">
// A name plate: the strip across the eyes in a gold frame, with the nickname in white on a dark wash at the left.
// A big hidden card plays its video; a sweep plate (a still picture on coral) glides between its two bands.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { assetUrl } from "../asset";
import { usePageActive } from "../composables/usePageActive";
import { renderActive } from "../stores/activity";
import { reducedMotion } from "../stores/theme";
import { roomStatus } from "../roomStatus";
import Icon from "../ui/Icon.vue";
import { getPlate, plateArt, sweepArt, sweepFrames, panCycle, videoFace } from "./plates";
import { followVideo } from "./plateVideo";

const props = withDefaults(
  /** `card` is the plate id: a big hidden card's id or a manifest plate's. */
  defineProps<{
    card: string; nick: string; width: number; height: number; color?: string; still?: boolean; font?: number;
    /** The member's room status, shown before the nickname. */
    status?: string | null;
  }>(),
  { color: undefined, still: false, font: undefined, status: null },
);
const shownStatus = computed(() => roomStatus(props.status));

const FRAME = 2;
const plate = computed(() => getPlate(props.card));
const card = computed(() => (plate.value?.kind === "card" ? plate.value.card : null));
const crop = computed(() => (plate.value?.kind === "card" ? plate.value.crop : null));
const sweep = computed(() => (plate.value?.kind === "sweep" ? plate.value.sweep : null));
const inner = computed(() => ({ w: props.width - FRAME * 2, h: props.height - FRAME * 2 }));
const sweepBoxes = computed(() => (sweep.value ? sweepArt(sweep.value, inner.value.w, inner.value.h) : null));
const stillArt = computed(() =>
  sweepBoxes.value?.face ?? (crop.value ? plateArt(crop.value, inner.value.w, inner.value.h) : null));
const artSrc = computed(() => sweep.value?.src ?? (card.value ? assetUrl(card.value.thumb) : ""));
const pageActive = usePageActive();
// The video and the sweep loop for as long as they are let: they stop with the idle desk too.
const moving = computed(() => pageActive.value && renderActive.value && !props.still && !reducedMotion.value);
const playing = computed(() => !!card.value?.video && moving.value);

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

// A sweep plate moves its picture from the first band to the face and back: the face is where the picture sits,
// the first band an offset from it.
const img = ref<HTMLImageElement>();
let sweeping: Animation | undefined;
watch([moving, sweep, sweepBoxes, img], () => {
  sweeping?.cancel();
  sweeping = undefined;
  const el = img.value, sw = sweep.value, boxes = sweepBoxes.value;
  if (!moving.value || !el?.animate || !sw || !boxes) return;
  const dx = boxes.from.left - boxes.face.left, dy = boxes.from.top - boxes.face.top;
  sweeping = el.animate(
    sweepFrames(sw.rhythm).map(({ offset, p, easing }) =>
      ({ offset, easing, transform: `translate(${dx * (1 - p)}px, ${dy * (1 - p)}px)` })),
    { duration: panCycle(sw.rhythm), iterations: Infinity },
  );
}, { immediate: true, flush: "post" });
onBeforeUnmount(() => sweeping?.cancel());

const px = (n: number) => `${n}px`;
</script>

<template>
  <div
    v-if="plate && stillArt" class="plate frame-gold"
    :style="{ width: px(width), height: px(height), '--r': px(Math.round(height * 0.27)) }"
  >
    <div class="win" :class="{ sweep: !!sweep }">
      <img
        ref="img" class="art" :src="artSrc" alt="" draggable="false" decoding="async"
        :style="{ width: px(stillArt.width), height: px(stillArt.height), left: px(stillArt.left), top: px(stillArt.top) }"
      />
      <canvas v-if="playing" ref="canvas" class="art" :class="{ on: drawn }" :style="{ width: px(inner.w), height: px(inner.h) }"></canvas>
      <div
        class="name"
        :style="{ maxWidth: px(inner.w - 8), fontSize: font ? px(font) : undefined }"
      >
        <span v-if="shownStatus" class="status"><Icon :name="shownStatus.icon" :size="Math.round((font ?? 12) * 1.25)" /><span class="label">{{ shownStatus.label }}</span></span>
        <i v-if="color" :style="{ background: color }" aria-hidden="true"></i>
        <span class="nick">{{ nick }}</span>
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
/* A cut-out picture stands on the coral of the sidebar it comes from. */
.win.sweep {
  background: var(--c-500);
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
/* The room status, in the nickname's white; the icon gets the text's shadow as a filter. */
.name .status {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.name .status .icon {
  filter: drop-shadow(0 1px 1px rgba(var(--shadow-rgb), 0.75));
}
.name .nick {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* The font's ink sits below the middle of its line box; lifted, the text lines up with the tick and the icon. */
.name .label,
.name .nick {
  position: relative;
  top: -0.03em;
}
</style>
