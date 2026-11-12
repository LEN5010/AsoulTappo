<script setup lang="ts">
// A profile as others see it, one namecard: the plate's artwork across the right fading into paper, the pet's bust
// framed on the upper edge, the name and collection counts on the paper, and up to three showcase cards pinned
// over the lower right corner. The own card on the 排行 page is the same card made editable: a key swaps the plate,
// an empty slot picks a card, a pinned card's corner key takes it down. The owner opens the pickers and the cards.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { assetUrl } from "../asset";
import { cardFrame } from "../cards";
import { characters } from "../characters";
import { characterColor, memberOf, type ManifestCard } from "../manifest";
import { MAX_SHOWCASE, type CollectionProgress } from "../net/protocol";
import { BANNER_ASPECT, BANNER_FIT, bannerArt, sweepArt, type Plate } from "../pet/plates";
import { roomStatus } from "../roomStatus";
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
const emit = defineEmits<{ open: [card: ManifestCard]; swap: []; pick: []; drop: [card: ManifestCard] }>();

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
/** A card plate shows its full-size still over its thumbnail; a sweep plate its cut-out on coral. */
const art = computed(() => {
  const p = props.plate, w = artWidth.value;
  if (!p || !w) return null;
  return p.kind === "card"
    ? { src: assetUrl(p.card.full), back: `url(${assetUrl(p.card.thumb)})`, at: bannerArt(p.crop, w, HEIGHT), sweep: false }
    : { src: p.sweep.src, back: undefined, at: sweepArt(p.sweep, w, HEIGHT, BANNER_FIT).face, sweep: true };
});
const plateCard = computed(() => (props.plate?.kind === "card" ? props.plate.card : null));

const color = computed(() => characterColor(props.character));
const bust = computed(() => (characters[props.character] ?? characters[memberOf(props.character)])?.bg ?? "");
/** Others' cards show only what is pinned; the own card keeps its empty slots to fill. */
const slots = computed(() =>
  props.editable ? Array.from({ length: MAX_SHOWCASE }, (_, i) => props.showcase[i] ?? null) : props.showcase);
/** How each pinned card leans, left to right; an empty slot stands straight. */
const TILTS = [-6, 2, 7];
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
    <ul v-if="slots.length && !failed" class="showcase" aria-label="展示卡">
      <li v-for="(card, i) in slots" :key="card?.id ?? `empty-${i}`" :style="{ '--tilt': card ? `${TILTS[i]}deg` : '0deg' }">
        <template v-if="card">
          <button type="button" class="pin" :class="[cardFrame(card), { framed: !!cardFrame(card) }]" :title="card.name" @click="emit('open', card)">
            <img :src="assetUrl(card.thumb)" :alt="card.name" decoding="async" draggable="false" />
          </button>
          <button v-if="editable" type="button" class="drop" title="取下" :aria-label="`取下${card.name}`" @click="emit('drop', card)">
            <Icon name="close" :size="10" />
          </button>
        </template>
        <button v-else type="button" class="pin empty" title="选展示卡" aria-label="选展示卡" @click="emit('pick')">
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
/* Collection counts as large numbers over small labels, split by short rules. */
.stats {
  position: absolute;
  left: 24px;
  bottom: 20px;
  margin: 0;
  display: flex;
  align-items: flex-end;
  pointer-events: none;
}
.stats > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 18px;
}
.stats > div:first-child {
  padding-left: 0;
}
.stats > div + div {
  border-left: 2px solid var(--c-100);
}
.stats dt {
  order: 2;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.stats dd {
  margin: 0;
  white-space: nowrap;
  text-shadow: 0 0 8px var(--surface);
}
.stats dd b {
  font: 800 34px/1 var(--font-latin);
  color: var(--ink);
}
.stats dd small {
  margin-left: 2px;
  font: 800 var(--fs-number)/1 var(--font-latin);
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
  transform: translateY(-6px) rotate(0deg);
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
