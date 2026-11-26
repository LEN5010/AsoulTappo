<script setup lang="ts">
// Resonance stage: the page itself. The dynamic cards are held as a fanned hand (CardHand.vue) in front of a soft
// wash of the front card's colours. Beside it the
// page names the card and sums up the collection: the total, the tiers side by side as one instrument, then the
// special collections as rows (CollectionRows.vue: the holo versions, and the 衣橱 series where this pool gives its
// tier odds), and the skins.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl } from "../asset";
import { cardLabel, cardWord, ownsHolo, poolName, TIER_LABEL } from "../cards";
import { characters, getCharacter } from "../characters";
import { getCard, characterColor, manifest, type Rarity } from "../manifest";
import type { Item } from "../items";
import type { Plate } from "../pet/plates";
import { heldItems, standingPool } from "../resonance";
import { collection } from "../stores/player";
import { economy } from "../stores/economy";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";
import PetBust from "./PetBust.vue";
import CardHand from "./CardHand.vue";
import CollectionRows from "./CollectionRows.vue";

const props = defineProps<{ busy: boolean; paused?: boolean }>();
const emit = defineEmits<{ inspect: [item: Item]; plate: [plate: Plate] }>();

const STATS: { rarity: Rarity; label: string; icon: string }[] = [
  { rarity: "legendary", label: "大隐藏", icon: "crown" },
  { rarity: "skin", label: "皮肤", icon: "shirt" },
  { rarity: "epic", label: "史诗", icon: "spark" },
  { rarity: "rare", label: "稀有", icon: "gem" },
  { rarity: "uncommon", label: "罕见", icon: "layers" },
  { rarity: "common", label: "普通", icon: "star5" },
];

// The standing pool: what a limited pool keeps to itself for now, and a tier only a limited pool gives odds, is not
// counted or shown here.
const pool = computed(() => standingPool(heldItems()));
const all = computed(() => Object.values(pool.value).flat());
/** The dynamic cards the standing pool can deal. */
const previews = computed(() => [...pool.value.legendary, ...pool.value.epic].filter((i) => i.kind === "card"));
const skins = computed(() => pool.value.skin.flatMap((item) => {
  const bg = getCharacter(item.ref)?.bg;
  return bg ? [{ item, bg }] : [];
}));
const have = (items: Item[]) => items.filter((i) => collection.owned[i.id]).length;
const meter = computed(() =>
  STATS.filter((s) => pool.value[s.rarity].length).map((s) => {
    const got = have(pool.value[s.rarity]);
    return { ...s, got, total: pool.value[s.rarity].length, fill: `${(got / pool.value[s.rarity].length) * 100}%` };
  }),
);
/** The holo versions (镭射款) count here only where the server deals them. */
const holoCards = manifest.cards.filter((c) => c.holo);
const holoOn = computed(() => holoCards.length > 0 && !!economy.value?.resonance.holoChance);
const holoGot = computed(() => holoCards.filter((c) => ownsHolo(c, collection.owned)).length);
/** The 衣橱 series is summed up here only while the standing pool gives its tier odds. */
const closetOn = computed(() => pool.value.limited.length > 0);
/** The holo versions count as items of their own, as the collection's page counts them. */
const collected = computed(() => have(all.value) + (holoOn.value ? holoGot.value : 0));
const totalItems = computed(() => all.value.length + (holoOn.value ? holoCards.length : 0));
const allFill = computed(() => `${totalItems.value ? (collected.value / totalItems.value) * 100 : 0}%`);

/** The card on show, as the hand reports it (CardHand.vue). */
const active = ref<Item | undefined>(previews.value[0]);
const card = computed(() => (active.value?.kind === "card" ? getCard(active.value.ref) : undefined));
const feature = computed(() => {
  const c = card.value;
  const item = active.value;
  if (!c || !item) return null;
  const { title, who } = cardLabel(c);
  return {
    title,
    who,
    color: characterColor(c.characters[0] ?? ""),
    gold: c.tier === "big",
    label: c.tier !== "normal" ? TIER_LABEL[c.tier] : c.still ? "有声卡" : "跳舞卡",
    // The reveal stamps the same word, so the banner speaks its language.
    word: cardWord(c),
    series: poolName(manifest.series.find((x) => x.id === c.series)?.name ?? ""),
    owned: collection.owned[item.id] ?? 0,
  };
});

