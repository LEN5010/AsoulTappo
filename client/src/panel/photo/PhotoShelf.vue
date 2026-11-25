<script setup lang="ts">
// The shelf of the photocards' page: the box of the series on show, its cards coming up behind it and a sealed bag before
// it (photo/shelf.ts in the shared canvas). With more than one series on sale the keys beside it and the row of small
// boxes under it pick one. A box that was bought and not opened to the end waits here, with the bags that are left.
// Until the canvas draws, and where there is no WebGL 2, the series' poster stands there.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, shallowRef, watch } from "vue";
import { usePageActive } from "../../composables/usePageActive";
import { manifest } from "../../manifest";
import { photoItem, photoItems, type PhotoItem, type PhotoItemKind } from "../../photocards";
import { seriesArt, seriesMini, seriesPoster } from "../../photo/art";
import { mountScene, onPhotoLost, photoGl, type Mount } from "../../photo/engine";
import type { CardPlace } from "../../photo/place";
import { createShelf, SHELF_FOOT, SHELF_ROOM, type Face, type Shelf } from "../../photo/shelf";
import * as photoSound from "../../photo/sound";
import { photoView } from "../../stores/photocards";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import { groundFoot, resumeOnShelf, shelfStage } from "./shop";

const props = defineProps<{
  series: string;
  /** Every series on sale, in shelf order. */
  shelf: string[];
  busy: boolean;
  /** A dialog lies over the page: what is here stands still. */
  paused?: boolean;
  /** Not now: it comes in once this is over. */
  hold?: boolean;
  /** It stands on a stage (PhotoBackdrop.vue), not on paper. */
  staged?: boolean;
  /** The kind to show, while its row is pointed at. */
  kind: PhotoItemKind | null;
}>();
const emit = defineEmits<{ inspect: [item: PhotoItem, from: CardPlace]; show: [item: PhotoItem]; pick: [series: string] }>();

/** Another card comes up in the middle this often, until nobody has been there for so long. */
const CYCLE_MS = 4600, LEFT_MS = 120_000;
/** The poster shows if the canvas takes longer. */
const POSTER_MS = 420;
/** It comes in this long after it was held back: the title passes first. */
const HELD_MS = 280;
/** The table's textures are loaded this long after the shelf came in. */
const WARM_MS = 1400;

const pageActive = usePageActive();
const seen = computed(() => pageActive.value && !props.paused);
const view = computed(() => photoView(props.series));
const size = computed(() => view.value.box?.cards.length ?? view.value.cfg?.size ?? 20);
/** Bags left of a box that waits; null without one. */
const waiting = computed(() => (view.value.opening && view.value.box ? size.value - view.value.opened : null));

const host = ref<HTMLElement>();
const room = ref<HTMLElement>();
const scene = shallowRef<Shelf | null>(null);
/** The canvas has drawn. */
const up = ref(false);
const late = ref(false);
/** No WebGL 2: the poster stays. */
const flat = ref(false);
let mount: Mount | null = null;
let alive = true;
let starting = false;
let lateTimer = 0;
let warmTimer = 0;
let heldTimer = 0;

const faceOf = (item: PhotoItem): Face => ({ card: item.card, signed: item.kind === "sign" });
const facesOf = (items: readonly PhotoItem[]) => items.map(faceOf);
const itemOf = (card: string, signed: boolean) => photoItem(`${signed ? "sign" : "photo"}:${props.series}/${card}`);
const wake = () => mount?.wake();

/** The middle of the part of the host that can be seen, and how big things are there: as on the table, where there is
 *  room for that. */
const fitted = ref({ x: 0, y: 0, scale: 1 });
function fit() {
  const h = host.value?.getBoundingClientRect(), r = room.value?.getBoundingClientRect();
  const table = host.value?.closest(".panel")?.getBoundingClientRect();
  if (!h || !r || !r.width || !table) return fitted.value;
  const scale = Math.min(table.width / 960, table.height / 640, r.width / SHELF_ROOM.w, r.height / SHELF_ROOM.h);
  fitted.value = {
    x: r.left + r.width / 2 - h.left - h.width / 2, y: r.top + r.height / 2 - h.top - h.height / 2 - SHELF_ROOM.cy * scale, scale,
  };
  // In one column there is no floor: the sheet comes right under it.
  groundFoot.value = !props.staged || table.width <= 660 ? null : {
    x: r.left + r.width / 2 + SHELF_FOOT.x * scale, y: r.top + r.height / 2 + (SHELF_FOOT.y - SHELF_ROOM.cy) * scale, css: scale,
  };
  return fitted.value;
}

