<script setup lang="ts">
// A profile as others see it, one namecard: the plate's artwork across the right fading into paper, the pet's bust
// framed on the upper edge with the collection counts in a column under it, the name on the paper beside it, and up
// to five showcase cards pinned over the lower right corner, held as a fanned hand once there are more than three.
// The own card on the 排行 page is the same card made editable: a key swaps the plate, the empty slot after the
// pinned cards picks the next one, a pinned card's corner key takes it down, and a pinned card dragged along the row
// takes another place. The owner opens the pickers and the cards.
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { assetUrl } from "../asset";
import { cardFrame } from "../cards";
import { characters } from "../characters";
import { characterColor, memberOf, type ManifestCard } from "../manifest";
import { MAX_SHOWCASE, type CollectionProgress } from "../net/protocol";
import { BANNER_ASPECT, BANNER_FIT, bannerArt, sweepArt, type Plate } from "../pet/plates";
import { roomStatus } from "../roomStatus";
import { reducedMotion } from "../stores/theme";
import { moved, nearestSlot, slotWhileDragging } from "./showcaseDrag";
import Icon from "../ui/Icon.vue";
import PetBust from "./PetBust.vue";

const props = defineProps<{
  plate: Plate | null;
  name: string;
  character: string;
  showcase: ManifestCard[];
  /** Undefined while it loads, null when it is not known. */
  progress: CollectionProgress | null | undefined;
  /** The profile did not load: no counts and no cards to show. */
  failed?: boolean;
  editable?: boolean;
  /** Whether the card offers a plate to wear; editable cards only. */
  swappable?: boolean;
  /** A room partner's status, shown after the name. */
  status?: string | null;
}>();
const shownStatus = computed(() => roomStatus(props.status));
const emit = defineEmits<{
  open: [card: ManifestCard]; swap: []; pick: []; drop: [card: ManifestCard];
  /** The pinned cards' ids in the order they were dragged into. */
  reorder: [ids: string[]];
}>();

/** The card's height. Its artwork spans at most BANNER_ASPECT times that, framed as the plate crops are set for,
 * and leaves TEXT_ROOM at the left for the name and counts. */
const HEIGHT = 184;
const TEXT_ROOM = 220;
const box = ref<HTMLElement>();
const width = ref(0);
let observer: ResizeObserver | undefined;
watch(box, (el) => {
  observer?.disconnect();
  if (!el || typeof ResizeObserver === "undefined") return;
  observer = new ResizeObserver(([entry]) => { if (entry) width.value = Math.floor(entry.contentRect.width); });
  observer.observe(el);
}, { immediate: true });
onBeforeUnmount(() => observer?.disconnect());
const artWidth = computed(() => Math.max(0, Math.min(width.value - TEXT_ROOM, HEIGHT * BANNER_ASPECT)));
/** A card plate shows its full-size still over its thumbnail, a series plate its full-size frame over the video's
 * poster, a sweep plate its cut-out on coral. */
const art = computed(() => {
  const p = props.plate, w = artWidth.value;
  if (!p || !w) return null;
  if (p.kind === "card") {
    return { src: assetUrl(p.card.full), back: `url(${assetUrl(p.card.thumb)})`, at: bannerArt(p.crop, w, HEIGHT), sweep: false };
  }
  if (p.kind === "series") {
    return { src: assetUrl(p.still), back: `url(${assetUrl(p.poster)})`, at: bannerArt(p.motion.face, w, HEIGHT, p.aspect), sweep: false };
  }
  return { src: p.sweep.src, back: undefined, at: sweepArt(p.sweep, w, HEIGHT, BANNER_FIT).face, sweep: true };
});
const plateCard = computed(() => (props.plate?.kind === "card" ? props.plate.card : null));

const color = computed(() => characterColor(props.character));
const bust = computed(() => (characters[props.character] ?? characters[memberOf(props.character)])?.bg ?? "");
const pinned = computed(() => props.showcase.slice(0, MAX_SHOWCASE));
/** Others' cards show only what is pinned; the own card has one empty slot after them while there is room. */
const slots = computed<(ManifestCard | null)[]>(() =>
  (props.editable && pinned.value.length < MAX_SHOWCASE ? [...pinned.value, null] : pinned.value));