/** The members on the front card, peeking over the top of the sheet. No card has more than two. */
const peek = computed(() => {
  const c = card.value;
  const busts = (c?.characters ?? []).slice(0, 2).flatMap((name) => {
    const bg = characters[name]?.bg;
    return bg ? [{ name, bg }] : [];
  });
  return busts.length ? { key: busts.map((b) => b.name).join("+"), busts } : null;
});
// The corner it stands in is what the title leaves of the sheet's width. The hand and the title both scale with
// the panel, so it is measured: the peek takes the room clear of the title, or stays down if there is too little.
const PEEK_MAX = 96;
const PEEK_MIN = 52;
/** Kept clear of the last glyph, plus .peek's inset from the sheet's right edge. */
const PEEK_MARGIN = 22;
const titleEl = ref<HTMLElement>();
const sheetEl = ref<HTMLElement>();
const peekRoom = ref(0);
function measurePeek() {
  if (!titleEl.value || !sheetEl.value) return;
  const sheet = sheetEl.value.getBoundingClientRect();
  if (!sheet.width) return;
  const glyphs = document.createRange();
  glyphs.selectNodeContents(titleEl.value);
  peekRoom.value = sheet.right - glyphs.getBoundingClientRect().right;
}
const peekSize = computed(() => {
  // A pair reaches past the box on the left (.pair in the styles).
  const span = (peek.value?.busts.length ?? 1) > 1 ? 1.32 : 1;
  const size = Math.min(PEEK_MAX, (peekRoom.value - PEEK_MARGIN) / span);
  return size >= PEEK_MIN ? Math.round(size) : 0;
});

const skinViewport = ref<HTMLElement>();
const skinGroup = ref<HTMLElement[]>();
const skinFocused = ref(false);
// The detail sheet restores focus to its trigger when it closes. Resume after
// that restoration instead of treating it as a new keyboard navigation action.
watch(() => props.paused, (paused) => {
  if (!paused) skinFocused.value = false;
}, { flush: "post" });
const pageActive = usePageActive();
const skinWidth = ref(0);
const viewportWidth = ref(0);
const canMarquee = computed(() => !reducedMotion.value && skinWidth.value > viewportWidth.value);
const scrolling = computed(() => canMarquee.value && pageActive.value && !props.busy && !props.paused && !skinFocused.value);
/** One group width at the old 24px/s, so the loop keeps the same pace at any panel size. */
const marqueeDuration = computed(() => `${Math.max(8, skinWidth.value / 24)}s`);
let resize: ResizeObserver | undefined;
let frame = 0;
let observing = false;
function measure() {
  frame = 0;
  const sw = skinGroup.value?.[0]?.offsetWidth ?? 0;
  const vw = skinViewport.value?.clientWidth ?? 0;
  if (vw > 0) {
    skinWidth.value = sw;
    viewportWidth.value = vw;
  }
  measurePeek();
}
function schedule() {
  if (!frame) frame = requestAnimationFrame(measure);
}
function connect() {
  observing = true;
  resize?.disconnect();
  if (skinViewport.value) resize?.observe(skinViewport.value);
  if (skinGroup.value?.[0]) resize?.observe(skinGroup.value[0]);
  if (sheetEl.value) resize?.observe(sheetEl.value);
  schedule();
}
function disconnect() {
  observing = false;
  resize?.disconnect();
  cancelAnimationFrame(frame);
  frame = 0;
}
onMounted(() => {
  measure();
  resize = new ResizeObserver(schedule);
  connect();
  // The title's width changes once the bundled font replaces the fallback.
  void document.fonts?.ready.then(schedule);
});
onActivated(connect);
onDeactivated(disconnect);
watch(skinViewport, () => { if (observing) connect(); }, { flush: "post" });
onBeforeUnmount(disconnect);
</script>

