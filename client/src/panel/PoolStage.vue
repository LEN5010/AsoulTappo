<script setup lang="ts">
// Resonance stage: the page itself. The dynamic cards are held as a fanned hand in front of slow rays
// and a soft wash of the front card's colours; the front card leans toward the pointer. Beside it the
// page names the card and sums up the collection and its skins. The lineup deals the next card on its own.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl } from "../asset";
import { cardFrame, cardLabel, poolName, TIER_LABEL } from "../cards";
import { characters, getCharacter } from "../characters";
import { getCard, characterColor, manifest, type ManifestCard, type Rarity } from "../manifest";
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
  { rarity: "uncommon", label: "罕见", icon: "layers" },
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
/** Steps still to play, one card at a time. A jump of several is the same deal, played faster. */
let pending = 0;
let stepTimer = 0;
let rushTimer = 0;
const STEP_GAP = 260;
const RUSH_GAP = 180;
/** Matches --deal on .fan.rush, so the fast timing stays until the last card has landed. */
const RUSH_MS = 360;
const rush = ref(false);
function stopRush() {
  window.clearTimeout(rushTimer);
  rushTimer = 0;
  rush.value = false;
}
function go(step: number) {
  if (!step || props.busy) return;
  if (reducedMotion.value) {
    window.clearTimeout(stepTimer);
    stepTimer = 0;
    pending = 0;
    stopRush();
    dealing.value = Math.sign(step);
    selected.value = neighbour(step).id;
    return;
  }
  const max = Math.max(1, previews.length - 1);
  pending = Math.max(-max, Math.min(max, step));
  if (Math.abs(step) > 1) {
    window.clearTimeout(rushTimer);
    rushTimer = 0;
    rush.value = true;
  } else if (!stepTimer) {
    stopRush();
  }
  runStep();
}
function runStep() {
  if (stepTimer || !pending) return;
  const dir = Math.sign(pending);
  pending -= dir;
  dealing.value = dir;
  selected.value = neighbour(dir).id;
  if (!pending) {
    if (rush.value) rushTimer = window.setTimeout(stopRush, RUSH_MS);
    return;
  }
  stepTimer = window.setTimeout(() => {
    stepTimer = 0;
    runStep();
  }, rush.value ? RUSH_GAP : STEP_GAP);
}

