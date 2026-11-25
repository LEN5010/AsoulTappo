<script setup lang="ts">
// A photocard looked at, over the whole panel: the card itself in the shared canvas (photo/viewer.ts), leaning after the
// pointer and turned over by hand, and what it is beside it. A signed card can be signed again.
// Where there is no WebGL 2 it is a picture.
import { computed, nextTick, onBeforeUnmount, onDeactivated, onMounted, ref, shallowRef, watch } from "vue";
import { usePageActive } from "../../composables/usePageActive";
import { characterColor, manifest } from "../../manifest";
import { photoPair, type PhotoItem } from "../../photocards";
import { seriesArt } from "../../photo/art";
import { mountScene, onPhotoLost, photoGl, type Mount } from "../../photo/engine";
import type { CardPlace } from "../../photo/place";
import { createViewer, type Viewer } from "../../photo/viewer";
import { formatCount } from "../../income";
import { photoView, type PhotocardSettled } from "../../stores/photocards";
import { reducedMotion } from "../../stores/theme";
import { ui } from "../../stores/ui";
import { takeFocus, trapTab } from "../../ui/focus";
import Icon from "../../ui/Icon.vue";
import StepKeys from "../StepKeys.vue";
import PhotoThumb from "./PhotoThumb.vue";
import { PHOTO_KIND_LABEL, photoName, photoNo, photoWho } from "./labels";

const props = defineProps<{
  item: PhotoItem;
  /** The cards as the page shows them, to step through. */
  list: readonly PhotoItem[];
  /** Where its small picture is, for it to come out of. */
  from?: CardPlace;
  /** Its signature is written as it opens. */
  write?: boolean;
  /** It was the last signed card there was to trade for: what the repeats left turned into. */
  settled?: PhotocardSettled;
  /** Offers the way to the shop for a card the save lacks. */
  shop?: boolean;
}>();
const emit = defineEmits<{ close: []; step: [item: PhotoItem]; shop: [] }>();

const calm = computed(() => reducedMotion.value);
const pageActive = usePageActive();
const info = computed(() => manifest.photocards.find((s) => s.id === props.item.series));
const owned = computed(() => photoView(props.item.series).owned.has(props.item.id));
const pair = computed(() => photoPair(props.item));
const signed = computed(() => props.item.kind === "sign");
const tones = computed(() => props.item.characters.map(characterColor));
const wash = computed(() => {
  const c = tones.value;
  return c.length < 2 ? { "--a": c[0], "--b": c[0], "--c": c[0] } : { "--a": c[0], "--b": c[1], "--c": c[2] ?? c[1] };
});

const at = computed(() => props.list.findIndex((i) => i.id === props.item.id));
const next = (d: -1 | 1) => (at.value < 0 ? undefined : props.list[at.value + d]);
function step(d: -1 | 1) {
  const item = next(d);
  if (item) emit("step", item);
}
function swapFace() {
  if (pair.value) emit("step", pair.value);
}

const root = ref<HTMLElement>();
const host = ref<HTMLElement>();
const facts = ref<HTMLElement>();
const flat = ref(false);
const closing = ref(false);
const viewer = shallowRef<Viewer | null>(null);
let mount: Mount | null = null;
let alive = true;

const faceOf = (item: PhotoItem) => ({ card: item.card, signed: item.kind === "sign" });
async function start(): Promise<void> {
  const gl = await photoGl();
  if (!alive) return;
  const art = seriesArt(props.item.series);
  await nextTick();
  if (!gl || !art || !host.value) {
    flat.value = true;
    return;
  }
  const v = createViewer(gl.gl, gl.kit, gl.painter, { art, calm: calm.value, rect: () => host.value!.getBoundingClientRect() });
  v.inset(facts.value?.offsetWidth ?? 0);
  viewer.value = v;
  mount = mountScene(host.value, v, { layer: 2 });
  mount.show(pageActive.value);
  v.open(faceOf(props.item), { from: props.from, write: props.write });
  mount.wake();
}
watch(() => props.item, (item, was) => {
  const same = item.series === was.series && item.card === was.card;
  const dir = props.list.findIndex((i) => i.id === item.id) < props.list.findIndex((i) => i.id === was.id) ? -1 : 1;
  viewer.value?.change(faceOf(item), same ? 0 : dir);
  mount?.wake();
});
function turnOver() {
  viewer.value?.turnOver();
  mount?.wake();
}
function sign() {
  viewer.value?.write();
  mount?.wake();
}
async function close() {
  if (closing.value) return;
  closing.value = true;
  if (viewer.value && !calm.value) {
    mount?.wake();
    await viewer.value.close();
  }
  if (alive) emit("close");
}