async function start(): Promise<void> {
  if (starting || mount || !alive || !host.value) return;
  starting = true;
  fit();
  clearTimeout(lateTimer);
  lateTimer = window.setTimeout(() => { late.value = !up.value && !props.hold; }, POSTER_MS);
  const gl = await photoGl();
  starting = false;
  if (!alive || mount || !host.value || !pageActive.value) return;
  const art = seriesArt(props.series);
  if (!gl || !art) {
    flat.value = true;
    return;
  }
  flat.value = false;
  scene.value?.dispose();
  photoSound.load();
  const s = createShelf(gl.gl, gl.kit, gl.painter, {
    art, cards: facesOf(photoItems(props.series)), calm: reducedMotion.value, sound: photoSound,
    rect: () => host.value!.getBoundingClientRect(), place: fit,
    on: (e) => {
      const item = itemOf(e.card, e.signed);
      if (item) emit("show", item);
    },
  });
  scene.value = s;
  s.waiting(waiting.value, size.value);
  await s.ready;
  if (!alive || scene.value !== s || !host.value || !pageActive.value) return;
  mount = mountScene(host.value, s);
  mount.show(seen.value);
  clearTimeout(lateTimer);
  if (!props.hold) comeIn(s);
  shelfStage.value = {
    pack: () => { wake(); return s.pack(); },
    unpack: () => { s.unpack(); wake(); },
    stow: () => { wake(); return s.stow(); },
    hand: () => s.hand(),
    place: (fresh) => s.place(fresh),
    back: (stands) => { s.back(stands); wake(); },
  };
  arm();
  // What a box is opened with, for the table to have it at once.
  warmTimer = window.setTimeout(() => {
    if (scene.value !== s) return;
    void gl.kit.load(art.id);
    void gl.kit.thumbs(art.id);
  }, WARM_MS);
}
function comeIn(s: Shelf): void {
  // Behind the poster it stands as the poster has it.
  if (late.value) s.stand();
  else s.enter();
  wake();
  up.value = true;
}
watch(() => props.hold, (on) => {
  clearTimeout(heldTimer);
  if (on) up.value = late.value = false;
  else heldTimer = window.setTimeout(() => { if (scene.value && mount && !up.value) comeIn(scene.value); }, reducedMotion.value ? 0 : HELD_MS);
});
function stop(): void {
  clearTimeout(cycle);
  clearTimeout(warmTimer);
  clearTimeout(lateTimer);
  clearTimeout(heldTimer);
  shelfStage.value = null;
  mount?.release();
  mount = null;
  scene.value?.dispose();
  scene.value = null;
  up.value = late.value = false;
}

