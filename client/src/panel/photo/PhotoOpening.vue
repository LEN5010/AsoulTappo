<script setup lang="ts">
// A box opened on the table, over the whole panel, sidebar and title bar included. The table is photo/opening.ts in the
// shared canvas; what stands over it is here: how far the box is, what each card is as it shows, where its repeats go and,
// once the whole box lies there, what it brought.
// The box and its cards are the save's since it was bought (stores/photocards.ts): leaving early loses nothing, the box
// waits on the shelf with the bags that are left. Where there is no WebGL 2 the cards are laid out at once as pictures.
import { computed, nextTick, onBeforeUnmount, onDeactivated, onMounted, ref, shallowRef, watch } from "vue";
import { prime } from "../../audio/sfx";
import { usePageActive } from "../../composables/usePageActive";
import { formatCount } from "../../income";
import { characterColor } from "../../manifest";
import { photoItem, photoItems, type PhotoItem, type PhotoItemKind } from "../../photocards";
import { seriesArt } from "../../photo/art";
import { mountScene, onPhotoLost, photoGl, type Mount } from "../../photo/engine";
import { createOpening, type Opening, type OpeningEvent } from "../../photo/opening";
import type { BoxPlace } from "../../photo/place";
import { openPhotoBags, photoBuying, photoError, photoLeft, photoView } from "../../stores/photocards";
import { online, shards } from "../../stores/player";
import { reducedMotion } from "../../stores/theme";
import { ui } from "../../stores/ui";
import { takeFocus, trapTab } from "../../ui/focus";
import Icon from "../../ui/Icon.vue";
import PhotoThumb from "./PhotoThumb.vue";
import { PHOTO_KIND_LABEL, photoNo, photoWho } from "./labels";
import { buyAnother, clearTable, shelfStage, type PhotoRun } from "./shop";
import { throwShards } from "./shards";

const props = defineProps<{ run: PhotoRun }>();

const calm = computed(() => reducedMotion.value);
const pageActive = usePageActive();
const view = computed(() => photoView(props.run.series));
const cfg = computed(() => view.value.cfg);

/** A bag on the table. A card this build lacks has none, so `index`, its place in the box, may be further on than here. */
interface Bag { index: number; item: PhotoItem; fresh: boolean; shards: number; spare: boolean }
const bags = shallowRef<Bag[]>([]);
const total = computed(() => bags.value.length);

/** Bags torn, cards that went to the row, and what the repeats among those turned into so far. */
const torn = ref(0);
const kept = ref(0);
const paid = ref(0);
const bump = ref(0);
const face = ref<number | null>(null);
const inspecting = ref<number | null>(null);
const playing = ref(false);
const dim = ref(false);
const auto = ref(false);
const ended = ref(false);
const leaving = ref(false);
/** No WebGL 2: the cards are pictures. */
const flat = ref(false);
/** The canvas draws. */
const up = ref(false);

const root = ref<HTMLElement>();
const host = ref<HTMLElement>();
const flights = ref<HTMLElement>();
const purse = ref<HTMLElement>();
const size = ref({ w: 960, h: 640, css: 1 });
let mount: Mount | null = null;
let table: Opening | null = null;
let alive = true;
let round = 0;
/** The box has come to the table: what comes after it does not come from the shelf. */
let taken = false;
/** It came with no shelf to come from: the table fades in. */
const plain = ref(false);

function deal(): void {
  bags.value = props.run.box.cards.flatMap((c, index) => {
    const item = photoItem(c.item);
    return item ? [{ index, item, fresh: !!c.new, shards: c.shards ?? 0, spare: !!c.spare }] : [];
  });
  torn.value = kept.value = bags.value.filter((b) => b.index < view.value.opened).length;
  paid.value = bags.value.slice(0, kept.value).reduce((sum, b) => sum + b.shards, 0);
  face.value = inspecting.value = null;
  playing.value = dim.value = auto.value = ended.value = false;
}
/** The first [n] bags on the table are open, as the box counts them. */
function tell(n: number): void {
  const { box, series } = props.run;
  openPhotoBags(series, box.id, bags.value[n]?.index ?? box.cards.length);
}