const point = (e: PointerEvent): [number, number, number] => [e.clientX, e.clientY, e.timeStamp];
function onDown(e: PointerEvent) {
  if (e.button !== 0) return;
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  viewer.value?.down(...point(e));
  mount?.wake();
}
function onMove(e: PointerEvent) {
  viewer.value?.move(...point(e));
  mount?.wake();
}
function onUp(e: PointerEvent) {
  // A press beside the card, not one that turned it, leaves.
  if (viewer.value?.up(e.type === "pointercancel") === "beside") void close();
  mount?.wake();
}
function onKey(e: KeyboardEvent) {
  if (e.key === "Tab" && root.value) return trapTab(root.value, e);
  if (e.key !== "Escape") return;
  e.preventDefault();
  e.stopImmediatePropagation();
  void close();
}

watch(pageActive, (on) => mount?.show(on));
const offLost = onPhotoLost(() => {
  mount = null;
  viewer.value = null;
  flat.value = false;
  if (!alive) return;
  if (closing.value) emit("close");
  else void start();
});
let observer: ResizeObserver | undefined;
let release: (() => void) | undefined;
onMounted(async () => {
  window.addEventListener("keydown", onKey, true);
  await nextTick();
  if (!alive) return;
  release = takeFocus(root.value);
  observer = new ResizeObserver(() => {
    viewer.value?.inset(facts.value?.offsetWidth ?? 0);
    mount?.wake();
  });
  if (facts.value) observer.observe(facts.value);
  void start();
});
onBeforeUnmount(() => {
  alive = false;
  offLost();
  observer?.disconnect();
  window.removeEventListener("keydown", onKey, true);
  viewer.value?.dispose();
  mount?.release();
  release?.();
});
onDeactivated(() => {
  if (ui.panelOpen && !ui.panelMinimized) emit("close");
});
</script>

<template>
  <Teleport defer to=".panel-overlay">
    <div
      ref="root" class="look" :class="{ calm, closing, flat }" :style="wash" data-overlay role="dialog" aria-modal="true"
      :aria-label="photoName(item)" tabindex="-1"
    >
      <div class="ground" aria-hidden="true"></div>
      <div
        ref="host" class="stage" @pointerdown="onDown" @pointermove="onMove" @pointerup="onUp" @pointercancel="onUp"
        @pointerleave="viewer?.leavePointer()"
      >
        <PhotoThumb v-if="flat" class="picture" :item="item" />
      </div>
      <StepKeys :prev="!!next(-1)" :next="!!next(1)" keyboard @step="step" />

      <aside ref="facts" class="facts">
        <Transition name="facts" mode="out-in" :css="!calm">
          <div :key="item.id" class="text">
            <p class="tags"><span class="ui-tag kind" :class="item.kind">{{ PHOTO_KIND_LABEL[item.kind] }}</span><i class="no">{{ photoNo(item) }}</i></p>
            <h3>{{ photoWho(item) }}</h3>
            <p v-if="item.kind === 'group'" class="members">
              <span v-for="c in item.characters" :key="c"><i :style="{ background: characterColor(c) }" aria-hidden="true"></i>{{ c }}</span>
            </p>
            <p class="where"><b>{{ info?.name }}</b>{{ info?.event }}</p>
            <p class="own" :class="{ yes: owned }"><Icon :name="owned ? 'check' : 'lock'" :size="14" />{{ owned ? "已拥有" : "未拥有" }}</p>
            <p v-if="settled" class="settled"><Icon name="shard" :size="13" />换签名余下 {{ settled.cards }} 张<b>+{{ formatCount(settled.shards) }}</b></p>
          </div>
        </Transition>
        <div class="acts">
          <span v-if="pair" class="faces" role="group" aria-label="卡面">
            <button type="button" class="ui-btn small" :aria-pressed="!signed" @click="signed && swapFace()">普通</button>
            <button type="button" class="ui-btn small" :aria-pressed="signed" @click="!signed && swapFace()">签名</button>
          </span>
          <span v-if="!flat" class="keys">
            <button type="button" class="ui-btn small" @click="turnOver"><Icon name="swap" :size="14" />翻面</button>
            <button v-if="signed" type="button" class="ui-btn small" @click="sign"><Icon name="pencil" :size="13" />签一遍</button>
          </span>
          <button v-if="shop && !owned" type="button" class="ui-btn primary" @click="emit('shop')">去买小卡</button>
        </div>
      </aside>
      <button type="button" class="x ui-btn small ghost" aria-label="关闭" @click="close"><Icon name="close" :size="16" /></button>
    </div>
  </Teleport>
