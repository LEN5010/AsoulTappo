<script setup lang="ts">
// The stage under the photocards' page: the key visual of the series on show (photo/stage.ts), under the whole panel with
// the sidebar over its left. It is part of the resonance page rather than of what stands on it, so going to another pool
// and back it fades by itself. A series without a key visual has no stage: its page is paper.
// Until the canvas draws, and where there is no WebGL 2, a picture of it lies there.
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, ref, shallowRef, watch } from "vue";
import { usePageActive } from "../../composables/usePageActive";
import { memberLight, seriesArt } from "../../photo/art";
import type { Vec3 } from "../../photo/gl";
import { onStageLost, photoStage, type Stage, type StageState } from "../../photo/stage";
import { E } from "../../photo/time";
import { reducedMotion } from "../../stores/theme";
import { ground } from "../../stores/ui";
import { groundFoot, groundKind, groundRose, groundTitle, groundUp, openPage, photoOver, photoRun, poster, shopSeries } from "./shop";

const props = defineProps<{
  /** The photocards' page is the one on show. */
  on: boolean;
}>();

const pageActive = usePageActive();
const there = ref(true);
onActivated(() => { there.value = true; });
onDeactivated(() => { there.value = false; });
const art = computed(() => seriesArt(shopSeries.value)?.stage ?? null);
const here = computed(() => props.on && there.value && !!art.value);
const host = ref<HTMLElement>();
const stage = shallowRef<Stage | null>(null);
/** The canvas draws. */
const up = ref(false);
/** There is no WebGL 2: the pictures stay. */
const flat = ref(false);
let alive = true;
let round = 0;

async function start(): Promise<void> {
  const mine = ++round, now = art.value;
  if (!now) return;
  await nextTick();
  const s = await photoStage();
  const ok = s ? await s.load(now) : false;
  if (!alive || mine !== round || !host.value) return;
  if (!s || !ok) {
    groundRose.value = performance.now();
    flat.value = groundUp.value = true;
    return;
  }
  flat.value = false;
  stage.value = s;
  s.show(now);
  place();
  s.set(poster.value === "opening" ? BLANK : lookOf());
  s.mount(host.value);
  s.seen(seen.value);
  await s.up;
  if (!alive || mine !== round) return;
  if (poster.value === "opening") rise(s);
  up.value = groundUp.value = true;
}
function stop(): void {
  round++;
  stage.value?.seen(false);
  stage.value?.release();
  stage.value = null;
  up.value = groundUp.value = false;
}
// Before anything of the page is drawn.
watch(here, (on) => { if (on && pageActive.value && !reducedMotion.value) openPage(shopSeries.value); }, { immediate: true, flush: "sync" });
watch(here, (on) => { if (on) void start(); else stop(); }, { immediate: true, flush: "post" });
// Another series fades over on the running canvas.
watch(art, async (now) => {
  const s = stage.value;
  if (!s || !now) return;
  if (await s.load(now) && stage.value === s && art.value === now) s.show(now);
});
const offLost = onStageLost(() => {
  stop();
  if (alive && here.value) void start();
});
onBeforeUnmount(() => {
  alive = false;
  offLost();
  stop();
});

// ---------------------------------------------------------------- what the page is doing
/** The table covers the page this long after it was come to. */
const TABLE_MS = 1000;
const PAGE: Partial<StageState> = { focus: 0.6, veil: 0.6, lamps: 1, play: 1, dolly: 0, dev: 1, leak: 1, wide: 0 };
const WHOLE: Partial<StageState> = { focus: 0, veil: 0.5, lamps: 0.6, play: 1.7, dolly: 0, dev: 1, leak: 0, wide: 1 };
/** The paper it comes up out of. */
const BLANK: Partial<StageState> = { ...WHOLE, lamps: 0, play: 1.2, dolly: 0.05, dev: 0 };
const lookOf = () => (poster.value ? WHOLE : PAGE);
/** It comes up out of the paper, the lens draws back a little. */
function rise(s: Stage): void {
  groundRose.value = performance.now();
  void s.to({ dev: 1 }, 1700, E.linear, 60);
  void s.to({ lamps: 0.6 }, 900, E.flow, 900);
  void s.to({ dolly: 0 }, 2600, E.out);
}
watch(poster, (now, was) => {
  const s = stage.value;
  if (!s) return;
  if (reducedMotion.value) s.set(lookOf());
  else if (now === "opening") { s.set(BLANK); if (up.value) rise(s); }
  // The sidebar is on its way out before the picture comes over there, and comes back over paper (MainPanel.vue).
  else if (now) void s.to(WHOLE, 900, E.flow, 140);
  else void s.to(PAGE, was === "opening" ? 1250 : 1050);
});
/** It is dark under the window's keys: once it has come up. */
const come = ref(true);
let coming = 0;
watch([poster, up], ([now, on]) => {
  clearTimeout(coming);
  if (now !== "opening" || flat.value) { come.value = true; return; }
  come.value = false;
  if (on) coming = window.setTimeout(() => { come.value = true; }, 760);
}, { immediate: true });
watch([here, poster, come], () => {
  ground.whole = here.value && !!poster.value;
  ground.dark = here.value && come.value;
}, { immediate: true });
onBeforeUnmount(() => {
  clearTimeout(coming);
  ground.whole = ground.dark = false;
});
/** The table lies over it: it is not drawn meanwhile. */
const tabled = ref(false);
let tableTimer = 0;
watch(() => !!photoRun.value, (on) => {
  clearTimeout(tableTimer);
  tabled.value = false;
  if (on) tableTimer = window.setTimeout(() => { tabled.value = true; }, TABLE_MS);
});
onBeforeUnmount(() => clearTimeout(tableTimer));
// Under a dialog it stands still.
const seen = computed(() => pageActive.value && !photoOver.value && !tabled.value);
watch(seen, (on) => stage.value?.seen(on));
watch(groundKind, (kind) => stage.value?.light(kind ? memberLight(kind) : null));

