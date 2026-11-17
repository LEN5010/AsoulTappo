<script setup lang="ts">
// The stage of a limited pool, laid out as the standing pool's (PoolStage.vue): a hero on the left, the pool's name
// and a sheet of paper on the right. The hero is a pearl card with the featured items piled on it as stickers. A
// featured skin sits at its desk as on the desktop; a two-form skin types for a moment and changes into its second
// form, as it does for the player. The lineup under the card brings the next item to the front on its own.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl } from "../asset";
import { getCharacter, PET_BASE, skinSeries } from "../characters";
import { cardLabel } from "../cards";
import { characterColor, getCard, memberOf } from "../manifest";
import type { Item } from "../items";
import { featuredItems } from "../resonance";
import { collection } from "../stores/player";
import type { Banner } from "../stores/economy";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";
import PetView from "../pet/PetView.vue";
import PetBust from "./PetBust.vue";

const props = defineProps<{ banner: Banner; busy: boolean; paused?: boolean }>();
const emit = defineEmits<{ inspect: [item: Item] }>();

/** A skin types this long in its first form, then shows its second for the rest of its turn. */
const TYPE_MS = 1900;
const KEY_MS = 120;
const PILE = 3;

const items = computed(() => featuredItems(props.banner));
const at = ref(0);
watch(() => props.banner.id, () => (at.value = 0));
const active = computed(() => items.value[at.value % Math.max(1, items.value.length)]);
const owns = (item: Item) => (collection.owned[item.id] ?? 0) > 0;
const got = computed(() => items.value.filter(owns).length);

interface Figure { item: Item; step: number; skin: boolean; twoForm: boolean; art: string }
const figure = (item: Item, step: number): Figure => {
  const skin = item.kind === "character";
  const card = skin ? undefined : getCard(item.ref);
  return { item, step, skin, twoForm: skin && !!getCharacter(item.ref)?.form, art: card ? assetUrl(card.full) : "" };
};
/** The pile: the item on show and the next ones behind it. */
const pile = computed(() => {
  const n = items.value.length;
  return Array.from({ length: Math.min(PILE, n) }, (_, step) => figure(items.value[(at.value + step) % n]!, step));
});
const front = computed(() => pile.value[0]);
/** The two pictures of the skin on show, for its form keys. */
const forms = computed(() => {
  const c = front.value?.twoForm ? getCharacter(front.value.item.ref) : undefined;
  return c?.form ? [c.bgSmall, c.form.bgSmall] : null;
});

const feature = computed(() => {
  const item = active.value;
  if (!item) return null;
  if (item.kind === "character") {
    const member = memberOf(item.ref);
    return { title: item.name, who: member, color: characterColor(member), series: skinSeries(item.ref), kind: "皮肤", owned: owns(item) };
  }
  const card = getCard(item.ref);
  const label = card ? cardLabel(card) : { title: item.name, who: item.characters.join(" ") };
  return { title: label.title, who: label.who, color: characterColor(item.characters[0] ?? ""), series: item.group, kind: "卡牌", owned: owns(item) };
});

const pageActive = usePageActive();
const pointing = ref(false);
const playing = computed(() => pageActive.value && !reducedMotion.value && !props.busy && !props.paused);
const hold = computed(() => !playing.value || pointing.value);

// The front skin's turn: it types in its first form, then changes. A form key pins one of the two while the pointer
// stays on the stage.
const typed = ref(false);
const pinned = ref<boolean | null>(null);
const keyDown = ref(false);
let typeTimer = 0;
let keyTimer = 0;
function stopTurn() {
  window.clearTimeout(typeTimer);
  window.clearInterval(keyTimer);
  typeTimer = keyTimer = 0;
  keyDown.value = false;
}
function startTurn() {
  stopTurn();
  typed.value = false;
  if (!front.value?.twoForm || !playing.value) return;
  keyTimer = window.setInterval(() => (keyDown.value = !keyDown.value), KEY_MS);
  typeTimer = window.setTimeout(() => (typed.value = true), TYPE_MS);
}
watch([() => front.value?.item.id, playing], startTurn, { immediate: true });
const formShown = computed(() => pinned.value ?? typed.value);
function pin(form: boolean) {
  pinned.value = form;
}
function unpoint() {
  pointing.value = false;
  pinned.value = null;
}
function go(step: number) {
  const n = items.value.length;
  if (!step || props.busy || n < 2) return;
  pinned.value = null;
  at.value = (at.value + step + n) % n;
}

