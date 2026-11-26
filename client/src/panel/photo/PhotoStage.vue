<script setup lang="ts">
// The photocards' page in the resonance page (官周小卡): the box and what comes in it on the left (PhotoShelf.vue), the
// series on a sheet of paper beside it: how much of it the save holds, then a row a kind with its odds and one pip a
// card. Every card of the series goes by underneath. A limited pool's tabs, the page's bar and its dialogs are the
// resonance page's.
// A series with a key visual has its page on a stage (PhotoBackdrop.vue), with the event's title as its own. The page
// opens on the key visual alone, over the whole panel: it comes up out of the paper, the title lights up on it, then the
// focus goes over to the box, and the title to its place. Pressing the title brings the key visual back.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { usePageActive } from "../../composables/usePageActive";
import { getCharacter } from "../../characters";
import { manifest } from "../../manifest";
import { isWidePhoto, photoItems, photoOdds, type PhotoItem, type PhotoItemKind } from "../../photocards";
import { seriesArt } from "../../photo/art";
import { placeOf, type CardPlace } from "../../photo/place";
import { photoView } from "../../stores/photocards";
import { reducedMotion } from "../../stores/theme";
import PetBust from "../PetBust.vue";
import PhotoShelf from "./PhotoShelf.vue";
import PhotoThumb from "./PhotoThumb.vue";
import { PHOTO_KINDS, PHOTO_KIND_LABEL, photoName } from "./labels";
import { oddsText } from "./odds";
import { groundKind, groundRose, groundTitle, groundUp, opened, openPage, poster } from "./shop";

const props = defineProps<{
  /** The series on show. */
  series: string;
  /** Every series on sale, in shelf order. */
  shelf: string[];
  /** A box is being bought or opened over the page. */
  busy: boolean;
  /** A dialog lies over the page. */
  paused?: boolean;
}>();
const emit = defineEmits<{
  inspect: [card: { item: PhotoItem; list: readonly PhotoItem[]; from?: CardPlace }];
  album: [kind: PhotoItemKind];
  pick: [series: string];
}>();

const pageActive = usePageActive();
const still = computed(() => !pageActive.value || props.busy || props.paused || !!poster.value);
const view = computed(() => photoView(props.series));
const info = computed(() => manifest.photocards.find((s) => s.id === props.series));
const items = computed(() => photoItems(props.series));
const size = computed(() => view.value.cfg?.size ?? 0);

/** What the pips show. It follows the save's cards, but not while the page is covered: they light up one by one once it
 *  is back in sight. */
const lit = ref<ReadonlySet<string>>(new Set(view.value.owned));
const popped = ref<ReadonlySet<string>>(new Set());
const STEP_MS = 90;
/** The save was there when it was last looked at. */
let known = !!view.value.save;
let timers: number[] = [];
const clearTimers = () => { for (const t of timers) window.clearTimeout(t); timers = []; };
watch([() => props.series, () => view.value.owned, () => props.busy], ([series, owned, busy], before) => {
  if (busy) return;
  clearTimers();
  const fresh = items.value.filter((i) => owned.has(i.id) && !lit.value.has(i.id));
  // Another series, a first load, or cards lost with a reset: shown at once.
  const jump = series !== before?.[0] || reducedMotion.value || !pageActive.value || !known
    || [...lit.value].some((id) => !owned.has(id));
  known = !!view.value.save;
  if (jump || !fresh.length) {
    lit.value = new Set(owned);
    popped.value = new Set();
    return;
  }
  popped.value = new Set();
  fresh.forEach((item, i) => timers.push(window.setTimeout(() => {
    lit.value = new Set([...lit.value, item.id]);
    popped.value = new Set([...popped.value, item.id]);
  }, 420 + i * STEP_MS)));
});
onBeforeUnmount(clearTimers);

const got = computed(() => items.value.filter((i) => lit.value.has(i.id)).length);
const fill = computed(() => `${items.value.length ? (got.value / items.value.length) * 100 : 0}%`);
const odds = computed(() => (view.value.cfg ? photoOdds(view.value.cfg) : null));