/** More than three are held as a hand: they overlap and fan out from the middle. */
const fanned = computed(() => pinned.value.length > 3);
/** How each pinned card leans, left to right; an empty slot stands straight. */
const TILTS = [-6, 2, 7];
const FAN_STEP = 5;
const tilt = (i: number) => (fanned.value ? (i - (pinned.value.length - 1) / 2) * FAN_STEP : TILTS[i] ?? 0);
/** The showcase's geometry as the style sets it: card widths, the gap between slots, a fanned card's overlap, and
 * its distance from the card's right edge. */
const PIN_WIDTH = 76;
const FAN_WIDTH = 72;
const PIN_GAP = 10;
const FAN_OVERLAP = 18;
const SHOWCASE_RIGHT = 22;
/** Where the counts' column ends, with some air; the hand stays right of it. */
const STATS_END = 136;
/** The least of each card that stays in sight past the next one. */
const MIN_STEP = 30;
/** How much further each pinned card slides over the one before it so the hand clears the counts on a narrow card
 * (the own card at a small panel size); 0 wherever the hand fits as it is. The outermost card's lean is counted. */
const squeeze = computed(() => {
  const n = pinned.value.length;
  if (n < 2 || !width.value) return 0;
  const w = fanned.value ? FAN_WIDTH : PIN_WIDTH;
  const step = fanned.value ? w - FAN_OVERLAP + PIN_GAP : w + PIN_GAP;
  const lean = Math.abs(tilt(0)) * Math.PI / 180;
  const swing = (fanned.value ? 1.2 : 0.5) * 1.5 * w * Math.sin(lean) + (w / 2) * (1 - Math.cos(lean));
  const hand = w + (n - 1) * step + (slots.value.length > n ? PIN_GAP + w : 0) + swing;
  const room = width.value - SHOWCASE_RIGHT - STATS_END;
  return Math.min(step - MIN_STEP, Math.max(0, Math.ceil((hand - room) / (n - 1))));
});
/**
 * Dragging a pinned card on the own card: past DRAG_START px it lifts and follows the pointer, and the cards between
 * its place and the slot nearest to it move over, taking that slot's lean. Let go, the order is handed up and the card
 * settles into its slot from where it was let go. Pointer events, as HTML drag and drop is unreliable in the webviews.
 */
const DRAG_START = 5;
const list = ref<HTMLElement>();
/** The press on a pinned card that may become a drag. */
let press: { pointer: number; from: number; x: number; y: number } | null = null;
/** The drag under way: where the card came from and where it would go, and the slots' centres in the row when it
 * started. */
const drag = ref<{ from: number; to: number; dx: number; dy: number; centers: number[] } | null>(null);
/** The click that ends a drag opens nothing. */
let swallowClick = false;
/** For the frame the new order is first drawn in: no transitions, and the dropped card still where it was let go. */
const settling = ref<{ id: string; dx: number; dy: number } | null>(null);

