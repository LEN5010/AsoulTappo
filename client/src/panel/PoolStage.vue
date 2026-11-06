<script setup lang="ts">
// Resonance stage: a banner washed in the colours of the card on show. The dynamic cards are held
// as a fanned hand in front of slow rays, with the card on show at the front; the banner names it
// and sums up the collection, its skins and the lineup. The lineup deals the next card on its own.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl } from "../asset";
import { cardLabel, poolName, TIER_LABEL } from "../cards";
import { getCharacter, skinSeries } from "../characters";
import { getCard, characterColor, manifest, memberOf, type ManifestCard, type Rarity } from "../manifest";
import type { Item } from "../items";
import { poolOf } from "../resonance";
import { collection } from "../stores/player";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";
import PetBust from "./PetBust.vue";

const props = defineProps<{ busy: boolean; paused?: boolean }>();
const emit = defineEmits<{ inspect: [item: Item] }>();

const LINEUP_SIZE = 7;
const FAN_SIZE = 3;
const STATS: { rarity: Rarity; label: string; icon: string }[] = [
  { rarity: "legendary", label: "大隐藏", icon: "crown" },
  { rarity: "skin", label: "皮肤", icon: "shirt" },
  { rarity: "epic", label: "史诗", icon: "spark" },
  { rarity: "rare", label: "稀有", icon: "gem" },
  { rarity: "uncommon", label: "罕见", icon: "gem" },
  { rarity: "common", label: "普通", icon: "star5" },
];
/** The words the reveal stamps on these cards, so the banner speaks the same language. */
const WORD: Record<ManifestCard["tier"], string> = { big: "SECRET", small: "HIDDEN", normal: "DANCE" };

const pool = poolOf();
const all = Object.values(pool).flat();
const previews = [...pool.legendary, ...pool.epic].filter((i) => i.kind === "card");
const skins = pool.skin.flatMap((item) => {
  const bg = getCharacter(item.ref)?.bg;
  return bg ? [{ item, bg }] : [];
});
const have = (items: Item[]) => items.filter((i) => collection.owned[i.id]).length;
const meter = computed(() =>
  STATS.filter((s) => pool[s.rarity].length).map((s) => {
    const got = have(pool[s.rarity]);
    return { ...s, got, total: pool[s.rarity].length, fill: `${(got / pool[s.rarity].length) * 100}%` };
  }),
);
const collected = computed(() => have(all));

const selected = ref(previews[0]?.id ?? "");
const at = computed(() => Math.max(0, previews.findIndex((i) => i.id === selected.value)));
const active = computed(() => previews[at.value]);
const card = computed(() => (active.value?.kind === "card" ? getCard(active.value.ref) : undefined));
const neighbour = (step: number) => previews[(at.value + step + previews.length) % previews.length]!;
const cardOf = (item: Item) => getCard(item.ref);

/** Which way the cards are travelling: forward deals the next card to the front. */
const dealing = ref(1);
function go(step: number) {
  if (!step) return;
  dealing.value = Math.sign(step);
  selected.value = neighbour(step).id;
}

/** The hand: the card on show and the next ones peeking out behind it. */
const fan = computed(() =>
  Array.from({ length: Math.min(FAN_SIZE, previews.length) }, (_, step) => {
    const item = neighbour(step);
    const c = cardOf(item);
    return { item, step, card: c, gold: c?.tier === "big", frame: c?.tier === "big" ? "frame-gold" : c?.tier === "small" ? "frame-rose" : "" };
  }),
);
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
    label: c.tier === "normal" ? "跳舞卡" : TIER_LABEL[c.tier],
    word: WORD[c.tier],
    series: poolName(manifest.series.find((x) => x.id === c.series)?.name ?? ""),
    owned: collection.owned[item.id] ?? 0,
  };
});

// The shown card keeps the middle of the strip while the others slide past it. The progress
// bar under it times the rotation, so pausing that animation pauses everything.
const stripSize = Math.min(LINEUP_SIZE, previews.length);
const lineup = computed(() =>
  Array.from({ length: stripSize }, (_, i) => {
    const step = i - Math.floor(stripSize / 2);
    return { item: neighbour(step), step };
  }),
);
const pointing = ref(false);
watch(() => props.busy, () => (pointing.value = false));

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
const scrolling = computed(() => pageActive.value && !reducedMotion.value && !props.busy && !props.paused
  && !skinFocused.value && skinWidth.value > viewportWidth.value);
