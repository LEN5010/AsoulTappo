<script setup lang="ts">
// A holo version (镭射款) drawn in WebGL: the art, with foil over the mask's white that shifts with the lean.
// It fills its box. While the shading loads, and where WebGL or the mask cannot be had, it is the art under a
// still gloss. Each one holds a pooled canvas only while mounted, so only the cards that move should mount it.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { HoloShine } from "../manifest";
import { acquire, loadImage, release, type HoloRenderer } from "./renderer";
import { FLAT, frameKey, sameFrame, type Tilt } from "./shader";

const props = withDefaults(defineProps<{
  art: string;
  mask: string;
  shine: HoloShine;
  tilt?: Tilt;
  /** Under the pointer: the foil a little brighter. */
  lit?: boolean;
  alt?: string;
}>(), { tilt: () => FLAT, lit: false, alt: "" });

const root = ref<HTMLElement>();
const host = ref<HTMLElement>();
const ready = ref(false);
const fallback = ref(false);
let renderer: HoloRenderer | null = null;
let observer: ResizeObserver | undefined;
let alive = true;
let loading = 0;
/** What the canvas shows now, so a frame that would come out the same is not drawn again. */
let drawn: number[] | null = null;

function giveUp() {
  drawn = null;
  fallback.value = true;
  ready.value = false;
  if (renderer) release(renderer);
  renderer = null;
}

function draw() {
  if (!renderer || !ready.value) return;
  if (renderer.lost) return giveUp();
  const on = props.lit ? 1 : 0.85;
  const key = frameKey(renderer.canvas.width, renderer.canvas.height, props.tilt, on, props.shine);
  if (sameFrame(drawn, key)) return;
  drawn = key;
  renderer.draw({ shine: props.shine, tilt: props.tilt, on });
}

function fit() {
  const el = root.value;
  if (!renderer || !el?.clientWidth) return;
  renderer.resize(el.clientWidth, el.clientHeight / el.clientWidth);
  draw();
}

async function load() {
  const mine = ++loading;
  drawn = null;
  ready.value = false;
  if (!props.art || !props.mask) return giveUp();
  renderer ??= acquire();
  if (!renderer) return giveUp();
  fallback.value = false;
  try {
    const [art, mask] = await Promise.all([loadImage(props.art), loadImage(props.mask)]);
    if (!alive || mine !== loading || !renderer) return;
    renderer.setImages(props.art, art, props.mask, mask);
  } catch {
    if (alive && mine === loading) giveUp();
    return;
  }
  host.value?.append(renderer.canvas);
  // New pictures on the canvas: the next frame is drawn whatever the lean.
  drawn = null;
  ready.value = true;
  fit();
}

watch(() => [props.art, props.mask], () => void load());
watch(() => [props.tilt, props.lit, props.shine], draw);

onMounted(() => {
  void load();
  if (root.value) {
    observer = new ResizeObserver(fit);
    observer.observe(root.value);
  }
});
onBeforeUnmount(() => {
  alive = false;
  observer?.disconnect();
  if (renderer) release(renderer);
  renderer = null;
});

const shown = computed(() => ready.value && !fallback.value);
</script>

<template>
  <span ref="root" class="holo-art">
    <img class="base" :src="art" :alt="alt" draggable="false" />
    <span ref="host" class="host" :class="{ shown }" aria-hidden="true"></span>
    <i v-if="fallback" class="gloss" aria-hidden="true"></i>
  </span>
</template>

<style scoped>
.holo-art {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: inherit;
}
.base,
.host,
.gloss {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
/* The card lean moves the whole box; the art itself never zooms or takes a well's contour. */
.base {
  display: block;
  max-width: none;
  max-height: none;
  margin: 0;
  object-fit: cover;
  filter: none !important;
  transform: none !important;
  transition: none;
}
.host {
  opacity: 0;
  transition: opacity var(--dur-base) var(--ease-out);
  pointer-events: none;
}
.host.shown {
  opacity: 1;
}
.host :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}
/* No shading to be had: the art under a still band of foil. */
.gloss {
  background: var(--holo-film), linear-gradient(160deg, rgba(255, 255, 255, 0.18), transparent 45%);
  pointer-events: none;
}
</style>