function pressPin(e: PointerEvent, i: number) {
  swallowClick = false;
  if (!props.editable || pinned.value.length < 2 || e.button !== 0 || settling.value) return;
  press = { pointer: e.pointerId, from: i, x: e.clientX, y: e.clientY };
}
function move(e: PointerEvent) {
  if (!press || e.pointerId !== press.pointer) return;
  // Let go where the card did not hear it (off the card before a drag captured the pointer): the press is over.
  if (!(e.buttons & 1)) return clear();
  const dx = e.clientX - press.x, dy = e.clientY - press.y;
  if (!drag.value) {
    if (Math.hypot(dx, dy) < DRAG_START) return;
    // The layout boxes, not the turned ones: a fanned card turns about a point under it, which moves its drawn box sideways.
    const items = [...(list.value?.children ?? [])].slice(0, pinned.value.length) as HTMLElement[];
    const centers = items.map((li) => li.offsetLeft + li.offsetWidth / 2);
    drag.value = { from: press.from, to: press.from, dx, dy, centers };
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  }
  const d = drag.value;
  d.dx = dx;
  d.dy = dy;
  d.to = nearestSlot(d.centers, d.centers[d.from] + dx);
}
/** The press, and the drag it became, are over. */
function clear() {
  press = null;
  drag.value = null;
}
async function release(e: PointerEvent) {
  if (!press || e.pointerId !== press.pointer) return;
  const d = drag.value;
  clear();
  if (!d) return;
  swallowClick = true;
  // Back in its own place, the card's transition takes it there.
  if (d.to === d.from) return;
  const ids = moved(pinned.value.map((c) => c.id), d.from, d.to);
  const id = ids[d.to];
  if (!reducedMotion.value) settling.value = { id, dx: d.centers[d.from] + d.dx - d.centers[d.to], dy: d.dy };
  emit("reorder", ids);
  if (!settling.value) return;
  // The new order is drawn with the card where it was let go; from there its transition takes it into the slot.
  await nextTick();
  list.value?.getBoundingClientRect();
  settling.value = null;
}
function cancel(e: PointerEvent) {
  if (!press || e.pointerId !== press.pointer) return;
  clear();
}
function openPin(card: ManifestCard) {
  if (swallowClick) { swallowClick = false; return; }
  emit("open", card);
}
/** Where pinned card [i] stands while a card is dragged or has just been let go; undefined leaves it to the style. */
function dragStyle(card: ManifestCard, i: number): Record<string, string> | undefined {
  const s = settling.value;
  if (s?.id === card.id) return { transform: `translate(${s.dx}px, ${s.dy - 8}px) scale(1.06)`, zIndex: "3" };
  const d = drag.value;
  if (!d) return undefined;
  if (i === d.from) return { transform: `translate(${d.dx}px, ${d.dy - 8}px) scale(1.06)`, zIndex: "3", transition: "none" };
  const slot = slotWhileDragging(i, d.from, d.to);
  if (slot === i) return undefined;
  return { transform: `translateX(${d.centers[slot] - d.centers[i]}px) rotate(${tilt(slot)}deg)` };
}

const stats = computed(() => (["cards", "emotes", "skins"] as const).map((kind, i) => ({
  label: ["卡片", "表情", "皮肤"][i],
  count: props.progress?.[kind] ?? null,
})));
const px = (n: number) => `${n}px`;
</script>