const rows = computed(() => PHOTO_KINDS.map((kind) => {
  const mine = items.value.filter((i) => i.kind === kind);
  const groups = new Map<string, PhotoItem[]>();
  for (const item of mine) {
    const key = item.characters.join();
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  const held = mine.filter((i) => lit.value.has(i.id));
  const rate = odds.value && (kind === "solo" ? 100 - odds.value.rare : odds.value[kind]);
  return {
    kind, label: PHOTO_KIND_LABEL[kind], got: held.length, total: mine.length, rate: rate === null ? "" : oddsText(rate),
    cover: held.at(-1) ?? mine[0], groups: [...groups.values()],
  };
}));

/** The kind the shelf shows while its row is pointed at. */
const pointed = ref<PhotoItemKind | null>(null);
watch(pointed, (kind) => { groundKind.value = kind; });

// ---------------------------------------------------------------- the stage
const stage = computed(() => seriesArt(props.series)?.stage ?? null);
const rgb = (c: readonly number[]) => `rgb(${c.map((v) => Math.round(v * 255)).join(" ")})`;
/** What the pool keys stand on, and the key visual's own dark and mist for them (`.on-poster`). */
const ground = computed<"paper" | "poster">(() => (stage.value ? "poster" : "paper"));
const tint = computed(() => (stage.value
  ? { "--poster-dark": rgb(stage.value.look.dark), "--poster-mist": rgb(stage.value.look.mist) }
  : undefined));
const rootEl = ref<HTMLElement>();
const slotEl = ref<HTMLElement>();
/** Where the title goes while the key visual is seen by itself, from its place on the page. */
const away = ref({ x: 0, y: 0, k: 1 });
/** The title, its light off: until the page opens. */
const unlit = ref(false);
const lighting = ref(false);
/** When the title lights up and when the focus goes over to the box, from when the key visual began to come up; and how
 *  long the page waits for that. */
const OPENING = { title: 1150, over: 2750, patience: 1400 };
/** The title on the key visual: how wide, in what part of the panel at least, how far from the page's left edge, where it
 *  would be cut off, and how far up from the panel's bottom. */
const TITLE = { wide: 580, part: 0.42, clear: 22, below: 44 / 700 };
function measure(): void {
  const slot = slotEl.value, main = rootEl.value?.closest(".main"), ground = main?.querySelector(".page-ground")?.getBoundingClientRect();
  const r = slot?.getBoundingClientRect(), page = rootEl.value?.getBoundingClientRect();
  if (!r?.width || !page || !ground?.width) return;
  groundTitle.value = { x: r.left, y: r.top, w: r.width, h: r.height };
  const room = ground.width - 2 * (page.left - ground.left + TITLE.clear);
  const w = Math.min(Math.max(TITLE.wide, ground.width * TITLE.part), room), k = w / r.width;
  away.value = {
    x: ground.left + (ground.width - w) / 2 - r.left, y: ground.bottom - ground.height * TITLE.below - r.height * k - r.top, k,
  };
}
let cues: number[] = [];
const cue = (ms: number, fn: () => void) => cues.push(window.setTimeout(fn, ms));
const dropCues = () => { for (const t of cues) window.clearTimeout(t); cues = []; };
/** The focus goes over to the box, from wherever things are. */
function toPage(): void {
  dropCues();
  unlit.value = false;
  poster.value = "";
}
if (stage.value && pageActive.value && !reducedMotion.value) openPage(props.series);
if (poster.value) {
  opened.add(props.series);
  unlit.value = true;
}
async function play(): Promise<void> {
  cue(OPENING.patience, () => { if (!groundUp.value) toPage(); });
  if (!groundUp.value) {
    await new Promise<void>((done) => { const off = watch([groundUp, poster], () => { off(); done(); }); });
  }
  if (poster.value !== "opening") return;
  dropCues();
  const gone = performance.now() - groundRose.value;
  cue(OPENING.title - gone, () => { unlit.value = false; lighting.value = true; });
  cue(OPENING.over - gone, toPage);
}
function showPoster(): void {
  if (!stage.value || props.busy || poster.value) return;
  measure();
  pointed.value = null;
  poster.value = "look";
}
/** Anything pressed brings the page back. */
function onKey(e: KeyboardEvent): void {
  if (!poster.value || e.metaKey || e.ctrlKey || e.altKey || e.key === "Shift") return;
  e.preventDefault();
  e.stopImmediatePropagation();
  toPage();
}
watch(poster, (on) => {
  if (on) window.addEventListener("keydown", onKey, true);
  else {
    window.removeEventListener("keydown", onKey, true);
    dropCues();
    unlit.value = lighting.value = false;
  }
}, { immediate: true });
watch(pageActive, (on) => { if (!on) toPage(); });
// Another series has a title of its own.
watch(() => props.series, toPage);
function onTitle(): void {
  measure();
  measurePeek();
}
onMounted(() => { if (poster.value === "opening") void play(); });
onBeforeUnmount(() => {
  toPage();
  window.removeEventListener("keydown", onKey, true);
  groundTitle.value = groundKind.value = null;
});

// The members on the front card of the shelf look over the top of the sheet, in the room the title leaves.
const front = ref<PhotoItem>();
const peek = computed(() => {
  const busts = (front.value?.characters ?? []).slice(0, 2).flatMap((name) => {
    const bg = getCharacter(name)?.bg;
    return bg ? [{ name, bg }] : [];
  });
  return busts.length ? { key: busts.map((b) => b.name).join("+"), busts } : null;
});
const PEEK_MAX = 92;
const PEEK_MIN = 52;
const PEEK_MARGIN = 22;
const titleEl = ref<HTMLElement>();
const sheetEl = ref<HTMLElement>();
const peekRoom = ref(0);
function measurePeek() {
  if (!titleEl.value || !sheetEl.value) return;
  const glyphs = document.createRange();
  glyphs.selectNodeContents(titleEl.value);
  peekRoom.value = sheetEl.value.getBoundingClientRect().right - glyphs.getBoundingClientRect().right;
}
const peekSize = computed(() => {
  const span = (peek.value?.busts.length ?? 1) > 1 ? 1.32 : 1;
  const room = Math.min(PEEK_MAX, (peekRoom.value - PEEK_MARGIN) / span);
  return room >= PEEK_MIN ? Math.round(room) : 0;
});

// The strip of every card, gliding by.
const stripEl = ref<HTMLElement>();
const groupEl = ref<HTMLElement[]>();
const stripFocus = ref(false);
const stripWidth = ref(0);
const roomWidth = ref(0);
const glides = computed(() => !reducedMotion.value && stripWidth.value > roomWidth.value);
const gliding = computed(() => glides.value && !still.value && !stripFocus.value);
const pace = computed(() => `${Math.max(10, stripWidth.value / 22)}s`);
/** The strip mixes the kinds, so any stretch of it has some of each. */
const strip = computed(() => {
  const byKind = PHOTO_KINDS.map((k) => items.value.filter((i) => i.kind === k));
  const out: { item: PhotoItem; at: number }[] = [];
  for (const list of byKind) list.forEach((item, i) => out.push({ item, at: (i + 0.5) / list.length }));
  return out.sort((a, b) => a.at - b.at).map((o) => o.item);
});
function look(item: PhotoItem, e: Event) {
  emit("inspect", { item, list: items.value, from: placeOf(e.currentTarget as HTMLElement) });
}
let resize: ResizeObserver | undefined;
onMounted(() => {
  resize = new ResizeObserver(() => {
    stripWidth.value = groupEl.value?.[0]?.offsetWidth ?? 0;
    roomWidth.value = stripEl.value?.clientWidth ?? 0;
    measurePeek();
    measure();
  });
  for (const el of [stripEl.value, groupEl.value?.[0], sheetEl.value, rootEl.value]) if (el) resize.observe(el);
  measure();
  void document.fonts.ready.then(measurePeek);
});
onBeforeUnmount(() => resize?.disconnect());
</script>

<template>
  <section
    ref="rootEl" class="photo-stage" :class="{ calm: reducedMotion, glides, run: gliding, staged: stage, poster: stage && poster }"
    :style="{ '--pace': pace }"
  >
    <PhotoShelf
      class="shelf" :series="series" :shelf="shelf" :busy="busy" :paused="paused" :kind="pointed" :hold="!!poster" :staged="!!stage"
      :inert="!!poster"
      @inspect="(item, from) => emit('inspect', { item, list: items, from })" @show="front = $event" @pick="emit('pick', $event)"
    />

    <div class="info">
      <header class="title">
        <div class="switch" :inert="!!poster" :style="tint">
          <slot name="switch" :ground="ground"><span class="ui-eyebrow">PHOTOCARDS</span></slot>
        </div>
        <Transition name="head" mode="out-in" :css="!reducedMotion" @enter="onTitle">
          <div v-if="stage" :key="stage.id">
            <div ref="slotEl" class="slot">
              <button
                type="button" class="event-title" :class="{ unlit, lighting }" :disabled="busy" :aria-label="`${info?.name} 主视觉`"
                :style="{ '--x': `${away.x}px`, '--y': `${away.y}px`, '--k': away.k, '--art': `url(${stage.title})` }"
                @click="poster ? toPage() : showPoster()"
              >
                <img :src="stage.title" :alt="info?.name" draggable="false" />
                <i class="gleam" aria-hidden="true"></i>
              </button>
            </div>
            <h3 class="small">官周小卡</h3>
          </div>
          <h3 v-else ref="titleEl">官周小卡</h3>
        </Transition>
      </header>

      <div ref="sheetEl" class="sheet" :inert="!!poster">
        <div v-if="peekSize && !stage" class="peek" :style="{ '--peek-w': `${peekSize}px` }" aria-hidden="true">
          <Transition name="peek" mode="out-in" :css="!reducedMotion">
            <span v-if="peek" :key="peek.key" class="peek-row" :class="{ pair: peek.busts.length > 1 }">
              <PetBust v-for="b in peek.busts" :key="b.name" class="peek-bust" :src="b.bg" />
            </span>
          </Transition>
        </div>

        <Transition name="series" mode="out-in" :css="!reducedMotion">
          <header :key="series" class="series" :class="{ staged: stage }">
            <p class="event">{{ info?.event }}</p>
            <h4 v-if="!stage">{{ info?.name }}</h4>
            <p class="facts"><span v-if="size">每盒 {{ size }} 张</span><span v-if="view.cfg && view.cfg.sure !== false">必有稀有</span></p>
            <p class="total"><b>{{ got }}</b><i>/ {{ items.length }}</i></p>
            <span class="bar" aria-hidden="true"><i :style="{ width: fill }"></i></span>
          </header>
        </Transition>

        <ul class="kinds" @pointerleave="pointed = null">
          <li v-for="r in rows" :key="r.kind">
            <button
              type="button" class="kind" :class="[`k-${r.kind}`, { done: r.got === r.total }]" :disabled="busy"
              :aria-label="`${r.label} ${r.got}/${r.total}`" @pointerenter="pointed = r.kind" @focus="pointed = r.kind"
              @blur="pointed = null" @click="emit('album', r.kind)"
            >
              <span class="cover"><PhotoThumb v-if="r.cover" :item="r.cover" /></span>
              <span class="name"><em>{{ r.label }}</em><b>{{ r.got }}</b><i>/{{ r.total }}</i></span>
              <span class="rate">{{ r.rate }}</span>
              <span class="pips" aria-hidden="true">
                <span v-for="(g, k) in r.groups" :key="k" class="set">
                  <i v-for="item in g" :key="item.id" :class="{ on: lit.has(item.id), pop: popped.has(item.id) }"></i>
                </span>
              </span>
            </button>
          </li>
        </ul>
      </div>

      <div
        ref="stripEl" class="strip" role="region" aria-label="本期小卡" :inert="!!poster"
        @pointerdown="stripFocus = false"
        @focusin="stripFocus = ($event.target as HTMLElement).matches(':focus-visible')"
        @focusout="stripFocus = ($event.currentTarget as HTMLElement).contains($event.relatedTarget as Node | null)"
      >
        <div class="track">
          <div v-for="copy in reducedMotion ? 1 : 2" :key="copy" ref="groupEl" class="lap" :aria-hidden="copy === 2 ? true : undefined">
            <button
              v-for="item in strip" :key="item.id" type="button" class="pass" :class="{ wide: isWidePhoto(item) }" :tabindex="copy === 2 ? -1 : undefined"
              :disabled="busy" :title="photoName(item)" :aria-label="`查看${photoName(item)}`" @click="look(item, $event)"
            >
              <PhotoThumb :item="item" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <Teleport defer to=".panel-overlay">
      <button v-if="stage && poster" type="button" class="photo-curtain" data-overlay aria-label="返回" @click="toPage"></button>
    </Teleport>
  </section>
</template>

<style scoped>
.photo-stage {
  /* The same measures as the standing pool's page, so switching between them moves nothing (PoolStage.vue). */
  --hero-h: max(196px, min(0.66 * (100cqh - 46px), 100cqh - 296px, 42cqw));
  --card-w: calc(var(--hero-h) * 0.7);
  --stage-gap: 28px;
  position: relative;
  isolation: isolate;
  flex: 1 0 auto;
  display: flex;
  align-items: stretch;
  gap: var(--stage-gap);
  padding: 18px 26px 10px 34px;
  box-sizing: border-box;
}
.shelf {
  flex: none;
  width: calc(var(--card-w) * 1.3);
}
.info {
  position: relative;
  z-index: 2;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.title .ui-eyebrow {
  margin-bottom: 8px;
  font-size: 13px;
  letter-spacing: 0.22em;
}
h3 {
  margin: 0;
  font: 800 clamp(36px, 5.2cqw, 48px)/1.04 var(--font);
  letter-spacing: 0.03em;
}

/* On a stage the event's title is the page's, and the pool's name stands by it. */
.staged .title {
  position: relative;
}
.slot {
  width: clamp(220px, 33.7cqw, 330px);
  aspect-ratio: 1500 / 438;
  margin: -8px 0 -4px;
}
.event-title {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  transform-origin: 0 0;
  filter: drop-shadow(0 0 1px rgba(20, 6, 60, 0.9)) drop-shadow(0 2px 14px rgba(176, 138, 255, 0.8));
  transition: transform 920ms cubic-bezier(0.58, 0.02, 0.16, 1), filter var(--dur-base);
}
.event-title:disabled {
  cursor: default;
}
.event-title img {
  display: block;
  width: 100%;
  height: 100%;
  transition: translate var(--dur-base) var(--ease-out);
}
.event-title:hover:not(:disabled) {
  filter: brightness(1.08) drop-shadow(0 0 1px rgba(20, 6, 60, 0.9)) drop-shadow(0 2px 16px rgba(190, 156, 255, 0.95));
}
.event-title:hover:not(:disabled) img {
  translate: 0 -1px;
}
.event-title:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
  border-radius: var(--radius-s);
}
.gleam {
  position: absolute;
  inset: 0;
  background: linear-gradient(100deg, transparent 42%, rgba(255, 255, 255, 0.95) 50%, transparent 58%) 130% 0 / 260% 100% no-repeat;
  -webkit-mask: var(--art) center / 100% 100% no-repeat;
  mask: var(--art) center / 100% 100% no-repeat;
  pointer-events: none;
}
.event-title:hover:not(:disabled) .gleam {
  animation: title-gleam 900ms var(--ease-in-out);
}
.poster .event-title {
  transform: translate(var(--x), var(--y)) scale(var(--k));
  transition: transform 760ms cubic-bezier(0.5, 0, 0.14, 1), filter var(--dur-base);
}
.event-title.unlit {
  opacity: 0;
  transition: none;
}
/* Its light comes on from the left, the edge of it bright. */
.lighting img {
  -webkit-mask: linear-gradient(100deg, #000 46%, transparent 54%) 0 0 / 230% 100% no-repeat;
  mask: linear-gradient(100deg, #000 46%, transparent 54%) 0 0 / 230% 100% no-repeat;
  animation: title-on 1000ms var(--ease-in-out) backwards;
}
.lighting .gleam {
  animation: title-gleam 1080ms var(--ease-in-out);
}
@keyframes title-on {
  from {
    -webkit-mask-position: 100% 0;
    mask-position: 100% 0;
  }
}
@keyframes title-gleam {
  from { background-position: 130% 0; }
  to { background-position: -30% 0; }
}
h3.small {
  position: absolute;
  right: 0;
  bottom: 9px;
  font: 800 var(--fs-strong)/1 var(--font);
  letter-spacing: 0.1em;
  color: #fff;
  text-shadow: 0 1px 8px rgba(16, 6, 46, 0.8);
}
/* While the key visual is seen by itself what lies on it is out of the way; then it comes back, the box first. */
.staged .switch,
.staged .small,
.staged .sheet,
.staged .strip {
  transition: opacity 420ms var(--ease-out) 620ms, transform 680ms var(--ease-out) 580ms;
}
.staged .strip {
  transition-delay: 740ms, 700ms;
}
.poster .switch,
.poster .small,
.poster .sheet,
.poster .strip {
  opacity: 0;
  transition: opacity 240ms var(--ease-out), transform 340ms var(--ease-in);
}
.poster .sheet {
  transform: translateX(30px);
}
.poster .strip {
  transform: translateY(18px);
}
.poster .info {
  pointer-events: none;
}
/* Over the whole panel but its window keys: the key visual goes back to the page wherever it is pressed. */
.photo-curtain {
  position: absolute;
  inset: 46px 0 0;
  border: 0;
  background: none;
  cursor: pointer;
  outline: none;
}
.photo-stage.staged.pool-enter-from {
  transform: none;
}

/* One paper sheet over the shelf's right edge. */
.sheet {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-left: calc(var(--stage-gap) * -1 - 18px);
  padding: 13px 18px 10px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.peek {
  position: absolute;
  z-index: -1;
  right: 8px;
  bottom: calc(100% - var(--peek-w) * 0.08);
  width: var(--peek-w);
  height: calc(var(--peek-w) * 1.04);
  pointer-events: none;
}
.peek-row {
  position: absolute;
  inset: 0;
  display: block;
}
.peek-bust {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  rotate: 7deg;
  filter: var(--contour) drop-shadow(0 2px 3px rgba(var(--shadow-rgb), 0.18));
}
.pair .peek-bust {
  inset: 4% 0 0 16%;
  width: 84%;
  height: 96%;
}
.pair .peek-bust + .peek-bust {
  z-index: -1;
  inset: 0 46% 4% -30%;
  rotate: -8deg;
}
.peek-enter-active {
  transition: translate 520ms var(--ease-pop);
}
.peek-leave-active {
  transition: translate 200ms var(--ease-in);
}
.peek-enter-from,
.peek-leave-to {
  translate: 0 100%;
}

/* The series: where it was sold, its name, what a box is, and how much of it is held. */
.series {
  flex: none;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 3px 12px;
}
.series p,
.series h4 {
  margin: 0;
}
.event {
  grid-column: 1;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.series h4 {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 clamp(22px, 2.8cqw, 27px)/1.2 var(--font);
  letter-spacing: 0.02em;
}
.facts {
  grid-area: 1 / 2;
  display: flex;
  gap: 8px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
  white-space: nowrap;
}
.facts span + span::before {
  content: "";
  display: inline-block;
  width: 3px;
  height: 3px;
  margin-right: 8px;
  border-radius: 50%;
  vertical-align: 3px;
  background: var(--c-300);
}
.total {
  justify-self: end;
  white-space: nowrap;
}
.total b {
  font: 800 34px/0.9 var(--font-latin);
}
.total i {
  margin-left: 6px;
  font: 800 18px/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.bar {
  grid-column: 1 / 3;
  height: 8px;
  margin-top: 4px;
  border-radius: 4px;
  background: var(--c-100);
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--c-400), var(--c-500));
  transition: width var(--dur-stage) var(--ease-out);
}
/* The title says the name; what is left of it stands in two lines beside the count. */
.series.staged .event {
  grid-area: 1 / 1;
  font-size: var(--fs-strong);
  font-weight: 800;
  color: var(--ink);
}
.series.staged .facts {
  grid-area: 2 / 1;
}
.series.staged .total {
  grid-area: 1 / 2 / 3 / 3;
  align-self: end;
}
.head-enter-active {
  transition: opacity 300ms;
}
.head-leave-active {
  transition: opacity 140ms var(--ease-in);
}
.head-enter-from,
.head-leave-to {
  opacity: 0;
}
.series-enter-active {
  transition: opacity 260ms, transform 360ms var(--ease-out);
}
.series-leave-active {
  transition: opacity 140ms var(--ease-in);
}
.series-enter-from {
  opacity: 0;
  transform: translateX(14px);
}
.series-leave-to {
  opacity: 0;
}

/* A row a kind, a hairline between them: one of its cards a little askew, its name and count, what it is at a bag, and
 * a bar of a pip a card, those of the same members together. */
.kinds {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  margin: 0;
  padding: 0;
  list-style: none;
}
.kinds li {
  flex: 1 1 0;
  display: flex;
}
.kind {
  /* The lines' heights are their own, so a tall card beside them does not spread them. */
  --line: 20px;
  --pip: 7px;
  flex: 1;
  display: grid;
  grid-template: var(--line) var(--pip) / 52px minmax(0, 1fr) auto;
  align-content: center;
  align-items: center;
  gap: 9px 14px;
  min-width: 0;
  min-height: 51px;
  box-sizing: border-box;
  margin: 0;
  padding: 5px 0;
  border: 0;
  border-top: 1px solid var(--c-100);
  background: none;
  color: var(--ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.kind:disabled {
  cursor: default;
}
.kind:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: 2px;
  border-radius: var(--radius-s);
}
.cover {
  grid-row: 1 / 3;
  justify-self: center;
  display: block;
  width: 30px;
  rotate: -5deg;
  box-shadow: 0 3px 7px -3px rgba(var(--shadow-rgb), 0.5);
  transition: rotate var(--dur-base) var(--ease-out), translate var(--dur-base) var(--ease-out), box-shadow var(--dur-base);
}
.k-duo .cover,
.k-group .cover {
  width: 50px;
  rotate: -3deg;
}
.kind:hover:not(:disabled) .cover,
.kind:focus-visible .cover {
  rotate: 0deg;
  translate: 0 -2px;
  box-shadow: 0 0 0 1.5px #fff, 0 6px 12px -4px rgba(var(--shadow-rgb), 0.5);
}
.calm .cover {
  rotate: 0deg;
  translate: none;
}
.name {
  display: flex;
  align-items: baseline;
  gap: 3px;
  white-space: nowrap;
}
.name em {
  margin-right: 6px;
  font: 800 var(--fs-strong)/1 var(--font);
  font-style: normal;
}
.name b {
  font: 800 19px/1 var(--font-latin);
}
.name i {
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.done .name b {
  color: var(--c-700);
}
.rate {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink-2);
}
/* One colour says what is held, the same as the bar above; gold is what a signature is written in. */
.pips {
  grid-column: 2 / 4;
  display: flex;
  gap: 9px;
  min-width: 0;
}
.set {
  flex: 1 1 0;
  display: flex;
  gap: 3px;
}
.pips i {
  flex: 1 1 0;
  height: var(--pip);
  border-radius: 2px;
  background: var(--c-100);
}
.pips i.on {
  background: var(--c-500);
}
.k-sign .pips i.on {
  background: var(--grad-gold);
}
.pips i.pop {
  transform-origin: 0 50%;
  animation: pip-pop 380ms var(--ease-out) both;
}
.calm .pips i.pop {
  animation: none;
}
@keyframes pip-pop {
  from { scale: 0 1; }
}

/* Every card of the series, gliding by; a card comes up under the pointer. */
.strip {
  flex: none;
  min-width: 0;
  overflow-x: auto;
  padding: 6px 0 4px;
  scrollbar-width: none;
}
.strip::-webkit-scrollbar { display: none; }
.glides .strip {
  overflow: hidden;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 28px, #000 calc(100% - 28px), transparent);
  mask-image: linear-gradient(90deg, transparent, #000 28px, #000 calc(100% - 28px), transparent);
}
.track {
  display: flex;
  width: max-content;
}
.glides .track {
  animation: strip-glide var(--pace, 60s) linear infinite;
  animation-play-state: paused;
}
.photo-stage.run .track {
  animation-play-state: running;
}
.strip:hover .track {
  animation-play-state: paused;
}
.lap {
  flex: none;
  display: flex;
  gap: 9px;
  padding-right: 9px;
}
.pass {
  --pass-h: 62px;
  flex: none;
  width: calc(var(--pass-h) * 54 / 86);
  height: var(--pass-h);
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  box-shadow: 0 3px 8px -3px rgba(var(--shadow-rgb), 0.42);
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base);
}
.pass:disabled {
  cursor: default;
}
.pass.wide {
  width: calc(var(--pass-h) * 86 / 54);
}
.pass:hover:not(:disabled) {
  transform: translateY(-5px);
  box-shadow: 0 9px 14px -6px rgba(var(--shadow-rgb), 0.5);
}
.pass:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: 2px;
}
@keyframes strip-glide {
  to { transform: translateX(-50%); }
}

/* A large window: more of it is the sheet's. */
@container panel (min-width: 1200px) and (min-height: 850px) {
  .slot {
    width: clamp(360px, 30cqw, 460px);
  }
  .sheet {
    padding: 20px 26px 16px;
    gap: 14px;
  }
  .series.staged .event {
    font-size: 19px;
  }
  .total b {
    font-size: 44px;
  }
  .kind {
    --line: 26px;
    --pip: 10px;
    grid-template-columns: 84px minmax(0, 1fr) auto;
    row-gap: 12px;
    column-gap: 20px;
    min-height: 82px;
  }
  .cover {
    width: 50px;
  }
  .k-duo .cover,
  .k-group .cover {
    width: 82px;
  }
  .name em {
    font-size: 20px;
  }
  .name b {
    font-size: 25px;
  }
  .name i,
  .rate {
    font-size: 17px;
  }
  .pips {
    gap: 14px;
  }
  .set {
    gap: 4px;
  }
  .pips i {
    border-radius: 3px;
  }
  .pass {
    --pass-h: 84px;
  }
}
/* The tab says it too. */
@container panel (max-width: 900px) {
  h3.small {
    display: none;
  }
}
@container panel (max-width: 820px) {
  .photo-stage {
    --stage-gap: 18px;
    padding-right: 18px;
  }
  /* Three pools in one row. */
  .title :deep(.pool-tabs) {
    gap: 6px;
    margin-right: -10px;
  }
  .facts {
    display: none;
  }
  .event {
    grid-column: 1 / 3;
  }
  .kind {
    --pip: 6px;
    column-gap: 10px;
  }
  .pips {
    gap: 7px;
  }
  .set {
    gap: 2px;
  }
}
/* Half of the strip would be under the bar. */
@container panel (max-height: 580px) and (min-width: 661px) {
  .strip {
    display: none;
  }
}
/* One column: the pools, the box under them, the sheet below the fold. */
@container panel (max-width: 660px) {
  .photo-stage {
    flex-direction: column;
    gap: 10px;
    padding: 10px 16px 12px;
  }
  .info {
    display: contents;
  }
  .title {
    position: relative;
    z-index: 2;
    order: -1;
  }
  .title :deep(.pool-tabs) {
    margin-bottom: 0;
  }
  .slot {
    margin: 2px auto 0;
  }
  h3,
  .peek {
    display: none;
  }
  .shelf {
    width: 100%;
    height: 272px;
  }
  .sheet {
    margin-left: 0;
  }
}
/* Keeps the bar above the fold. */
@container panel (max-height: 640px) {
  .bar {
    display: none;
  }
  .kind {
    min-height: 46px;
    padding: 3px 0;
    row-gap: 5px;
  }
  .cover {
    width: 24px;
  }
  .k-duo .cover,
  .k-group .cover {
    width: 40px;
  }
  .pass {
    --pass-h: 48px;
  }
}
</style>