async function start(): Promise<void> {
  const mine = ++round;
  deal();
  const gl = await photoGl();
  const art = seriesArt(props.run.series);
  if (gl && art) await gl.kit.load(art.id);
  if (!alive || mine !== round) return;
  // The panel is not there to show it on: the box waits on the shelf.
  if (!host.value) return clearTable();
  if (!gl || !art || !total.value) {
    flat.value = true;
    finishBags();
    ended.value = true;
    up.value = true;
    return;
  }
  flat.value = false;
  table?.dispose(true);
  const from = taken ? undefined : shelfStage.value?.hand();
  plain.value = !from && !taken;
  taken = true;
  table = createOpening(gl.gl, gl.kit, gl.painter, {
    art, deal: bags.value.map((b) => ({ card: b.item.card, signed: b.item.kind === "sign" })),
    opened: torn.value, calm: calm.value, from, rect: () => host.value!.getBoundingClientRect(),
    on: (e) => { if (alive && mine === round) told(e); },
  });
  if (mount) mount.swap(table);
  else mount = mountScene(host.value, table, { bare: !!from, layer: 1 });
  mount.show(pageActive.value);
  mount.wake();
  up.value = true;
}

function told(e: OpeningEvent): void {
  switch (e.type) {
    case "phase":
      playing.value = e.phase === "play" || e.phase === "spot";
      if (e.phase === "gather") face.value = null;
      break;
    case "torn":
      torn.value = e.index + 1;
      tell(torn.value);
      break;
    case "shown": face.value = e.index; break;
    case "kept": keep(e.index); break;
    case "auto": auto.value = e.on; break;
    case "dim": dim.value = e.on; break;
    case "inspect": inspecting.value = e.index; break;
    case "end":
      finishBags();
      ended.value = true;
      endedAt = performance.now();
      void nextTick(() => root.value?.querySelector<HTMLElement>(".foot .primary")?.focus({ preventScroll: true }));
      break;
  }
  mount?.wake();
}

/** A card leaves for the row: its caption goes, and a repeat pays. */
function keep(index: number): void {
  if (face.value === index) face.value = null;
  kept.value = Math.max(kept.value, index + 1);
  const b = bags.value[index];
  if (!b?.shards) return;
  const box = host.value?.getBoundingClientRect();
  const to = purse.value?.getBoundingClientRect();
  if (calm.value || !box || !to || !flights.value) return credit(b.shards);
  throwShards(flights.value, { x: box.left + box.width / 2, y: box.top + box.height * 0.42 },
    { x: to.left + 14, y: to.top + to.height / 2 }, b.shards, credit);
}
function credit(n: number): void {
  paid.value += n;
  bump.value++;
}
const paidAll = computed(() => bags.value.reduce((sum, b) => sum + b.shards, 0));
/** The purse as it has to be in the end, whatever was still on its way. */
function settlePaid(): void {
  flights.value?.replaceChildren();
  if (paid.value !== paidAll.value) paid.value = paidAll.value;
}
function finishBags(): void {
  tell(total.value);
  torn.value = kept.value = total.value;
  settlePaid();
}

/** What stands over the card on show: who it is, what kind, and what came of it. */
const caption = computed(() => {
  const b = bags.value[inspecting.value ?? face.value ?? -1];
  if (!b) return null;
  const spares = bags.value.filter((x) => x.spare && x.index <= b.index).length;
  return {
    key: `${props.run.box.id}:${b.index}`, kind: b.item.kind, tag: PHOTO_KIND_LABEL[b.item.kind],
    who: photoWho(b.item), no: photoNo(b.item), fresh: b.fresh, shards: b.shards,
    spare: b.spare && cfg.value ? `${Math.min(cfg.value.swap, spareBefore.value + spares)}/${cfg.value.swap}` : "",
  };
});
/** Signed repeats put by before this box. */
const spareBefore = computed(() => {
  const save = view.value.save;
  if (!save) return 0;
  const here = bags.value.filter((b) => b.spare).length;
  const settled = props.run.box.settled?.cards ?? 0;
  return Math.max(0, settled ? settled - here : save.spare - here);
});

