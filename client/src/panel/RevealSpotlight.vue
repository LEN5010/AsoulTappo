<script setup lang="ts">
// A hidden card, a skin or a first animated card, lifted off its tile onto a band of its tone.
// The art flies between the tile and the stage, so the board below never loses its place. Once it
// lands it sways, and leans toward the pointer in 3D with glare and a holo sheen on hidden cards.
// Glare and holo are oversized layers that only move, with no blend modes, so a playing video
// stays smooth under them.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl } from "../asset";
import { vCardSound } from "../audio/cardSound";
import { cardFrame, cardWord } from "../cards";
import { PET_BASE } from "../characters";
import { characterColor } from "../manifest";
import { EASE_IN_OUT, EASE_OUT } from "../ui/motion";
import Icon from "../ui/Icon.vue";
import type { BoardEntry } from "./reveal-board";

const props = defineProps<{
  entry: BoardEntry;
  /** Its tile on the board, measured again for each flight so a resize or a scroll cannot strand it. */
  tile: HTMLElement | null;
  calm: boolean;
}>();
const emit = defineEmits<{ done: [] }>();

const LEFT = "translateX(-104%)";
const RIGHT = "translateX(104%)";
const IN_MS = 560;
const OUT_MS = 340;
const TILT_DEG = 14;
const SWAY_MS = 6000;
/** How fast the lean catches up: quick behind the pointer, slower back into the sway. */
const FOLLOW_MS = 70;
const SETTLE_MS = 240;
/** A drawn card's own sound plays a little above full volume. */
const DRAWN_GAIN = 1.15;

