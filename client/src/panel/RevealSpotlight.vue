<script setup lang="ts">
// A hidden card, a skin or a first animated card, lifted off its tile onto a band of its tone.
// The art flies between the tile and the stage, so the board below never loses its place. Once it
// lands it follows the pointer in 3D, with glare, and a holo sheen on hidden cards. Glare and holo
// are oversized layers that only move, with no blend modes, so a playing video stays smooth under them.
import { computed, onMounted, ref } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl } from "../asset";
import { characterColor } from "../manifest";
import { EASE_IN_OUT, EASE_OUT } from "../ui/motion";
import Icon from "../ui/Icon.vue";
import type { BoardEntry } from "./reveal-board";

const props = defineProps<{ entry: BoardEntry; from: DOMRect | null; calm: boolean }>();
const emit = defineEmits<{ done: [] }>();

const LEFT = "translateX(-104%)";
const RIGHT = "translateX(104%)";
const IN_MS = 560;
const OUT_MS = 340;
const TILT_DEG = 14;

const pageActive = usePageActive();
const landed = ref(props.calm);
const leaving = ref(false);
const fullReady = ref(false);
const card = computed(() => props.entry.card);
const skin = computed(() => props.entry.item.kind === "character");
const hidden = computed(() => card.value?.tier === "big" || card.value?.tier === "small");
const big = computed(() => props.entry.drop.rarity === "legendary");
const word = computed(() => {
  if (skin.value) return "SKIN";
  if (card.value?.tier === "big") return "SECRET";
  if (card.value?.tier === "small") return "HIDDEN";
  return card.value?.video ? "DANCE" : "NEW";
});
const playing = computed(() => !!card.value?.video && landed.value && !leaving.value && pageActive.value);
const memberColor = computed(() => characterColor(props.entry.item.characters[0] ?? ""));
const BURST = Array.from({ length: 12 }, (_, n) => ({
  angle: `${n * 30 + (n % 2) * 11}deg`,
  reach: `${170 + (n % 4) * 40}px`,
  size: n % 3 === 0 ? 26 : n % 3 === 1 ? 14 : 20,
}));

const veil = ref<HTMLElement>();
const band = ref<HTMLElement>();
const hero = ref<HTMLElement>();
const tilt = ref<HTMLElement>();

/** Where the hero would sit to cover its tile, from its resting box. */
function onTile(): string | null {
  const from = props.from;
  const to = hero.value?.getBoundingClientRect();
  if (!from || !to?.width) return null;
  const scale = from.width / to.width;
  return `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${scale}) rotate(${props.entry.tilt}deg)`;
}

/** Pointer over the art: lean toward it and move the glare there. */
function lean(e: PointerEvent) {
  const el = tilt.value;
  if (!el || !landed.value || leaving.value || props.calm) return;
  const box = el.getBoundingClientRect();
  const x = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width));
  const y = Math.min(1, Math.max(0, (e.clientY - box.top) / box.height));
  el.style.setProperty("--rx", `${(0.5 - y) * TILT_DEG}deg`);
  el.style.setProperty("--ry", `${(x - 0.5) * TILT_DEG}deg`);
  el.style.setProperty("--px", `${x}`);
  el.style.setProperty("--py", `${y}`);
  el.classList.add("leaning");
}
function rest() {
  const el = tilt.value;
  if (!el) return;
  for (const name of ["--rx", "--ry", "--px", "--py"]) el.style.removeProperty(name);
  el.classList.remove("leaning");
}

const go = ref<HTMLButtonElement>();
onMounted(() => {
  go.value?.focus({ preventScroll: true });
  if (props.calm) return;
  band.value?.animate([{ transform: LEFT }, { transform: "none" }], { duration: 300, easing: EASE_IN_OUT, fill: "both" });
  const start = onTile();
  const flight = hero.value?.animate(
    start
      ? [{ transform: start }, { transform: "translateY(-14px) scale(1.04)", offset: 0.7 }, { transform: "none" }]
      : [{ transform: "scale(.6)", opacity: 0 }, { transform: "none", opacity: 1 }],
    { duration: IN_MS, easing: EASE_OUT, fill: "both" },
  );
  void flight?.finished.then(() => (landed.value = true), () => {});
});

