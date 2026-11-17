<script setup lang="ts">
// The hand of a resonance pool's stage (PoolStage.vue, BannerStage.vue): cards held as a fan in front of slow rays,
// the front one leaning toward the pointer, and under it the lineup that deals the next card on its own. A stage
// can put a featured item at the foot of the fan through the foreground slot.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl } from "../asset";
import { cardFrame } from "../cards";
import { getCard } from "../manifest";
import type { Item } from "../items";
import { reducedMotion } from "../stores/theme";
import { arrowSelect } from "../ui/focus";
import Icon from "../ui/Icon.vue";

/**
 * [hold] stops the rotation's clock, as [busy] and [paused] do. [crest] is the word on the cards' top edge. [bare]
 * leaves the lineup out: the cards still deal on the clock, and a card behind is picked by pressing it.
 */
const props = defineProps<{ items: Item[]; busy: boolean; paused?: boolean; hold?: boolean; crest?: string; bare?: boolean }>();
const emit = defineEmits<{ inspect: [item: Item]; show: [item: Item | undefined] }>();

const LINEUP_SIZE = 7;
const FAN_SIZE = 3;

const selected = ref(props.items[0]?.id ?? "");
const at = computed(() => Math.max(0, props.items.findIndex((i) => i.id === selected.value)));
const active = computed(() => props.items[at.value]);
watch(active, (item) => emit("show", item), { immediate: true });
const neighbour = (step: number) => props.items[(at.value + step + props.items.length) % props.items.length]!;
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
  if (!step || props.busy || props.items.length < 2) return;
  if (reducedMotion.value) {
    window.clearTimeout(stepTimer);
    stepTimer = 0;
    pending = 0;
    stopRush();
    dealing.value = Math.sign(step);
    selected.value = neighbour(step).id;
    return;
  }
  const max = Math.max(1, props.items.length - 1);
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
  if (stepTimer || !pending || props.items.length < 2) return;
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
  Array.from({ length: Math.min(FAN_SIZE, props.items.length) }, (_, step) => {
    const item = neighbour(step);
    const c = cardOf(item);
    return { item, step, card: c, gold: c?.tier === "big", frame: cardFrame(c) };
  }),
);
// The shown card keeps the middle of the strip while the others slide past it. The progress
// bar under it times the rotation, so pausing that animation pauses everything.
const stripSize = computed(() => Math.min(LINEUP_SIZE, props.items.length));
const lineup = computed(() =>
  Array.from({ length: stripSize.value }, (_, i) => {
    const step = i - Math.floor(stripSize.value / 2);
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


const pageActive = usePageActive();
const playing = computed(() => pageActive.value && !reducedMotion.value && !props.busy && !props.paused);
watch(playing, (on) => { if (!on) writeLean(0, 0); });
onBeforeUnmount(() => {
  cancelAnimationFrame(leanFrame);
  window.clearTimeout(stepTimer);
  window.clearTimeout(rushTimer);
});
</script>

<template>
  <div class="hand" :class="{ hold: !pageActive || busy || paused || hold || pointing, calm: reducedMotion }">
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
            <b class="crest">{{ crest ?? "A-SOUL" }}</b>
          </span>
        </button>
      </TransitionGroup>
      <span class="inspect-pill" aria-hidden="true"><Icon name="search" :size="11" />查看</span>
      <template v-if="!bare">
        <Icon name="spark" :size="26" class="twinkle top" />
        <Icon name="spark" :size="14" class="twinkle side" />
      </template>
      <i v-if="bare && !reducedMotion && items.length > 1" :key="active?.id" class="tick clock" aria-hidden="true" @animationend="go(1)"></i>
    </div>
    <slot name="foreground" />
    <div v-if="!bare" class="lineup" @pointerenter="pointing = true" @pointerleave="pointing = false">
      <button v-if="items.length > 1" type="button" class="flip ui-btn ghost" aria-label="上一张" :disabled="busy" @click="go(-1)">
        <Icon name="back" :size="18" />
      </button>
      <TransitionGroup tag="div" name="strip" class="row" :css="!reducedMotion" @keydown="arrowSelect($event, $event.currentTarget as HTMLElement)">
        <button
          v-for="{ item, step } in lineup" :key="item.id" type="button" class="mini" :class="{ on: !step }"
          :disabled="busy" :title="item.name" :aria-pressed="!step" @click="go(step)"
        >
          <span class="ui-frame"><img :src="assetUrl(item.art)" :alt="item.name" draggable="false" /></span>
          <i v-if="!step && !reducedMotion && items.length > 1" class="tick" aria-hidden="true" @animationend="go(1)"></i>
        </button>
      </TransitionGroup>
      <button v-if="items.length > 1" type="button" class="flip next ui-btn ghost" aria-label="下一张" :disabled="busy" @click="go(1)">
        <Icon name="back" :size="18" />
      </button>
    </div>
  </div>
</template>

<style scoped>
/* The hand and, under it, the lineup that deals it. */
.hand {
  position: relative;
  z-index: 1;
  flex: none;
  width: calc(var(--card-w) * 1.3);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
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
  -webkit-mask: radial-gradient(circle, #000 18%, transparent 66%);
  mask: radial-gradient(circle, #000 18%, transparent 66%);
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
.fan:hover .s0.gold:not(:disabled) .face {
  box-shadow: 0 0 0 3px #fff, 0 0 28px 4px rgba(var(--gold-rgb), 0.52), 0 24px 32px -16px rgba(var(--shadow-rgb), 0.6);
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
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.45);
  color: #fff;
  font: 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.18em;
  white-space: nowrap;
}
.gold .crest {
  background: linear-gradient(180deg, var(--c-900), var(--ink));
  box-shadow: 0 0 0 1px var(--gold);
  color: var(--gold-soft);
}
.inspect-pill {
  position: absolute;
  z-index: 4;
  left: calc(var(--card-w) * 0.5);
  /* --pill-bottom: set by a stage that stands something in front of the card's foot. */
  bottom: var(--pill-bottom, 10px);
  translate: -50% 4px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px 3px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 0 0 1.5px var(--c-300), 0 6px 14px -6px rgba(var(--shadow-rgb), 0.35);
  color: var(--ink);
  font: 800 var(--fs-caption)/1.2 var(--font);
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--dur-base), translate var(--dur-base) var(--ease-out);
}
.fan:has(.s0.gold) .inspect-pill {
  box-shadow: 0 0 0 1.5px var(--gold), 0 6px 14px -6px rgba(var(--shadow-rgb), 0.35);
}
.fan:hover .inspect-pill,
.fan:has(.s0:focus-visible) .inspect-pill {
  opacity: 1;
  translate: -50% 0;
}
.twinkle {
  position: absolute;
  z-index: 4;
  color: var(--c-300);
  fill: var(--surface);
  stroke-width: 1.2;
  pointer-events: none;
  transition: color var(--dur-base);
}
.fan:has(.s0.gold) .twinkle {
  color: var(--gold-soft);
}
.twinkle.top {
  top: -14px;
  left: -16px;
}
.twinkle.side {
  top: 12px;
  left: 14px;
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
.lineup .mini {
  position: relative;
  width: 100%;
  max-width: 36px;
  justify-self: center;
  aspect-ratio: 0.76;
  padding: 2px;
  box-sizing: border-box;
  border: 0;
  border-radius: var(--radius-s);
  background: var(--c-100);
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast);
}
.lineup .mini:hover:not(:disabled) {
  transform: translateY(-2px);
}
.lineup .mini.on {
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
/* Without a lineup the clock runs unseen. */
.tick.clock {
  left: 0;
  right: auto;
  bottom: 0;
  width: 8px;
  opacity: 0;
  pointer-events: none;
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
  .hand {
    width: calc(var(--card-w) * 1.22);
  }
  .s1 { transform: translateX(7%) rotate(3deg) scale(0.93); }
  .s2 { transform: translateX(12%) rotate(6deg) scale(0.86); }
  .fan:hover .s1:not(:disabled) { transform: translateX(13%) rotate(6deg) scale(0.93); }
  .fan:hover .s2:not(:disabled) { transform: translateX(23%) rotate(11deg) scale(0.86); }
}
</style>