const playing = computed(() => pageActive.value && !reducedMotion.value && !props.busy && !props.paused);
let skinFrame = 0;
let skinTime = 0;
let skinOffset = 0;
let resize: ResizeObserver | undefined;
function scrollSkins(time: number) {
  const viewport = skinViewport.value;
  if (viewport && skinTime) {
    skinOffset = (skinOffset + Math.min(time - skinTime, 50) * .024) % skinWidth.value;
    viewport.scrollLeft = skinOffset;
  }
  skinTime = time;
  skinFrame = requestAnimationFrame(scrollSkins);
}
function startSkins() {
  if (skinFrame || !scrolling.value) return;
  skinTime = 0;
  skinOffset = skinViewport.value?.scrollLeft ?? 0;
  skinFrame = requestAnimationFrame(scrollSkins);
}
function stopSkins() {
  cancelAnimationFrame(skinFrame);
  skinFrame = 0;
}
watch(scrolling, (run) => run ? startSkins() : stopSkins());
onMounted(() => {
  resize = new ResizeObserver(() => {
    skinWidth.value = skinGroup.value?.[0]?.offsetWidth ?? 0;
    viewportWidth.value = skinViewport.value?.clientWidth ?? 0;
  });
  if (skinViewport.value) resize.observe(skinViewport.value);
  if (skinGroup.value?.[0]) resize.observe(skinGroup.value[0]);
});
onActivated(startSkins);
onDeactivated(stopSkins);
onBeforeUnmount(() => { stopSkins(); resize?.disconnect(); });
</script>