/** A cell a bag: empty, opened, or opened and rare in its members' colours. */
const cells = computed(() => bags.value.map((b, k) => {
  if (k >= kept.value) return { on: k < torn.value, tone: "" };
  const c = b.item.characters.map(characterColor);
  const tone: Record<PhotoItemKind, string> = {
    solo: "", sign: "var(--grad-gold)", group: `linear-gradient(180deg, ${c.join(", ")})`, duo: `linear-gradient(180deg, ${c.join(", ")})`,
  };
  return { on: true, tone: tone[b.item.kind] };
}));

const tally = computed(() => {
  const count = (kind: PhotoItemKind) => bags.value.filter((b) => b.item.kind === kind).length;
  return {
    fresh: bags.value.filter((b) => b.fresh).length,
    rare: (["sign", "group", "duo"] as const).flatMap((kind) => (count(kind) ? [{ kind, label: PHOTO_KIND_LABEL[kind], n: count(kind) }] : [])),
    spare: bags.value.filter((b) => b.spare).length, settled: props.run.box.settled ?? null,
  };
});
/** How much of the series the save holds now, and held before this box. */
const whole = computed(() => {
  const items = photoItems(props.run.series);
  const got = items.filter((i) => view.value.owned.has(i.id)).length;
  const part = (n: number) => `${items.length ? (Math.max(0, n) / items.length) * 100 : 0}%`;
  return { got, of: items.length, now: part(got), was: part(got - tally.value.fresh) };
});
/** Where the new cards lie in the spread, in CSS pixels: their NEW marks. */
const marks = computed(() => {
  if (!ended.value || flat.value || inspecting.value !== null) return [];
  const { w, h, css } = size.value;
  const places = table?.places() ?? [];
  return places.flatMap((p) => (bags.value[p.index]?.fresh
    ? [{ index: p.index, x: w / 2 + (p.x + p.w / 2) * css, y: h / 2 + (p.y - p.h / 2) * css }] : []));
});

/** A minute's tick: the boxes left are the day's. */
const now = ref(Date.now());
const clock = window.setInterval(() => (now.value = Date.now()), 30_000);
onBeforeUnmount(() => window.clearInterval(clock));
const left = computed(() => photoLeft(props.run.series, now.value));
const canAgain = computed(() => !!cfg.value && !!left.value && online.value && shards.value >= cfg.value.price);
async function again(): Promise<void> {
  if (!canAgain.value || photoBuying.value || leaving.value) return;
  const box = await buyAnother();
  if (!alive || !box) return;
  leaving.value = true;
  if (table && !calm.value) await table.leave();
  if (!alive) return;
  leaving.value = false;
  await start();
}

/** Back to the page: an opened box is put away; one with bags left goes back to the shelf. */
async function close(): Promise<void> {
  if (leaving.value) return;
  leaving.value = true;
  round++;
  let place: BoxPlace | undefined;
  if (table && !calm.value && !flat.value) {
    mount?.wake();
    place = shelfStage.value?.place(ended.value);
    await (ended.value ? table.goOut(place) : table.goBack(place));
  }
  if (!alive) return;
  clearTable(!!place);
}
function skip(): void {
  if (leaving.value || !playing.value && !table) return;
  finishBags();
  face.value = null;
  table?.skip();
  mount?.wake();
}
function toggleAuto(): void {
  if (leaving.value) return;
  table?.setAuto(!auto.value);
  mount?.wake();
}

// ---------------------------------------------------------------- pointer and keys
const at = (e: PointerEvent): [number, number, number] => {
  const r = host.value!.getBoundingClientRect();
  return [(e.clientX - r.left - r.width / 2) / size.value.css, (e.clientY - r.top - r.height / 2) / size.value.css, e.timeStamp];
};
function onDown(e: PointerEvent): void {
  if (e.button !== 0 || leaving.value) return;
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  table?.down(...at(e));
  mount?.wake();
}
function onMove(e: PointerEvent): void {
  if (leaving.value) return;
  table?.move(...at(e));
  mount?.wake();
}
function onUp(e: PointerEvent): void {
  table?.up(e.type === "pointercancel");
  mount?.wake();
}
/** A key still being pressed as the result comes up does not put it away. */
const END_GUARD_MS = 450;
let endedAt = -Infinity;

