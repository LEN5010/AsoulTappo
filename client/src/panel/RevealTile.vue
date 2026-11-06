<script setup lang="ts">
// One result on the reveal board. Cards land like cards stuck onto the page and stickers get
// slapped on, both tilted until the pointer straightens them. Sealed ones lie face down and glow
// until they are turned. Rare and above turn with a flash, a ring and a burst of stars; a plain
// first copy turns quietly off a paper back. An animated emote stays on a plate of its tone, a
// plain sticker peels off the paper it was turned on.
import { computed } from "vue";
import { cardFrame } from "../cards";
import type { BoardEntry } from "./reveal-board";
import CardBack from "./CardBack.vue";
import PetBust from "./PetBust.vue";
import Icon from "../ui/Icon.vue";

const props = defineProps<{
  entry: BoardEntry;
  index: number;
  open: boolean;
  /** Opened by a turn just now, rather than dealt face up. */
  turned: boolean;
  /** Its art is up in the spotlight. */
  lifted: boolean;
  calm: boolean;
  /** A grouped board of many tiles: lighter filters. */
  dense?: boolean;
}>();
const emit = defineEmits<{ press: [] }>();

const sticker = computed(() => props.entry.item.kind === "emote");
/** Common and uncommon: sealed only as a first copy, and turned without the fanfare. */
const quiet = computed(() => props.entry.drop.rarity === "common" || props.entry.drop.rarity === "uncommon");
/** Animated emotes sit on a plate of their tone, so they read apart from plain stickers at a glance. */
const plated = computed(() => sticker.value && props.entry.drop.rarity === "rare");
/** Hidden cards wear their tier's frame, as they do in the spotlight and the pool's hand. */
const frame = computed(() => cardFrame(props.entry.card));
const actionable = computed(() => !props.open || props.entry.spot);
const label = computed(() => (props.open ? `再看一次${props.entry.title}` : `翻开${props.entry.hint}`));
const note = computed(() => {
  const d = props.entry.drop;
  if (d.shards) return `+${d.shards} 碎片`;
  if (d.got > 1) return `本次 +${d.got}`;
  return d.count > 1 ? `×${d.count}` : "";
});
const SPARKS = Array.from({ length: 8 }, (_, n) => ({
  angle: `${n * 45 + (n % 2) * 12}deg`,
  reach: `${70 + (n % 3) * 22}px`,
  size: n % 3 === 0 ? 20 : n % 3 === 1 ? 13 : 16,
}));
</script>

<template>
  <component
    :is="actionable ? 'button' : 'div'" :type="actionable ? 'button' : undefined"
    class="tile"
    :class="[entry.tone, `kind-${entry.item.kind}`, { sticker, plated, quiet, open, sealed: !open, turned, lifted, calm, dense, actionable }]"
    :style="{ '--i': Math.min(index, 14), '--tilt': `${entry.tilt}deg`, ...entry.toneStyle }"
    :aria-label="actionable ? label : undefined"
    @click="actionable && emit('press')"
  >
    <span class="body">
      <span class="flipper">
        <span class="face face-front">
          <span v-if="entry.card && frame" class="card-frame card-face" :class="frame">
            <img class="card-art" :src="entry.art" alt="" draggable="false" />
          </span>
          <img v-else-if="entry.card" class="card-art card-face" :src="entry.art" alt="" draggable="false" />
          <span v-else-if="entry.item.kind === 'character'" class="plate">
            <PetBust class="bust" :src="entry.art" />
          </span>
          <template v-else>
            <i v-if="plated" class="pad" aria-hidden="true"></i>
            <i v-else-if="turned && !calm" class="pad paper" aria-hidden="true"></i>
            <img class="sticker-art" :src="entry.art" alt="" draggable="false" />
          </template>
          <i v-if="turned && !calm" class="flash" aria-hidden="true"></i>
        </span>
        <span v-if="entry.sealed" class="face face-back"><CardBack /></span>
      </span>
      <template v-if="turned && !calm && !quiet">
        <i class="ring" aria-hidden="true"></i>
        <span class="burst" aria-hidden="true">
          <i v-for="(s, n) in SPARKS" :key="n" :style="{ '--a': s.angle, '--d': s.reach }">
            <Icon name="spark" :size="s.size" />
          </i>
        </span>
      </template>
      <span v-if="open && entry.drop.new" class="ui-tag fresh">新</span>
    </span>
    <span class="caption">
      <b>{{ open ? entry.title : entry.hint }}</b>
      <small v-if="open"><i class="dot"></i>{{ entry.kind }}<em v-if="note">{{ note }}</em></small>
    </span>
  </component>
</template>