<template>
  <section class="pool-stage" :class="{ hold: !pageActive || busy || paused || pointing || skinFocused, calm: reducedMotion }">
    <div class="wash" aria-hidden="true">
      <Transition name="wash" :css="!reducedMotion">
        <img v-if="card" :key="card.id" :src="assetUrl(card.thumb)" alt="" draggable="false" />
      </Transition>
    </div>

    <div class="hand">
      <div class="fan" @pointerenter="pointing = true" @pointerleave="pointing = false">
        <i class="rays" aria-hidden="true"></i>
        <TransitionGroup :name="dealing > 0 ? 'fan-fwd' : 'fan-back'" :css="!reducedMotion">
          <button
            v-for="f in fan" :key="f.item.id" type="button"
            class="fan-card" :class="[`s${f.step}`, f.frame, { gold: f.gold }]"
            :disabled="busy" :title="f.item.name" :tabindex="f.step ? -1 : undefined"
            :aria-label="f.step ? `换到${f.item.name}` : `查看${f.item.name}`"
            @click="f.step ? go(f.step) : emit('inspect', f.item)"
          >
            <span class="art ui-frame">
              <video
                v-if="!f.step && f.card?.video && playing" :key="f.card.id"
                :src="assetUrl(f.card.video)" :poster="assetUrl(f.card.thumb)" autoplay loop muted playsinline
              ></video>
              <img
                v-else-if="f.card" :src="assetUrl(f.step || f.card.video ? f.card.thumb : f.card.full)" alt=""
                :style="{ backgroundImage: `url(${assetUrl(f.card.thumb)})` }" draggable="false"
              />
            </span>
            <b class="crest">A-SOUL</b>
          </button>
        </TransitionGroup>
        <Icon name="spark" :size="26" class="twinkle top" />
        <Icon name="spark" :size="14" class="twinkle side" />
      </div>
      <div class="lineup" @pointerenter="pointing = true" @pointerleave="pointing = false">
        <button v-if="previews.length > 1" type="button" class="flip" aria-label="上一张" :disabled="busy" @click="go(-1)">
          <Icon name="back" :size="18" />
        </button>
        <TransitionGroup tag="div" name="strip" class="row" :css="!reducedMotion">
          <button
            v-for="{ item, step } in lineup" :key="item.id" type="button" class="mini" :class="{ on: !step }"
            :disabled="busy" :title="item.name" :aria-pressed="!step" @click="go(step)"
          >
            <span class="ui-frame"><img :src="assetUrl(item.art)" :alt="item.name" draggable="false" /></span>
            <i v-if="!step && !reducedMotion && previews.length > 1" class="tick" aria-hidden="true" @animationend="go(1)"></i>
          </button>
        </TransitionGroup>
        <button v-if="previews.length > 1" type="button" class="flip next" aria-label="下一张" :disabled="busy" @click="go(1)">
          <Icon name="back" :size="18" />
        </button>
      </div>
    </div>

    <div class="info">
      <header class="title">
        <svg class="orbit" viewBox="0 0 320 110" aria-hidden="true">
          <ellipse cx="160" cy="55" rx="150" ry="34" transform="rotate(-8 160 55)" />
        </svg>
        <h3>此间共鸣</h3>
        <em>Resonance</em>
        <small>A-SOUL TAPPO</small>
      </header>

      <Transition name="feature" mode="out-in" :css="!reducedMotion">
        <div v-if="feature" :key="active?.id" class="feature">
          <p class="tags">
            <span class="ui-tag tier" :class="{ gold: feature.gold }"><em>{{ feature.word }}</em>{{ feature.label }}</span>
            <span class="who"><i :style="{ background: feature.color }"></i>{{ feature.who }}</span>
            <span class="series">{{ feature.series }}</span>
          </p>
          <h4>{{ feature.title }}</h4>
          <p class="owned" :class="{ yes: feature.owned }">
            <template v-if="feature.owned"><Icon name="check" :size="13" />已拥有<b v-if="feature.owned > 1">×{{ feature.owned }}</b></template>
            <template v-else><Icon name="lock" :size="13" />未获得</template>
          </p>
        </div>
      </Transition>

      <div class="meter">
        <p class="total"><b>{{ collected }}</b><i>/ {{ all.length }}</i><small>COLLECTED</small></p>
        <ul class="tiers">
          <li v-for="t in meter" :key="t.rarity" :class="t.rarity">
            <span class="t-head"><Icon :name="t.icon" :size="12" />{{ t.label }}<b>{{ t.got }}</b><i>/{{ t.total }}</i></span>
            <span class="t-bar"><i :style="{ width: t.fill }"></i></span>
          </li>
        </ul>
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
          v-for="{ item, bg } in skins" :key="item.id" type="button" class="skin-tile"
          :style="{ '--member': characterColor(item.ref) }"
          :tabindex="copy === 2 ? -1 : undefined"
          :disabled="busy" :title="item.name" :aria-label="`查看${item.name}`" @click="emit('inspect', item)"
        >
          <PetBust class="skin-bust" :src="bg" />
          <span class="skin-label"><b>{{ memberOf(item.ref) }}</b><small>{{ skinSeries(item.ref) }}</small></span>
        </button>
        </div>
        </div>
      </div>

    </div>
  </section>
</template>

<style scoped>
.pool-stage {
  /* 330px covers the page title, the dock below, the lineup under the hand and the paddings. */
  --hero-h: max(220px, min(36cqw, 100cqh - 330px));
  --card-w: calc(var(--hero-h) * 0.7);
  position: relative;
  flex: 1 0 auto;
  display: flex;
  align-items: stretch;
  gap: 18px;
  min-height: calc(var(--hero-h) + 64px);
  margin-top: 26px;
  padding: 18px 18px 14px 26px;
  box-sizing: border-box;
}

/* The card on show, blurred and lifted to a pale wash, so every card brings its own colours. */
.wash {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.7), 0 14px 30px -22px rgba(var(--accent-rgb), 0.9);
}
.wash img {
  position: absolute;
  left: -10%;
  top: -20%;
  width: 70%;
  height: 140%;
  object-fit: cover;
  filter: blur(34px) saturate(1.6) brightness(1.15);
  opacity: 0.58;
}
/* Fades to paper under the words; a soft floor of the accent along the bottom. */
.wash::after {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(98deg, transparent 18%, rgba(255, 255, 255, 0.78) 50%, rgba(255, 255, 255, 0.9) 70%),
    linear-gradient(180deg, transparent 70%, color-mix(in srgb, var(--accent-tint) 70%, transparent));
}
.wash-enter-active,
.wash-leave-active {
  transition: opacity 900ms var(--ease-in-out);
}
.wash-enter-from,
.wash-leave-to {
  opacity: 0;
}

