<script setup lang="ts">
// One result on the reveal board. Cards land like cards stuck onto the page and stickers get
// slapped on, both tilted until the pointer straightens them. Sealed ones all lie face down behind
// the same card-sized back and glow alike, so nothing shows until a tile turns. Rare and above turn
// with a flash, a ring and a burst of stars; plain ones turn quietly. An animated emote stays on a plate of its tone, a
// plain sticker peels off the paper it was turned on. A repeat gets a physical stamp of the shards it turned into.
// A holo version (镭射款) wears its small mark and a band of foil light runs across it as it turns and under the pointer.
import { computed } from "vue";
import { cardFrame } from "../cards";
import type { BoardEntry } from "./reveal-board";
import HoloBadge from "../holo/HoloBadge.vue";
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
  /** Its repeats have turned into shards: the stamp is on. */
  exchanged?: boolean;
}>();
const emit = defineEmits<{ press: [] }>();

const sticker = computed(() => props.entry.item.kind === "emote");
/** Common and uncommon: sealed only as a first copy, and turned without the fanfare. */
const quiet = computed(() => !props.entry.holo && (props.entry.drop.rarity === "common" || props.entry.drop.rarity === "uncommon"));
/** Animated emotes sit on a plate of their tone, so they read apart from plain stickers at a glance. */
const plated = computed(() => sticker.value && props.entry.drop.rarity === "rare");
/** Hidden and limited cards wear their tier's frame, as they do in the spotlight and the pool's hand. */
const frame = computed(() => cardFrame(props.entry.card));
const actionable = computed(() => !props.open || props.entry.spot);
const label = computed(() => (props.open ? `再看一次${props.entry.title}` : "翻开这一张"));
/** Nothing of it was kept: the art steps back under the stamp. */
const spent = computed(() => !!props.exchanged && !props.entry.drop.new);
/** A hidden card pays in gold. */
const gold = computed(() => props.entry.card?.tier === "small");
const note = computed(() => {
  const d = props.entry.drop;
  if (d.got > 1) return `本次 +${d.got}`;
  if (spent.value) return "已兑换";
  return d.count > 1 && !d.shards ? `×${d.count}` : "";
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
    :class="[
      entry.tone,
      `kind-${entry.item.kind}`,
      {
        sticker, plated, quiet, open, sealed: !open, turned, lifted, calm, dense, actionable, spent,
        holo: entry.holo, 'is-new': entry.drop.new, stamped: !!exchanged,
      },
    ]"
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
          <i v-if="!sticker && !calm" class="hover-sheen" :class="frame" aria-hidden="true"></i>
          <template v-if="entry.holo">
            <i v-if="turned && !calm" class="foil-run" aria-hidden="true"></i>
            <HoloBadge class="holo-mark" />
          </template>
          <i v-if="turned && !calm" class="flash" aria-hidden="true"></i>
        </span>
        <span v-if="entry.sealed" class="face face-back"><CardBack :calm="calm" /></span>
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
      <span v-if="exchanged" class="stamp" :class="{ gold }">
        <Icon name="shard" :size="16" /><b>+{{ entry.drop.shards }}</b>
      </span>
    </span>
    <span class="caption">
      <b>{{ open ? entry.title : "？" }}</b>
      <small v-if="open"><i class="dot"></i>{{ entry.kind }}<em v-if="note">{{ note }}</em></small>
      <!-- A sealed tile keeps the second line's room, so turning it moves nothing on the board. -->
      <small v-else aria-hidden="true">&nbsp;</small>
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
/* Only a sticker dealt face up is slapped on; a sealed one lands like any other card. */
.sticker.open {
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
.tone-limited { --dot: var(--pearl-deep); }
.tone-holo { --dot: var(--grad-holo); }
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
/* Subtle physical thud when the shard conversion stamp hits the face. */
.stamped:not(.calm) .body {
  animation: stamp-thud 320ms var(--ease-out);
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
/* A sticker is a smaller square than a card, sitting a little low in the card's slot. Only its face
   is: face down it shares the card-sized back with everything else. */
.sticker .face-front {
  inset: 22% 8% auto;
  aspect-ratio: 1;
}
.tile:hover .flipper,
.tile:focus-visible .flipper {
  rotate: 0deg;
}
/* Every collectible — sealed or opened — straightens and lifts out of the board under the pointer. */
.tile:not(.calm):hover .flipper,
.tile:not(.calm):focus-visible .flipper {
  translate: 0 -6px;
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
  transition: filter 420ms var(--ease-out), opacity 420ms var(--ease-out);
}
.spent .face-front {
  filter: saturate(0.32);
  opacity: 0.7;
}
/* One uniform coral back for every rarity: nothing spoils the front before a turn. */
.face-back {
  --seal-fill: var(--c-500);
  --seal-mark: #fff;
  --seal-rule: rgba(255, 255, 255, 0.6);
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
  transition: box-shadow var(--dur-base) var(--ease-out);
}
/* Same proportions as the spotlight's framed card, so the card flying home lands on this frame. */
.card-frame {
  position: absolute;
  inset: 0;
  border-radius: 5cqw;
  background: var(--frame-fill) var(--frame-at) / var(--frame-size);
  box-shadow: 0 0 0 3px #fff, 0 10px 18px -10px rgba(var(--shadow-rgb), 0.5);
  transition:
    background-position 420ms var(--ease-out),
    box-shadow var(--dur-base) var(--ease-out);
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

/* Material-specific hover elevation and luster on opened collectibles. */
.open:not(.calm):hover .card-face:not(.card-frame),
.open:not(.calm):focus-visible .card-face:not(.card-frame),
.open:not(.calm):hover .plate,
.open:not(.calm):focus-visible .plate {
  box-shadow: 0 0 0 3px #fff, 0 16px 26px -12px rgba(var(--shadow-rgb), 0.56);
}
.open:not(.calm):hover .card-frame,
.open:not(.calm):focus-visible .card-frame {
  background-position: 82% 76%;
}
.open:not(.calm):hover .card-frame.frame-gold,
.open:not(.calm):focus-visible .card-frame.frame-gold {
  box-shadow:
    0 0 0 3px #fff,
    0 0 22px 3px rgba(var(--gold-rgb), 0.52),
    0 18px 28px -12px rgba(var(--shadow-rgb), 0.58);
}
.open:not(.calm):hover .card-frame.frame-pearl,
.open:not(.calm):focus-visible .card-frame.frame-pearl {
  box-shadow:
    0 0 0 3px #fff,
    0 0 22px 3px color-mix(in srgb, var(--holo-lilac) 58%, transparent),
    0 18px 28px -12px rgba(var(--shadow-rgb), 0.58);
}
.open:not(.calm):hover .card-frame.frame-rose,
.open:not(.calm):focus-visible .card-frame.frame-rose {
  box-shadow:
    0 0 0 3px #fff,
    0 0 20px 2px rgba(var(--c-500-rgb), 0.45),
    0 18px 28px -12px rgba(var(--shadow-rgb), 0.58);
}
.holo.open:not(.calm):hover .card-face,
.holo.open:not(.calm):focus-visible .card-face {
  box-shadow:
    0 0 0 3px #fff,
    0 0 22px 3px color-mix(in srgb, var(--holo-lilac) 56%, transparent),
    0 18px 28px -12px rgba(var(--shadow-rgb), 0.58);
}

/* Specular / foil sweep across opened cards and plates under the pointer. */
.hover-sheen {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-m);
  pointer-events: none;
  background: linear-gradient(
    115deg,
    transparent 32%,
    rgba(255, 255, 255, 0.48) 48%,
    transparent 64%
  ) 150% 0 / 260% 100% no-repeat;
  opacity: 0;
  transition: background-position 520ms var(--ease-out), opacity var(--dur-base);
}
.hover-sheen.frame-gold,
.hover-sheen.frame-pearl,
.hover-sheen.frame-rose {
  border-radius: 5cqw;
}
.hover-sheen.frame-gold {
  background: linear-gradient(
    115deg,
    transparent 28%,
    color-mix(in oklab, var(--gold-soft) 65%, transparent) 42%,
    rgba(255, 255, 255, 0.72) 49%,
    color-mix(in oklab, var(--gold-soft) 55%, transparent) 56%,
    transparent 70%
  ) 150% 0 / 260% 100% no-repeat;
}
.hover-sheen.frame-pearl {
  background: linear-gradient(
    115deg,
    transparent 26%,
    color-mix(in srgb, var(--holo-pink) 58%, transparent) 39%,
    rgba(255, 255, 255, 0.76) 48%,
    color-mix(in srgb, var(--holo-mint) 58%, transparent) 57%,
    color-mix(in srgb, var(--holo-lilac) 52%, transparent) 64%,
    transparent 74%
  ) 150% 0 / 260% 100% no-repeat;
}
.holo .hover-sheen {
  background: var(--holo-film) 150% 0 / 260% 100% no-repeat;
}
.open:not(.spent):hover .hover-sheen,
.open:not(.spent):focus-visible .hover-sheen {
  opacity: 1;
  background-position: -45% 0;
}

/* The holo mark sits in the art's corner; steps to top-left when top-right carries the 新 tag. */
.holo-mark {
  position: absolute;
  z-index: 1;
  right: 7%;
  top: 5%;
  transition: transform var(--dur-base) var(--ease-spring);
}
.holo.is-new .holo-mark {
  right: auto;
  left: 7%;
}
.holo.open:not(.calm):hover .holo-mark {
  transform: scale(1.14);
}
/* As the face comes round, a band of foil light runs once from corner to corner. */
.foil-run {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-m);
  pointer-events: none;
  background: linear-gradient(115deg, transparent 30%, rgba(255, 191, 213, 0.75) 40%, rgba(255, 255, 255, 0.95) 47%,
    rgba(181, 233, 222, 0.75) 54%, rgba(203, 192, 255, 0.7) 61%, transparent 70%) 140% 0 / 300% 100% no-repeat;
  animation: foil-run 900ms var(--ease-out) 300ms both;
}
.sticker-art {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  filter: var(--sticker-lg);
  transition: transform var(--dur-base) var(--ease-spring);
}
.sticker.open:not(.calm):hover .sticker-art,
.sticker.open:not(.calm):focus-visible .sticker-art {
  transform: translateY(-3px) scale(1.06);
}
/* The card the sticker was turned on: a plate of its tone that stays, or paper that peels away. */
.pad {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-m);
  background: var(--tone-fill, var(--c-500));
  box-shadow: inset 0 0 0 3px #fff, 0 10px 18px -10px rgba(var(--shadow-rgb), 0.45);
  transition: box-shadow var(--dur-base) var(--ease-out);
}
.plated.open:not(.calm):hover .pad {
  box-shadow: inset 0 0 0 3px #fff, 0 0 18px 2px rgba(var(--c-500-rgb), 0.38), 0 14px 22px -10px rgba(var(--shadow-rgb), 0.5);
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
.plated.open:not(.calm):hover .sticker-art {
  rotate: 0deg;
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
  transition: box-shadow var(--dur-base) var(--ease-out);
}
.bust {
  display: block;
  width: 112%;
  height: 92%;
  filter: var(--contour);
  transition: transform var(--dur-base) var(--ease-out);
}
.open:not(.calm):hover .bust {
  transform: translateY(-2px) scale(1.03);
}

/* Face down: uniform coral edge light breathes while waiting to be pressed. */
.sealed .body::before {
  content: "";
  position: absolute;
  inset: 3px;
  border-radius: var(--radius-m);
  box-shadow:
    0 0 22px 5px rgba(var(--c-500-rgb), 0.55),
    0 0 8px 1px rgba(var(--c-500-rgb), 0.35);
  rotate: var(--tilt);
  opacity: 0.42;
  animation: seal-breathe 2.4s var(--ease-in-out) infinite;
  transition: rotate var(--dur-base) var(--ease-out), opacity var(--dur-base), box-shadow var(--dur-base);
}
.sealed:hover .body::before,
.sealed:focus-visible .body::before {
  rotate: 0deg;
  opacity: 1;
  box-shadow:
    0 0 26px 6px rgba(var(--c-500-rgb), 0.72),
    0 0 10px 2px rgba(255, 255, 255, 0.55);
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

/* Top-right "新" seal badge with crisp die-cut ring and spring pop. */
.fresh {
  position: absolute;
  z-index: 4;
  right: -6px;
  top: -6px;
  padding: 0 7px;
  line-height: 18px;
  box-shadow: 0 0 0 2px #fff, 0 4px 10px -3px rgba(var(--c-900-rgb), 0.42);
  pointer-events: none;
}
.tone-legendary .fresh {
  --tag-bg: var(--grad-gold);
  --tag-fg: var(--ink);
}
.tone-limited .fresh {
  --tag-bg: var(--grad-pearl);
  --tag-fg: var(--night);
}
.turned:not(.calm) .fresh {
  animation: fresh-pop 380ms var(--ease-pop) 260ms both;
}
.sticker .fresh {
  right: 1%;
  top: 17%;
}

/* Physical double-ruled ink stamp slapped onto repeats, sized in tile width for crisp legibility at any scale. */
.stamp {
  position: absolute;
  z-index: 4;
  left: 50%;
  top: 56%;
  display: inline-flex;
  align-items: center;
  gap: 0.16em;
  padding: 0.25em 0.52em 0.25em 0.38em;
  border-radius: var(--radius-key-s);
  background: var(--surface);
  box-shadow:
    inset 0 0 0 2px var(--c-600),
    0 0 0 2.5px #fff,
    0 8px 16px -6px rgba(var(--shadow-rgb), 0.5);
  color: var(--c-700);
  font: 800 clamp(13px, 14.5cqw, 30px)/1 var(--font-latin);
  letter-spacing: 0.02em;
  white-space: nowrap;
  translate: -50% -50%;
  rotate: -6deg;
  pointer-events: none;
  animation: stamp-slam 440ms var(--ease-pop) both;
}
.stamp::before {
  content: "";
  position: absolute;
  inset: 3.5px;
  border-radius: calc(var(--radius-key-s) - 3px);
  box-shadow: inset 0 0 0 1px var(--c-200);
}
.stamp::after {
  content: "";
  position: absolute;
  inset: -2px;
  border-radius: var(--radius-key);
  box-shadow: 0 0 0 2px var(--c-500);
  opacity: 0;
  animation: stamp-ring 480ms var(--ease-out) 140ms both;
}
.stamp :deep(svg) {
  width: 0.92em;
  height: 0.92em;
  stroke-width: 2.3;
  fill: color-mix(in oklab, var(--c-400) 45%, #fff);
}
.stamp.gold {
  background: var(--grad-gold);
  color: var(--ink);
  box-shadow:
    inset 0 0 0 1.5px color-mix(in oklab, var(--gold) 65%, var(--c-800)),
    0 0 0 2.5px #fff,
    0 0 18px 2px rgba(var(--gold-rgb), 0.65),
    0 8px 16px -6px rgba(var(--shadow-rgb), 0.5);
}
.stamp.gold::before {
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.55);
}
.stamp.gold::after {
  box-shadow: 0 0 0 2px var(--gold);
}
.stamp.gold :deep(svg) {
  fill: var(--gold-soft);
}
.calm .stamp,
.calm .stamp::after {
  animation: none;
}
.lifted .stamp,
.lifted .fresh {
  visibility: hidden;
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
  border-radius: 1px;
  background: var(--dot);
}
.caption em {
  margin-left: auto;
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.open.turned:not(.calm) .caption {
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
@keyframes foil-run {
  from { background-position: 140% 0; opacity: 1; }
  80% { opacity: 1; }
  to { background-position: -40% 0; opacity: 0; }
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
  50% { opacity: 0.92; }
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
@keyframes fresh-pop {
  0% { opacity: 0; transform: scale(0.4) rotate(10deg); }
  65% { opacity: 1; transform: scale(1.14) rotate(-3deg); }
  100% { opacity: 1; transform: none; }
}
@keyframes stamp-slam {
  0% { opacity: 0; scale: 2.15; translate: -50% -68%; rotate: -18deg; }
  44% { opacity: 1; scale: 0.9; translate: -50% -47%; rotate: -4.5deg; }
  72% { scale: 1.04; translate: -50% -51%; rotate: -6.5deg; }
  100% { opacity: 1; scale: 1; translate: -50% -50%; rotate: -6deg; }
}
@keyframes stamp-ring {
  0% { opacity: 0.85; scale: 0.88; }
  100% { opacity: 0; scale: 1.32; }
}
@keyframes stamp-thud {
  0% { transform: none; }
  38% { transform: translateY(2.5px) scale(0.985); }
  100% { transform: none; }
}
@keyframes caption-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: none; }
}
</style>