<template>
  <section
    class="pool-stage"
    :class="{ calm: reducedMotion, marquee: canMarquee, run: scrolling, tabbed: $slots.switch, full: closetOn && $slots.switch }"
    :style="{ '--marquee': marqueeDuration }"
  >
    <div class="wash" aria-hidden="true">
      <Transition name="wash" :css="!reducedMotion">
        <span v-if="card" :key="card.id" class="wash-blob">
          <img :src="assetUrl(card.thumb)" alt="" draggable="false" />
        </span>
      </Transition>
    </div>

    <CardHand :items="previews" :busy="busy" :paused="paused" :hold="skinFocused" @inspect="emit('inspect', $event)" @show="active = $event" />

    <div class="info">
      <header class="title">
        <slot name="switch"><span class="ui-eyebrow">RESONANCE</span></slot>
        <h3 ref="titleEl">常驻共鸣</h3>
      </header>

      <div ref="sheetEl" class="sheet">
      <div v-if="peekSize" class="peek" :style="{ '--peek-w': `${peekSize}px` }" aria-hidden="true">
        <Transition name="peek" mode="out-in" :css="!reducedMotion">
          <span v-if="peek" :key="peek.key" class="peek-row" :class="{ pair: peek.busts.length > 1 }">
            <PetBust v-for="b in peek.busts" :key="b.name" class="peek-bust" :src="b.bg" />
          </span>
        </Transition>
      </div>
      <div class="feature-slot">
      <Transition name="feature" mode="out-in" :css="!reducedMotion">
        <div v-if="feature" :key="active?.id" class="feature">
          <p class="tags">
            <span class="ui-tag tier" :class="{ gold: feature.gold }"><em>{{ feature.word }}</em>{{ feature.label }}</span>
            <span class="who"><i :style="{ background: feature.color }"></i>{{ feature.who }}</span>
            <span class="series">{{ feature.series }}</span>
          </p>
          <h4>{{ feature.title }}</h4>
          <p class="owned" :class="{ yes: feature.owned }">
            <template v-if="feature.owned"><Icon name="check" :size="14" />已拥有<b v-if="feature.owned > 1">×{{ feature.owned }}</b></template>
            <template v-else><Icon name="lock" :size="13" />未获得</template>
          </p>
        </div>
      </Transition>
      </div>

      <div class="meter">
        <p class="total">
          <b>{{ collected }}</b><i>/ {{ totalItems }}</i>
          <span class="all-bar" aria-hidden="true"><i :style="{ width: allFill }"></i></span>
        </p>
        <ul class="tiers">
          <li v-for="t in meter" :key="t.rarity" :class="[t.rarity, { done: t.got === t.total }]" :title="`${t.label} ${t.got}/${t.total}`">
            <span class="t-ring" :style="{ '--p': t.fill }" role="img" :aria-label="`${t.label} ${t.got}/${t.total}`">
              <Icon :name="t.icon" :size="15" />
            </span>
            <span class="t-count"><b>{{ t.got }}</b><i>/{{ t.total }}</i></span>
            <em class="t-name">{{ t.label }}</em>
          </li>
        </ul>
        <CollectionRows :closet="closetOn" holo :busy="busy" :hold="!pageActive || busy || paused" @plate="emit('plate', $event)" />
      </div>
      </div>

      <div
        v-if="skins.length" ref="skinViewport" class="skins" role="region" aria-label="皮肤预览"
        @pointerdown="skinFocused = false"
        @focusin="skinFocused = ($event.target as HTMLElement).matches(':focus-visible')"
        @focusout="skinFocused = ($event.currentTarget as HTMLElement).contains($event.relatedTarget as Node | null)"
      >
        <div class="skin-track">
        <div v-for="copy in reducedMotion ? 1 : 2" :key="copy" ref="skinGroup" class="skin-group" :aria-hidden="copy === 2 ? true : undefined">
        <button
          v-for="{ item, bg } in skins" :key="item.id" type="button" class="skin-stand"
          :tabindex="copy === 2 ? -1 : undefined"
          :disabled="busy" :title="item.name" :aria-label="`查看${item.name}`" @click="emit('inspect', item)"
        >
          <span class="stand"><PetBust class="skin-bust" :src="bg" /></span>
          <b class="skin-name">{{ item.name }}</b>
        </button>
        </div>
        </div>
      </div>

    </div>
  </section>
</template>