// The pet is drawn in pixels of its 240-wide canvas: its scale follows the card's width.
const heroEl = ref<HTMLElement>();
const heroW = ref(0);
const frontScale = computed(() => Math.max(0.6, (heroW.value * 0.98) / PET_BASE.width));
const backScale = computed(() => frontScale.value * 0.6);
let resize: ResizeObserver | undefined;
onMounted(() => {
  resize = new ResizeObserver(() => (heroW.value = heroEl.value?.clientWidth ?? 0));
  if (heroEl.value) resize.observe(heroEl.value);
});
onBeforeUnmount(() => {
  resize?.disconnect();
  stopTurn();
});
</script>

<template>
  <section class="banner-stage" :class="{ hold, calm: reducedMotion }" @pointerleave="unpoint">
    <div class="hand">
      <div ref="heroEl" class="hero" @pointerenter="pointing = true">
        <span class="plate" aria-hidden="true">
          <i class="rays"><i></i></i>
          <b class="crest">LIMITED</b>
        </span>
        <TransitionGroup name="pile" :css="!reducedMotion">
          <button
            v-for="f in pile" :key="f.item.id" type="button" class="figure" :class="[`s${f.step}`, { card: !f.skin, lacking: !owns(f.item) }]"
            :disabled="busy" :title="f.item.name" :tabindex="f.step ? -1 : undefined"
            :aria-label="f.step ? `换到${f.item.name}` : `查看${f.item.name}`"
            @click="f.step ? go(f.step) : emit('inspect', f.item)"
          >
            <PetView
              v-if="f.skin" class="pet-sticker" :character="f.item.ref" :scale="f.step ? backScale : frontScale"
              :key-down="!f.step && keyDown" :form="f.step ? false : formShown"
            />
            <span v-else class="card-face frame-pearl"><img :src="f.art" alt="" draggable="false" /></span>
          </button>
        </TransitionGroup>
        <Icon name="spark" :size="24" class="twinkle top" />
        <Icon name="spark" :size="13" class="twinkle side" />
      </div>
      <div v-if="items.length > 1" class="lineup" @pointerenter="pointing = true">
        <button type="button" class="flip ui-btn ghost" aria-label="上一个" :disabled="busy" @click="go(-1)"><Icon name="back" :size="18" /></button>
        <div class="row">
          <button
            v-for="(item, i) in items" :key="item.id" type="button" class="mini" :class="{ on: i === at, got: owns(item) }"
            :disabled="busy" :title="item.name" :aria-pressed="i === at" @click="go(i - at)"
          >
            <span class="mini-art">
              <PetBust v-if="item.kind === 'character'" :src="getCharacter(item.ref)!.bg" />
              <img v-else :src="assetUrl(item.art)" :alt="item.name" draggable="false" />
            </span>
            <i v-if="i === at && !reducedMotion" class="tick" aria-hidden="true" @animationend="go(1)"></i>
          </button>
        </div>
        <button type="button" class="flip next ui-btn ghost" aria-label="下一个" :disabled="busy" @click="go(1)"><Icon name="back" :size="18" /></button>
      </div>
    </div>

    <div class="info">
      <header class="title">
        <slot name="switch"></slot>
        <h3>{{ banner.name }}</h3>
      </header>

      <div class="sheet">
        <div class="feature-slot">
          <Transition name="feature" mode="out-in" :css="!reducedMotion">
            <div v-if="feature" :key="active?.id" class="feature">
              <p class="tags">
                <span class="ui-tag up"><em>UP</em>限定{{ feature.kind }}</span>
                <span class="who"><i :style="{ background: feature.color }"></i>{{ feature.who }}</span>
                <span class="series">{{ feature.series }}</span>
              </p>
              <h4>{{ feature.title }}</h4>
              <p class="owned" :class="{ yes: feature.owned }">
                <template v-if="feature.owned"><Icon name="check" :size="14" />已拥有</template>
                <template v-else><Icon name="lock" :size="13" />未获得</template>
              </p>
            </div>
          </Transition>
        </div>

        <div v-if="forms" class="forms" role="group" aria-label="形态">
          <template v-for="(f, i) in forms" :key="i">
            <Icon v-if="i" name="forward" :size="14" class="form-arrow" />
            <button type="button" class="form-key" :class="{ on: formShown === !!i }" :aria-pressed="formShown === !!i" :disabled="busy" @click="pin(!!i)">
              <span class="form-art"><img :src="f" alt="" draggable="false" /></span>
              <b>{{ i ? '二形态' : '一形态' }}</b>
            </button>
          </template>
        </div>

        <div class="meter">
          <p class="total"><b>{{ got }}</b><i>/ {{ items.length }}</i></p>
          <ul class="featured">
            <li v-for="(item, i) in items" :key="item.id">
              <button type="button" class="seg" :class="{ on: i === at, done: owns(item) }" :disabled="busy" :aria-label="item.name" @click="go(i - at)">
                <span class="seg-bar"><i></i></span>
                <span class="seg-who">
                  <i :style="{ background: characterColor(item.characters[0] ?? '') }"></i><span>{{ item.name }}</span>
                  <Icon :name="owns(item) ? 'check' : 'lock'" :size="10" />
                </span>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.banner-stage {
  /* The same hero as the standing pool's, so switching pools moves nothing but the content. */
  --hero-h: max(200px, min(0.7 * (100cqh - 46px), 100cqh - 262px, 44cqw));
  --card-w: calc(var(--hero-h) * 0.7);
  --stage-gap: 28px;
  position: relative;
  isolation: isolate;
  flex: 1 0 auto;
  display: flex;
  align-items: stretch;
  gap: var(--stage-gap);
  padding: 26px 26px 12px 34px;
  box-sizing: border-box;
}
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
.hero {
  position: relative;
  flex: none;
  height: var(--hero-h);
}
/* The pearl card the stickers are piled on: the size and lean of the standing pool's front card. */
.plate {
  position: absolute;
  left: 0;
  bottom: 0;
  width: var(--card-w);
  height: var(--hero-h);
  box-sizing: border-box;
  border-radius: var(--radius-m);
  border: calc(var(--card-w) * 0.015) solid transparent;
  background:
    linear-gradient(160deg, #fff, color-mix(in srgb, var(--holo-lilac) 26%, #fff) 55%, color-mix(in srgb, var(--holo-pink) 30%, #fff)) padding-box,
    linear-gradient(125deg, var(--pearl), var(--holo-pink) 20%, #fff 30%, var(--holo-lilac) 45%, var(--pearl-deep) 62%, var(--holo-mint) 80%, var(--holo-cream)) border-box;
  box-shadow: 0 0 0 3px #fff, 0 16px 28px -16px rgba(var(--shadow-rgb), 0.6);
  transform: rotate(-3deg);
  transform-origin: 50% 100%;
  overflow: hidden;
}
.rays {
  position: absolute;
  left: 50%;
  top: 58%;
  width: 190%;
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  overflow: hidden;
  mask: radial-gradient(circle, #000 12%, transparent 62%);
  -webkit-mask: radial-gradient(circle, #000 12%, transparent 62%);
  opacity: 0.8;
}
.rays i {
  position: absolute;
  inset: -20%;
  background: repeating-conic-gradient(#fff 0 5deg, transparent 5deg 20deg);
  animation: rays-turn 96s linear infinite;
}
.hold .rays i,
.calm .rays i {
  animation-play-state: paused;
}
@keyframes rays-turn {
  to { rotate: 360deg; }
}
.crest {
  position: absolute;
  top: 0;
  left: 50%;
  translate: -50% 0;
  padding: 3px 18px 4px;
  border-radius: 0 0 var(--radius-l) var(--radius-l);
  background: var(--night);
  color: var(--holo-cream);
  font: 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.18em;
  white-space: nowrap;
}

/* A sticker of the pile. The one on show sits low and large; the next ones lean out behind it, at the top. */
.figure {
  position: absolute;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  transform-origin: 50% 100%;
  transition: left var(--dur-stage) var(--ease-out), top var(--dur-stage) var(--ease-out), rotate var(--dur-stage) var(--ease-out),
    translate var(--dur-base) var(--ease-out), opacity var(--dur-base);
}
.figure :deep(.bg) {
  filter: var(--sticker-lg);
}
.figure:not(.s0) :deep(.bg) {
  filter: var(--sticker);
}
.pet-sticker {
  display: block;
  pointer-events: none;
}
.s0 {
  z-index: 3;
  left: 1%;
  top: 44%;
}
.s1 {
  z-index: 2;
  left: -4%;
  top: 7%;
  rotate: -7deg;
}
.s2 {
  z-index: 1;
  left: 39%;
  top: 17%;
  rotate: 6deg;
}
.figure:not(.s0):hover:not(:disabled) {
  rotate: 0deg;
  translate: 0 -4px;
}
.s0:hover:not(:disabled) {
  translate: 0 -3px;
}
/* A card among the featured items stands in the pile as a small framed card. */
.figure.card.s0 { left: 14%; top: 22%; width: 62%; }
.figure.card:not(.s0) { width: 34%; }
.card-face {
  display: block;
  aspect-ratio: 2 / 3;
  padding: 3%;
  border-radius: var(--radius-m);
  box-shadow: 0 0 0 3px #fff, 0 12px 20px -14px rgba(var(--shadow-rgb), 0.6);
}
.card-face img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: calc(var(--radius-m) - 3px);
}
.pile-enter-active,
.pile-leave-active {
  transition: opacity 320ms, translate 420ms var(--ease-out);
}
.pile-leave-active {
  z-index: 4;
}
.pile-enter-from {
  opacity: 0;
  translate: 12% -6%;
}
.pile-leave-to {
  opacity: 0;
  translate: -30% 6%;
}
.twinkle {
  position: absolute;
  z-index: 4;
  color: var(--pearl-deep);
  fill: var(--surface);
  stroke-width: 1.2;
  pointer-events: none;
}
.twinkle.top { top: -14px; left: -16px; }
.twinkle.side { top: 12px; left: 14px; }

/* As wide as the card: the sheet lies over the rest of the hand. */
.lineup {
  width: var(--card-w);
  display: flex;
  align-items: center;
  gap: 2px;
  padding-bottom: 8px;
}
.flip {
  flex: none;
  width: 28px;
  height: 28px;
  padding: 0;
}
.flip.next svg {
  rotate: 180deg;
}
.row {
  flex: 1;
  display: flex;
  justify-content: center;
  gap: 10px;
}
.mini {
  position: relative;
  flex: none;
  width: 46px;
  height: 46px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-s);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base);
}
.mini-art {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  overflow: hidden;
}
.mini-art > * {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.mini:not(.got) .mini-art {
  filter: var(--dim);
}
.mini.on {
  transform: translateY(-3px);
  box-shadow: 0 0 0 2px var(--pearl-deep), 0 6px 12px -6px rgba(var(--shadow-rgb), 0.5);
}
.mini.on .mini-art {
  filter: none;
}
/* The turn of the item on show: when the bar is full the next one comes forward. */
.tick {
  position: absolute;
  left: 4px;
  right: 4px;
  bottom: -7px;
  height: 3px;
  border-radius: 2px;
  background: var(--pearl-deep);
  transform-origin: 0 50%;
  animation: tick 7s linear both;
}
.hold .tick {
  animation-play-state: paused;
}
@keyframes tick {
  from { transform: scaleX(0); }
}

.info {
  position: relative;
  z-index: 2;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 4px;
}
h3 {
  margin: 0;
  font: 800 clamp(42px, 6cqw, 58px)/1.05 var(--font);
  letter-spacing: 0.03em;
}
.sheet {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-left: calc(var(--stage-gap) * -1 - 18px);
  padding: 16px 18px 14px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.feature-slot {
  min-height: 96px;
}
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
.up {
  --tag-bg: var(--grad-pearl);
  --tag-fg: var(--night);
  padding: 0 8px 0 6px;
  line-height: 19px;
  font-size: var(--fs-label);
}
.up em {
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
  font: 800 clamp(22px, 3.1cqw, 30px)/1.25 var(--font);
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

/* The two forms of the skin on show, as two small pictures: the lit one is what it wears now, a press holds the other. */
.forms {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
}
.form-key {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 6px 5px;
  border: 0;
  border-bottom: 3px solid var(--c-200);
  border-radius: var(--radius-key);
  background: linear-gradient(180deg, #fff, var(--key-white-shade));
  box-shadow: 0 3px 6px -3px rgba(var(--shadow-rgb), 0.28);
  color: var(--ink-2);
  font: 800 var(--fs-label)/1 var(--font);
  cursor: pointer;
  transition: border-color var(--dur-base), color var(--dur-base), transform var(--dur-press) ease-out;
}
.form-key:active:not(:disabled) {
  transform: translateY(1px);
}
.form-art {
  display: block;
  aspect-ratio: 16 / 9;
  border-radius: var(--radius-s);
  background: var(--c-50);
  overflow: hidden;
  transition: background var(--dur-base);
}
.form-art img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 100%;
}
.form-key.on {
  border-bottom-color: var(--pearl-deep);
  color: var(--night);
}
.form-key.on .form-art {
  background: linear-gradient(115deg, color-mix(in srgb, var(--holo-pink) 55%, #fff), color-mix(in srgb, var(--holo-lilac) 60%, #fff) 45%,
    color-mix(in srgb, var(--holo-mint) 55%, #fff) 80%, color-mix(in srgb, var(--holo-cream) 60%, #fff));
}
.form-arrow {
  flex: none;
  color: var(--ink-3);
}

.meter {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 14px;
}
.total {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin: 0;
  white-space: nowrap;
}
.total > b {
  font: 800 44px/0.9 var(--font-latin);
  color: var(--ink);
}
.total > i {
  font: 800 22px/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.featured {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(0, 1fr));
  grid-auto-flow: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.featured li {
  min-width: 0;
}
.seg {
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--ink-2);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.seg-bar {
  display: block;
  height: 8px;
  border-radius: 2px;
  background: var(--c-100);
  overflow: hidden;
}
.seg-bar i {
  display: block;
  width: 0;
  height: 100%;
  background: var(--grad-pearl);
  transition: width var(--dur-stage) var(--ease-out);
}
.seg.done .seg-bar i {
  width: 100%;
}
.seg-who {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  white-space: nowrap;
}
.seg-who > i {
  flex: none;
  width: 4px;
  height: 11px;
}
.seg-who > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.seg-who svg {
  flex: none;
  color: var(--ink-3);
}
.seg.done .seg-who svg {
  color: var(--c-700);
}
.seg.on .seg-who,
.seg:hover:not(:disabled) .seg-who {
  color: var(--ink);
}
@container panel (max-width: 820px) {
  .featured { gap: 6px; }
}
</style>