/** The hand: the card on show and the next ones peeking out behind it. */
const fan = computed(() =>
  Array.from({ length: Math.min(FAN_SIZE, previews.length) }, (_, step) => {
    const item = neighbour(step);
    const c = cardOf(item);
    return { item, step, card: c, gold: c?.tier === "big", frame: cardFrame(c) };
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
  const glyphs = document.createRange();
  glyphs.selectNodeContents(titleEl.value);
  peekRoom.value = sheetEl.value.getBoundingClientRect().right - glyphs.getBoundingClientRect().right;
}
const peekSize = computed(() => {
  // A pair reaches past the box on the left (.pair in the styles).
  const span = (peek.value?.busts.length ?? 1) > 1 ? 1.32 : 1;
  const size = Math.min(PEEK_MAX, (peekRoom.value - PEEK_MARGIN) / span);
  return size >= PEEK_MIN ? Math.round(size) : 0;
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

// The front card leans toward the pointer, up to LEAN_DEG, and the light on its frame and face
// follows. The pointer is read once per frame and written as custom properties on the hand.
const LEAN_DEG = 8;
const fanEl = ref<HTMLElement>();
let leanBox: DOMRect | null = null;
let leanFrame = 0;
let leanAt = { x: 0, y: 0 };
function writeLean(x: number, y: number) {
  const front = fanEl.value?.querySelector(".s0");
  if (!(front instanceof HTMLElement)) return;
  front.style.setProperty("--lx", x.toFixed(3));
  front.style.setProperty("--ly", y.toFixed(3));
  front.style.setProperty("--frame-x", (0.3 + x * 0.25).toFixed(3));
  front.style.setProperty("--frame-y", (0.2 + y * 0.25).toFixed(3));
}
function leanStart(e: PointerEvent) {
  pointing.value = true;
  leanBox = (e.currentTarget as HTMLElement).getBoundingClientRect();
}
function leanMove(e: PointerEvent) {
  if (!leanBox || !playing.value) return;
  const clampUnit = (v: number) => Math.max(-1, Math.min(1, v));
  leanAt = {
    x: clampUnit(((e.clientX - leanBox.left) / leanBox.width) * 2 - 1),
    y: clampUnit(((e.clientY - leanBox.top) / leanBox.height) * 2 - 1),
  };
  if (!leanFrame) leanFrame = requestAnimationFrame(() => {
    leanFrame = 0;
    writeLean(leanAt.x, leanAt.y);
  });
}
function leanEnd() {
  pointing.value = false;
  leanBox = null;
  cancelAnimationFrame(leanFrame);
  leanFrame = 0;
  writeLean(0, 0);
}

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
const playing = computed(() => pageActive.value && !reducedMotion.value && !props.busy && !props.paused);
watch(playing, (on) => { if (!on) writeLean(0, 0); });
let resize: ResizeObserver | undefined;
onMounted(() => {
  resize = new ResizeObserver(() => {
    skinWidth.value = skinGroup.value?.[0]?.offsetWidth ?? 0;
    viewportWidth.value = skinViewport.value?.clientWidth ?? 0;
    measurePeek();
  });
  if (skinViewport.value) resize.observe(skinViewport.value);
  if (skinGroup.value?.[0]) resize.observe(skinGroup.value[0]);
  if (sheetEl.value) resize.observe(sheetEl.value);
  // The title's width changes once the bundled font replaces the fallback.
  void document.fonts.ready.then(measurePeek);
});
onBeforeUnmount(() => {
  resize?.disconnect();
  cancelAnimationFrame(leanFrame);
  window.clearTimeout(stepTimer);
  window.clearTimeout(rushTimer);
});
</script>

<template>
  <section
    class="pool-stage"
    :class="{ hold: !pageActive || busy || paused || pointing || skinFocused, calm: reducedMotion, marquee: canMarquee, run: scrolling }"
    :style="{ '--marquee': marqueeDuration }"
  >
    <div class="wash" aria-hidden="true">
      <Transition name="wash" :css="!reducedMotion">
        <span v-if="card" :key="card.id" class="wash-blob">
          <img :src="assetUrl(card.thumb)" alt="" draggable="false" />
        </span>
      </Transition>
    </div>

    <div class="hand">
      <div ref="fanEl" class="fan" :class="{ rush }" :style="{ '--lean': `${LEAN_DEG}deg` }" @pointerenter="leanStart" @pointermove="leanMove" @pointerleave="leanEnd">
        <i class="rays" aria-hidden="true"><i></i></i>
        <TransitionGroup :name="dealing > 0 ? 'fan-fwd' : 'fan-back'" :css="!reducedMotion">
          <button
            v-for="f in fan" :key="f.item.id" type="button"
            class="fan-card" :class="[`s${f.step}`, f.frame, { gold: f.gold }]"
            :disabled="busy" :title="f.item.name" :tabindex="f.step ? -1 : undefined"
            :aria-label="f.step ? `换到${f.item.name}` : `查看${f.item.name}`"
            @click="f.step ? go(f.step) : emit('inspect', f.item)"
          >
            <span class="face">
              <span class="art ui-frame">
                <video
                  v-if="!f.step && f.card?.video && playing" :key="f.card.id"
                  :src="assetUrl(f.card.video)" :poster="assetUrl(f.card.thumb)" autoplay loop muted playsinline
                ></video>
                <img
                  v-else-if="f.card" :src="assetUrl(f.step || f.card.video ? f.card.thumb : f.card.full)" alt=""
                  :style="{ backgroundImage: `url(${assetUrl(f.card.thumb)})` }" draggable="false"
                />
                <i v-if="!f.step" class="glare" aria-hidden="true"></i>
              </span>
              <b class="crest">A-SOUL</b>
            </span>
          </button>
        </TransitionGroup>
        <Icon name="spark" :size="26" class="twinkle top" />
        <Icon name="spark" :size="14" class="twinkle side" />
      </div>
      <div class="lineup" @pointerenter="pointing = true" @pointerleave="pointing = false">
        <button v-if="previews.length > 1" type="button" class="flip ui-btn ghost" aria-label="上一张" :disabled="busy" @click="go(-1)">
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
        <button v-if="previews.length > 1" type="button" class="flip next ui-btn ghost" aria-label="下一张" :disabled="busy" @click="go(1)">
          <Icon name="back" :size="18" />
        </button>
      </div>
    </div>

    <div class="info">
      <header class="title">
        <span class="ui-eyebrow">RESONANCE</span>
        <h3 ref="titleEl">此间共鸣</h3>
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
        <p class="total"><b>{{ collected }}</b><i>/ {{ all.length }}</i></p>
        <ul class="tiers">
          <li v-for="t in meter" :key="t.rarity" :class="t.rarity" :title="`${t.label} ${t.got}/${t.total}`">
            <span class="t-head"><Icon :name="t.icon" :size="12" /><b>{{ t.got }}</b><i>/{{ t.total }}</i></span>
            <span class="t-bar" role="img" :aria-label="`${t.label} ${t.got}/${t.total}`"><i :style="{ width: t.fill }"></i></span>
          </li>
        </ul>
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
  /* About seven tenths of the page, short of what the lineup and the action bar need, and of the width the text needs. */
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
  mask: radial-gradient(closest-side, #000 25%, transparent 100%);
  -webkit-mask: radial-gradient(closest-side, #000 25%, transparent 100%);
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
  --lx: 0;
  --ly: 0;
  position: relative;
  flex: none;
  height: var(--hero-h);
}
.rays {
  position: absolute;
  left: calc(var(--card-w) * 0.5 - var(--hero-h) * 0.75);
  top: calc(var(--hero-h) * -0.25);
  width: calc(var(--hero-h) * 1.5);
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 50%;
  mask: radial-gradient(circle, #000 18%, transparent 66%);
  -webkit-mask: radial-gradient(circle, #000 18%, transparent 66%);
  opacity: 0.45;
  pointer-events: none;
}
.rays i {
  position: absolute;
  inset: -20%;
  background: repeating-conic-gradient(rgba(255, 255, 255, 0.85) 0 4deg, transparent 4deg 20deg);
  animation: rays-turn 96s linear infinite;
}
.hold .rays i,
.calm .rays i {
  animation-play-state: paused;
}
.fan-card {
  position: absolute;
  left: 0;
  bottom: 0;
  width: var(--card-w);
  height: var(--hero-h);
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  transform-origin: 50% 100%;
  transition: transform var(--deal, 520ms) var(--ease-out), opacity 320ms;
}
/* A jump of several cards plays each deal faster. One card at a time stays on the defaults. */
.fan.rush {
  --deal: 360ms;
  --deal-fade: 280ms;
}
/* The card itself: a metal frame (the same share of the width as the reveal's framed cards) around the art. */
.face {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  padding: calc(var(--card-w) * 0.015);
  box-sizing: border-box;
  border-radius: var(--radius-m);
  background: var(--frame-fill, var(--surface)) var(--frame-at, 0 0) / var(--frame-size, auto);
  box-shadow: 0 0 0 3px #fff, 0 16px 28px -16px rgba(var(--shadow-rgb), 0.6);
  transform: perspective(900px) rotateX(0deg) rotateY(0deg);
  transition: transform 160ms var(--ease-out), box-shadow var(--dur-base);
}
.s0 {
  z-index: 3;
  transform: translateY(0) rotate(-3deg);
}
.s0 .face {
  transform: perspective(900px) rotateX(calc(var(--ly) * -1 * var(--lean))) rotateY(calc(var(--lx) * var(--lean)));
}
.s1 {
  z-index: 2;
  transform: translateX(9%) rotate(4deg) scale(0.93);
}
.s2 {
  z-index: 1;
  transform: translateX(16%) rotate(8deg) scale(0.86);
}
/* Under the pointer the front card stands up straight and the ones behind spread out. */
.fan:hover .s0:not(:disabled) {
  transform: translateY(-6px) rotate(0deg);
}
.fan:hover .s0:not(:disabled) .face {
  box-shadow: 0 0 0 3px #fff, 0 0 26px 4px rgba(var(--c-500-rgb), 0.45), 0 24px 32px -16px rgba(var(--shadow-rgb), 0.6);
}
.fan:hover .s1:not(:disabled) {
  transform: translateX(17%) rotate(8deg) scale(0.93);
}
.fan:hover .s2:not(:disabled) {
  transform: translateX(31%) rotate(15deg) scale(0.86);
}
/* The ones behind sit in its shade until the pointer picks one out. */
.fan-card:not(.s0) .face::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: rgba(var(--c-900-rgb), 0.22);
  transition: opacity var(--dur-base);
}
.fan-card:not(.s0):hover .face::after {
  opacity: 0.4;
}
/* A soft glare on the face, sliding opposite the lean. */
.glare {
  position: absolute;
  left: -50%;
  top: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.42), transparent 34%);
  opacity: 0;
  pointer-events: none;
  transform: translate(calc(var(--lx) * 22%), calc(var(--ly) * 22%));
  transition: opacity var(--dur-base), transform 160ms var(--ease-out);
}
.fan:hover .glare {
  opacity: 1;
}
.calm .s0 .face {
  --lean: 0deg;
}
.calm .glare {
  display: none;
}
/* Forward: the front card is thrown off to the left, a new one slips in at the back. */
.fan-fwd-leave-active,
.fan-back-leave-active {
  z-index: 4;
  transition: transform var(--deal, 520ms) var(--ease-in-out), opacity var(--deal-fade, 420ms) var(--ease-in);
}
.fan-fwd-leave-to,
.fan:hover .s0.fan-fwd-leave-to {
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
  background: var(--c-900);
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
  background: var(--c-800);
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
  z-index: 2;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 4px;
}
/* One paper sheet, above the fanned cards. It overlaps the hand's right edge so the back cards slide under it. */
.sheet {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-left: calc(var(--stage-gap) * -1 - 18px);
  padding: 16px 18px 14px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.feature-slot {
  min-height: 108px;
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
  font: 800 clamp(42px, 6cqw, 58px)/1.05 var(--font);
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
  margin: 8px 0 6px;
  overflow: hidden;
  text-wrap: balance;
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
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.total {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin: 0;
}
.total b {
  font: 800 44px/0.9 var(--font-latin);
  color: var(--ink);
}
.total i {
  font: 800 22px/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.tiers {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  align-items: center;
  gap: 8px 22px;
  margin: 0;
  padding: 0;
  list-style: none;
}
/* Fills climb the rarity ladder, a step deeper wherever the ladder colour is too pale to read as a fill. */
.tiers li {
  --fill: var(--c-500);
  min-width: 0;
}
.tiers .legendary { --fill: var(--grad-gold); --mark: var(--gold); }
.tiers .skin { --fill: var(--c-500); }
.tiers .epic { --fill: var(--c-800); }
.tiers .rare { --fill: var(--c-500); }
.tiers .uncommon { --fill: var(--c-400); }
.tiers .common { --fill: var(--c-300); }
.t-head {
  display: flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}
.t-head svg {
  flex: none;
  margin-right: 1px;
  color: var(--mark, var(--c-700));
}
.t-head b {
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
  height: 8px;
  margin-top: 6px;
  border-radius: 2px;
  background: var(--c-100);
  overflow: hidden;
}
.t-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--fill);
  transition: width var(--dur-stage) var(--ease-out);
}

/* Skins as acrylic standees: the bust in a wide clear outline, on an oval base, its name underneath. */
.skins {
  min-width: 0;
  overflow-x: auto;
  padding: 10px 0 2px;
  scrollbar-width: none;
}
.marquee .skins {
  overflow: hidden;
  /* The row dissolves at the two ends it scrolls off, not along each bust. */
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
  width: 84px;
  padding: 0;
  border: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  background: none;
  color: var(--ink);
  cursor: pointer;
}
.stand {
  position: relative;
  display: block;
  width: 64px;
  height: 66px;
  transition: transform var(--dur-base) var(--ease-out);
}
.skin-bust {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  filter: var(--contour);
}
.skin-stand:hover:not(:disabled) .stand {
  transform: translateY(-3px);
}
.skin-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 700 var(--fs-caption)/1.3 var(--font);
}

.lineup {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-bottom: 8px;
}
.flip {
  flex: none;
  width: 22px;
  height: 40px;
  padding: 0;
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
  background: var(--c-100);
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast);
}
.mini:hover:not(:disabled) {
  transform: translateY(-2px);
}
.mini.on {
  box-shadow: 0 0 0 2px var(--c-500);
}
/* The rotation's clock: reaching the end deals the next card. */
.tick {
  position: absolute;
  left: 1px;
  right: 1px;
  bottom: -8px;
  height: 3px;
  border-radius: 2px;
  background: var(--c-500);
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
@keyframes skin-marquee {
  to {
    transform: translateX(-50%);
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
  .series {
    display: none;
  }
  .pool-stage {
    --stage-gap: 18px;
    padding-right: 18px;
  }
  .hand {
    width: calc(var(--card-w) * 1.22);
  }
  .s1 { transform: translateX(7%) rotate(3deg) scale(0.93); }
  .s2 { transform: translateX(12%) rotate(6deg) scale(0.86); }
  .fan:hover .s1:not(:disabled) { transform: translateX(13%) rotate(6deg) scale(0.93); }
  .fan:hover .s2:not(:disabled) { transform: translateX(23%) rotate(11deg) scale(0.86); }
  .total b { font-size: 36px; }
  .tiers { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px 12px; }
}
@container panel (max-width: 660px) {
  .pool-stage { flex-direction: column; align-items: center; gap: 18px; padding: 18px 16px 12px; }
  .hand { --hero-h: 214px; --card-w: 150px; }
  .wash { left: 50%; transform: translateX(-50%); height: 300px; bottom: auto; }
  .info { width: 100%; }
  .sheet { margin-left: 0; }
}
/* Keeps the action bar above the fold: the total still sums up what the tier gauges break down. */
@container panel (max-height: 600px) {
  .tiers {
    display: none;
  }
}
</style>