<style scoped>
.pool-stage {
  /* Fits the fanned hand, lineup, pool tabs, sheet and standees above the sticky console without scrolling. */
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

/* The front card, blurred into a soft blob behind the hand only. It is gone well before the page's
 * left edge, where the sidebar tab joins the page, and before the text. */
.wash {
  position: absolute;
  left: 24px;
  top: 0;
  bottom: 0;
  width: calc(var(--card-w) * 1.3 + 90px);
  overflow: hidden;
  pointer-events: none;
  -webkit-mask: radial-gradient(closest-side, #000 25%, transparent 100%);
  mask: radial-gradient(closest-side, #000 25%, transparent 100%);
}
/* Blur a postage-stamp image, then scale the already-filtered layer. The mask stays on .wash. */
.wash-blob {
  position: absolute;
  left: 50%;
  top: 46%;
  width: 72px;
  height: 72px;
  transform: translate(-50%, -50%) scale(7);
}
.wash-blob img {
  display: block;
  width: 72px;
  height: 72px;
  object-fit: cover;
  filter: blur(5px) saturate(1.5) brightness(1.12);
  opacity: 0.55;
}
.wash-enter-active,
.wash-leave-active {
  transition: opacity 900ms var(--ease-in-out);
}
.wash-enter-from,
.wash-leave-to {
  opacity: 0;
}

.info {
  position: relative;
  z-index: 2;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 0;
}
/* One paper sheet, above the fanned cards. It overlaps the hand's right edge so the back cards slide under it. */
.sheet {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 11px;
  margin-left: calc(var(--stage-gap) * -1 - 18px);
  padding: 13px 18px 12px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.feature-slot {
  min-height: 78px;
}

/* The front card's member stands behind the sheet with only her head over its top edge, in the corner the title
 * leaves free. She ducks behind the paper and the next one comes up whenever the card changes. */
.sheet {
  position: relative;
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
/* Two members: the second one a step behind and to the left, leaning the other way. */
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

/* What the front card is: its tier, its member and its name, big. */
.feature {
  min-width: 0;
}
.tags {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  min-width: 0;
  white-space: nowrap;
}
.tier {
  padding: 0 8px 0 6px;
  line-height: 19px;
  font-size: var(--fs-label);
}
.tier.gold {
  --tag-bg: var(--grad-gold);
  --tag-fg: var(--ink);
}
.tier em {
  margin-right: 5px;
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  letter-spacing: 0.08em;
}
.who {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-label);
  font-weight: 800;
}
.who i {
  width: 4px;
  height: 12px;
}
.series {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--fs-label);
  font-weight: 500;
  color: var(--ink-3);
}
.feature h4 {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  margin: 4px 0 3px;
  overflow: hidden;
  text-wrap: balance;
  font: 800 clamp(20px, 2.8cqw, 26px)/1.22 var(--font);
  letter-spacing: 0.02em;
}
.owned {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.owned.yes {
  color: var(--c-700);
}
.owned b {
  margin-left: 2px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
}
.feature-enter-active {
  transition: opacity 260ms, transform 360ms var(--ease-out);
}
.feature-leave-active {
  transition: opacity 140ms var(--ease-in), transform 140ms var(--ease-in);
}
.feature-enter-from {
  opacity: 0;
  transform: translateX(14px);
}
.feature-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}

/* The collection at a glance: the total beside its own bar, then a medal a tier: its mark in a ring that fills. */
.meter {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
}
.total {
  flex: none;
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin: 0;
  white-space: nowrap;
}
.total b {
  font: 800 38px/0.9 var(--font-latin);
  color: var(--ink);
}
.total > i {
  font: 800 20px/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.all-bar {
  flex: 1;
  align-self: center;
  height: 10px;
  margin-left: 10px;
  border-radius: 5px;
  background: var(--c-100);
  overflow: hidden;
}
.all-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--c-400), var(--c-500));
  transition: width var(--dur-stage) var(--ease-out);
}
.tiers {
  flex: none;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
/* Fills climb the rarity ladder, a step deeper wherever the ladder colour is too pale to read as a fill. */
.tiers li {
  --fill: var(--c-500);
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}
.tiers .legendary { --fill: var(--gold); --mark: var(--gold); }
.tiers .skin { --fill: var(--c-500); }
.tiers .epic { --fill: var(--c-800); --mark: var(--c-800); }
.tiers .rare { --fill: var(--c-600); }
.tiers .uncommon { --fill: var(--c-500); }
.tiers .common { --fill: var(--c-400); }
.t-ring {
  position: relative;
  width: 42px;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: conic-gradient(var(--fill) var(--p), var(--c-100) 0);
  color: var(--mark, var(--c-700));
}
/* The paper inside the ring: what is left is a band 5px wide. */
.t-ring::before {
  content: "";
  position: absolute;
  inset: 5px;
  border-radius: 50%;
  background: var(--surface);
}
.t-ring svg {
  position: relative;
}
.tiers .done .t-ring::before {
  background: color-mix(in srgb, var(--fill) 14%, var(--surface));
}
.t-count {
  display: flex;
  align-items: baseline;
  gap: 1px;
  white-space: nowrap;
}
.t-count b {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.tiers .done .t-count b {
  color: var(--c-700);
}
.tiers .legendary.done .t-count b {
  color: color-mix(in oklab, var(--gold) 72%, var(--ink));
}
.t-count i {
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.t-name {
  margin-top: -2px;
  font: 700 var(--fs-caption)/1 var(--font);
  font-style: normal;
  color: var(--ink-2);
  white-space: nowrap;
}

/* Skins as acrylic standees: the bust in a wide clear outline, on an oval base, its name underneath. */
.skins {
  min-width: 0;
  overflow-x: auto;
  padding: 4px 0 2px;
  scrollbar-width: none;
}
.marquee .skins {
  overflow: hidden;
  /* The row dissolves at the two ends it scrolls off, not along each bust. */
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 28px, #000 calc(100% - 28px), transparent);
  mask-image: linear-gradient(90deg, transparent, #000 28px, #000 calc(100% - 28px), transparent);
}
.skins::-webkit-scrollbar { display: none; }
.skin-track { display: flex; width: max-content; }
.marquee .skin-track {
  animation: skin-marquee var(--marquee, 40s) linear infinite;
  animation-play-state: paused;
}
.run .skin-track {
  animation-play-state: running;
}
.skin-group {
  flex: none;
  display: flex;
  gap: 6px;
  padding-right: 6px;
}
.skin-stand {
  position: relative;
  flex: none;
  width: 82px;
  padding: 0;
  border: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  background: none;
  color: var(--ink);
  cursor: pointer;
}
.stand {
  position: relative;
  display: block;
  width: 58px;
  height: 58px;
}
.stand::before {
  content: "";
  position: absolute;
  left: 10%;
  right: 10%;
  bottom: 1px;
  height: 10px;
  border-radius: 50%;
  background: var(--c-100);
  box-shadow: 0 2px 0 var(--c-200), 0 3px 6px -2px rgba(var(--shadow-rgb), 0.22);
  transition: background var(--dur-base), box-shadow var(--dur-base);
}
.skin-bust {
  position: relative;
  z-index: 1;
  display: block;
  width: 100%;
  height: calc(100% - 3px);
  filter: var(--contour) drop-shadow(0 2px 2px rgba(var(--shadow-rgb), 0.18));
  transition: transform var(--dur-base) var(--ease-out);
}
.skin-stand:hover:not(:disabled) .skin-bust {
  transform: translateY(-4px);
}
.skin-stand:hover:not(:disabled) .stand::before {
  background: var(--c-200);
  box-shadow: 0 2px 0 var(--c-300), 0 4px 8px -2px rgba(var(--shadow-rgb), 0.24);
}
.skin-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 700 var(--fs-caption)/1.3 var(--font);
}

@keyframes skin-marquee {
  to {
    transform: translateX(-50%);
  }
}

@container panel (max-width: 820px) {
  .series {
    display: none;
  }
  .pool-stage {
    --stage-gap: 18px;
    padding-right: 18px;
  }
  .total b { font-size: 36px; }
  .t-ring { width: 36px; }
  .t-name { display: none; }
}
@container panel (max-width: 660px) {
  .pool-stage { flex-direction: column; align-items: center; gap: 18px; padding: 18px 16px 12px; }
  .pool-stage :deep(.hand) { --hero-h: 214px; --card-w: 150px; }
  .wash { left: 50%; transform: translateX(-50%); height: 300px; bottom: auto; }
  .info { width: 100%; }
  .sheet { margin-left: 0; }
}
/* Both rows under the pools' tabs: a little closer together, so the standees stay above the bar. */
@container panel (min-width: 661px) and (max-height: 745px) {
  .full .feature-slot {
    min-height: 58px;
  }
  .full .feature {
    position: relative;
  }
  .full .feature h4 {
    margin-bottom: 0;
    padding-right: 76px;
  }
  .full .owned {
    position: absolute;
    right: 0;
    bottom: 7px;
  }
  .full .sheet {
    gap: 8px;
    padding: 11px 18px 10px;
  }
  .full .meter {
    gap: 7px;
  }
  .full .tiers li {
    gap: 4px;
  }
  .full .t-ring {
    width: 38px;
  }
}
@container panel (max-height: 690px) {
  .full .tiers {
    display: none;
  }
}
/* Under the tabs a low window has no room for the standees' names. */
@container panel (min-width: 661px) and (max-height: 600px) {
  .tabbed .skin-name {
    display: none;
  }
  .tabbed .skins {
    padding: 2px 0 0;
  }
}
/* Keeps the action bar above the fold: the total still sums up what the tier gauges break down. */
@container panel (max-height: 640px) {
  .tiers {
    display: none;
  }
}
</style>