function onKey(e: KeyboardEvent): void {
  if (e.key === "Tab" && root.value) return trapTab(root.value, e);
  if (e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
  if (e.key === "Escape") {
    e.preventDefault();
    e.stopImmediatePropagation();
    if (e.repeat || leaving.value) return;
    if (inspecting.value !== null) table?.press();
    else void close();
    mount?.wake();
    return;
  }
  if (e.key !== " " && e.key !== "Enter") return;
  // A key of the bar or the corner takes its own press; holding one never repeats it.
  if (document.activeElement instanceof HTMLButtonElement && root.value?.contains(document.activeElement)) {
    if (e.repeat || performance.now() - endedAt < END_GUARD_MS) e.preventDefault();
    return;
  }
  e.preventDefault();
  if (leaving.value || ended.value && inspecting.value === null) return;
  table?.press(e.repeat);
  mount?.wake();
}
function onKeyUp(e: KeyboardEvent): void {
  if (e.key === " " && (!(document.activeElement instanceof HTMLButtonElement) || performance.now() - endedAt < END_GUARD_MS)) {
    e.preventDefault();
  }
}

watch(pageActive, (on) => mount?.show(on));
const offLost = onPhotoLost(() => {
  mount = null;
  // What is waited for of it is over.
  table?.dispose();
  table = null;
  if (alive && !leaving.value) void start();
});
let observer: ResizeObserver | undefined;
let release: (() => void) | undefined;
onMounted(async () => {
  prime();
  window.addEventListener("keydown", onKey, true);
  window.addEventListener("keyup", onKeyUp, true);
  await nextTick();
  if (!alive) return;
  if (host.value) {
    const fit = () => {
      const w = host.value!.clientWidth, h = host.value!.clientHeight;
      size.value = { w, h, css: Math.min(w / 960, h / 640) };
    };
    fit();
    observer = new ResizeObserver(fit);
    observer.observe(host.value);
  }
  release = takeFocus(root.value);
  void start();
});
onBeforeUnmount(() => {
  alive = false;
  offLost();
  observer?.disconnect();
  window.removeEventListener("keydown", onKey, true);
  window.removeEventListener("keyup", onKeyUp, true);
  table?.dispose();
  mount?.release();
  release?.();
});
// Teleported content stays behind when its page turns away (a desk shortcut can do that). A hidden or minimized window
// deactivates the whole panel: the table stays, to go on when it is back.
onDeactivated(() => {
  if (!ui.panelOpen || ui.panelMinimized) return;
  clearTable();
});
</script>

<template>
  <Teleport defer to=".panel-overlay">
    <div
      ref="root" class="opening" :class="{ calm, up, dim, ended, leaving, flat, plain, playing }" data-overlay role="dialog" aria-modal="true"
      aria-label="开盒" tabindex="-1"
    >
      <div
        ref="host" class="table" @pointerdown="onDown" @pointermove="onMove" @pointerup="onUp" @pointercancel="onUp"
        @pointerleave="table?.leavePointer()"
      ></div>

      <div v-if="flat" class="board ui-scroll">
        <div v-for="b in bags" :key="b.index" class="tile" :class="{ wide: b.item.kind === 'duo' || b.item.kind === 'group' }">
          <PhotoThumb :item="b.item" />
          <i v-if="b.fresh" class="new">NEW</i>
        </div>
      </div>

      <header class="hud">
        <div class="far">
          <p class="count"><b>{{ torn }}</b><i>/ {{ total }}</i></p>
          <span class="cells" aria-hidden="true">
            <i v-for="(c, k) in cells" :key="k" :class="{ on: c.on, rare: !!c.tone }" :style="c.tone ? { background: c.tone } : undefined"></i>
          </span>
          <span ref="purse" class="purse" :class="{ some: paid > 0 }"><Icon name="shard" :size="14" /><b :key="bump">+{{ paid }}</b></span>
        </div>
      </header>
      <div class="tools">
        <template v-if="playing">
          <button type="button" class="desk-key" :aria-pressed="auto" @click="toggleAuto"><Icon name="play" :size="13" />连拆</button>
          <button type="button" class="desk-key" @click="skip"><Icon name="skip" :size="13" />跳过</button>
        </template>
        <button type="button" class="desk-key x" aria-label="离开" :disabled="leaving" @click="close"><Icon name="close" :size="15" /></button>
      </div>

      <Transition name="cap" :css="!calm">
        <div v-if="caption" :key="caption.key" class="caption" :class="caption.kind">
          <span class="kind">{{ caption.tag }}</span>
          <b class="who">{{ caption.who }}</b><i class="no">{{ caption.no }}</i>
          <span v-if="caption.fresh" class="mark fresh">NEW</span>
          <span v-else-if="caption.shards" class="mark back"><Icon name="shard" :size="13" />{{ caption.shards }}</span>
          <span v-else-if="caption.spare" class="mark back"><Icon name="swap" :size="13" />{{ caption.spare }}</span>
        </div>
      </Transition>

      <TransitionGroup tag="div" name="new" class="marks" :css="!calm" aria-hidden="true">
        <i v-for="(m, k) in marks" :key="m.index" class="new" :style="{ left: `${m.x}px`, top: `${m.y}px`, '--k': k }">NEW</i>
      </TransitionGroup>

      <Transition name="foot" :css="!calm">
        <footer v-if="ended && !leaving" class="foot">
          <div class="whole" :style="{ '--was': whole.was, '--now': whole.now }">
            <p><b>{{ whole.got }}</b><i>/ {{ whole.of }}</i></p>
            <span class="bar" aria-hidden="true"><i></i></span>
          </div>
          <div class="tally">
            <span v-if="tally.fresh" class="pill fresh"><Icon name="spark" :size="13" />新收藏<b>{{ tally.fresh }}</b></span>
            <span v-for="r in tally.rare" :key="r.kind" class="pill" :class="r.kind">{{ r.label }}<b>{{ r.n }}</b></span>
            <span v-if="paidAll" class="pill paid"><Icon name="shard" :size="13" />重复兑换<b>+{{ formatCount(paidAll) }}</b></span>
            <span v-if="tally.settled" class="pill paid"><Icon name="shard" :size="13" />换签名余下 {{ tally.settled.cards }} 张<b>+{{ formatCount(tally.settled.shards) }}</b></span>
            <span v-else-if="tally.spare" class="pill swap"><Icon name="swap" :size="13" />换签名<b>+{{ tally.spare }}</b></span>
          </div>
          <p v-if="photoError" class="failed" role="alert">{{ photoError }}</p>
          <button v-if="canAgain" type="button" class="ui-btn large" :disabled="!!photoBuying" @click="again">
            再开一盒<small class="cost"><Icon name="shard" :size="12" />{{ formatCount(cfg!.price) }}</small>
          </button>
          <button type="button" class="ui-btn primary large take" @click="close">收下</button>
        </footer>
      </Transition>
      <div ref="flights" class="flights" aria-hidden="true"></div>
    </div>
  </Teleport>
</template>

<style scoped>
.opening {
  position: absolute;
  inset: 0;
  z-index: 40;
  container: opening / size;
  overflow: hidden;
  outline: none;
  font-family: var(--font);
  color: #fff;
  user-select: none;
}
.opening.flat {
  background: var(--c-50);
  color: var(--ink);
}
.opening.plain {
  animation: table-in 320ms var(--ease-out) both;
}
.opening.plain.calm {
  animation: none;
}
@keyframes table-in { from { opacity: 0; } }
.table {
  position: absolute;
  inset: 0;
  touch-action: none;
  cursor: grab;
}
.table:active {
  cursor: grabbing;
}

/* How far the box is, and what its repeats came to. */
.hud {
  position: absolute;
  left: 22px;
  top: 16px;
  pointer-events: none;
  opacity: 0;
  translate: 0 -8px;
  transition: opacity 420ms var(--ease-out), translate 420ms var(--ease-out);
}
.playing .hud {
  opacity: 1;
  translate: none;
}
.dim .hud,
.dim .tools {
  opacity: 0.32;
}
.far {
  display: grid;
  grid-template-columns: auto auto;
  align-items: center;
  justify-content: start;
  gap: 8px 14px;
}
.count {
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin: 0;
  text-shadow: 0 1px 6px rgba(20, 10, 24, 0.5);
}
.count b {
  min-width: 1.1em;
  font: 800 34px/0.9 var(--font-latin);
}
.count i {
  font: 800 17px/1 var(--font-latin);
  font-style: normal;
  opacity: 0.6;
}
.cells {
  display: flex;
  gap: 3px;
}
.cells i {
  width: 6px;
  height: 14px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.16);
  transition: background 320ms var(--ease-out), scale 320ms var(--ease-out);
}
.cells i.on {
  background: rgba(255, 255, 255, 0.72);
}
.cells i.rare {
  scale: 1.18;
}
.purse {
  grid-column: 1 / 3;
  justify-self: start;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 11px 0 9px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  font: 800 15px/1 var(--font-latin);
  opacity: 0;
  transition: opacity 240ms var(--ease-out);
}
.purse.some {
  opacity: 1;
}
.purse svg {
  color: var(--c-400);
  fill: var(--c-500);
}
.purse b {
  animation: purse-pop 320ms var(--ease-pop) both;
}
.calm .purse b {
  animation: none;
}
@keyframes purse-pop {
  40% { scale: 1.16; }
}