async function close() {
  if (leaving.value) return;
  leaving.value = true;
  rest();
  if (props.calm) {
    emit("done");
    return;
  }
  const back = onTile();
  const moves = [
    band.value?.animate([{ transform: "none" }, { transform: RIGHT }], { duration: OUT_MS, easing: EASE_IN_OUT, fill: "both" }),
    hero.value?.animate([{ transform: "none" }, back ? { transform: back } : { transform: "scale(.6)", opacity: 0 }], { duration: OUT_MS, easing: EASE_IN_OUT, fill: "both" }),
    veil.value?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: OUT_MS, easing: EASE_IN_OUT, fill: "both" }),
  ];
  await Promise.allSettled(moves.map((m) => m?.finished));
  emit("done");
}

defineExpose({ close });
</script>

<template>
  <div
    class="spot" :class="[entry.tone, { skin, hidden, big, landed, leaving, calm }]" :style="entry.toneStyle"
    role="group" :aria-label="`${entry.kind}：${entry.title}`" @click="close"
  >
    <i ref="veil" class="veil" aria-hidden="true"></i>
    <div ref="band" class="band" aria-hidden="true">
      <i v-if="landed && !calm" class="flash"></i>
    </div>
    <div class="stage">
      <div class="hero-cell" @pointermove="lean" @pointerleave="rest" @click.stop>
        <i v-if="landed && !calm" class="ring" aria-hidden="true"></i>
        <div ref="hero" class="hero">
          <div ref="tilt" class="tilt">
            <img v-if="skin" class="pet" :src="entry.art" :alt="entry.title" draggable="false" />
            <span v-else-if="card" class="card">
              <img class="art" :src="entry.art" :alt="entry.title" draggable="false" />
              <img v-if="!card.video" class="art full" :class="{ ready: fullReady }" :src="assetUrl(card.full)" alt="" draggable="false" @load="fullReady = true" />
              <video v-if="playing" class="art" :src="assetUrl(card.video)" :poster="entry.art" autoplay loop muted playsinline></video>
              <i v-if="hidden" class="holo" aria-hidden="true"></i>
              <i class="glare" aria-hidden="true"></i>
              <i class="sheen" aria-hidden="true"></i>
            </span>
          </div>
          <template v-if="landed && !calm">
            <span class="burst" aria-hidden="true">
              <i v-for="(s, n) in BURST" :key="n" :style="{ '--a': s.angle, '--d': s.reach }"><Icon name="spark" :size="s.size" /></i>
            </span>
            <Icon v-for="n in 6" :key="n" name="spark" :size="[26, 14, 20, 12, 22, 16][n - 1]" class="spark" :class="`s${n}`" />
          </template>
        </div>
      </div>
      <div class="facts">
        <b class="word" aria-hidden="true"><i v-for="(c, n) in [...word]" :key="n" :style="{ '--n': n }">{{ c }}</i></b>
        <span class="ui-tag dark kind">{{ entry.kind }}</span>
        <h3>{{ entry.title }}</h3>
        <p class="who"><i :style="{ background: memberColor }"></i>{{ entry.who }}</p>
        <p class="own">
          <template v-if="entry.drop.new"><Icon name="spark" :size="14" />首次获得</template>
          <template v-else>已拥有 <b>×{{ entry.drop.count }}</b></template>
          <small v-if="entry.drop.shards">重复返还 {{ entry.drop.shards }} 碎片</small>
        </p>
      </div>
    </div>
    <button ref="go" type="button" class="ui-btn primary large go" @click.stop="close">继续</button>
  </div>
</template>