<template>
  <div ref="box" class="namecard" :class="{ pinning: slots.length > 0 && !failed }" :style="{ height: px(HEIGHT) }">
    <div class="face">
      <component
        :is="plateCard ? 'button' : 'div'" class="art-box" :class="{ sweep: art?.sweep, bare: !art }"
        :style="{ width: px(artWidth) }"
        v-bind="plateCard ? { type: 'button', title: plateCard.name, 'aria-label': `查看${plateCard.name}` } : {}"
        @click="plateCard && emit('open', plateCard)"
      >
        <img
          v-if="art" class="art" :src="art.src" alt="" draggable="false" decoding="async"
          :style="{ width: px(art.at.width), height: px(art.at.height), left: px(art.at.left), top: px(art.at.top), backgroundImage: art.back }"
        />
      </component>
    </div>

    <span class="badge-bust" :style="{ '--member': color }" aria-hidden="true"><PetBust v-if="bust" class="bust" :src="bust" detail /></span>
    <h3 class="name">
      <i :style="{ background: color }" aria-hidden="true"></i><span>{{ name }}</span>
      <em v-if="shownStatus" class="status"><Icon :name="shownStatus.icon" :size="14" />{{ shownStatus.label }}</em>
    </h3>
    <p v-if="failed" class="stats failed">没加载出来</p>
    <dl v-else class="stats">
      <div v-for="s in stats" :key="s.label">
        <dt>{{ s.label }}</dt>
        <dd><b>{{ s.count ? s.count[0] : progress === undefined ? "…" : "—" }}</b><small v-if="s.count">/{{ s.count[1] }}</small></dd>
      </div>
    </dl>

    <button v-if="editable && swappable" type="button" class="ui-btn small swap" @click="emit('swap')">
      {{ plate ? "换铭牌" : "戴铭牌" }}
    </button>
    <ul
      v-if="slots.length && !failed" ref="list" class="showcase"
      :class="{ fanned, sorting: !!drag, calm: reducedMotion || !!settling }" :style="{ '--squeeze': px(squeeze) }" aria-label="展示卡"
    >
      <li
        v-for="(card, i) in slots" :key="card?.id ?? `empty-${i}`" :class="{ spare: !card }"
        :style="[{ '--tilt': card ? `${tilt(i)}deg` : '0deg' }, card ? dragStyle(card, i) : undefined]"
      >
        <template v-if="card">
          <button
            type="button" class="pin" :class="[cardFrame(card), { framed: !!cardFrame(card), movable: editable && pinned.length > 1 }]"
            :title="card.name" @click="openPin(card)"
            @pointerdown="pressPin($event, i)" @pointermove="move" @pointerup="release" @pointercancel="cancel" @lostpointercapture="cancel"
          >
            <img :src="assetUrl(card.thumb)" :alt="card.name" decoding="async" draggable="false" />
          </button>
          <button v-if="editable" type="button" class="drop" title="取下" :aria-label="`取下${card.name}`" @click="emit('drop', card)">
            <Icon name="close" :size="10" />
          </button>
        </template>
        <button v-else type="button" class="pin empty" :title="`选展示卡 ${pinned.length}/${MAX_SHOWCASE}`" aria-label="选展示卡" @click="emit('pick')">
          <Icon name="plus" :size="18" />
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
/* Room above for the bust's head and below for the pinned cards, which both reach past the paper. */
.namecard {
  position: relative;
  flex: none;
  margin: 62px 0 0;
}
.namecard.pinning {
  margin-bottom: 48px;
}
/* The one sheet of paper; the artwork is inside it, not a second frame. */
.face {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: 20px;
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
/* The artwork stands at the right and fades into the paper toward the name. */
.art-box {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  display: block;
  padding: 0;
  border: 0;
  overflow: hidden;
  background: var(--ink);
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 46%);
  mask-image: linear-gradient(90deg, transparent, #000 46%);
}
button.art-box {
  cursor: pointer;
}
.art-box.sweep {
  background: var(--c-500);
}
/* Without a plate: the coral alone. */
.art-box.bare {
  background: var(--grad-sky);
}
.art {
  position: absolute;
  display: block;
  max-width: none;
  background: center / cover no-repeat;
  pointer-events: none;
  user-select: none;
  transition: transform var(--dur-slow) var(--ease-out);
}
button.art-box:hover .art {
  transform: scale(1.03);
}

/* The pet's bust whole in a frame of its own proportions (the bust crop, 132 x 120), standing over the upper edge:
 * the crop's sides and the desk line fall on the frame's edges instead of being cut across the hair. */
.badge-bust {
  position: absolute;
  left: 24px;
  top: -34px;
  width: 104px;
  height: 95px;
  overflow: hidden;
  border-radius: var(--radius-l);
  background: color-mix(in srgb, var(--member) 22%, var(--c-50));
  box-shadow: 0 0 0 4px var(--surface), 0 6px 16px -8px rgba(var(--shadow-rgb), 0.45);
  pointer-events: none;
}
.bust {
  display: block;
  width: 100%;
  height: 100%;
}
.name {
  position: absolute;
  left: 146px;
  right: 128px;
  top: 16px;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  font: 800 28px/1.25 var(--font);
  color: var(--ink);
  text-shadow: 0 0 10px var(--surface), 0 0 3px var(--surface);
  pointer-events: none;
}
.name i {
  flex: none;
  width: 6px;
  height: 0.8em;
  border-radius: 2px;
}
.name span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.name .status {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 9px;
  border-radius: 999px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12);
  font: 800 var(--fs-label)/1 var(--font);
  font-style: normal;
  color: var(--c-700);
  text-shadow: none;
}
/* Collection counts in a column under the bust, one kind per line: the label, then the number and its total. */
.stats {
  position: absolute;
  left: 24px;
  top: 74px;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  pointer-events: none;
}
.stats > div {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.stats dt {
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.stats dd {
  margin: 0;
  line-height: 1;
  white-space: nowrap;
  text-shadow: 0 0 8px var(--surface);
}
.stats dd b {
  font: 800 24px/1 var(--font-latin);
  color: var(--ink);
}
.stats dd small {
  margin-left: 1px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink-3);
}
.stats.failed {
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink-3);
}