<style scoped>
.tile {
  --dot: var(--ink-3);
  --burst: var(--tone-glow, rgba(var(--c-500-rgb), 0.7));
  position: relative;
  width: var(--tile-w);
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  color: var(--ink);
  text-align: left;
  user-select: none;
    animation: card-drop 460ms var(--ease-spring) calc(var(--deal-at, 0ms) + var(--i) * 42ms) backwards;
}
.sticker {
  animation-name: sticker-slap;
  animation-duration: 420ms;
  animation-timing-function: var(--ease-out);
}
/* Turning swaps the root from a button to a plain block, which Vue builds anew; it must not land a second time. */
.tile.calm,
.tile.turned {
  animation: none;
}
.actionable {
  cursor: pointer;
}
.tone-uncommon { --dot: var(--c-300); }
/* Plain first copies: the back comes from the ladder in tokens.css, with a faint glow. */
.quiet {
  --tone-glow: rgba(var(--c-500-rgb), 0.35);
}
.tone-rare { --dot: var(--c-500); }
.tone-epic { --dot: var(--c-800); }
.tone-skin { --dot: var(--tone-glow); }
.tone-legendary { --dot: var(--gold); }

.body {
  position: relative;
  width: 100%;
  aspect-ratio: 0.7;
  perspective: 900px;
  /* Frames are sized in its width, matching the spotlight's card at any size. */
  container-type: inline-size;
}
/*
 * Out of hit-testing: a face turned away in 3D still caught clicks meant for the tile beside it.
 * The tile's own box takes the pointer instead.
 */
.flipper {
  position: absolute;
  inset: 0;
  pointer-events: none;
  transform-style: preserve-3d;
  rotate: var(--tilt);
  transition: rotate var(--dur-base) var(--ease-out), translate var(--dur-base) var(--ease-out);
}
/* A sticker is a smaller square than a card, sitting a little low in the card's slot. */
.sticker .flipper {
  inset: 22% 8% auto;
  aspect-ratio: 1;
}
.tile:hover .flipper,
.tile:focus-visible .flipper {
  rotate: 0deg;
}
.actionable:hover .flipper,
.actionable:focus-visible .flipper {
  translate: 0 -5px;
}
.sealed .flipper {
  transform: rotateY(180deg);
}
.turned .flipper {
  animation: tile-turn 640ms linear both;
}
.quiet.turned .flipper {
  animation-duration: 520ms;
}
.lifted .flipper {
  visibility: hidden;
}
.face {
  position: absolute;
  inset: 0;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}
.face-back {
  transform: rotateY(180deg);
}

.card-art {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: 0 0 0 3px #fff, 0 10px 18px -10px rgba(var(--shadow-rgb), 0.5);
}
/* Same proportions as the spotlight's framed card, so the card flying home lands on this frame. */
.card-frame {
  position: absolute;
  inset: 0;
  border-radius: 5cqw;
  background: var(--frame-fill) var(--frame-at) / var(--frame-size);
  box-shadow: 0 0 0 3px #fff, 0 10px 18px -10px rgba(var(--shadow-rgb), 0.5);
}
/* An image keeps its own size under auto, so the size inside the frame is spelled out. */
.card-frame .card-art {
  position: absolute;
  inset: 1.5cqw;
  width: calc(100% - 3cqw);
  height: calc(100% - 3cqw);
  border-radius: 3.5cqw;
  box-shadow: none;
}
.sticker-art {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  filter: var(--sticker-lg);
}
/* The card the sticker was turned on: a plate of its tone that stays, or paper that peels away. */
.pad {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-m);
  background: var(--tone-fill, var(--c-500));
  box-shadow: inset 0 0 0 3px #fff, 0 10px 18px -10px rgba(var(--shadow-rgb), 0.45);
}
.pad::after {
  content: "";
  position: absolute;
  inset: 8px;
  border-radius: var(--radius-s);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.55);
}
.pad.paper {
  background: var(--seal-fill);
  animation: pad-peel 340ms var(--ease-in) 470ms both;
}
.pad.paper::after {
  box-shadow: inset 0 0 0 1px var(--seal-rule);
}
.plated .sticker-art {
  position: absolute;
  left: 10%;
  top: 10%;
  width: 80%;
  height: 80%;
  rotate: -4deg;
}
.plated.turned:not(.calm) .sticker-art {
  animation: sticker-pop 560ms var(--ease-spring) 280ms both;
}
.quiet.sticker.turned:not(.calm) .sticker-art {
  animation: sticker-lift 460ms var(--ease-out) 440ms both;
}
.dense .sticker-art {
  filter: var(--contour);
}
.plate {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: end center;
  overflow: hidden;
  border-radius: var(--radius-m);
  background: linear-gradient(180deg, var(--surface) 35%, color-mix(in srgb, var(--tone-glow) 34%, var(--surface)));
  box-shadow: 0 0 0 3px #fff, 0 10px 18px -10px rgba(var(--shadow-rgb), 0.5);
}
.bust {
  display: block;
  width: 112%;
  height: 92%;
  filter: var(--contour);
}