.tools {
  position: absolute;
  right: 18px;
  top: 16px;
  display: flex;
  gap: 8px;
  transition: opacity 420ms var(--ease-out);
}
/* A key of the dark table: smoked glass, lit a little under the pointer, lit up while latched. */
.desk-key {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 13px;
  border: 0;
  border-radius: var(--radius-key-s);
  background: rgba(255, 255, 255, 0.13);
  color: #fff;
  font: 800 var(--fs-body)/1 var(--font);
  cursor: pointer;
  transition: background var(--dur-fast), transform var(--dur-fast) var(--ease-out);
}
.desk-key:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.22);
  transform: translateY(-1px);
}
.desk-key:active:not(:disabled) {
  transform: translateY(1px);
}
.desk-key[aria-pressed="true"] {
  background: var(--c-500);
  color: var(--ink);
}
.desk-key:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}
.desk-key.x {
  width: 32px;
  padding: 0;
  justify-content: center;
}
.flat .desk-key {
  background: var(--c-100);
  color: var(--ink);
}

/* Over the card on show. */
.caption {
  position: absolute;
  left: 50%;
  top: 24px;
  translate: -50% 0;
  display: flex;
  align-items: center;
  gap: 9px;
  white-space: nowrap;
  pointer-events: none;
  text-shadow: 0 1px 8px rgba(20, 10, 24, 0.6);
}
.kind {
  padding: 0 9px;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.18);
  font: 800 var(--fs-label)/22px var(--font);
  text-shadow: none;
}
.sign .kind {
  background: var(--grad-gold);
  color: var(--ink);
}
.duo .kind,
.group .kind {
  background: #fff;
  color: var(--night);
}
.who {
  font: 800 21px/1 var(--font);
  letter-spacing: 0.02em;
}
.no {
  font: 800 19px/1 var(--font-latin);
  font-style: normal;
  opacity: 0.7;
}
.mark {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  padding: 0 9px;
  border-radius: 5px;
  font: 800 14px/22px var(--font-latin);
  text-shadow: none;
}
.mark.fresh {
  background: var(--c-500);
  color: var(--ink);
  letter-spacing: 0.06em;
}
.mark.back {
  background: rgba(255, 255, 255, 0.16);
}
.mark.back svg {
  color: var(--c-400);
}
.cap-enter-active {
  transition: opacity 260ms var(--ease-out), translate 360ms var(--ease-out);
}
.cap-leave-active {
  transition: opacity 160ms var(--ease-in);
}
.cap-enter-from {
  opacity: 0;
  translate: -50% 10px;
}
.cap-leave-to {
  opacity: 0;
}