/* A flat key on a frosted face, as the card detail's video keys, so it reads over any artwork. */
.swap,
.swap:not(:disabled) {
  --key-top: rgba(255, 255, 255, 0.86);
  --key-bottom: rgba(255, 255, 255, 0.86);
  --key-y: 0px;
  --key-lip-h: 0px;
  --key-lift: 0px;
  position: absolute;
  right: 16px;
  top: 16px;
  color: var(--ink);
  backdrop-filter: blur(6px);
}
.swap:hover:not(:disabled) {
  --key-top: #fff;
  --key-bottom: #fff;
}

/* Showcase cards pinned over the lower right corner, leaning a little; the pointer straightens one and lifts it. */
.showcase {
  position: absolute;
  right: 22px;
  bottom: -40px;
  display: flex;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.showcase li {
  position: relative;
  width: 76px;
  transform: rotate(var(--tilt));
  transition: transform var(--dur-base) var(--ease-out);
}
.showcase li:hover {
  z-index: 2;
  transform: translateY(-6px) rotate(0deg);
}
/* On a narrow card the cards close up over one another by --squeeze (see the script) to stay clear of the counts. */
.showcase li + li {
  margin-left: calc(-1 * var(--squeeze, 0px));
}
/* A hand of four or five: each card lies over the one before it, pivoting low so the fan opens at the top. The
 * empty slot stands clear of the hand. */
.fanned li {
  width: 72px;
  transform-origin: 50% 120%;
}
.fanned li + li {
  margin-left: calc(-18px - var(--squeeze, 0px));
}
.showcase li.spare {
  margin-left: 0;
}
.pin {
  display: block;
  width: 100%;
  aspect-ratio: 2 / 3;
  padding: 0;
  border: 0;
  border-radius: var(--radius-m);
  overflow: hidden;
  background: var(--c-100);
  box-shadow: 0 2px 4px rgba(var(--shadow-rgb), 0.18), 0 12px 22px -12px rgba(var(--shadow-rgb), 0.55);
  cursor: pointer;
}
.pin.framed {
  padding: 3px;
  background: var(--frame-fill) var(--frame-at) / var(--frame-size);
}
.pin img {
  display: block;
  width: 100%;
  height: 100%;
  max-width: none;
  object-fit: cover;
}
.pin.framed img {
  border-radius: calc(var(--radius-m) - 3px);
}
.pin.empty {
  display: grid;
  place-items: center;
  box-sizing: border-box;
  border: 2px dashed var(--c-300);
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(6px);
  color: var(--c-400);
  box-shadow: none;
}
.pin.empty:hover {
  border-color: var(--c-400);
  color: var(--c-500);
}
/* A pinned card the owner can drag along the row; while one is dragged, the row keeps its pointer off the others. */
.pin.movable {
  touch-action: none;
  user-select: none;
}
.sorting li:hover {
  transform: rotate(var(--tilt));
}
.showcase.sorting li .drop,
.showcase.sorting li:hover .drop {
  opacity: 0;
}
.calm li {
  transition: none;
}
/* Takes the card down; shown over the card's corner while the pointer is on it. */
.drop {
  position: absolute;
  z-index: 2;
  right: -7px;
  top: -7px;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--surface);
  color: var(--ink-3);
  box-shadow: 0 1px 3px rgba(var(--shadow-rgb), 0.3);
  cursor: pointer;
  opacity: 0;
  transition: opacity var(--dur-fast), color var(--dur-fast);
}
.showcase li:hover .drop,
.drop:focus-visible {
  opacity: 1;
}
.drop:hover {
  color: var(--ink);
}
</style>