const pageActive = usePageActive();
const landed = ref(props.calm);
const leaving = ref(false);
const fullReady = ref(false);
const card = computed(() => props.entry.card);
const skin = computed(() => props.entry.item.kind === "character");
const hidden = computed(() => card.value?.tier === "big" || card.value?.tier === "small");
const big = computed(() => props.entry.drop.rarity === "legendary");
/** Hidden cards wear their tier's frame, the same one their tile and the pool's hand show. */
const frameTier = computed(() => cardFrame(card.value));
const word = computed(() => {
  if (skin.value) return "SKIN";
  return card.value ? cardWord(card.value) : "NEW";
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

const plate = ref<HTMLElement>();
const frameEl = ref<HTMLElement>();
const pet = ref<HTMLElement>();
const cardEl = ref<HTMLElement>();
const glare = ref<HTMLElement>();
const holo = ref<HTMLElement>();

/** Styles a part of the hero takes on to match its tile; the hero itself takes `transform`. */
type Look = Record<string, string>;
type Part = { el: HTMLElement; tile: Look };

const scalePx = (css: string, f: number) => css.replace(/(-?[\d.]+)px/g, (_, n: string) => `${(parseFloat(n) * f).toFixed(3)}px`);
const NO_SHADOW = "drop-shadow(rgba(0, 0, 0, 0) 0px 0px 0px)";
/** Pads a drop-shadow list to `count`, so two filter lists interpolate instead of flipping. */
function padShadows(filter: string, count: number): string {
  const have = filter === "none" ? 0 : filter.split("drop-shadow(").length - 1;
  return [filter === "none" ? "" : filter, ...Array(Math.max(0, count - have)).fill(NO_SHADOW)].join(" ").trim();
}
function read(el: HTMLElement, keys: string[]): Look {
  const style = getComputedStyle(el) as unknown as Record<string, string>;
  return Object.fromEntries(keys.map((k) => [k, style[k] ?? ""]));
}

/**
 * The hero laid over its tile: one matrix from the hero's resting box onto the tile's face, with
 * the tile's own rotation about its centre, and the styles that make the art look like the tile's.
 * A card matches its tile box for box. A skin's desk scene is placed so its pixels land where the
 * tile's bust draws them, then cut down to the tile's plate.
 */
function onTile(): { transform: string; parts: Part[] } | null {
  const flip = props.tile?.querySelector<HTMLElement>(".flipper");
  const body = props.tile?.querySelector<HTMLElement>(".body");
  const rest = hero.value?.getBoundingClientRect();
  if (!flip || !body || !rest?.width) return null;
  const box = body.getBoundingClientRect();
  const look = getComputedStyle(flip);
  const turn = ((parseFloat(look.rotate) || 0) * Math.PI) / 180;
  const [tx = 0, ty = 0] = look.translate === "none" ? [] : look.translate.split(" ").map(parseFloat);
  const cos = Math.cos(turn);
  const sin = Math.sin(turn);
  const w = box.width;
  const h = box.height;

  // Face coordinates of the hero's top-left corner, and face pixels per hero pixel.
  let ox = 0;
  let oy = 0;
  let scale = w / rest.width;
  const parts: Part[] = [];
  const bust = flip.querySelector<SVGSVGElement>(".bust");
  const tilePlate = flip.querySelector<HTMLElement>(".plate");
  if (skin.value && bust && tilePlate && plate.value && frameEl.value && pet.value) {
    // The bust's box on the face: its centre comes out of the rotation unchanged, its size from layout.
    const b = bust.getBoundingClientRect();
    const p = tilePlate.getBoundingClientRect();
    const dx = b.left + b.width / 2 - (p.left + p.width / 2);
    const dy = b.top + b.height / 2 - (p.top + p.height / 2);
    const bs = getComputedStyle(bust);
    const bw = parseFloat(bs.width);
    const bh = parseFloat(bs.height);
    const bx = w / 2 + (cos * dx + sin * dy) - bw / 2;
    const by = h / 2 + (-sin * dx + cos * dy) - bh / 2;
    // PetBust fits its viewBox with xMidYMax meet; one unit of it is one pixel of the desk scene.
    const vb = bust.viewBox.baseVal;
    const unit = Math.min(bw / vb.width, bh / vb.height);
    ox = bx + (bw - vb.width * unit) / 2 - vb.x * unit;
    oy = by + bh - vb.height * unit - vb.y * unit;
    scale = unit / (rest.width / PET_BASE.width);

    const ps = getComputedStyle(tilePlate);
    const radius = scalePx(ps.borderRadius, 1 / scale);
    const left = -ox / scale;
    const top = -oy / scale;
    const pw = w / scale;
    const ph = h / scale;
    Object.assign(plate.value.style, {
      left: `${left}px`, top: `${top}px`, width: `${pw}px`, height: `${ph}px`,
      borderRadius: radius, boxShadow: scalePx(ps.boxShadow, 1 / scale),
    });
    const tileFilter = scalePx(bs.filter, 1 / scale);
    const restCount = getComputedStyle(pet.value).filter.split("drop-shadow(").length - 1;
    parts.push(
      { el: plate.value, tile: { opacity: "1" } },
      { el: frameEl.value, tile: { clipPath: `inset(${top}px ${rest.width - left - pw}px ${rest.height - top - ph}px ${left}px round ${radius})` } },
      { el: pet.value, tile: { filter: padShadows(tileFilter, restCount) } },
    );
  } else if (cardEl.value) {
    const art = getComputedStyle(flip.querySelector(".card-face") ?? flip);
    parts.push({ el: cardEl.value, tile: { borderRadius: scalePx(art.borderRadius, 1 / scale), boxShadow: scalePx(art.boxShadow, 1 / scale) } });
    for (const light of [glare.value, holo.value]) if (light) parts.push({ el: light, tile: { opacity: "0" } });
  }

  // Face position of that corner, turned about the face centre, then onto the screen.
  const fx = ox - w / 2;
  const fy = oy - h / 2;
  const e = box.left + w / 2 + tx + cos * fx - sin * fy - rest.left;
  const f = box.top + h / 2 + ty + sin * fx + cos * fy - rest.top;
  const m = [scale * cos, scale * sin, -scale * sin, scale * cos, e, f].map((n) => +n.toFixed(4));
  return { transform: `matrix(${m.join(", ")})`, parts };
}

/** Flights between the tile and the stage, kept so a close can take over one still under way. */
let flights: Animation[] = [];

/**
 * The lean is eased toward its target every frame, so taking or losing the pointer never jumps:
 * the target is the pointer while it is over the art, a slow sway otherwise, and flat on the way out.
 */
type Pose = { rx: number; ry: number; px: number; py: number };
const REST: Pose = { rx: 0, ry: 0, px: 0.3, py: 0.2 };
const pose: Pose = { ...REST };
let aim: { x: number; y: number } | null = null;
let frame = 0;
let last = 0;
let swayFrom = 0;
/** On the way out the lean flattens on a fixed clock, so it is level when the hero lands on its tile. */
let leaveAt = 0;
const leaveFrom: Pose = { ...REST };
const FLATTEN_MS = OUT_MS * 0.8;

function target(now: number): Pose {
  if (aim) return { rx: (0.5 - aim.y) * TILT_DEG, ry: (aim.x - 0.5) * TILT_DEG, px: aim.x, py: aim.y };
  const c = Math.cos(((now - swayFrom) / SWAY_MS) * 2 * Math.PI);
  return { ...REST, rx: 2 * c, ry: -5 * c };
}
function step(now: number) {
  const el = tilt.value;
  if (!el) return;
  const dt = Math.min(64, now - (last || now));
  last = now;
  const keys = ["rx", "ry", "px", "py"] as const;
  if (leaving.value) {
    const t = Math.min(1, (now - leaveAt) / FLATTEN_MS);
    const eased = t * t * (3 - 2 * t);
    for (const key of keys) pose[key] = leaveFrom[key] + (REST[key] - leaveFrom[key]) * eased;
  } else {
    const to = target(now);
    const k = 1 - Math.exp(-dt / (aim ? FOLLOW_MS : SETTLE_MS));
    for (const key of keys) pose[key] += (to[key] - pose[key]) * k;
  }
  el.style.transform = `perspective(1000px) rotateX(${pose.rx.toFixed(2)}deg) rotateY(${pose.ry.toFixed(2)}deg)`;
  el.style.setProperty("--px", pose.px.toFixed(3));
  el.style.setProperty("--py", pose.py.toFixed(3));
  frame = requestAnimationFrame(step);
}
function startSway() {
  if (props.calm || frame) return;
  swayFrom = performance.now();
  frame = requestAnimationFrame(step);
}

/** Pointer over the art: lean toward it and move the glare there. */
function lean(e: PointerEvent) {
  const box = hero.value?.getBoundingClientRect();
  if (!box?.width || !landed.value || leaving.value || props.calm) return;
  aim = {
    x: Math.min(1, Math.max(0, (e.clientX - box.left) / box.width)),
    y: Math.min(1, Math.max(0, (e.clientY - box.top) / box.height)),
  };
}
function rest() {
  aim = null;
}
onBeforeUnmount(() => cancelAnimationFrame(frame));

const go = ref<HTMLButtonElement>();
onMounted(() => {
  go.value?.focus({ preventScroll: true });
  if (props.calm) return;
  band.value?.animate([{ transform: LEFT }, { transform: "none" }], { duration: 300, easing: EASE_IN_OUT, fill: "both" });
  const start = onTile();
  const timing: KeyframeAnimationOptions = { duration: IN_MS, easing: EASE_OUT, fill: "both" };
  const flight = hero.value?.animate(
    start
      ? [{ transform: start.transform }, { transform: "translateY(-14px) scale(1.04)", offset: 0.7 }, { transform: "none" }]
      : [{ transform: "scale(.6)", opacity: 0 }, { transform: "none", opacity: 1 }],
    timing,
  );
  flights = [
    ...(flight ? [flight] : []),
    ...(start?.parts ?? []).map(({ el, tile }) => el.animate([tile, read(el, Object.keys(tile))], timing)),
  ];
  void flight?.finished.then(() => {
    landed.value = true;
    startSway();
  }, () => {});
});

async function close() {
  if (leaving.value) return;
  leaving.value = true;
  rest();
  if (props.calm) {
    emit("done");
    return;
  }
  leaveAt = performance.now();
  Object.assign(leaveFrom, pose);
  // Take over from wherever the way in has got to: note the styles on screen, drop the flight so
  // the resting box can be measured, and start from the noted styles in the same frame.
  const el = hero.value;
  const parts = [plate.value, frameEl.value, pet.value, cardEl.value, glare.value, holo.value].filter((p) => !!p);
  const keys = ["transform", "opacity", "clipPath", "filter", "borderRadius", "boxShadow"];
  const now = new Map(parts.map((p) => [p, read(p, keys)] as const));
  const heroNow = el ? read(el, ["transform", "opacity"]) : {};
  for (const f of flights) f.cancel();
  const back = onTile();
  const timing: KeyframeAnimationOptions = { duration: OUT_MS, easing: EASE_IN_OUT, fill: "both" };
  const pick = (from: Look, to: Look) => Object.fromEntries(Object.keys(to).map((k) => [k, from[k]!]));
  const moves = [
    band.value?.animate([{ transform: "none" }, { transform: RIGHT }], timing),
    el?.animate([heroNow, back ? { transform: back.transform, opacity: "1" } : { transform: "scale(.6)", opacity: 0 }], timing),
    ...(back?.parts ?? []).map(({ el: p, tile }) => p.animate([pick(now.get(p) ?? read(p, keys), tile), tile], timing)),
    veil.value?.animate([{ opacity: 1 }, { opacity: 0 }], timing),
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
            <template v-if="skin">
              <i ref="plate" class="plate" aria-hidden="true"></i>
              <span ref="frameEl" class="frame">
                <img ref="pet" class="pet" :src="entry.art" :alt="entry.title" draggable="false" />
              </span>
            </template>
            <span v-else-if="card" ref="cardEl" class="card" :class="frameTier">
              <i v-if="frameTier" class="metal" aria-hidden="true"></i>
              <img class="art" :src="entry.art" :alt="entry.title" draggable="false" />
              <img v-if="!card.video" class="art full" :class="{ ready: fullReady }" :src="assetUrl(card.full)" alt="" draggable="false" @load="fullReady = true" />
              <video v-if="playing" v-card-sound="DRAWN_GAIN" class="art" :src="assetUrl(card.video)" :poster="entry.art" loop playsinline></video>
              <i v-if="hidden" ref="holo" class="holo" aria-hidden="true"></i>
              <i ref="glare" class="glare" aria-hidden="true"></i>
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
          <template v-if="entry.drop.new"><Icon name="spark" :size="17" />首次获得</template>
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
  background: color-mix(in srgb, var(--c-50) 90%, transparent);
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
  /* Frames are sized in its width, so the card and its tile draw the same frame at any size. */
  container-type: inline-size;
}
/* Its transform and the light's --px/--py are written every frame by the script. */
.tilt {
  position: absolute;
  inset: 0;
  will-change: transform;
}
.card {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: 0 0 0 5px #fff, 0 24px 44px -18px rgba(var(--shadow-rgb), 0.55);
}
/* A band of the tier's metal inside the white edge. Same proportions as RevealTile's frame. */
.card.frame-gold,
.card.frame-rose {
  border-radius: 5cqw;
  background: var(--frame-fill) var(--frame-at) / var(--frame-size);
}
/*
 * The metal's light follows the lean. Like the glare it is an oversized layer that only moves, so
 * the card is not repainted every frame. 220% wide and shifted by 120% x the lean (54.55% of its
 * own size), it lines up with the tile's background-position for the same lean.
 */
.metal {
  position: absolute;
  left: 0;
  top: 0;
  width: 220%;
  height: 220%;
  background: var(--frame-fill);
  translate: calc(var(--px, 0.3) * -54.5455%) calc(var(--py, 0.2) * -54.5455%);
  will-change: translate;
  pointer-events: none;
}
/* Images and videos keep their own size under auto, so the size inside the frame is spelled out. */
.card.frame-gold .art,
.card.frame-rose .art {
  inset: 1.5cqw;
  width: calc(100% - 3cqw);
  height: calc(100% - 3cqw);
  border-radius: 3.5cqw;
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
  will-change: translate;
}
.glare {
  background: radial-gradient(circle, rgba(255, 255, 255, 0.34), transparent 26%);
}
/* Holo foil on hidden cards: a band of pale hues that slides against the pointer. */
.holo {
  translate: calc((0.5 - var(--px, 0.3)) * 40%) calc((0.5 - var(--py, 0.2)) * 40%);
  background: var(--holo-film);
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
/* The tile's plate, faded in behind the scene as it is cut down to the tile on the way back. */
.plate {
  position: absolute;
  opacity: 0;
  background: linear-gradient(180deg, var(--surface) 35%, color-mix(in srgb, var(--tone-glow) 34%, var(--surface)));
}
/* Clipped only in flight; the resting inset leaves room for the contour and the hop. */
.frame {
  position: absolute;
  inset: 0;
  clip-path: inset(-50% -50% -50% -50% round 0px);
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
  filter: drop-shadow(0 1px 2px rgba(var(--shadow-rgb), 0.25));
  animation: spark-in 600ms var(--ease-pop) 300ms both, twinkle 2.6s var(--ease-in-out) 1200ms infinite;
}
.s1 { right: -30px; top: 6%; }
.s2 { right: -14px; top: -4%; animation-delay: 380ms, 1400ms; }
.s3 { left: -34px; top: 36%; animation-delay: 440ms, 1600ms; }
.s4 { left: -16px; top: 28%; animation-delay: 500ms, 1800ms; }
.s5 { right: -36px; bottom: 16%; animation-delay: 420ms, 2000ms; }
.s6 { left: -22px; bottom: 6%; animation-delay: 540ms, 1500ms; }

/* Nothing rides back to the tile that the tile does not show. */
.leaving .spark {
  animation: spark-out 160ms var(--ease-in) both;
}
.leaving .burst {
  opacity: 0;
  transition: opacity var(--dur-fast);
}

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
  text-shadow: 0 2px 0 rgba(var(--shadow-rgb), 0.08);
}
.word i {
  display: block;
  font-style: normal;
  animation: letter-stamp 420ms var(--ease-out) calc(260ms + var(--n) * 50ms) both;
}
.calm .word i {
  animation: none;
}
/* Chinese reads small beside the Latin word, so the facts run a size or two above body text. */
.kind {
  margin-top: 14px;
  padding: 0 12px;
  font-size: 17px;
  line-height: 30px;
  border-radius: var(--radius-key-s);
}
h3 {
  margin: 10px 0 8px;
  font: 800 clamp(28px, 4cqw, 40px)/1.2 var(--font);
  text-wrap: balance;
}
/* White paper, so the member's tick reads on any band. */
.who {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 4px 12px 4px 9px;
  border-radius: var(--radius-key-s);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
  color: var(--ink);
  font-size: 18px;
  font-weight: 800;
}
.who i {
  flex: none;
  width: 4px;
  height: 17px;
}
.own {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin: 16px 0 0;
  font-size: 17px;
  font-weight: 800;
}
.own b {
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.own small {
  flex-basis: 100%;
  font-size: 14px;
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
@keyframes spark-out {
  to { opacity: 0; transform: scale(0.4); }
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