<style scoped>
.spot {
  position: absolute;
  inset: 0;
  z-index: 6;
  overflow: hidden;
  cursor: pointer;
}
/* The board stays faintly behind, so the card visibly comes from and returns to it. */
.veil {
  position: absolute;
  inset: 0;
  background: color-mix(in srgb, var(--page) 90%, transparent);
  animation: veil-in 220ms var(--ease-out) both;
}
.calm .veil {
  animation: none;
}
.band {
  position: absolute;
  left: -4%;
  right: -4%;
  top: 23%;
  height: 54%;
  overflow: hidden;
  background: var(--tone-fill);
  box-shadow: 0 0 0 6px rgba(255, 255, 255, 0.55), 0 18px 40px -24px var(--tone-glow);
}
.flash {
  position: absolute;
  inset: 0;
  background: #fff;
  animation: flash-out 480ms var(--ease-out) both;
}
.big.landed .stage {
  animation: hit 380ms var(--ease-out) both;
}
.stage {
  position: absolute;
  inset: 0 0 64px;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  align-items: center;
}
.hero-cell {
  position: relative;
  display: grid;
  place-items: center;
  height: 100%;
}
.ring {
  position: absolute;
  left: 50%;
  top: 50%;
  width: min(70cqh, 460px);
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  box-shadow: 0 0 0 4px #fff, 0 0 30px 6px var(--tone-glow), inset 0 0 30px 6px var(--tone-glow);
  pointer-events: none;
  animation: ring-out 700ms var(--ease-out) both;
}
.hero {
  position: relative;
  height: min(76cqh, 540px);
  aspect-ratio: 0.7;
  transform-origin: 0 0;
}
.tilt {
  position: absolute;
  inset: 0;
  transform: perspective(1000px) rotateX(var(--rx, 0deg)) rotateY(var(--ry, 0deg));
  transition: transform 420ms var(--ease-out);
}
.landed:not(.calm) .tilt:not(.leaning) {
  animation: sway 6s var(--ease-in-out) infinite;
}
.tilt.leaning {
  transition: transform 80ms linear;
}
.card {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: 0 0 0 5px #fff, 0 24px 44px -18px rgba(var(--ink-rgb), 0.55);
}
.art {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.full {
  opacity: 0;
  transition: opacity var(--dur-slow);
}
.full.ready {
  opacity: 1;
}
/* Twice the card's size and centred on it; moving it by half its offset puts the light under the pointer. */
.glare,
.holo {
  position: absolute;
  inset: -50%;
  pointer-events: none;
  translate: calc((var(--px, 0.3) - 0.5) * 50%) calc((var(--py, 0.2) - 0.5) * 50%);
  transition: translate 420ms var(--ease-out);
}
.leaning .glare,
.leaning .holo {
  transition: translate 80ms linear;
}
.glare {
  background: radial-gradient(circle, rgba(255, 255, 255, 0.34), transparent 26%);
}
/* Holo foil on hidden cards: a band of pale hues that slides against the pointer. */
.holo {
  translate: calc((0.5 - var(--px, 0.3)) * 40%) calc((0.5 - var(--py, 0.2)) * 40%);
  background: linear-gradient(115deg, transparent 34%, rgba(255, 154, 213, 0.22) 41%, rgba(255, 224, 138, 0.22) 46%, rgba(138, 245, 208, 0.22) 51%, rgba(138, 184, 255, 0.22) 56%, rgba(215, 155, 255, 0.22) 61%, transparent 68%);
}
.sheen {
  position: absolute;
  inset: 0;
  background: linear-gradient(105deg, transparent 38%, rgba(255, 255, 255, 0.6) 50%, transparent 62%) 160% 0 / 260% 100% no-repeat;
}
.landed .sheen {
  animation: hero-sheen 760ms var(--ease-out) both;
}
/* A skin shows the whole desk scene, the way it will sit on the desktop. */
.skin .hero {
  width: min(52cqw, 600px);
  height: auto;
  aspect-ratio: 240 / 135;
}
.pet {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  filter: var(--sticker-lg);
}
.skin.landed:not(.calm) .pet {
  animation: pet-hop 520ms var(--ease-spring) both;
}

.burst {
  position: absolute;
  z-index: 3;
  left: 50%;
  top: 50%;
  pointer-events: none;
}
.burst i {
  position: absolute;
  left: 0;
  top: 0;
  rotate: var(--a);
  transform-origin: 0 0;
}
.burst svg {
  position: absolute;
  left: 0;
  top: 0;
  stroke-width: 0;
  fill: #fff;
  filter: drop-shadow(0 0 3px var(--tone-glow));
  animation: burst-fly 860ms var(--ease-out) both;
}
.spark {
  position: absolute;
  z-index: 2;
  stroke-width: 0;
  fill: #fff;
  filter: drop-shadow(0 1px 2px rgba(var(--ink-rgb), 0.25));
  animation: spark-in 600ms var(--ease-pop) 300ms both, twinkle 2.6s var(--ease-in-out) 1200ms infinite;
}
.s1 { right: -30px; top: 6%; }
.s2 { right: -14px; top: -4%; animation-delay: 380ms, 1400ms; }
.s3 { left: -34px; top: 36%; animation-delay: 440ms, 1600ms; }
.s4 { left: -16px; top: 28%; animation-delay: 500ms, 1800ms; }
.s5 { right: -36px; bottom: 16%; animation-delay: 420ms, 2000ms; }
.s6 { left: -22px; bottom: 6%; animation-delay: 540ms, 1500ms; }

.facts {
  position: relative;
  min-width: 0;
  padding-right: 36px;
  color: var(--tone-ink);
  animation: facts-in 380ms var(--ease-out) 220ms both;
}
.calm .facts {
  animation: none;
}
.leaving .facts {
  animation: facts-out 140ms var(--ease-in) both;
}
.word {
  display: flex;
  margin-left: -4px;
  font: 800 clamp(48px, 11cqw, 96px)/0.86 var(--font-latin);
  letter-spacing: 0.01em;
  color: #fff;
  text-shadow: 0 2px 0 rgba(var(--ink-rgb), 0.08);
}
.word i {
  display: block;
  font-style: normal;
  animation: letter-stamp 420ms var(--ease-out) calc(260ms + var(--n) * 50ms) both;
}
.calm .word i {
  animation: none;
}
.kind {
  margin-top: 14px;
}
h3 {
  margin: 10px 0 8px;
  font: 800 clamp(22px, 4cqw, 34px)/1.25 var(--font);
  text-wrap: balance;
}
/* A white tab, so the member's name colour reads on any band. */
.who {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 3px 12px 3px 8px;
  border-radius: var(--radius-s);
  background: rgba(255, 255, 255, 0.9);
  color: var(--ink);
  font-size: var(--fs-strong);
  font-weight: 800;
}
.who i {
  flex: none;
  width: 5px;
  height: 14px;
}
.own {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin: 16px 0 0;
  font-size: var(--fs-body);
  font-weight: 800;
}
.own b {
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.own small {
  flex-basis: 100%;
  font-size: var(--fs-label);
  font-weight: 700;
  opacity: 0.8;
}
.own svg {
  stroke-width: 0;
  fill: currentColor;
}
.go {
  position: absolute;
  z-index: 2;
  right: 24px;
  bottom: 18px;
  min-width: 132px;
}

@keyframes veil-in {
  from { opacity: 0; }
}
@keyframes flash-out {
  from { opacity: 0.9; }
  to { opacity: 0; }
}
@keyframes hit {
  0% { translate: 0 0; }
  20% { translate: -7px 3px; }
  40% { translate: 6px -3px; }
  60% { translate: -4px 2px; }
  80% { translate: 2px -1px; }
  100% { translate: 0 0; }
}
@keyframes ring-out {
  from { opacity: 1; scale: 0.5; }
  to { opacity: 0; scale: 1.5; }
}
@keyframes sway {
  0%, 100% { transform: perspective(1000px) rotateX(2deg) rotateY(-5deg); }
  50% { transform: perspective(1000px) rotateX(-2deg) rotateY(5deg); }
}
@keyframes hero-sheen {
  from { background-position: 160% 0; }
  to { background-position: -60% 0; }
}
@keyframes pet-hop {
  0% { transform: translateY(0) scale(1, 1); }
  35% { transform: translateY(-14%) scale(0.96, 1.05); }
  65% { transform: translateY(0) scale(1.05, 0.95); }
  100% { transform: none; }
}
@keyframes burst-fly {
  0% { opacity: 0; translate: -50% -50%; scale: 0.2; }
  15% { opacity: 1; }
  100% { opacity: 0; translate: calc(var(--d) - 50%) -50%; scale: 1.1; }
}
@keyframes spark-in {
  from { opacity: 0; transform: scale(0) rotate(-60deg); }
  to { opacity: 1; transform: none; }
}
@keyframes twinkle {
  50% { transform: scale(0.7) rotate(20deg); opacity: 0.7; }
}
@keyframes letter-stamp {
  0% { opacity: 0; transform: scale(2.2); }
  55% { opacity: 1; transform: scale(0.92); }
  80% { transform: scale(1.04); }
  100% { opacity: 1; transform: none; }
}
@keyframes facts-out {
  to { opacity: 0; transform: translateX(10px); }
}
@keyframes facts-in {
  from { opacity: 0; transform: translateX(-14px); }
  to { opacity: 1; transform: none; }
}

@container reveal (max-width: 600px) {
  .stage { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .hero { height: min(62cqh, 420px); }
  .facts { padding-right: 18px; }
  .spark.s3, .spark.s4 { display: none; }
}
@container reveal (max-height: 480px) {
  .band { top: 18%; height: 64%; }
  .hero { height: 70cqh; }
  h3 { margin: 6px 0; }
  .own { margin-top: 8px; }
}
</style>
