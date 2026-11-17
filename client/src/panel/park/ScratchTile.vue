<script setup lang="ts">
// What a scratch card cell shows: an amount, an emote, or one of the named symbols. The same face is drawn on the
// card, on the prize shelf beside it and in the odds table, so a prize looks alike wherever it is listed. It fills the
// nearest positioned box (the caller's tile, which draws the background) and sizes itself by that box's width.
import { assetUrl } from "../../asset";
import { emoteCover } from "../../manifest";
import Icon from "../../ui/Icon.vue";
import { COIN_SMALL } from "./coin";
import type { Cell, Level } from "./scratchCards";

withDefaults(
  defineProps<{
    cell: Cell;
    /** Part of the three-of-a-kind match on an opened card. */
    hit?: boolean;
    /** Non-winning cell on an opened card: steps back softly. */
    muted?: boolean;
    /** The card's top shard prize: its shard emblem wears legendary gold. */
    top?: boolean;
    /** Celebration tier of the revealed card, when hit. */
    level?: Level;
  }>(),
  { hit: false, muted: false, top: false, level: 0 },
);

const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <span class="tile-face" :class="[hit ? `hit lv-${level}` : '', { muted, top }]">
    <span
      v-if="cell.kind === 'shards'" class="amount"
      :class="{ long: cell.amount >= 10000, longer: cell.amount >= 100000 }"
    >
      <Icon name="shard" :size="16" /><b>{{ fmt(cell.amount) }}</b>
    </span>
    <img v-else-if="cell.kind === 'emote'" class="emote" :src="assetUrl(emoteCover(cell.key))" alt="" draggable="false" />
    <span v-else-if="cell.kind === 'again'" class="sym again">
      <span class="sym-badge"><img :src="COIN_SMALL" alt="" draggable="false" /></span>
      <small>再来</small>
    </span>
    <span v-else-if="cell.kind === 'skin'" class="sym item skin">
      <span class="sym-badge"><Icon name="shirt" :size="24" /></span>
      <small>皮肤</small>
    </span>
    <span v-else-if="cell.kind === 'big'" class="sym item big">
      <span class="sym-badge"><Icon name="card-spark" :size="24" /></span>
      <small>大隐藏</small>
    </span>
    <i v-else class="blank"></i>
  </span>
</template>

<style scoped>
.tile-face {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  container-type: inline-size;
  user-select: none;
  transition: opacity var(--dur-slow) var(--ease-out), transform var(--dur-slow) var(--ease-out);
}
.tile-face.muted {
  opacity: 0.34;
  transform: scale(0.93);
}

/* Amounts scale with the tile, so a formatted six-digit jackpot stays crisp inside small panels too. */
.amount {
  display: inline-flex;
  align-items: center;
  gap: 0.05em;
  font: 800 33cqi/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.amount b {
  font: inherit;
  letter-spacing: -0.01em;
}
.amount.long {
  font-size: 27cqi;
}
.amount.longer {
  font-size: 22.5cqi;
}
.amount svg {
  width: 0.56em;
  height: 0.56em;
  color: var(--c-600);
  transition: color var(--dur-base), transform var(--dur-base) var(--ease-out);
}
/* Top shard tier or legendary level-3 win: gold shard mark, crisp sunlit contrast. */
.top .amount svg,
.hit.lv-3 .amount svg {
  color: color-mix(in oklab, var(--gold) 78%, var(--c-700));
  filter: drop-shadow(0 1px 0 rgba(255, 255, 255, 0.8));
}
.hit.lv-1 .amount {
  color: var(--c-700);
}
.hit.lv-2 .amount {
  color: var(--c-800);
}
.hit.lv-2 .amount svg {
  color: var(--c-700);
}
.hit.lv-3 .amount {
  color: var(--ink);
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.85);
}

/* An emote is sized by the tile, not by the picture. */
.emote {
  position: absolute;
  inset: 8%;
  width: 84%;
  height: 84%;
  object-fit: contain;
  filter: var(--sticker);
  transition: transform var(--dur-base) var(--ease-spring);
}
.hit .emote {
  transform: scale(1.06) rotate(-3deg);
}

/* Named symbols: a tactile medallion badge with its short label underneath. */
.sym {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3cqi;
  color: var(--c-700);
}
.sym-badge {
  display: grid;
  place-items: center;
  width: 48cqi;
  height: 48cqi;
  border-radius: 50%;
  background: var(--c-100);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
}
.sym.again .sym-badge {
  background: transparent;
  box-shadow: none;
}
.sym.again img {
  width: 42cqi;
  height: 42cqi;
  filter: drop-shadow(0 1.5px 2px rgba(var(--c-900-rgb), 0.28));
}
.sym.skin .sym-badge {
  background: linear-gradient(180deg, var(--c-50), var(--c-200));
  color: var(--c-700);
}
/* Legendary hidden card symbol: gold-tinted medallion. */
.sym.big .sym-badge {
  background: linear-gradient(180deg, #FFFDF6, var(--gold-soft));
  box-shadow: inset 0 0 0 1.5px rgba(var(--gold-rgb), 0.55), inset 0 1px 0 #fff;
  color: color-mix(in oklab, var(--gold) 72%, var(--c-700));
}
.sym svg {
  width: 30cqi;
  height: 30cqi;
}
.sym small {
  font: 800 clamp(10px, 12.5cqi, 14px)/1 var(--font);
  color: var(--ink-2);
  white-space: nowrap;
}
.hit .sym small {
  color: var(--ink);
}

/* A blank cell: the A-SOUL mark, faint. */
.blank {
  width: 52%;
  aspect-ratio: 3.172;
  background: var(--c-200);
  -webkit-mask: url("../../assets/brand/asoul-logo.svg") center / contain no-repeat;
  mask: url("../../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
</style>