.marks {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.new {
  padding: 2px 6px;
  border-radius: 5px;
  background: var(--c-500);
  box-shadow: 0 2px 5px rgba(20, 10, 24, 0.4);
  color: var(--ink);
  font: 800 11px/1.15 var(--font-latin);
  font-style: normal;
  letter-spacing: 0.05em;
}
.marks .new {
  position: absolute;
  translate: -74% -42%;
}
.new-enter-active {
  transition: opacity 200ms calc(var(--k) * 40ms), scale 320ms var(--ease-pop) calc(var(--k) * 40ms);
}
.new-leave-active {
  transition: opacity 140ms;
}
.new-enter-from {
  opacity: 0;
  scale: 0.3;
}
.new-leave-to {
  opacity: 0;
}

/* A sheet of paper along the bottom edge, where the page's own bar is. */
.foot {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 20px 17px 24px;
  border-radius: 20px 20px 0 0;
  background: var(--surface);
  box-shadow: 0 -12px 34px -12px rgba(0, 0, 0, 0.5);
  color: var(--ink);
}
.foot-enter-active {
  transition: transform 520ms var(--ease-out), opacity 300ms;
}
.foot-leave-active {
  transition: transform 240ms var(--ease-in), opacity 200ms;
}
.foot-enter-from,
.foot-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
/* How much of the series there is now; what this box added comes on at the end of the bar. */
.whole {
  flex: none;
  width: 118px;
  margin-right: 10px;
}
.whole p {
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin: 0 0 6px;
}
.whole b {
  font: 800 26px/0.9 var(--font-latin);
}
.whole p i {
  font: 800 15px/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.bar {
  display: block;
  height: 6px;
  border-radius: 3px;
  background: var(--c-100);
  overflow: hidden;
}
.bar i {
  display: block;
  width: var(--now);
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--c-400), var(--c-500));
  animation: bar-on 900ms var(--ease-out) 520ms backwards;
}
.calm .bar i {
  animation: none;
}
@keyframes bar-on { from { width: var(--was); } }
.tally {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 8px;
}
.pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: var(--c-50);
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
  white-space: nowrap;
}
.pill b {
  margin-left: 1px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.pill.fresh {
  background: var(--c-100);
  color: var(--c-700);
}
.pill.fresh b {
  color: var(--c-700);
}
.pill.fresh svg {
  stroke-width: 0;
  fill: var(--c-500);
}
.pill.sign {
  background: var(--grad-gold);
  color: var(--ink);
}
.pill.group,
.pill.duo {
  background: color-mix(in srgb, var(--holo-lilac) 42%, #fff);
  color: var(--night);
}
.pill.group b,
.pill.duo b {
  color: var(--night);
}
.pill.paid svg {
  color: var(--c-700);
}
.failed {
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--bad);
}
.foot .ui-btn {
  flex: none;
  min-width: 116px;
}
.cost {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font: 800 var(--fs-label)/1 var(--font-latin);
  opacity: 0.75;
}
.flights {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}
.flights :deep(.shard) {
  position: absolute;
  left: 0;
  top: 0;
  width: 22px;
  height: 22px;
  margin: -11px 0 0 -11px;
  will-change: transform, opacity;
}
.flights :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
  overflow: visible;
  filter: drop-shadow(0 2px 3px rgba(0, 0, 0, 0.45));
}
.flights :deep(path) {
  fill: var(--c-500);
  stroke: #fff;
  stroke-width: 2.2;
  stroke-linejoin: round;
}
.flights :deep(.cut) {
  fill: none;
  stroke: rgba(255, 255, 255, 0.7);
  stroke-width: 1.1;
}
.leaving .hud,
.leaving .tools,
.leaving .caption,
.leaving .marks {
  opacity: 0;
  transition: opacity 180ms;
}
.leaving {
  pointer-events: none;
}

/* Without the canvas: the cards as pictures on paper. */
.board {
  position: absolute;
  inset: 60px 0 92px;
  display: flex;
  flex-wrap: wrap;
  align-content: safe center;
  justify-content: center;
  gap: 14px;
  padding: 0 40px;
  overflow-y: auto;
}
.tile {
  position: relative;
  width: 78px;
  box-shadow: 0 8px 16px -9px rgba(var(--shadow-rgb), 0.5);
}
.tile.wide {
  width: 124px;
}
.tile .new {
  position: absolute;
  right: -6px;
  top: -6px;
}

@container opening (max-width: 760px) {
  .count b {
    font-size: 27px;
  }
  .cells i {
    width: 4px;
    height: 11px;
  }
  .hud {
    left: 14px;
    top: 10px;
  }
  .tools {
    right: 12px;
    top: 10px;
  }
  .caption {
    top: 46px;
  }
  .who {
    font-size: 17px;
  }
  .no {
    font-size: 16px;
  }
  .whole {
    display: none;
  }
  .foot {
    padding: 9px 12px 12px 14px;
  }
  .pill {
    height: 26px;
    padding: 0 9px;
  }
  .foot .ui-btn {
    min-width: 0;
    padding: 0 18px;
  }
}
</style>