/* The hand and, under it, the lineup that deals it. */
.hand {
  position: relative;
  z-index: 1;
  flex: none;
  width: calc(var(--card-w) * 1.3);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 14px;
}
/* The hand of cards. Cards pivot on their bottom edge, so the ones behind fan out at the top. */
.fan {
  position: relative;
  flex: none;
  height: var(--hero-h);
  /* The front card stands proud of the banner's top edge. */
  margin-top: -38px;
}
.rays {
  position: absolute;
  left: calc(var(--card-w) * 0.5 - var(--hero-h) * 0.75);
  top: calc(var(--hero-h) * -0.25);
  width: calc(var(--hero-h) * 1.5);
  aspect-ratio: 1;
  border-radius: 50%;
  background: repeating-conic-gradient(rgba(255, 255, 255, 0.85) 0 4deg, transparent 4deg 20deg);
  mask: radial-gradient(circle, #000 18%, transparent 66%);
  -webkit-mask: radial-gradient(circle, #000 18%, transparent 66%);
  opacity: 0.8;
  pointer-events: none;
  animation: rays-turn 48s linear infinite;
}
.hold .rays,
.calm .rays {
  animation-play-state: paused;
}
.fan-card {
  position: absolute;
  left: 0;
  bottom: 0;
  width: var(--card-w);
  height: var(--hero-h);
  /* The same share of the width as the reveal's framed cards. */
  padding: calc(var(--card-w) * 0.015);
  box-sizing: border-box;
  border: 0;
  border-radius: var(--radius-m);
  background: var(--frame-fill, var(--surface)) var(--frame-at, 0 0) / var(--frame-size, auto);
  box-shadow: 0 0 0 3px #fff, 0 16px 28px -16px rgba(var(--ink-rgb), 0.6);
  cursor: pointer;
  transform-origin: 50% 100%;
  transition: transform 520ms var(--ease-out), opacity 320ms, box-shadow var(--dur-base);
}
.s0 {
  z-index: 3;
  transform: rotate(-3deg);
}
.s1 {
  z-index: 2;
  transform: translateX(9%) rotate(4deg) scale(0.93);
}
.s2 {
  z-index: 1;
  transform: translateX(16%) rotate(8deg) scale(0.86);
}
/* The ones behind sit in its shade until the pointer picks one out. */
.fan-card:not(.s0)::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: rgba(var(--ink-rgb), 0.22);
  transition: opacity var(--dur-base);
}
.fan-card.s0:hover:not(:disabled) {
  transform: translateY(-6px) rotate(0deg);
  box-shadow: 0 0 0 3px #fff, 0 0 26px 4px rgba(var(--accent-rgb), 0.55), 0 22px 30px -16px rgba(var(--ink-rgb), 0.6);
}
.fan-card.s1:hover:not(:disabled) {
  transform: translateX(9%) translateY(-10px) rotate(5deg) scale(0.93);
}
.fan-card.s2:hover:not(:disabled) {
  transform: translateX(16%) translateY(-10px) rotate(9deg) scale(0.86);
}
.fan-card:not(.s0):hover::after {
  opacity: 0.4;
}
/* Forward: the front card is thrown off to the left, a new one slips in at the back. */
.fan-fwd-leave-active,
.fan-back-leave-active {
  z-index: 4;
  transition: transform 520ms var(--ease-in-out), opacity 420ms var(--ease-in);
}
.fan-fwd-leave-to {
  opacity: 0;
  transform: translate(-46%, 6%) rotate(-18deg) scale(0.9);
}
.fan-fwd-enter-from {
  opacity: 0;
  transform: translateX(22%) rotate(12deg) scale(0.8);
}
/* Back: the last card drops away behind, the previous one is pulled back in from the left. */
.fan-back-leave-active {
  z-index: 0;
}
.fan-back-leave-to {
  opacity: 0;
  transform: translateX(22%) rotate(12deg) scale(0.8);
}
.fan-back-enter-from {
  opacity: 0;
  transform: translate(-46%, 6%) rotate(-18deg) scale(0.9);
}
.art {
  display: block;
  width: 100%;
  height: 100%;
  background: var(--ink);
}
.art img,
.art video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: center / cover;
}
.crest {
  position: absolute;
  top: 2px;
  left: 50%;
  transform: translateX(-50%);
  padding: 3px 18px 4px;
  border-radius: 0 0 var(--radius-l) var(--radius-l);
  background: var(--ink);
  box-shadow: 0 0 0 1px var(--accent-mid);
  color: #fff;
  font: 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.18em;
  white-space: nowrap;
}
.gold .crest {
  box-shadow: 0 0 0 1px var(--gold);
  color: var(--gold-soft);
}
.twinkle {
  position: absolute;
  z-index: 4;
  color: var(--gold-soft);
  fill: var(--surface);
  stroke-width: 1.2;
  pointer-events: none;
}
.twinkle.top {
  top: -14px;
  left: -16px;
}
.twinkle.side {
  top: 12px;
  left: 14px;
}