</template>

<style scoped>
.look {
  --step-inset: 14px;
  position: absolute;
  inset: 0;
  z-index: 40;
  container: look / size;
  outline: none;
  color: var(--ink);
  font-family: var(--font);
  user-select: none;
}
/* A light table: paper, with the members' colours faintly behind the card. */
.ground {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(50cqw 66cqh at 20cqw 36cqh, color-mix(in oklch, var(--a) 30%, transparent), transparent 72%),
    radial-gradient(50cqw 66cqh at 58cqw 66cqh, color-mix(in oklch, var(--b) 30%, transparent), transparent 72%),
    radial-gradient(36cqw 46cqh at 42cqw 14cqh, color-mix(in oklch, var(--c) 22%, transparent), transparent 72%),
    var(--c-50);
  animation: ground-in 240ms var(--ease-out) both;
  transition: opacity 260ms var(--ease-in);
}
.closing .ground {
  opacity: 0;
}
@keyframes ground-in { from { opacity: 0; } }
.calm .ground {
  animation: none;
}
.stage {
  position: absolute;
  inset: 0;
  touch-action: none;
  cursor: grab;
}
.stage:active {
  cursor: grabbing;
}
.flat .stage {
  display: grid;
  place-items: center;
  padding-right: 250px;
  cursor: default;
}
.picture {
  max-width: 100%;
  max-height: 74cqh;
  box-shadow: 0 20px 44px -18px rgba(var(--shadow-rgb), 0.5);
}
.look :deep(.step.next) {
  right: 262px;
}
.facts {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 250px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 18px;
  padding: 0 28px 0 6px;
  box-sizing: border-box;
  pointer-events: none;
  animation: facts-in 420ms var(--ease-out) 80ms both;
  transition: opacity 180ms;
}
.facts :deep(.ui-btn) {
  pointer-events: auto;
}
.closing .facts {
  opacity: 0;
}
.calm .facts {
  animation: none;
}
@keyframes facts-in { from { opacity: 0; translate: 18px 0; } }
.text > * {
  margin: 0;
}
.tags {
  display: flex;
  align-items: center;
  gap: 8px;
}
.kind {
  padding: 0 9px;
  font-size: var(--fs-label);
  line-height: 21px;
}
.kind.sign {
  --tag-bg: var(--grad-gold);
}
.kind.duo,
.kind.group {
  --tag-bg: var(--night);
  --tag-fg: #fff;
}
.no {
  font: 800 20px/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
h3 {
  margin: 12px 0 0 !important;
  font: 800 clamp(26px, 3.8cqw, 38px)/1.16 var(--font);
  text-wrap: balance;
}
.members {
  margin-top: 8px !important;
}
.members {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: var(--fs-body);
  font-weight: 800;
}
.members span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.members i {
  width: 4px;
  height: 13px;
}
.where {
  margin-top: 14px !important;
  font-size: var(--fs-label);
  font-weight: 700;
  line-height: 1.6;
  color: var(--ink-2);
}
.where b {
  display: block;
  font-size: var(--fs-strong);
  font-weight: 800;
  color: var(--ink);
}
.own {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 12px !important;
  font-size: var(--fs-body);
  font-weight: 800;
  color: var(--ink-3);
}
.own.yes {
  color: var(--c-700);
}
.settled {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 10px !important;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.settled svg {
  color: var(--c-700);
}
.settled b {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.acts {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}
.faces,
.keys {
  display: flex;
  gap: 8px;
}
.facts-enter-active {
  transition: opacity 240ms, transform 320ms var(--ease-out);
}
.facts-leave-active {
  transition: opacity 120ms;
}
.facts-enter-from {
  opacity: 0;
  transform: translateX(12px);
}
.facts-leave-to {
  opacity: 0;
}
.x.ui-btn {
  --key-top: rgba(255, 255, 255, 0.86);
  --key-bottom: rgba(255, 255, 255, 0.86);
  --key-lip-h: 0px;
  position: absolute;
  top: 12px;
  right: 14px;
  z-index: 4;
  width: 32px;
  padding: 0;
  color: var(--ink);
}
@container look (max-width: 720px) {
  .facts {
    width: 190px;
    padding-right: 18px;
  }
  .look :deep(.step.next) {
    right: 198px;
  }
  .flat .stage {
    padding-right: 190px;
  }
}
</style>