// ---------------------------------------------------------------- what comes up
let cycle = 0;
let moved = performance.now();
const onWindowMove = () => { moved = performance.now(); };
onMounted(() => window.addEventListener("pointermove", onWindowMove, { passive: true }));
onBeforeUnmount(() => window.removeEventListener("pointermove", onWindowMove));
function arm(): void {
  clearTimeout(cycle);
  if (!seen.value || reducedMotion.value || !mount) return;
  cycle = window.setTimeout(() => {
    const there = performance.now() - moved < LEFT_MS && !document.hidden;
    if (there && !props.busy && !props.hold && scene.value?.over !== "card" && !scene.value?.held) {
      scene.value?.next();
      wake();
    }
    arm();
  }, CYCLE_MS);
}
watch(seen, (on) => {
  mount?.show(on);
  if (on) {
    onWindowMove();
    scene.value?.take(null);
  }
  wake();
  arm();
});
// Another series brings its own box: the one that leaves is not told of it.
watch([() => props.series, waiting, size] as const, ([id, n, of], [was]) => {
  const s = scene.value, art = seriesArt(id);
  if (!s) return;
  if (id === was) s.waiting(n, of);
  else if (art) {
    s.change(art, facesOf(photoItems(id)), props.shelf.indexOf(id) < props.shelf.indexOf(was) ? -1 : 1, n, of);
    arm();
  }
  wake();
});
watch(() => props.kind, (kind) => {
  scene.value?.only(kind ? facesOf(photoItems(props.series).filter((i) => i.kind === kind)) : null);
  wake();
  arm();
});
const offLost = onPhotoLost(() => {
  stop();
  flat.value = false;
  if (alive && pageActive.value) void start();
});
let observer: ResizeObserver | undefined;
let scroller: HTMLElement | null = null;
const onScroll = () => void fit();
onMounted(() => {
  observer = new ResizeObserver(() => void fit());
  if (host.value) observer.observe(host.value);
  scroller = host.value?.closest<HTMLElement>(".ui-scroll") ?? null;
  scroller?.addEventListener("scroll", onScroll, { passive: true });
  void start();
});
watch(() => props.staged, () => void fit());
// A window that comes up may tell so only after the page was shown.
onActivated(() => void start());
watch(pageActive, (on) => { if (on) void start(); });
// The canvas goes to whichever page shows photocards next.
onDeactivated(stop);
onBeforeUnmount(() => {
  alive = false;
  offLost();
  observer?.disconnect();
  scroller?.removeEventListener("scroll", onScroll);
  groundFoot.value = null;
  stop();
});

// ---------------------------------------------------------------- pointer
const cursor = ref("");
const at = (e: PointerEvent): [number, number, number] => {
  const r = host.value!.getBoundingClientRect();
  return [e.clientX - r.left - r.width / 2, e.clientY - r.top - r.height / 2, e.timeStamp];
};
function onMove(e: PointerEvent) {
  const s = scene.value;
  if (!s) return;
  s.move(...at(e));
  cursor.value = props.busy ? "" : s.held ? "grabbing"
    : { box: waiting.value === null ? "grab" : "pointer", card: "pointer", bag: "", none: "" }[s.over];
  wake();
}
function onLeave() {
  scene.value?.leave();
  wake();
}
function onDown(e: PointerEvent) {
  if (e.button !== 0 || props.busy) return;
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  photoSound.wake();
  scene.value?.down(...at(e));
  wake();
}
function onUp(e: PointerEvent) {
  const hit = scene.value?.up();
  if (scene.value) onMove(e);
  // A press the system took away (to scroll, say) is not a tap.
  if (!hit || props.busy || e.type === "pointercancel") return;
  if (hit.kind === "box" && waiting.value !== null) void resumeOnShelf();
  else if (hit.kind === "card") {
    const item = itemOf(hit.card, hit.signed);
    if (!item) return;
    scene.value?.take({ card: hit.card, signed: hit.signed });
    emit("inspect", item, hit.place);
  }
}

// ---------------------------------------------------------------- the other series
const nameOf = (id: string) => manifest.photocards.find((s) => s.id === id)?.name ?? id;
const index = computed(() => props.shelf.indexOf(props.series));
function step(d: -1 | 1) {
  const id = props.shelf[(index.value + d + props.shelf.length) % props.shelf.length];
  if (id && id !== props.series) emit("pick", id);
}
const look = (id: string) => seriesArt(id)?.look;
/** The poster lies where the canvas draws the same. */
const posterStyle = computed(() => ({
  left: `calc(50% + ${fitted.value.x}px)`, top: `calc(50% + ${fitted.value.y}px)`, "--unit": `${fitted.value.scale}px`,
}));
</script>