.info {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
}

.title {
  position: relative;
  padding: 2px 0 0 10px;
}
.orbit {
  position: absolute;
  left: -14px;
  top: -10px;
  width: min(100%, 280px);
  height: auto;
  fill: none;
  stroke: var(--accent-mid);
  stroke-width: 1.4;
  pointer-events: none;
}
h3 {
  position: relative;
  margin: 0;
  font: 800 clamp(26px, 3.8cqw, 38px)/1.15 var(--font);
  letter-spacing: 0.03em;
}
.title em {
  position: relative;
  display: block;
  margin: -5px 0 0 30px;
  font: italic 400 clamp(15px, 2.2cqw, 21px)/1 "Snell Roundhand", "Segoe Script", "Brush Script MT", cursive;
  color: var(--accent-deep);
}
.title small {
  position: absolute;
  top: 0;
  right: 0;
  font: 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.14em;
  color: var(--ink-3);
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
  --tag-bg: var(--grad-deep);
  --tag-fg: #fff;
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
  margin: 6px 0 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 clamp(24px, 4.2cqw, 42px)/1.2 var(--font);
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
  color: var(--ok);
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

/* The collection at a glance: the total, then one small gauge per tier. */
.meter {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 9px 12px 10px;
  border-radius: var(--radius-m);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.total {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin: 0;
}
.total b {
  font: 800 28px/0.9 var(--font-latin);
  color: var(--accent-deep);
}
.total i {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.total small {
  margin-left: auto;
  font: 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.14em;
  color: var(--ink-3);
}
.tiers {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tiers li {
  --fill: var(--accent);
  min-width: 0;
}
.tiers .legendary { --fill: linear-gradient(90deg, var(--gold-soft), var(--gold)); }
.tiers .skin { --fill: linear-gradient(90deg, var(--grad-from), var(--accent)); }
.tiers .epic { --fill: linear-gradient(90deg, var(--accent), var(--tone-bottom)); }
.tiers .rare { --fill: var(--accent); }
.tiers .uncommon { --fill: var(--accent-mid); }
.tiers .common { --fill: var(--ink-3); }
.t-head {
  display: flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
.t-head svg {
  flex: none;
  color: var(--accent-deep);
}
.t-head b {
  margin-left: auto;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.t-head i {
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.t-bar {
  display: block;
  height: 4px;
  margin-top: 3px;
  border-radius: 2px;
  background: var(--accent-soft);
  overflow: hidden;
}
.t-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--fill);
  transition: width var(--dur-stage) var(--ease-out);
}

/* Skins stand up out of their tiles like acrylic standees. */
.skins {
  min-width: 0;
  overflow-x: auto;
  padding: 14px 0 2px;
  margin-top: -10px;
  scrollbar-width: none;
}
.skins::-webkit-scrollbar { display: none; }
.skin-track { display: flex; width: max-content; }
.skin-group {
  flex: none;
  display: flex;
  gap: 8px;
  padding-right: 8px;
}
.skin-tile {
  position: relative;
  flex: none;
  width: 118px;
  height: 50px;
  padding: 0 8px 0 2px;
  box-sizing: border-box;
  border: 0;
  border-radius: var(--radius-m);
  display: flex;
  align-items: flex-end;
  gap: 4px;
  background: linear-gradient(180deg, var(--surface) 40%, color-mix(in oklab, var(--member) 16%, var(--surface)));
  box-shadow: inset 0 0 0 1px var(--line-2), inset 0 -3px 0 var(--member);
  color: var(--ink);
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast);
}
.skin-tile:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: inset 0 0 0 1px var(--accent-mid), inset 0 -3px 0 var(--member), var(--glow-s);
}
.skin-bust {
  flex: none;
  width: 52px;
  height: 60px;
  margin-bottom: 3px;
  filter: var(--contour);
}
.skin-label {
  align-self: center;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
}
.skin-label b {
  font: 800 var(--fs-body)/1.25 var(--font);
}
.skin-label small {
  white-space: nowrap;
  font: 500 var(--fs-caption)/1.25 var(--font);
  color: var(--ink-2);
}

.lineup {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-bottom: 8px;
}
.flip {
  flex: none;
  width: 18px;
  height: 40px;
  padding: 0;
  display: grid;
  place-items: center;
  border: 0;
  background: none;
  color: var(--ink-2);
  cursor: pointer;
}
.flip:hover:not(:disabled) {
  color: var(--accent-deep);
}
.flip.next svg {
  transform: rotate(180deg);
}
.row {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 5px;
}
.mini {
  position: relative;
  aspect-ratio: 0.76;
  padding: 2px;
  border: 0;
  border-radius: var(--radius-s);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line-2);
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast);
}
.mini:hover:not(:disabled) {
  transform: translateY(-2px);
}
.mini.on {
  box-shadow: 0 0 0 2px var(--accent), var(--glow-s);
}
/* The rotation's clock: reaching the end deals the next card. */
.tick {
  position: absolute;
  left: 1px;
  right: 1px;
  bottom: -8px;
  height: 3px;
  border-radius: 2px;
  background: var(--accent);
  transform-origin: 0 50%;
  animation: tick 6s linear both;
}
@keyframes tick {
  from {
    transform: scaleX(0);
  }
}
@keyframes rays-turn {
  to {
    transform: rotate(1turn);
  }
}
.hold .tick,
.lineup:has(:focus-visible) .tick {
  animation-play-state: paused;
}
.mini span {
  display: block;
  width: 100%;
  height: 100%;
}
.mini img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.strip-move,
.strip-enter-active {
  transition: transform 460ms var(--ease-out), opacity 300ms;
}
.strip-enter-from {
  opacity: 0;
}
/* Gone at once: holding its grid cell would push the strip off line for the length of the slide. */
.strip-leave-active {
  display: none;
}

@container panel (max-width: 820px) {
  .title small,
  .series {
    display: none;
  }
  .pool-stage {
    gap: 12px;
    padding-right: 12px;
  }
  .hand {
    width: calc(var(--card-w) * 1.22);
  }
  .s1 { transform: translateX(7%) rotate(3deg) scale(0.93); }
  .s2 { transform: translateX(12%) rotate(6deg) scale(0.86); }
  .meter { padding: 8px 10px; }
  .total b { font-size: 24px; }
  .tiers { gap: 6px 10px; }
  .skin-tile { width: 112px; }
}
@container panel (max-width: 660px) {
  .pool-stage { flex-direction: column; align-items: center; gap: 18px; padding: 16px; }
  .hand { --hero-h: 214px; --card-w: 150px; }
  .fan { margin-top: 0; }
  .info { width: 100%; }
}
/* Keeps the draw buttons above the fold: the total still sums up what the tier gauges break down. */
@container panel (max-height: 600px) {
  .tiers {
    display: none;
  }
}
</style>