const colour = (c: readonly number[]) => `rgb(${c.map((v) => Math.round(v * 255)).join(" ")})`;
/** What the key visual stands on, as CSS has it. */
const floor = computed(() => (art.value ? `linear-gradient(180deg, ${art.value.look.ground.map(colour).join(", ")})` : ""));

// ---------------------------------------------------------------- where the page's things are
/** The page's paper, as it is there. */
function paperOf(): Vec3 {
  const main = host.value?.closest(".main"), c = main && getComputedStyle(main).backgroundColor.match(/[\d.]+/g);
  return c && c.length >= 3 ? [Number(c[0]) / 255, Number(c[1]) / 255, Number(c[2]) / 255] : [1, 1, 1];
}
function place(): void {
  const r = host.value?.getBoundingClientRect(), s = stage.value;
  if (!r || !s) return;
  const foot = groundFoot.value, title = groundTitle.value;
  const side = host.value?.closest(".face")?.querySelector<HTMLElement>(".side")?.offsetWidth ?? 0;
  s.layout({
    side, paper: paperOf(),
    foot: foot && { x: foot.x - r.left, y: foot.y - r.top, css: foot.css },
    title: title && { x: title.x - r.left, y: title.y - r.top, w: title.w, h: title.h },
  });
}
watch([groundFoot, groundTitle], place);

function onMove(e: PointerEvent): void {
  const r = host.value?.getBoundingClientRect();
  if (!r?.width || reducedMotion.value) return;
  const at = (v: number, from: number, size: number) => Math.max(-1, Math.min(1, ((v - from) / size) * 2 - 1));
  stage.value?.pointer([at(e.clientX, r.left, r.width), at(e.clientY, r.top, r.height)]);
}
const onLeave = () => stage.value?.pointer(null);
let face: HTMLElement | null = null;
watch(host, (el) => {
  face?.removeEventListener("pointermove", onMove);
  face?.removeEventListener("pointerleave", onLeave);
  face = el?.closest<HTMLElement>(".face") ?? null;
  face?.addEventListener("pointermove", onMove);
  face?.addEventListener("pointerleave", onLeave);
});
</script>

<template>
  <Teleport defer to=".page-ground">
    <Transition name="photo-ground" :css="!reducedMotion">
      <div v-if="here" ref="host" class="photo-ground" :class="{ up, flat, blank: poster === 'opening' && !flat, calm: reducedMotion }">
        <div class="still" :style="{ '--mist': art ? colour(art.look.mist) : undefined }"><img :src="art?.focus.at(-2)" alt="" draggable="false" /></div>
        <div v-if="flat" class="whole" :class="{ on: poster }" :style="{ background: floor }">
          <img :src="art?.focus[0]" alt="" draggable="false" />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.photo-ground {
  position: absolute;
  inset: 0;
  overflow: hidden;
}
.photo-ground-enter-active {
  transition: opacity 380ms var(--ease-out);
}
.photo-ground-leave-active {
  transition: opacity 260ms var(--ease-in);
}
.photo-ground-enter-from,
.photo-ground-leave-to {
  opacity: 0;
}
/* About as the canvas draws it behind the page (stage.ts): whiter by its own colours toward the edges, then paper. */
.still {
  position: absolute;
  inset: 0 0 0 var(--side-w);
  overflow: hidden;
  -webkit-mask: linear-gradient(90deg, transparent 4%, #000 17%), linear-gradient(180deg, #000 54%, transparent 76%);
  -webkit-mask-composite: source-in;
  mask: linear-gradient(90deg, transparent 4%, #000 17%), linear-gradient(180deg, #000 54%, transparent 76%);
  mask-composite: intersect;
}
.still img {
  position: absolute;
  left: 50%;
  top: 0;
  width: 112%;
  min-height: 74%;
  object-fit: cover;
  translate: -49% 0;
}
.still::after {
  content: "";
  position: absolute;
  inset: 0;
  --pale: color-mix(in srgb, var(--mist) 50%, color-mix(in srgb, var(--c-50) 90%, transparent));
  --haze: color-mix(in srgb, var(--mist) 60%, transparent);
  background:
    linear-gradient(90deg, var(--pale) 8%, var(--haze) 17%, transparent 33%),
    linear-gradient(0deg, var(--pale) 30%, var(--haze) 44%, transparent 66%);
}
.blank .still {
  visibility: hidden;
}
.whole {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 700ms var(--ease-in-out);
}
.whole.on {
  opacity: 1;
}
.whole img {
  position: absolute;
  left: 50%;
  top: 0;
  width: 106%;
  translate: -50% 0;
  -webkit-mask: linear-gradient(180deg, #000 80%, transparent 99%);
  mask: linear-gradient(180deg, #000 80%, transparent 99%);
}
.photo-ground :deep(.stage-gl) {
  z-index: 1;
  opacity: 0;
  transition: opacity 320ms var(--ease-out);
}
.up :deep(.stage-gl) {
  opacity: 1;
}
.blank :deep(.stage-gl),
.calm :deep(.stage-gl),
.calm .whole {
  transition: none;
}
</style>