<template>
  <div class="photo-shelf" :class="{ many: shelf.length > 1, up, flat, staged, calm: reducedMotion }">
    <div v-if="!staged" class="wash" aria-hidden="true" :style="{ '--photo-wash': look(series)?.wash }"></div>
    <div
      ref="host" class="glass" :style="{ cursor }" @pointermove="onMove" @pointerleave="onLeave" @pointerdown="onDown" @pointerup="onUp"
      @pointercancel="onUp"
    >
      <span ref="room" class="room" aria-hidden="true"></span>
      <img
        v-if="(flat || late && waiting === null) && !hold && seriesPoster(series)" class="poster" :src="seriesPoster(series)" :style="posterStyle" alt="" draggable="false"
      />
    </div>
    <template v-if="shelf.length > 1">
      <button type="button" class="turn prev ui-btn small" :class="{ ghost: !staged }" aria-label="上一盒" :disabled="busy" @click="step(-1)"><Icon name="back" :size="16" /></button>
      <button type="button" class="turn next ui-btn small" :class="{ ghost: !staged }" aria-label="下一盒" :disabled="busy" @click="step(1)"><Icon name="back" :size="16" /></button>
      <div class="lineup" role="tablist" aria-label="小卡系列">
        <button
          v-for="id in shelf" :key="id" type="button" role="tab" class="mini" :class="{ on: id === series }" :aria-selected="id === series"
          :disabled="busy" :title="nameOf(id)" :aria-label="nameOf(id)" @click="id !== series && emit('pick', id)"
        >
          <img v-if="seriesMini(id)" :src="seriesMini(id)" alt="" draggable="false" />
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.photo-shelf {
  position: relative;
  z-index: 1;
}
@property --photo-wash {
  syntax: "<color>";
  inherits: true;
  initial-value: transparent;
}
/* The light behind the box, in the series' colour; gone well before the page's left edge and the text. */
.wash {
  transition: --photo-wash 560ms var(--ease-in-out);
  position: absolute;
  left: 0;
  right: -30px;
  top: -4%;
  bottom: 0;
  background: radial-gradient(closest-side, color-mix(in srgb, var(--photo-wash) 46%, transparent), transparent 92%);
  pointer-events: none;
}
/* The canvas reaches the page's left edge and under the sheet, so nothing of the fan is cut short. */
.glass {
  position: absolute;
  left: -34px;
  right: -66px;
  top: -18px;
  bottom: -10px;
  overflow: hidden;
  touch-action: pan-y;
}
.glass :deep(.photo-gl) {
  opacity: 0;
  transition: opacity 260ms var(--ease-out);
}
.up .glass :deep(.photo-gl) {
  opacity: 1;
}
/* What of the canvas is neither under the sheet nor under the small boxes. */
.room {
  position: absolute;
  inset: 6px 84px 6px 0;
  pointer-events: none;
}
.many .room {
  bottom: 58px;
}
.poster {
  position: absolute;
  width: calc(var(--unit) * 480);
  height: calc(var(--unit) * 580);
  max-width: none;
  translate: -50% -50%;
  transition: opacity 260ms var(--ease-out);
  animation: poster-in 240ms var(--ease-out) backwards;
}
.up .poster {
  opacity: 0;
}
@keyframes poster-in { from { opacity: 0; } }
.calm .poster,
.calm .glass :deep(.photo-gl) {
  transition: none;
}
.turn {
  position: absolute;
  top: 46%;
  width: 28px;
  height: 44px;
  padding: 0;
}
.prev {
  left: -22px;
}
.next {
  right: 24px;
}
.next svg {
  transform: rotate(180deg);
}
/* A row of small boxes, the one on show ringed. */
.lineup {
  position: absolute;
  left: 0;
  right: 18px;
  bottom: 0;
  display: flex;
  justify-content: center;
  gap: 8px;
}
.mini {
  width: 38px;
  height: 48px;
  padding: 3px;
  border: 0;
  border-radius: var(--radius-s);
  background: none;
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast), background var(--dur-fast);
}
.mini:hover:not(:disabled) {
  transform: translateY(-2px);
}
.mini.on {
  background: var(--c-100);
  box-shadow: 0 0 0 2px var(--c-500);
}
.mini:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: 3px;
}
.mini img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
@container panel (max-width: 660px) {
  .glass {
    right: -16px;
    left: -16px;
  }
  .room {
    right: 0;
  }
}
</style>