/* Face down: the glow breathes because the tile is waiting to be pressed. */
.sealed .body::before {
  content: "";
  position: absolute;
  inset: 3px;
  border-radius: var(--radius-m);
  box-shadow: 0 0 22px 5px var(--tone-glow);
  rotate: var(--tilt);
  opacity: 0.4;
  animation: seal-breathe 2.4s var(--ease-in-out) infinite;
  transition: rotate var(--dur-base) var(--ease-out);
}
.sticker.sealed .body::before {
  inset: 22% 8% auto;
  aspect-ratio: 1;
}
.sealed:hover .body::before {
  rotate: 0deg;
  opacity: 1;
  animation: none;
}
.calm .body::before {
  animation: none;
}

/* The turn: a flash as the face comes round, a ring, and stars thrown out of the card. */
.flash {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-m);
  background: #fff;
  opacity: 0;
  pointer-events: none;
  animation: turn-flash 640ms var(--ease-out) both;
}
.quiet .flash {
  animation-name: turn-flash-soft;
  animation-duration: 520ms;
}
.ring {
  position: absolute;
  z-index: 2;
  left: 50%;
  top: 50%;
  width: 120%;
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  box-shadow: 0 0 0 3px var(--burst), inset 0 0 18px var(--burst);
  opacity: 0;
  pointer-events: none;
  animation: turn-ring 620ms var(--ease-out) 200ms both;
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
  fill: var(--burst);
  filter: drop-shadow(0 0 1px #fff) drop-shadow(0 0 2px #fff);
  animation: burst-fly 720ms var(--ease-out) 220ms both;
}

.fresh {
  position: absolute;
  z-index: 4;
  left: -6px;
  top: -6px;
}
.sticker .fresh {
  top: 18%;
}

.caption {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  margin-top: 9px;
}
.caption b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-label);
  font-weight: 700;
}
.sealed .caption b {
  color: var(--ink-2);
}
.caption small {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
  white-space: nowrap;
}
.dot {
  flex: none;
  width: 4px;
  height: 10px;
  background: var(--dot);
}
.caption em {
  margin-left: auto;
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.open.turned .caption {
  animation: caption-in 300ms var(--ease-out) 240ms both;
}

@keyframes card-drop {
  0% { opacity: 0; transform: translateY(-34px) scale(1.18) rotate(6deg); }
  55% { opacity: 1; }
  100% { opacity: 1; transform: none; }
}
@keyframes sticker-slap {
  0% { opacity: 0; transform: scale(1.7) rotate(-8deg); }
  45% { opacity: 1; transform: scale(0.9) rotate(2deg); }
  70% { transform: scale(1.05); }
  100% { opacity: 1; transform: none; }
}
/*
 * Every step names the same functions in the same order, so the angle itself is interpolated. Mixed
 * lists fall back to matrix interpolation, which flattens a half turn and threw the card off its axis.
 * Speeds up into edge-on, overshoots past face-up and settles: a damped spring written out by hand.
 */
@keyframes tile-turn {
  0% { transform: translateZ(0) rotateY(180deg) scale(1); animation-timing-function: cubic-bezier(0.45, 0, 0.9, 0.55); }
  40% { transform: translateZ(60px) rotateY(90deg) scale(1.12); animation-timing-function: cubic-bezier(0.15, 0.6, 0.35, 1); }
  72% { transform: translateZ(12px) rotateY(-14deg) scale(1.04); animation-timing-function: cubic-bezier(0.45, 0, 0.55, 1); }
  88% { transform: translateZ(0) rotateY(5deg) scale(1); animation-timing-function: cubic-bezier(0.45, 0, 0.55, 1); }
  100% { transform: translateZ(0) rotateY(0deg) scale(1); }
}
@keyframes turn-flash-soft {
  0%, 30% { opacity: 0; }
  42% { opacity: 0.6; }
  100% { opacity: 0; }
}
@keyframes pad-peel {
  to { opacity: 0; transform: translateY(10%) scale(0.86) rotate(4deg); }
}
@keyframes sticker-pop {
  0% { transform: scale(0.72); }
  55% { transform: scale(1.16) rotate(5deg); }
  100% { transform: none; }
}
@keyframes sticker-lift {
  0% { transform: none; }
  40% { transform: translateY(-7%) scale(1.08) rotate(-3deg); }
  100% { transform: none; }
}
@keyframes seal-breathe {
  50% { opacity: 1; }
}
@keyframes turn-flash {
  0%, 30% { opacity: 0; }
  42% { opacity: 0.95; }
  100% { opacity: 0; }
}
@keyframes turn-ring {
  0% { opacity: 1; scale: 0.3; }
  100% { opacity: 0; scale: 1.6; }
}
@keyframes burst-fly {
  0% { opacity: 0; translate: -50% -50%; scale: 0.2; }
  20% { opacity: 1; }
  100% { opacity: 0; translate: calc(var(--d) - 50%) -50%; scale: 1; }
}
@keyframes caption-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: none; }
}
</style>
